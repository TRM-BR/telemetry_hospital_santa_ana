"""
app/bridges/mqtt_bridge.py — Bridge MQTT para ingestão RAW.

Responsabilidade única:
  Receber mensagens do broker → gravar em raw_messages → ACK.

NÃO parseia, NÃO calcula, NÃO decide nada sobre o payload.
O parse_worker consome raw_messages depois.

Correções em relação à bridge legada (audit-bridge-legacy.md):
     client_id fixo (não aleatório)
     clean_session=False (sessão persistente; broker mantém backlog offline)
     subscribe com QoS=1
     LWT (Last Will and Testament)
     manual_ack_set(True) — ACK só após commit no banco
     TLS opcional (port 8883 quando mqtt_tls=True)
     reconnect_delay_set para backoff controlado
     keepalive=30s (reduzido de 60s)
     Publica status MQTT (online/offline) no tópico de status
     Sem lógica de "desativar RAW em caso de erro" — falha → não acker

Adaptações para SN50_analog (DTN-200-FPS0):
     Assina lista de tópicos telemetry_topics (default: SN50_analog/data).
     IMEI extraído do payload JSON quando não está no tópico.
     CMD = outbound apenas; nunca assinado como telemetria.
"""
from __future__ import annotations

import hashlib
import json
import signal
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import paho.mqtt.client as mqtt
from psycopg2.extensions import connection as PgConnection

from app.bridges._common import make_sync_connection, write_raw
from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _imei_from_topic(topic: str) -> Optional[str]:
    """
    Tenta extrair o IMEI do tópico MQTT.

    Padrão legado: 'SN50/data/<imei>'  (ex.: 'SN50/data/868927084622450')
    Padrão novo:   'telemetry/<slug>/devices/<imei>/data'

    Retorna None se não conseguir extrair.
    """
    parts = topic.split("/")
    # Novo padrão: telemetry/<slug>/devices/<imei>/data
    if len(parts) >= 4 and parts[0] == "telemetry" and parts[2] == "devices":
        candidate = parts[3]
        if candidate.isdigit() and len(candidate) >= 10:
            return candidate
    # Padrão legado: SN50/data/<imei>  (qualquer nível final numérico)
    if parts[-1].isdigit() and len(parts[-1]) >= 10:
        return parts[-1]
    return None


def _is_energy_topic(topic: str) -> bool:
    """Retorna True para tópicos de medição de energia (sem IMEI no tópico/payload)."""
    return topic == "/param_energ"


def _compute_dedup_hash(topic: str, payload_raw: str, received_at_utc: datetime) -> str:
    """
    Calcula o hash de deduplicação por tipo de tópico.

    - Energia (/param_energ): sha256(payload | received_at_second)
      O payload não traz timestamp e é idêntico em repouso; incluir o segundo
      de chegada garante que heartbeats distintos não sejam descartados.
    - Demais (SN50 etc.): sha256(payload_raw) — idêntico ao payload_hash,
      mantendo o comportamento original.
    """
    raw_bytes = payload_raw.encode("utf-8", errors="replace")
    if _is_energy_topic(topic):
        ts_s = received_at_utc.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw_bytes = raw_bytes + b"|" + ts_s.encode()
    return hashlib.sha256(raw_bytes).hexdigest()


def _imei_from_payload(payload_raw: str) -> Optional[str]:
    """
    Extrai IMEI do JSON do payload — fallback para DTN-200-FPS0 (SN50_analog/data).

    O tópico SN50_analog/data não contém IMEI; ele está no campo "IMEI" do payload.
    Retorna None se payload não for JSON válido ou campo ausente/inválido.
    """
    try:
        data = json.loads(payload_raw)
        candidate = str(data.get("IMEI", "") or "").strip()
        if candidate.isdigit() and len(candidate) >= 10:
            return candidate
    except (json.JSONDecodeError, Exception):
        pass
    return None


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

