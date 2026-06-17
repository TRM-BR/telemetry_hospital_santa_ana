"""
app/workers/calibration_worker.py — Calibração dinâmica de dispositivos.

Espelha 1:1 o algoritmo de scripts/update_dragino_calibration.py do legado.

Algoritmo (por device com pressure2_raw disponível):
  1. Busca os N menores e N maiores valores de pressure2_raw (kPa)
     na janela dos últimos calib_window_days dias.
  2. Converte cada valor para MCA: v_mca = v_kpa * PRESSURE_KPA_TO_MCA
  3. ref_min_mca = média dos N menores (já em MCA)
  4. ref_max_mca = média dos N maiores (já em MCA)
  5. Valida span: se (ref_max_mca - ref_min_mca) < calib_min_span_mca → descarta
  6. Upsert em calibrations por device_id (ON CONFLICT DO UPDATE)

Periodicidade: a cada calib_poll_seconds (default 7200 = 2h), idêntico ao legado.

Não herda de WorkerRunner porque não consome fila com FOR UPDATE SKIP LOCKED.
É um loop de agregação periódica, sem claim/release/watchdog de fila.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.logging import configure_logging, get_logger

logger = get_logger(__name__)

# 1 kPa = 0.1019716 MCA (idêntico ao legado e a pressure_mca.py)
PRESSURE_KPA_TO_MCA: float = 0.1019716

# ── SQLs ────────────────────────────────────────────────────────────────────

# Upsert de calibração por device_id (ON CONFLICT = mesma semântica do legado)
_SQL_UPSERT = text("""
    INSERT INTO calibrations (
        device_id, ref_min_mca, ref_max_mca,
        n_low, n_high, window_days,
        last_source_ts, calc_version,
        created_at, updated_at
    ) VALUES (
        :device_id, :ref_min_mca, :ref_max_mca,
        :n_low, :n_high, :window_days,
        :last_source_ts, :calc_version,
        now(), now()
    )
    ON CONFLICT (device_id) DO UPDATE SET
        ref_min_mca    = EXCLUDED.ref_min_mca,
        ref_max_mca    = EXCLUDED.ref_max_mca,
        n_low          = EXCLUDED.n_low,
        n_high         = EXCLUDED.n_high,
        window_days    = EXCLUDED.window_days,
        last_source_ts = EXCLUDED.last_source_ts,
        calc_version   = EXCLUDED.calc_version,
        updated_at     = now()
