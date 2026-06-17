"""
app/workers/baseline_worker.py — Baselines estatísticos por instalação.

Ciclo (a cada baseline_interval_seconds, default 6h):
  1. Carrega instalações ativas com dispositivos ativos.
  2. Para cada instalação:
     a. Computa baseline global de cada métrica com os últimos 30 dias.
     b. Faz UPSERT em metric_baselines por installation_id + metric_name.

Estratégia de amostragem:
  • 30 dias × 96 leituras/dia ≈ 2880 pontos por métrica por instalação.
  • O baseline é sempre global para a instalação e a métrica.

Métricas com baseline:
  flow_total_lph, flow1_lph, flow2_lph, level_pct, pressure, pressure2

Não herda de WorkerRunner — é loop de agregação periódica sem fila.
"""
from __future__ import annotations

import asyncio
import statistics

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.logging import get_logger
from app.processing.derivations.flow_window import windowed_flow_series

logger = get_logger(__name__)

# Intervalo padrão entre ciclos (6 horas)
_DEFAULT_INTERVAL_SECONDS = 6 * 3600

# Métricas não-flow — baseline calculado diretamente de derived_metrics
_BASELINE_METRICS = (
    "level_pct",
    "pressure",
    "pressure2",
)

# Métricas de flow — baseline calculado de contadores via janela deslizante
_FLOW_METRIC_NAMES = (
    "flow_total_lph",
    "flow1_lph",
    "flow2_lph",
)

# Parâmetros de amostragem
_BASELINE_WINDOW_DAYS   = 30     # janela histórica para baselines
_MIN_SAMPLES_GLOBAL     = 5      # mínimo de pontos para baseline global


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SQL_INSTALLATIONS = text("""
    SELECT DISTINCT
        i.id,
        i.slug
    FROM installations i
    JOIN device_installations di
        ON di.installation_id = i.id
    AND di.valid_to IS NULL
    JOIN devices d
        ON d.id = di.device_id
    AND d.is_active = true
    WHERE i.is_active = true
    ORDER BY i.id
""")

_SQL_METRIC_SERIES = text("""
    SELECT dm.value
    FROM derived_metrics dm
    JOIN device_installations di ON di.device_id = dm.device_id
    WHERE di.installation_id = :installation_id
      AND di.valid_to IS NULL
      AND dm.metric_name = :metric_name
      AND dm.derived_at_utc >= now() - :window * INTERVAL '1 day'
      AND dm.value IS NOT NULL
    ORDER BY dm.derived_at_utc ASC
""")

# Busca contadores acumulados para computar baselines de flow via janela 1h.
# window_days+1 = 30d + 1d de margem para o primeiro ponto não ficar a zero.
_SQL_FLOW_COUNTS = text("""
    SELECT pm.collected_at_utc, pm.count_pulses, pm.count2_pulses
    FROM parsed_measurements pm
    WHERE pm.installation_id = :installation_id
      AND pm.collected_at_utc >= now() - (:window + 1) * INTERVAL '1 day'
    ORDER BY pm.collected_at_utc ASC
""")

