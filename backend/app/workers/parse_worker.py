"""
app/workers/parse_worker.py — Worker que converte raw_messages → parsed_measurements.

Ciclo:
  1. Watchdog: devolve para 'pending' registros presos em 'processing'.
  2. TX1 (claim): marca lote de raw_messages como 'processing'.
  3. Parseia cada mensagem com sn50_analog.parse() (fora de TX).
  4. TX2 (finaliza): insere em parsed_measurements + atualiza raw_messages.

Dispatch por tópico/modelo:
  - Tópico começa com 'SN50_analog/' → sn50_analog.parse()
  - Model começa com 'DTN' no payload → sn50_analog.parse()

Autodetecção de device:
  No 1º payload válido (IMEI novo + Model DTN*), cria device automaticamente
  (model=DTN-200-FPS0, status='auto_detected', label provisório) e vincula
  à instalação definida em device_autodetect.attach_installation_slug.
  IMEIs não são pré-cadastrados — o device nasce pelo tráfego.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

# Rejeita timestamps com bug de RTC e timestamps absurdamente futuros.
_MIN_VALID_TS = datetime(2025, 1, 1, tzinfo=timezone.utc)
_MAX_FUTURE_OFFSET = timedelta(hours=1)

_ANALOG_TOPIC_ROOT = "SN50_analog/"
_ENERGY_TOPIC = "/param_energ"

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.logging import get_logger
from app.processing.parsers import sm3egw_energy, sn50_analog
from app.processing.parsers.base import ParsedReading
from app.workers._runner import WorkerRunner

logger = get_logger(__name__)


def _is_energy_topic(topic: str) -> bool:
    return topic == _ENERGY_TOPIC


def _to_decimal(v: Optional[str]) -> Optional[Decimal]:
    """String decimal → Decimal; None ou inválido → None."""
    if v is None:
        return None
    try:
        return Decimal(v)
    except (InvalidOperation, TypeError):
        return None


def _is_analog_payload(topic: str, payload_raw: str) -> bool:
    """Retorna True se o payload deve ser processado como analógico DTN."""
    if topic.startswith(_ANALOG_TOPIC_ROOT):
        return True
    # Fallback: verifica Model no JSON
    try:
        obj = json.loads(payload_raw)
        model = str(obj.get("Model") or obj.get("model") or "")
        if model.upper().startswith("DTN"):
            return True
    except Exception:
        pass
    return False


class ParseWorker(WorkerRunner):
    worker_name = "parse_worker"

    # ── Queries ─────────────────────────────────────────────────────────────

    _SQL_CLAIM = text("""
        WITH batch AS (
            SELECT id FROM raw_messages
            WHERE parse_status IN ('pending', 'temporary_error')
              AND (
                last_attempt_at IS NULL
                OR last_attempt_at < now() - (
                    CASE parse_attempts
                        WHEN 0 THEN INTERVAL '0 seconds'
                        WHEN 1 THEN INTERVAL '60 seconds'
                        WHEN 2 THEN INTERVAL '300 seconds'
                        WHEN 3 THEN INTERVAL '900 seconds'
                        ELSE          INTERVAL '3600 seconds'
                    END
                )
              )
            ORDER BY received_at_utc
            LIMIT :batch_size
            FOR UPDATE SKIP LOCKED
        )
        UPDATE raw_messages r
        SET
            parse_status    = 'processing',
            processing_since = now(),
            worker_id        = :worker_id,
            parse_attempts   = parse_attempts + 1,
            last_attempt_at  = now()
        FROM batch
        WHERE r.id = batch.id
        RETURNING r.id
    """)

    _SQL_DONE = text("""
        UPDATE raw_messages
        SET parse_status = 'done',
            error_message = NULL,
            processing_since = NULL
        WHERE id = :id
          AND worker_id = :worker_id
          AND parse_status = 'processing'
    """)

    _SQL_ERROR = text("""
        UPDATE raw_messages
        SET parse_status  = :status,
            error_message = :error_message,
            processing_since = NULL
        WHERE id = :id
          AND worker_id = :worker_id
          AND parse_status = 'processing'
    """)

    _SQL_DEVICE = text("""
        SELECT id, model FROM devices WHERE imei = :imei LIMIT 1
    """)

    _SQL_INSTALLATION_BY_SLUG = text("""
        SELECT id FROM installations WHERE slug = :slug LIMIT 1
    """)

    _SQL_INSTALLATION = text("""
        SELECT installation_id FROM device_installations
        WHERE device_id = :device_id
          AND valid_to IS NULL
        LIMIT 1
    """)

    # Auto-registro analógico: cria device com status/label para DTN
    _SQL_DEVICE_UPSERT_ANALOG = text("""
        INSERT INTO devices (imei, model, status, label, is_active, created_at)
        VALUES (:imei, :model, :status, :label, true, now())
        ON CONFLICT (imei) DO UPDATE
          SET imei = EXCLUDED.imei
        RETURNING id
    """)

    # Vincula device à instalação (idempotente) — índice UNIQUE (device_id, installation_id) WHERE valid_to IS NULL
    _SQL_DEVICE_INSTALLATION_LINK = text("""
        INSERT INTO device_installations (device_id, installation_id, valid_from, valid_to)
        VALUES (:device_id, :installation_id, now(), NULL)
        ON CONFLICT (device_id, installation_id) WHERE valid_to IS NULL DO NOTHING
    """)

    # Resolve device pelo external_id (SM-3EGW — sem IMEI numérico)
    _SQL_DEVICE_BY_EXTERNAL_ID = text("""
        SELECT id FROM devices WHERE external_id = :external_id LIMIT 1
    """)

    # INSERT energy_measurement — dedup por (device_id, collected_at_utc)
    _SQL_INSERT_ENERGY = text("""
        INSERT INTO energy_measurements (
            raw_message_id, device_id, installation_id,
            collected_at_utc,
            active_power_total_w,
            reactive_power_total_var,
            voltage_phase_a_v,
            voltage_phase_b_v,
            voltage_phase_c_v,
            current_total_a,
            power_factor_total,
            active_energy_consumed_total_kwh,
            active_energy_generated_total_kwh,
            reactive_energy_generated_total_kvarh,
            delta_active_energy_consumed_kwh,
            delta_active_energy_generated_kwh,
            gsm_signal_rssi_dbm,
            created_at
        ) VALUES (
            :raw_message_id, :device_id, :installation_id,
            :collected_at_utc,
            :active_power_total_w,
            :reactive_power_total_var,
            :voltage_phase_a_v,
            :voltage_phase_b_v,
            :voltage_phase_c_v,
            :current_total_a,
            :power_factor_total,
            :active_energy_consumed_total_kwh,
            :active_energy_generated_total_kwh,
            :reactive_energy_generated_total_kvarh,
            :delta_active_energy_consumed_kwh,
            :delta_active_energy_generated_kwh,
            :gsm_signal_rssi_dbm,
            now()
        )
        ON CONFLICT (device_id, collected_at_utc) DO NOTHING
    """)

    # INSERT parsed_measurement analógico — dedup por (device_id, collected_at_utc)
    _SQL_INSERT_PARSED = text("""
        INSERT INTO parsed_measurements (
            raw_message_id, device_id, installation_id, hist_index,
            collected_at_utc,
            current_ma, voltage_v,
            signal_rssi, battery_v,
            derive_status, created_at
        ) VALUES (
            :raw_message_id, :device_id, :installation_id, :hist_index,
            :collected_at_utc,
            :current_ma, :voltage_v,
            :signal_rssi, :battery_v,
            'pending', now()
        )
        ON CONFLICT (device_id, collected_at_utc) DO NOTHING
    """)

    # ── Autodetecção ────────────────────────────────────────────────────────

    async def _resolve_or_autodetect_device(
        self,
        session: AsyncSession,
        imei: str,
        model_from_payload: str,
        raw_id: int,
        installation_id_cache: dict[str, Optional[int]],
    ) -> Optional[int]:
        """
        Resolve device_id pelo IMEI. Cria device e vínculo de instalação
        automaticamente se não existir (autodetecção).
        Retorna device_id ou None em caso de falha.
        """
        s = self._settings

        dev_row = await session.execute(self._SQL_DEVICE, {"imei": imei})
        dev = dev_row.fetchone()

        if dev:
            return dev[0]

        # ── Device novo: autodetecção ────────────────────────────────────────
        if not s.device_autodetect_enabled:
            self._log.warning(
                "parse_worker.autodetect_disabled_skip",
                raw_id=raw_id,
                imei=imei,
            )
            return None

        model = model_from_payload or "DTN-200-FPS0"
        imei_suffix = imei[-4:] if len(imei) >= 4 else imei
        label = s.device_autodetect_label_template.replace("{imei_suffix}", imei_suffix)
        status = s.device_autodetect_default_status

        upsert_row = await session.execute(
            self._SQL_DEVICE_UPSERT_ANALOG,
            {"imei": imei, "model": model, "status": status, "label": label},
        )
        new_dev = upsert_row.fetchone()
        if not new_dev:
            return None
        device_id = new_dev[0]

        # Resolve installation_id para o vínculo
        attach_slug = s.device_autodetect_attach_installation_slug
        if attach_slug not in installation_id_cache:
            inst_row = await session.execute(
                self._SQL_INSTALLATION_BY_SLUG, {"slug": attach_slug}
            )
            inst = inst_row.fetchone()
            installation_id_cache[attach_slug] = inst[0] if inst else None

        installation_id = installation_id_cache[attach_slug]
        if installation_id:
            await session.execute(
                self._SQL_DEVICE_INSTALLATION_LINK,
                {"device_id": device_id, "installation_id": installation_id},
            )

        self._log.info(
            "parse_worker.device_auto_registered",
            raw_id=raw_id,
            imei=imei,
            model=model,
            label=label,
            device_id=device_id,
            installation_id=installation_id,
        )
        return device_id

    async def _resolve_energy_device(
        self,
        session: AsyncSession,
        external_id: str,
        raw_id: int,
        device_cache: dict[str, Optional[int]],
    ) -> Optional[int]:
        """
        Resolve device_id pelo external_id (SM-3EGW).
        Sem autodetecção — device deve estar seedado via migration 0023.
        Retorna device_id ou None se não encontrado.
        """
        if external_id in device_cache:
            return device_cache[external_id]

        row = await session.execute(
            self._SQL_DEVICE_BY_EXTERNAL_ID, {"external_id": external_id}
        )
        dev = row.fetchone()
        device_id = dev[0] if dev else None

        if device_id is None:
            self._log.error(
                "parse_worker.energy_device_not_found",
                raw_id=raw_id,
                external_id=external_id,
            )

        device_cache[external_id] = device_id
        return device_id

    # ── Implementações obrigatórias ─────────────────────────────────────────

    async def claim_batch(self, session: AsyncSession) -> list[int]:
        s = self._settings
        result = await session.execute(
            self._SQL_CLAIM,
            {"batch_size": s.worker_batch_size, "worker_id": self._worker_id},
        )
        await session.commit()
        return [row[0] for row in result.fetchall()]

    async def process_batch(
        self,
        session: AsyncSession,
        row_ids: list[int],
    ) -> list[int]:
        if not row_ids:
            return []

        rows_result = await session.execute(
            text("SELECT id, topic, payload_raw, received_at_utc FROM raw_messages WHERE id = ANY(:ids)"),
            {"ids": list(row_ids)},
        )
        rows = {row[0]: (row[1], row[2], row[3]) for row in rows_result.fetchall()}

        done_ids: list[int] = []
        device_cache: dict[str, Optional[int]] = {}
        installation_id_cache: dict[str, Optional[int]] = {}

        for raw_id in row_ids:
            row = rows.get(raw_id)
            if row is None:
                continue
            topic, payload_raw, received_at_utc = row

            # ── Branch de energia (/param_energ → energy_measurements) ────────
            if _is_energy_topic(topic):
                result_e = sm3egw_energy.parse(payload_raw)
                if result_e.failed:
                    self._log.warning(
                        "parse_worker.energy_parse_failed",
                        raw_id=raw_id,
                        reason=result_e.reason,
                    )
                    done_ids.append(raw_id)
                    continue

                reading = result_e.reading
                device_id = await self._resolve_energy_device(
                    session, reading.device_external_id, raw_id, device_cache
                )
                if device_id is None:
                    # Device não seedado — erro permanente; não tenta de novo.
                    done_ids.append(raw_id)
                    continue

                inst_result = await session.execute(
                    self._SQL_INSTALLATION, {"device_id": device_id}
                )
                inst_row = inst_result.fetchone()
                installation_id = inst_row[0] if inst_row else None

                await session.execute(
                    self._SQL_INSERT_ENERGY,
                    {
                        "raw_message_id": raw_id,
                        "device_id": device_id,
                        "installation_id": installation_id,
                        "collected_at_utc": received_at_utc,
                        "active_power_total_w": reading.active_power_total_w,
                        "reactive_power_total_var": reading.reactive_power_total_var,
                        "voltage_phase_a_v": reading.voltage_phase_a_v,
                        "voltage_phase_b_v": reading.voltage_phase_b_v,
                        "voltage_phase_c_v": reading.voltage_phase_c_v,
                        "current_total_a": reading.current_total_a,
                        "power_factor_total": reading.power_factor_total,
                        "active_energy_consumed_total_kwh": _to_decimal(reading.active_energy_consumed_total_kwh),
                        "active_energy_generated_total_kwh": _to_decimal(reading.active_energy_generated_total_kwh),
                        "reactive_energy_generated_total_kvarh": _to_decimal(reading.reactive_energy_generated_total_kvarh),
                        "delta_active_energy_consumed_kwh": _to_decimal(reading.delta_active_energy_consumed_kwh),
                        "delta_active_energy_generated_kwh": _to_decimal(reading.delta_active_energy_generated_kwh),
                        "gsm_signal_rssi_dbm": reading.gsm_signal_rssi_dbm,
                    },
                )
                self._log.info(
                    "parse_worker.energy_parsed",
                    raw_id=raw_id,
                    device_id=device_id,
                    installation_id=installation_id,
                    collected_at_utc=received_at_utc.isoformat() if received_at_utc else None,
                )
                done_ids.append(raw_id)
                continue

            if not _is_analog_payload(topic, payload_raw):
                # Tópico/model não analógico — permanente (sem parser disponível)
                self._log.warning(
                    "parse_worker.unsupported_payload",
                    raw_id=raw_id,
                    topic=topic,
                )
                done_ids.append(raw_id)
                continue

            # Extrai model do payload para autodetecção
            model_from_payload = "DTN-200-FPS0"
            try:
                obj = json.loads(payload_raw)
                model_from_payload = str(obj.get("Model") or obj.get("model") or "DTN-200-FPS0").strip()
            except Exception:
                pass

            try:
                result = sn50_analog.parse(payload_raw)
            except Exception as exc:
                self._log.error(
                    "parse_worker.parse_exception",
                    raw_id=raw_id,
                    error=str(exc),
                    exc_info=True,
                )
                continue

            if result.failed:
                self._log.warning(
                    "parse_worker.parse_failed",
                    raw_id=raw_id,
                    reason=result.reason,
                )
                done_ids.append(raw_id)
                continue

            imei = result.readings[0].imei
            if imei not in device_cache:
                device_id = await self._resolve_or_autodetect_device(
                    session, imei, model_from_payload, raw_id, installation_id_cache
                )
                device_cache[imei] = device_id
            else:
                device_id = device_cache[imei]

            if device_id is None:
                self._log.error(
                    "parse_worker.device_resolve_failed",
                    raw_id=raw_id,
                    imei=imei,
                )
                continue

            # Resolve installation_id pelo vínculo ativo
            inst_result = await session.execute(
                self._SQL_INSTALLATION, {"device_id": device_id}
            )
            inst_row = inst_result.fetchone()
            installation_id = inst_row[0] if inst_row else None

            now_utc = datetime.now(timezone.utc)
            max_valid_ts = now_utc + _MAX_FUTURE_OFFSET
            inserted = 0

            for reading in result.readings:
                if reading.collected_at_utc < _MIN_VALID_TS:
                    self._log.warning(
                        "parse_worker.rtc_timestamp_rejected",
                        raw_id=raw_id,
                        imei=imei,
                        collected_at_utc=reading.collected_at_utc.isoformat(),
                        hist_index=reading.hist_index,
                    )
                    continue
                if reading.collected_at_utc > max_valid_ts:
                    self._log.warning(
                        "parse_worker.future_timestamp_rejected",
                        raw_id=raw_id,
                        imei=imei,
                        collected_at_utc=reading.collected_at_utc.isoformat(),
                        hist_index=reading.hist_index,
                    )
                    continue
                await session.execute(
                    self._SQL_INSERT_PARSED,
                    {
                        "raw_message_id": raw_id,
                        "device_id": device_id,
                        "installation_id": installation_id,
                        "hist_index": reading.hist_index,
                        "collected_at_utc": reading.collected_at_utc,
                        "current_ma": reading.current_ma,
                        "voltage_v": reading.voltage_v,
                        "signal_rssi": reading.signal,
                        "battery_v": reading.battery,
                    },
                )
                inserted += 1

            self._log.info(
                "parse_worker.parsed",
                raw_id=raw_id,
                imei=imei,
                readings_total=len(result.readings),
                readings_inserted=inserted,
                status=result.status,
            )
            done_ids.append(raw_id)

        return done_ids

    async def finalize_batch(
        self,
        session: AsyncSession,
        done_ids: list[int],
        error_ids: list[tuple[int, str, bool]],
    ) -> None:
        for raw_id in done_ids:
            await session.execute(
                self._SQL_DONE,
                {"id": raw_id, "worker_id": self._worker_id},
            )

        s = self._settings
        for raw_id, error_msg, is_permanent in error_ids:
            attempts_check = await session.execute(
                text("SELECT parse_attempts FROM raw_messages WHERE id=:id"),
                {"id": raw_id},
            )
            row = attempts_check.fetchone()
            attempts = row[0] if row else 0

            if is_permanent or attempts >= s.worker_max_attempts:
                status = "permanent_error"
            else:
                status = "temporary_error"

            await session.execute(
                self._SQL_ERROR,
                {
                    "id": raw_id,
                    "worker_id": self._worker_id,
                    "status": status,
                    "error_message": error_msg[:500] if error_msg else None,
                },
            )

        await session.commit()

    async def reset_stuck(self, session: AsyncSession) -> int:
        s = self._settings
        result = await session.execute(
            text("""
                UPDATE raw_messages
                SET parse_status = 'pending',
                    processing_since = NULL,
                    worker_id = NULL
                WHERE parse_status = 'processing'
                  AND worker_id = :worker_id
                  AND processing_since < now() - make_interval(secs => :seconds)
                RETURNING id
            """),
            {
                "worker_id": self._worker_id,
                "seconds": float(s.worker_stuck_threshold_seconds),
            },
        )
        await session.commit()
        return len(result.fetchall())


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def _main() -> None:
    from app.config import get_settings
    from app.logging import configure_logging

    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)
    await ParseWorker().run()


if __name__ == "__main__":
    asyncio.run(_main())