""")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _mean(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _safe_float(v) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


# ── Worker ──────────────────────────────────────────────────────────────────

class CalibrationWorker:
    """
    Worker de calibração dinâmica.

    Não herda de WorkerRunner — não há fila, apenas agregação periódica.
    Espelha CalibrationService do legado update_dragino_calibration.py.
    """

    worker_name = "calibration_worker"

    def __init__(self) -> None:
        from app.config import get_settings
        self._settings = get_settings()
        self._log = logger.bind(worker=self.worker_name)
        self._running = True

    async def _list_devices(self, session: AsyncSession) -> list[int]:
        """Retorna device_ids com pressure2_raw disponível na janela."""
        result = await session.execute(
            text("""
                SELECT DISTINCT device_id
                FROM parsed_measurements
                WHERE pressure2_raw IS NOT NULL
                  AND collected_at_utc >= now() AT TIME ZONE 'UTC'
                                        - :days * INTERVAL '1 day'
            """),
            {"days": self._settings.calib_window_days},
        )
        return [row[0] for row in result.fetchall()]

    async def _fetch_values(
        self,
        session: AsyncSession,
        device_id: int,
        order: str,
        n: int,
    ) -> list[float]:
        """Busca N valores de pressure2_raw (kPa) ordenados ASC ou DESC."""
        result = await session.execute(
            text(f"""
                SELECT pressure2_raw
                FROM parsed_measurements
                WHERE device_id = :device_id
                  AND pressure2_raw IS NOT NULL
                  AND collected_at_utc >= now() AT TIME ZONE 'UTC'
                                          - :days * INTERVAL '1 day'
                ORDER BY pressure2_raw {order}
                LIMIT :n
            """),
            {
                "device_id": device_id,
                "days": self._settings.calib_window_days,
                "n": n,
            },
        )
        out = []
        for row in result.fetchall():
            v = _safe_float(row[0])
            if v is not None:
                out.append(v)
        return out

    async def _fetch_last_ts(
        self,
        session: AsyncSession,
        device_id: int,
    ) -> Optional[datetime]:
        result = await session.execute(
            text("""
                SELECT MAX(collected_at_utc)
                FROM parsed_measurements
                WHERE device_id = :device_id
                  AND pressure2_raw IS NOT NULL
                  AND collected_at_utc >= now() AT TIME ZONE 'UTC'
                                          - :days * INTERVAL '1 day'
            """),
            {"device_id": device_id, "days": self._settings.calib_window_days},
        )
        row = result.fetchone()
        return row[0] if row else None

    async def recalc_once(self) -> int:
        """
        Executa um ciclo completo de recalibração para todos os devices.
        Retorna o número de calibrações atualizadas.
        """
        s = self._settings
        updated = 0

        async with get_session() as session:
            device_ids = await self._list_devices(session)

        if not device_ids:
            self._log.info("calibration_worker.no_devices")
            return 0

        for device_id in device_ids:
            try:
                async with get_session() as session:
                    lows_kpa = await self._fetch_values(
                        session, device_id, "ASC", s.calib_n_low
                    )
                    highs_kpa = await self._fetch_values(
                        session, device_id, "DESC", s.calib_n_high
                    )

                if not lows_kpa or not highs_kpa:
                    self._log.debug(
                        "calibration_worker.insufficient_data",
                        device_id=device_id,
                        n_lows=len(lows_kpa),
                        n_highs=len(highs_kpa),
                    )
                    continue

                # Converte kPa → MCA antes da média (idêntico ao legado)
                lows_mca  = [v * PRESSURE_KPA_TO_MCA for v in lows_kpa]
                highs_mca = [v * PRESSURE_KPA_TO_MCA for v in highs_kpa]

                ref_min_mca = _mean(lows_mca)
                ref_max_mca = _mean(highs_mca)

                if ref_min_mca is None or ref_max_mca is None:
                    continue

                span = ref_max_mca - ref_min_mca
                if span < s.calib_min_span_mca:
                    self._log.info(
                        "calibration_worker.span_too_small",
                        device_id=device_id,
                        ref_min_mca=round(ref_min_mca, 6),
                        ref_max_mca=round(ref_max_mca, 6),
                        span=round(span, 6),
                        min_required=s.calib_min_span_mca,
                    )
                    continue

                async with get_session() as session:
                    last_ts = await self._fetch_last_ts(session, device_id)

                async with get_session() as session:
                    await session.execute(
                        _SQL_UPSERT,
                        {
                            "device_id":      device_id,
                            "ref_min_mca":    ref_min_mca,
                            "ref_max_mca":    ref_max_mca,
                            "n_low":          s.calib_n_low,
                            "n_high":         s.calib_n_high,
                            "window_days":    s.calib_window_days,
                            "last_source_ts": last_ts,
                            "calc_version":   s.calib_version,
                        },
                    )

                updated += 1
                self._log.info(
                    "calibration_worker.updated",
                    device_id=device_id,
                    ref_min_mca=round(ref_min_mca, 6),
                    ref_max_mca=round(ref_max_mca, 6),
                    span=round(span, 6),
                    n_lows=len(lows_mca),
                    n_highs=len(highs_mca),
                    last_source_ts=str(last_ts) if last_ts else None,
                )

            except Exception as exc:
                self._log.error(
                    "calibration_worker.device_error",
                    device_id=device_id,
                    error=str(exc),
                    exc_info=True,
                )

        return updated

    async def run(self) -> None:
        """Loop principal. Roda recalc_once() e dorme calib_poll_seconds."""
        s = self._settings
        self._log.info(
            "calibration_worker.starting",
            poll_seconds=s.calib_poll_seconds,
            window_days=s.calib_window_days,
            n_low=s.calib_n_low,
            n_high=s.calib_n_high,
            min_span_mca=s.calib_min_span_mca,
        )

        # On error, retry after a short interval to self-heal transient failures
        # (e.g. DNS hiccup at startup). On success, sleep the full poll interval.
        _ERROR_RETRY_SECONDS = 60.0

        while self._running:
            sleep_seconds = s.calib_poll_seconds
            try:
                updated = await self.recalc_once()
                self._log.info("calibration_worker.cycle_done", updated=updated)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._log.error(
                    "calibration_worker.loop_error",
                    error=str(exc),
                    exc_info=True,
                )
                sleep_seconds = _ERROR_RETRY_SECONDS

            try:
                await asyncio.sleep(sleep_seconds)
            except asyncio.CancelledError:
                break

        self._log.info("calibration_worker.stopped")

    def stop(self) -> None:
        self._running = False


# ── Entrypoint ───────────────────────────────────────────────────────────────

async def _main() -> None:
    from app.config import get_settings
    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)
    await CalibrationWorker().run()


if __name__ == "__main__":
    asyncio.run(_main())