class MQTTBridge:
    """
    Bridge MQTT síncrona (thread Paho) que persiste RAW e aciona ACK manual.

    Ciclo de vida:
      1. run() configura cliente Paho e chama loop_forever().
      2. on_connect: subscreve no tópico com QoS=1.
      3. on_message: write_raw() → commit → ack(). Se qualquer etapa falhar,
         a mensagem NÃO é ackada e o broker reentrega (QoS=1).
      4. Sinal SIGINT/SIGTERM: publicar LWT "offline" e desconectar limpo.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._con: Optional[PgConnection] = None
        self._client: Optional[mqtt.Client] = None
        self._running = True
        self._msg_count = 0
        self._ack_count = 0
        self._skip_count = 0  # duplicatas

    # ── DB ─────────────────────────────────────────────────────────────────

    def _ensure_db(self) -> PgConnection:
        """
        Retorna conexão aberta; reconecta se necessário.
        Lança exceção se não conseguir conectar.
        """
        if self._con is not None:
            try:
                # ping leve — cursor sem query
                with self._con.cursor() as cur:
                    cur.execute("SELECT 1")
                return self._con
            except Exception:
                try:
                    self._con.close()
                except Exception:
                    pass
                self._con = None

        self._con = make_sync_connection()
        logger.info("bridge.db_connected", host=self._settings.db_host)
        return self._con

    # ── Status MQTT ────────────────────────────────────────────────────────

    @property
    def _status_topic(self) -> str:
        return f"telemetry/{self._settings.client_slug}/bridge/status"

    # ── Callbacks Paho ─────────────────────────────────────────────────────

    def on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: dict,  # type: ignore[type-arg]
        reason_code: mqtt.ReasonCode,
        properties: object = None,
    ) -> None:
        if reason_code == 0:
            s = self._settings
            # Assina lista de tópicos de telemetria (nunca CMD — CMD é outbound)
            topics = s.telemetry_topics or [s.mqtt_topic_prefix]
            for topic in topics:
                client.subscribe(topic, qos=1)
            client.publish(self._status_topic, payload="online", qos=1, retain=True)
            logger.info(
                "bridge.connected",
                broker=s.mqtt_host,
                port=s.mqtt_port,
                topics=topics,
                client_id=s.mqtt_client_id,
            )
        else:
            logger.error("bridge.connect_failed", reason_code=str(reason_code))

    def on_disconnect(
        self,
        client: mqtt.Client,
        userdata: object,
        disconnect_flags: object,
        reason_code: object,
        properties: object = None,
    ) -> None:
        logger.warning("bridge.disconnected", reason_code=str(reason_code))

    def on_message(
        self,
        client: mqtt.Client,
        userdata: object,
        msg: mqtt.MQTTMessage,
    ) -> None:
        """
        Callback principal. Contrato de ACK:
          - ACK (client.ack) SÓ após commit bem-sucedido no banco.
          - Se write_raw ou commit falhar → não acker → broker reentrega.
          - Duplicata (ON CONFLICT / skip) → acker normalmente (já temos).
        """
        topic = getattr(msg, "topic", "") or ""
        payload_raw = msg.payload.decode("utf-8", errors="replace")
        # SN50_analog/data não tem IMEI no tópico — extrai do payload JSON.
        # Energia (/param_energ) usa external_id, não IMEI — imei fica None.
        imei = _imei_from_topic(topic) or _imei_from_payload(payload_raw)

        # received_at_utc gerado no app (não DEFAULT now() do banco).
        # O mesmo valor é usado na coluna E no cálculo de dedup_hash de energia.
        received_at_utc = datetime.now(tz=timezone.utc)
        dedup_hash = _compute_dedup_hash(topic, payload_raw, received_at_utc)

        row_id: Optional[int] = None
        try:
            con = self._ensure_db()
            row_id = write_raw(
                con,
                topic=topic,
                payload_raw=payload_raw,
                imei=imei,
                received_at_utc=received_at_utc,
                dedup_hash=dedup_hash,
            )
            con.commit()
        except Exception as exc:
            # Falha no banco: rollback, NÃO acker.
            # Broker reentrega (QoS=1 + clean_session=False).
            logger.error(
                "bridge.db_error",
                topic=topic,
                imei=imei,
                error=str(exc),
                exc_info=True,
            )
            try:
                if self._con:
                    self._con.rollback()
            except Exception:
                pass
            return  # ← sem ack

        # ── Commit bem-sucedido — AGORA podemos ACK ─────────────────────────
        # Paho 2.x: ack(mid, qos) — não aceita o objeto msg diretamente
        client.ack(msg.mid, msg.qos)

        self._msg_count += 1
        if row_id is None:
            # Duplicata ignorada via ON CONFLICT DO NOTHING
            self._skip_count += 1
            logger.debug("bridge.duplicate_skipped", topic=topic, imei=imei)
        else:
            self._ack_count += 1
            logger.info(
                "bridge.message_stored",
                raw_id=row_id,
                topic=topic,
                imei=imei,
                msg_total=self._msg_count,
            )

    # ── Setup Paho ─────────────────────────────────────────────────────────

    def _build_client(self) -> mqtt.Client:
        s = self._settings

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=s.mqtt_client_id,
            clean_session=False,  # sessão persistente — broker mantém backlog offline
            protocol=mqtt.MQTTv311,
        )

        # ACK manual — garantia de entrega pós-commit
        client.manual_ack_set(True)

        # Credenciais
        client.username_pw_set(s.mqtt_username, s.mqtt_password)

        # LWT: broker publica "offline" se a conexão cair abruptamente
        client.will_set(
            topic=self._status_topic,
            payload="offline",
            qos=1,
            retain=True,
        )

        # TLS opcional (porta 8883 em produção)
        if s.mqtt_tls:
            tls_ctx = ssl.create_default_context()
            if s.mqtt_ca_cert_path:
                tls_ctx = ssl.create_default_context(cafile=s.mqtt_ca_cert_path)
            client.tls_set_context(tls_ctx)
            logger.info("bridge.tls_enabled", ca_cert=s.mqtt_ca_cert_path)

        # Backoff de reconexão: 1s → até 30s
        client.reconnect_delay_set(min_delay=1, max_delay=30)

        # Callbacks
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_message = self.on_message

        return client

    # ── Shutdown ───────────────────────────────────────────────────────────

    def _shutdown(self, *_: object) -> None:
        """Desconecta limpo (publica 'offline' antes de sair)."""
        logger.info("bridge.shutdown_requested")
        self._running = False
        try:
            if self._client:
                self._client.publish(
                    self._status_topic, payload="offline", qos=1, retain=True
                )
                # Pequena espera para o publish ser enviado antes de desconectar
                time.sleep(0.3)
                self._client.disconnect()
        except Exception:
            pass
        try:
            if self._con:
                self._con.close()
        except Exception:
            pass
        logger.info(
            "bridge.stopped",
            msg_total=self._msg_count,
            acked=self._ack_count,
            skipped=self._skip_count,
        )
        sys.exit(0)

    # ── Entrypoint ─────────────────────────────────────────────────────────

    def run(self) -> None:
        """Inicializa e executa o loop de mensagens."""
        s = self._settings
        hostname = socket.gethostname()

        logger.info(
            "bridge.starting",
            client_id=s.mqtt_client_id,
            broker=s.mqtt_host,
            port=s.mqtt_port,
            tls=s.mqtt_tls,
            topics=s.telemetry_topics or [s.mqtt_topic_prefix],
            host=hostname,
        )

        # Conecta ao banco antes de entrar no loop MQTT
        # (falha imediata se banco indisponível — systemd irá reiniciar)
        self._ensure_db()

        # Constrói e conecta cliente Paho
        self._client = self._build_client()
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        self._client.connect(
            host=s.mqtt_host,
            port=s.mqtt_port,
            keepalive=s.mqtt_keepalive,
        )

        logger.info("bridge.running")
        self._client.loop_forever()
