"""
app/bridges/_common.py — Escritas atômicas na tabela raw_messages.

Este módulo é o ÚNICO caminho de escrita em raw_messages.
Toda bridge (MQTT, API) deve usar write_raw() daqui.

Usa psycopg2 síncrono: a bridge MQTT roda em thread Paho (síncrona) e
não pode usar asyncpg. A session assíncrona é usada pelos workers e pela API.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection

from app.config import get_settings

# ---------------------------------------------------------------------------
# Conexão síncrona (bridge MQTT — thread Paho)
# ---------------------------------------------------------------------------

def make_sync_connection() -> PgConnection:
    """
    Abre e retorna uma conexão psycopg2 usando as settings correntes.
    Autocommit OFF (controle manual, necessário para write_raw garantir
    que o ACK só ocorra após commit).
    """
    s = get_settings()
    return psycopg2.connect(
        host=s.db_host,
        port=s.db_port,
        dbname=s.db_name,
        user=s.db_user,
        password=s.db_password,
        connect_timeout=10,
        options="-c timezone=UTC",
    )


# ---------------------------------------------------------------------------
# Escrita atômica em raw_messages
# ---------------------------------------------------------------------------

_INSERT_RAW = """
INSERT INTO raw_messages (
    received_at_utc,
    origin,
    topic,
    imei,
    payload_raw,
    payload_hash,
    parse_status
)
VALUES (
    %(received_at_utc)s,
    %(origin)s,
    %(topic)s,
    %(imei)s,
    %(payload_raw)s,
    %(payload_hash)s,
    'pending'
)
ON CONFLICT (origin, topic, payload_hash) DO NOTHING
RETURNING id;
"""


def write_raw(
    con: PgConnection,
    *,
    topic: str,
    payload_raw: str,
    origin: str = "mqtt",
    imei: Optional[str] = None,
) -> Optional[int]:
    """
    Insere uma mensagem bruta em raw_messages de forma atômica.

    Contrato:
    - NÃO faz commit. O chamador (mqtt_bridge) faz commit e SÓ ENTÃO aciona
      client.ack(). Se o commit falhar, o ACK nunca é enviado e o broker
      reentrega a mensagem.
    - Retorna o id inserido, ou None se a mensagem já existia (ON CONFLICT).
    - Lança exceção em qualquer outro erro — deixar o chamador decidir.

    Args:
        con:         Conexão psycopg2 aberta (autocommit=False).
        topic:       Tópico MQTT original (ex.: 'SN50/data/868927084622450').
        payload_raw: Payload bruto decodificado como string UTF-8.
        origin:      Origem da mensagem ('mqtt' | 'api').
        imei:        IMEI extraído do tópico ou payload (pode ser None se
                     indisponível antes da bridge — o parse_worker descobre).

    Returns:
        int  → id da linha inserida.
        None → mensagem duplicada (ON CONFLICT), ignorada normalmente.
    """
    payload_hash = hashlib.sha256(payload_raw.encode("utf-8", errors="replace")).hexdigest()

    with con.cursor() as cur:
        cur.execute(
            _INSERT_RAW,
            {
                "received_at_utc": datetime.now(tz=timezone.utc),
                "origin": origin,
                "topic": topic,
                "imei": imei,
                "payload_raw": payload_raw,
                "payload_hash": payload_hash,
            },
        )
        row = cur.fetchone()
        return row[0] if row else None