_SQL_UPSERT_BASELINE = text("""
    INSERT INTO metric_baselines
        (installation_id, metric_name,
         mean, std, p10, p90, sample_count, window_days, computed_at)
    VALUES
        (:installation_id, :metric_name,
         :mean, :std, :p10, :p90, :sample_count, :window_days, now())
    ON CONFLICT (installation_id, metric_name) DO UPDATE SET
        mean         = EXCLUDED.mean,
        std          = EXCLUDED.std,
        p10          = EXCLUDED.p10,
        p90          = EXCLUDED.p90,
        sample_count = EXCLUDED.sample_count,
        window_days  = EXCLUDED.window_days,
        computed_at  = now()
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _percentile(data: list[float], p: float) -> float:
    """Percentil via interpolação linear. p em 0–100."""
    if not data:
        return 0.0
    s = sorted(data)
    n = len(s)
    if n == 1:
        return s[0]
    rank = p / 100 * (n - 1)
    lo = int(rank)
    hi = lo + 1
    frac = rank - lo
    if hi >= n:
        return s[-1]
    return s[lo] + frac * (s[hi] - s[lo])


def _compute_stats(values: list[float]) -> dict:
    """Retorna mean/std/p10/p90 para uma lista de valores."""
    mean = statistics.mean(values)
    std  = statistics.stdev(values) if len(values) > 1 else 0.0
    return {
        "mean": mean,
        "std":  std,
        "p10":  _percentile(values, 10),
        "p90":  _percentile(values, 90),
    }


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class BaselineWorker:
    """Computa baselines de métricas e schedules de operação periodicamente."""

    worker_name = "baseline_worker"

    def __init__(self, interval_seconds: int = _DEFAULT_INTERVAL_SECONDS) -> None:
        self._interval = interval_seconds
        self._running  = True
        self._log      = logger.bind(worker=self.worker_name)

    async def run(self) -> None:
        self._log.info(f"{self.worker_name}.starting", interval_h=self._interval / 3600)

        while self._running:
            try:
                async with get_session() as session:
                    await self._compute_all(session)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._log.error(f"{self.worker_name}.loop_error",
                                error=str(exc), exc_info=True)

            await asyncio.sleep(self._interval)

        self._log.info(f"{self.worker_name}.stopped")

    def stop(self) -> None:
        self._running = False

    # ── Ciclo principal ───────────────────────────────────────────────────────

    async def _compute_all(self, session: AsyncSession) -> None:
        result = await session.execute(_SQL_INSTALLATIONS)
        installations = result.fetchall()
        if not installations:
            return

        for inst_id, slug in installations:
            try:
                metrics_ready = await self._compute_baselines(session, inst_id)
                await session.commit()
                self._log.debug(f"{self.worker_name}.baselines_computed",
                                installation=slug, metrics=metrics_ready)
            except Exception as exc:
                await session.rollback()
                self._log.error(f"{self.worker_name}.inst_error",
                                installation=slug, error=str(exc), exc_info=True)

        self._log.info(f"{self.worker_name}.cycle_done",
                       installations=len(installations))

    # ── Baselines ─────────────────────────────────────────────────────────────

    async def _compute_baselines(self, session: AsyncSession, inst_id: int) -> int:
        """
        Computa baselines de métricas não-flow (level, pressão) + métricas de flow.

        Métricas não-flow: usam derived_metrics diretamente.
        Métricas de flow:  usam contadores acumulados (parsed_measurements) com
                           janela deslizante de 1h para eliminar spikes instantâneos.

        Retorna o número de métricas com baseline global computado com sucesso.
        """
        metrics_ready = 0

        # ── Métricas não-flow (derived_metrics) ───────────────────────────────
        for metric in _BASELINE_METRICS:
            result = await session.execute(
                _SQL_METRIC_SERIES,
                {"installation_id": inst_id, "metric_name": metric,
                 "window": _BASELINE_WINDOW_DAYS},
            )
            rows = result.fetchall()

            if not rows:
                continue

            all_values = [float(r[0]) for r in rows]

            if len(all_values) >= _MIN_SAMPLES_GLOBAL:
                await self._upsert_baseline(session, inst_id, metric, all_values)
                metrics_ready += 1

        # ── Métricas de flow (contadores → janela 1h) ─────────────────────────
        flow_ready = await self._compute_flow_baselines(session, inst_id)
        metrics_ready += flow_ready

        return metrics_ready

    async def _compute_flow_baselines(
        self, session: AsyncSession, inst_id: int
    ) -> int:
        """
        Computa baselines de flow usando contadores acumulados e janela de 1h.
        Elimina o viés dos spikes instantâneos que inflam mean/p90.
        """
        result = await session.execute(
            _SQL_FLOW_COUNTS,
            {"installation_id": inst_id, "window": _BASELINE_WINDOW_DAYS},
        )
        rows = result.fetchall()  # (collected_at_utc, count_pulses, count2_pulses)
        if not rows:
            return 0

        lpp = float(get_settings().flow_liter_per_pulse)

        pts1 = [(ts, c1) for ts, c1, _c2 in rows]
        pts2 = [(ts, c2) for ts, _c1, c2 in rows]
        flow1 = windowed_flow_series(pts1, liter_per_pulse=lpp)
        flow2 = windowed_flow_series(pts2, liter_per_pulse=lpp)

        values_by_metric: dict[str, list[float]] = {
            name: [] for name in _FLOW_METRIC_NAMES
        }

        for (ts, v1), (_, v2) in zip(flow1, flow2):
            v_total = v1 + v2
            values_by_metric["flow_total_lph"].append(v_total)
            values_by_metric["flow1_lph"].append(v1)
            values_by_metric["flow2_lph"].append(v2)

        metrics_ready = 0
        for metric_name, values in values_by_metric.items():
            if len(values) >= _MIN_SAMPLES_GLOBAL:
                await self._upsert_baseline(
                    session, inst_id, metric_name, values
                )
                metrics_ready += 1

        return metrics_ready

    async def _upsert_baseline(
        self,
        session: AsyncSession,
        inst_id: int,
        metric: str,
        values: list[float],
    ) -> None:
        stats = _compute_stats(values)
        await session.execute(
            _SQL_UPSERT_BASELINE,
            {
                "installation_id": inst_id,
                "metric_name":     metric,
                "mean":            stats["mean"],
                "std":             stats["std"],
                "p10":             stats["p10"],
                "p90":             stats["p90"],
                "sample_count":    len(values),
                "window_days":     _BASELINE_WINDOW_DAYS,
            },
        )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def _main() -> None:
    from app.config import get_settings
    from app.logging import configure_logging

    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)
    await BaselineWorker().run()


if __name__ == "__main__":
    asyncio.run(_main())
