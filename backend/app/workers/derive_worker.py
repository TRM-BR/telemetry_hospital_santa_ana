"""
app/workers/derive_worker.py — Worker que converte parsed_measurements → derived_metrics.

Métricas emitidas (por leitura analógica DTN-200-FPS0):
  current_ma   (mA)  — sempre, quando disponível
  level_m      (m)   — só quando current_ma está na faixa válida e há perfil
  level_pct    (%)   — idem
  voltage_v    (V)   — diagnóstico do canal analógico (sempre que disponível)
  battery_v    (V)   — tensão da bateria
  signal       (dBm) — RSSI NB-IoT

Sem pressão, calibração, pulsos ou vazão — hardware analógico.

Fault detection (via analog_level.current_to_level):
  undercurrent (<fault_below_ma) ou overrange (>fault_above_ma):
    → emite current_ma (para diagnóstico), NÃO emite level_m/level_pct
    → sensor_fault gerado pelo alert_worker via capabilities

Perfil analógico por modelo: vem de settings.analog_profiles[device.model].
Sem perfil → emite só current_ma/voltage_v/battery_v/signal (sem nível).

Ciclo (padrão 2-TX via WorkerRunner):
  1. Watchdog: devolve para 'pending' registros presos em 'processing'.
  2. TX1 (claim): marca lote de parsed_measurements como 'processing'.
  3. Calcula derivações por dispositivo (fora de TX).
  4. TX2 (finaliza): insere em derived_metrics + atualiza parsed_measurements.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.logging import get_logger
from app.processing.derivations.analog_level import current_to_level
from app.workers._runner import WorkerRunner
from app.workers.alert_trigger import mark_dirty as _mark_alert_dirty

logger = get_logger(__name__)


class DeriveWorker(WorkerRunner):
    worker_name = "derive_worker"

    # ── Queries ─────────────────────────────────────────────────────────────

    _SQL_CLAIM = text("""
        WITH batch AS (
            SELECT id, collected_at_utc FROM parsed_measurements
            WHERE derive_status IN ('pending', 'temporary_error')
              AND (
                last_attempt_at IS NULL
                OR last_attempt_at < now() - (
                    CASE derive_attempts
                        WHEN 0 THEN INTERVAL '0 seconds'
                        WHEN 1 THEN INTERVAL '60 seconds'
                        WHEN 2 THEN INTERVAL '300 seconds'
                        WHEN 3 THEN INTERVAL '900 seconds'
                        ELSE          INTERVAL '3600 seconds'
                    END
                )
              )
            ORDER BY collected_at_utc
            LIMIT :batch_size
            FOR UPDATE SKIP LOCKED
        )
        UPDATE parsed_measurements pm
        SET
            derive_status    = 'processing',
            processing_since = now(),
            worker_id        = :worker_id,
            derive_attempts  = derive_attempts + 1,
            last_attempt_at  = now()
        FROM batch
        WHERE pm.id = batch.id
          AND pm.collected_at_utc = batch.collected_at_utc
        RETURNING pm.id
    """)

    _SQL_LOAD_BATCH = text("""
        SELECT
            pm.id, pm.device_id, pm.installation_id, pm.collected_at_utc, pm.hist_index,
            pm.current_ma, pm.voltage_v, pm.signal_rssi, pm.battery_v,
            d.model
        FROM parsed_measurements pm
        JOIN devices d ON d.id = pm.device_id
        WHERE pm.id = ANY(:ids)
        ORDER BY pm.device_id, pm.collected_at_utc, pm.hist_index
    """)

    _SQL_INSERT_METRIC = text("""
        INSERT INTO derived_metrics (
            derived_at_utc, parsed_measurement_id, device_id, installation_id,
            metric_name, value, unit
        ) VALUES (
            :derived_at_utc, :parsed_measurement_id, :device_id, :installation_id,
            :metric_name, :value, :unit
        )
        ON CONFLICT (device_id, derived_at_utc, metric_name) DO NOTHING
    """)

    _SQL_DONE = text("""
        UPDATE parsed_measurements
        SET derive_status    = 'done',
            error_message    = NULL,
            processing_since = NULL
        WHERE id = :id
          AND worker_id = :worker_id
          AND derive_status = 'processing'
    """)

    _SQL_ERROR = text("""
        UPDATE parsed_measurements
        SET derive_status    = :status,
            error_message    = :error_message,
            processing_since = NULL
        WHERE id = :id
          AND worker_id = :worker_id
          AND derive_status = 'processing'
    """)

    # ── Interface (WorkerRunner) ─────────────────────────────────────────────

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

        s = self._settings

        rows_result = await session.execute(
            self._SQL_LOAD_BATCH,
            {"ids": list(row_ids)},
        )
        rows = rows_result.fetchall()

        inserts: list[tuple[int, int, Optional[int], datetime, list[dict]]] = []
        done_ids: list[int] = []

        for row in rows:
            (
                pm_id, device_id, installation_id, ts, hist_idx,
                current_ma, voltage_v, signal_rssi, battery_v, model,
            ) = row

            metrics: list[dict] = []

            # ── Corrente — sempre emitida quando disponível ───────────────────
            if current_ma is not None:
                metrics.append({
                    "metric_name": "current_ma",
                    "value": float(current_ma),
                    "unit": "mA",
                })

                # ── Nível — só com perfil analógico e sem fault ──────────────
                profile = s.analog_profiles.get(model) if model else None
                if profile:
                    level_m, level_pct, _fault_kind = current_to_level(float(current_ma), profile)
                    if level_m is not None:
                        metrics.append({"metric_name": "level_m",   "value": level_m,   "unit": "m"})
                    if level_pct is not None:
                        metrics.append({"metric_name": "level_pct", "value": level_pct, "unit": "%"})
                    # fault_kind não é emitida como métrica aqui —
                    # é detectada pelo alert_worker via sensor_fault

            # ── Tensão analógica — diagnóstico ───────────────────────────────
            if voltage_v is not None:
                metrics.append({
                    "metric_name": "voltage_v",
                    "value": float(voltage_v),
                    "unit": "V",
                })

            # ── Bateria e sinal ───────────────────────────────────────────────
            if battery_v is not None:
                metrics.append({
                    "metric_name": "battery_v",
                    "value": float(battery_v),
                    "unit": "V",
                })
            if signal_rssi is not None:
                metrics.append({
                    "metric_name": "signal",
                    "value": float(signal_rssi),
                    "unit": "dBm",
                })

            inserts.append((pm_id, device_id, installation_id, ts, metrics))
            done_ids.append(pm_id)

        # Insere todas as métricas
        total_inserts = 0
        for pm_id, dev_id, install_id, ts, metrics in inserts:
            for m in metrics:
                await session.execute(
                    self._SQL_INSERT_METRIC,
                    {
                        "derived_at_utc":        ts,
                        "parsed_measurement_id": pm_id,
                        "device_id":             dev_id,
                        "installation_id":       install_id,
                        "metric_name":           m["metric_name"],
                        "value":                 m["value"],
                        "unit":                  m["unit"],
                    },
                )
                total_inserts += 1

        # Sinaliza instalações com dados novos para avaliação de alertas
        dirty_installs: set[Optional[int]] = {install_id for _, _, install_id, _, _ in inserts}
        for iid in dirty_installs:
            if iid is not None:
                await _mark_alert_dirty(iid)

        self._log.info(
            "derive_worker.derived",
            readings=len(inserts),
            metric_rows=total_inserts,
        )
        return done_ids

    async def finalize_batch(
        self,
        session: AsyncSession,
        done_ids: list[int],
        error_ids: list[tuple[int, str, bool]],
    ) -> None:
        for pm_id in done_ids:
            await session.execute(
                self._SQL_DONE,
                {"id": pm_id, "worker_id": self._worker_id},
            )

        s = self._settings
        for pm_id, error_msg, is_permanent in error_ids:
            attempts_check = await session.execute(
                text("SELECT derive_attempts FROM parsed_measurements WHERE id=:id"),
                {"id": pm_id},
            )
            row = attempts_check.fetchone()
            attempts = row[0] if row else 0

            status = (
                "permanent_error"
                if (is_permanent or attempts >= s.worker_max_attempts)
                else "temporary_error"
            )
            await session.execute(
                self._SQL_ERROR,
                {
                    "id": pm_id,
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
                UPDATE parsed_measurements
                SET derive_status    = 'pending',
                    processing_since = NULL,
                    worker_id        = NULL
                WHERE derive_status = 'processing'
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
    await DeriveWorker().run()


if __name__ == "__main__":
    asyncio.run(_main())
