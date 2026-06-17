"""
app/workers/behavior_baseline_worker.py — Baseline comportamental por instalação.

Ciclo (uma vez por dia — agendamento exato às 02:30 BRT via systemd, Fase 8):
  1. Calcula janela de 30 dias fechados em BRT (exclui o dia corrente incompleto).
  2. Para cada instalação ativa com device ativo:
     a. Carrega capabilities para saber quais canais se aplicam.
     b. Busca contadores acumulados na janela (+1h de margem).
     c. Computa flow1_lph / flow2_lph via windowed_flow_series (1h deslizante).
     d. Filtra para [window_start, window_end) e descarta artefatos (hard cap).
     e. Calcula cobertura em dias-calendário BRT distintos.
     f. Para cada canal aplicável × 6 períodos:
        - Segmenta a série por período via period_types_for.
        - Chama compute_baseline_row (behavior.py — sem banco).
        - Faz UPSERT em installation_behavior_baselines.
     g. Commit isolado por instalação; rollback em falha sem derrubar o ciclo.

Suporta execução única via --once para validação manual (Fase 5):
    python -m app.workers.behavior_baseline_worker --once

A unit systemd (telemetry-worker-behavior-baseline.service) é Fase 8 — não
habilitada aqui.

Modelado em BaselineWorker (baseline_worker.py): loop de agregação periódica,
não usa WorkerRunner (que é para filas com SKIP LOCKED).
"""
from __future__ import annotations

import argparse
import asyncio
import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.behavior import (
    compute_baseline_row,
    period_types_for,
    to_brt,
)
from app.alerts.capabilities import get_installation_capabilities
from app.config import get_settings
from app.db.session import get_session
from app.logging import configure_logging, get_logger
from app.processing.derivations.flow_window import windowed_flow_series

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_WINDOW_DAYS: int = 30
_DEFAULT_INTERVAL_SECONDS: int = 24 * 3600   # loop diário; horário exato = systemd
_MIN_SAMPLES_GLOBAL: int = 5                  # amostras mínimas p/ gravar linha de período
_FLOW_HARD_CAP_LPH: float = 100_000.0        # descarta artefatos de delta de contador
                                              # (reset de hardware) — igual alert_worker

# Derivação de level_drop_pph e level_drop_abs_2h
_LEVEL_DROP_PPH_LOOKBACK_H: float = 1.5     # janela de regressão linear (1,5 h)
_LEVEL_DROP_PPH_MIN_POINTS: int = 3          # pontos mínimos na janela para computar slope
_LEVEL_DROP_ABS2H_WINDOW_H: float = 2.0     # janela absoluta (2 h)
_LEVEL_DROP_ABS2H_SPAN_MIN_MIN: float = 90.0  # span mínimo da janela para ser válida

# Conjunto fechado de períodos (espelha o retorno de behavior.period_types_for).
_PERIODS: tuple[str, ...] = (
    "overall", "night", "day", "business_hours", "off_hours", "weekend"
)

# Mapeamento canal → métrica. Espelha capabilities._channel_role e
# alert_worker._channel_role (sem duplicar a lógica).
#   (atributo_capability, channel_role, metric_name)
_CHANNELS: tuple[tuple[str, str, str], ...] = (
    ("has_street_inlet_counter", "street_inlet", "flow1_lph"),
    ("has_tank_outlet_counter",  "tank_outlet",  "flow2_lph"),
)

# Canais de magnitude direta (de derived_metrics, não de contadores) usados
# APENAS para a velocidade típica (typical_variation_per_hour) — habilitam o
# detector variacao_rapida em pressão/nível. Não geram alertas de magnitude.
#   (atributo_capability, channel_role, metric_name)
_RAW_METRIC_CHANNELS: tuple[tuple[str, str, str], ...] = (
    ("has_street_pressure", "street_pressure", "pressure"),
    ("has_tank_pressure",   "tank_pressure",   "pressure2"),
    ("can_alert_level",     "tank_level",      "level_pct"),
)


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

# Margem de 1h antes do início da janela: necessária para que windowed_flow_series
# consiga calcular o primeiro ponto da janela (igual a baseline_worker).
_SQL_FLOW_COUNTS = text("""
    SELECT pm.collected_at_utc, pm.count_pulses, pm.count2_pulses
    FROM parsed_measurements pm
    WHERE pm.installation_id = :installation_id
      AND pm.collected_at_utc >= :start_margin
      AND pm.collected_at_utc <  :window_end
    ORDER BY pm.collected_at_utc ASC
""")

_SQL_LEVEL_PCT = text("""
    SELECT dm.derived_at_utc, dm.value
    FROM derived_metrics dm
    JOIN device_installations di ON di.device_id = dm.device_id
    WHERE di.installation_id = :installation_id
      AND di.valid_to IS NULL
      AND dm.metric_name = 'level_pct'
      AND dm.value IS NOT NULL
      AND dm.derived_at_utc >= :start_margin
      AND dm.derived_at_utc <  :window_end
    ORDER BY dm.derived_at_utc ASC
""")

# Séries de magnitude direta (pressão/nível) para a velocidade típica.
_SQL_RAW_METRIC_SERIES = text("""
    SELECT dm.metric_name, dm.derived_at_utc, dm.value
    FROM derived_metrics dm
    JOIN device_installations di ON di.device_id = dm.device_id
    WHERE di.installation_id = :installation_id
      AND di.valid_to IS NULL
      AND dm.metric_name = ANY(:metrics)
      AND dm.value IS NOT NULL
      AND dm.derived_at_utc >= :window_start
      AND dm.derived_at_utc <  :window_end
    ORDER BY dm.metric_name, dm.derived_at_utc ASC
""")

_SQL_UPSERT = text("""
    INSERT INTO installation_behavior_baselines (
        installation_id, channel_role, metric_name, period_type,
        mean, std, min, max,
        p05, p10, p25, p50, p75, p90, p95,
        zero_ratio, near_zero_ratio,
        longest_zero_minutes, typical_zero_minutes,
        longest_continuous_flow_minutes, typical_continuous_flow_minutes,
        minimum_night_flow,
        normal_low, normal_high, anomaly_low, anomaly_high,
        typical_variation_per_hour,
        profile_type, confidence,
        coverage_pct, window_days, expected_samples, sample_count,
        window_start_at, window_end_at, computed_at
    ) VALUES (
        :installation_id, :channel_role, :metric_name, :period_type,
        :mean, :std, :min, :max,
        :p05, :p10, :p25, :p50, :p75, :p90, :p95,
        :zero_ratio, :near_zero_ratio,
        :longest_zero_minutes, :typical_zero_minutes,
        :longest_continuous_flow_minutes, :typical_continuous_flow_minutes,
        :minimum_night_flow,
        :normal_low, :normal_high, :anomaly_low, :anomaly_high,
        :typical_variation_per_hour,
        :profile_type, :confidence,
        :coverage_pct, :window_days, :expected_samples, :sample_count,
        :window_start_at, :window_end_at, now()
    )
    ON CONFLICT (installation_id, channel_role, metric_name, period_type) DO UPDATE SET
        mean                             = EXCLUDED.mean,
        std                              = EXCLUDED.std,
        min                              = EXCLUDED.min,
        max                              = EXCLUDED.max,
        p05                              = EXCLUDED.p05,
        p10                              = EXCLUDED.p10,
        p25                              = EXCLUDED.p25,
        p50                              = EXCLUDED.p50,
        p75                              = EXCLUDED.p75,
        p90                              = EXCLUDED.p90,
        p95                              = EXCLUDED.p95,
        zero_ratio                       = EXCLUDED.zero_ratio,
        near_zero_ratio                  = EXCLUDED.near_zero_ratio,
        longest_zero_minutes             = EXCLUDED.longest_zero_minutes,
        typical_zero_minutes             = EXCLUDED.typical_zero_minutes,
        longest_continuous_flow_minutes  = EXCLUDED.longest_continuous_flow_minutes,
        typical_continuous_flow_minutes  = EXCLUDED.typical_continuous_flow_minutes,
        minimum_night_flow               = EXCLUDED.minimum_night_flow,
        normal_low                       = EXCLUDED.normal_low,
        normal_high                      = EXCLUDED.normal_high,
        anomaly_low                      = EXCLUDED.anomaly_low,
        anomaly_high                     = EXCLUDED.anomaly_high,
        typical_variation_per_hour       = EXCLUDED.typical_variation_per_hour,
        profile_type                     = EXCLUDED.profile_type,
        confidence                       = EXCLUDED.confidence,
        coverage_pct                     = EXCLUDED.coverage_pct,
        window_days                      = EXCLUDED.window_days,
        expected_samples                 = EXCLUDED.expected_samples,
        sample_count                     = EXCLUDED.sample_count,
        window_start_at                  = EXCLUDED.window_start_at,
        window_end_at                    = EXCLUDED.window_end_at,
        computed_at                      = now()
""")


# ---------------------------------------------------------------------------
# Derivação de séries de queda de nível
# ---------------------------------------------------------------------------

def derive_level_drop_pph_series(
    level_points: list[tuple[datetime, float]],
) -> list[tuple[datetime, float]]:
    """
    Deriva a série level_drop_pph a partir dos pontos de level_pct.

    Para cada ponto t, aplica regressão linear nos pontos [t-1.5h, t].
    Retorna positivo = queda. Filtra negativos (subidas) e artefatos > 100 p.p./h.
    """
    result: list[tuple[datetime, float]] = []
    for i, (ts_t, _) in enumerate(level_points):
        cutoff = ts_t.timestamp() - _LEVEL_DROP_PPH_LOOKBACK_H * 3600
        window = [
            (ts, v) for ts, v in level_points[: i + 1]
            if ts.timestamp() >= cutoff
        ]
        if len(window) < _LEVEL_DROP_PPH_MIN_POINTS:
            continue
        ts_ref = window[0][0].timestamp()
        xs = [(ts.timestamp() - ts_ref) / 3600 for ts, _ in window]
        ys = [v for _, v in window]
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        den = sum((x - mx) ** 2 for x in xs)
        if den == 0:
            continue
        drop_pph = -(num / den)   # positivo = queda
        if not math.isfinite(drop_pph):
            continue
        if drop_pph <= 0 or drop_pph > 100.0:
            continue
        result.append((ts_t, drop_pph))
    return result


def derive_level_drop_abs_2h_series(
    level_points: list[tuple[datetime, float]],
) -> list[tuple[datetime, float]]:
    """
    Deriva a série level_drop_abs_2h a partir dos pontos de level_pct.

    Para cada ponto t, calcula (level_início_janela_2h − level_t).
    Requer ≥2 pontos com span ≥90 min em [t-2h, t].
    Retorna positivo = queda. Filtra negativos e > 100 p.p.
    """
    result: list[tuple[datetime, float]] = []
    for i, (ts_t, v_t) in enumerate(level_points):
        cutoff = ts_t.timestamp() - _LEVEL_DROP_ABS2H_WINDOW_H * 3600
        window = [
            (ts, v) for ts, v in level_points[: i + 1]
            if ts.timestamp() >= cutoff
        ]
        if len(window) < 2:
            continue
        span_min = (ts_t.timestamp() - window[0][0].timestamp()) / 60
        if span_min < _LEVEL_DROP_ABS2H_SPAN_MIN_MIN:
            continue
        drop_abs = window[0][1] - v_t   # positivo = queda
        if not math.isfinite(drop_abs):
            continue
        if drop_abs <= 0 or drop_abs > 100.0:
            continue
        result.append((ts_t, drop_abs))
    return result


def _coverage_expected(
    window_ts: list[datetime],
) -> tuple[float, Optional[int], int]:
    """
    Calcula (coverage_pct, expected_samples, distinct_days) a partir dos
    timestamps de uma série já filtrada para a janela. Espelha a lógica usada
    para vazão/nível — cobertura por dias-calendário BRT distintos.
    """
    distinct_dates = {to_brt(ts).date() for ts in window_ts}
    distinct_days = len(distinct_dates)
    coverage_pct = 100.0 * distinct_days / _WINDOW_DAYS
    expected: Optional[int] = None
    if distinct_days > 0:
        rpd: dict[object, int] = {}
        for ts in window_ts:
            d = to_brt(ts).date()
            rpd[d] = rpd.get(d, 0) + 1
        expected = _WINDOW_DAYS * round(statistics.median(rpd.values()))
    return coverage_pct, expected, distinct_days


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class BehaviorBaselineWorker:
    """
    Computa e persiste o baseline comportamental de cada instalação/canal/período.

    Análogo a BaselineWorker: loop de agregação periódica sem fila. Não herda
    WorkerRunner (que é para filas com FOR UPDATE SKIP LOCKED).
    """

    worker_name = "behavior_baseline_worker"

    def __init__(self, interval_seconds: int = _DEFAULT_INTERVAL_SECONDS) -> None:
        self._interval = interval_seconds
        self._running  = True
        self._log      = logger.bind(worker=self.worker_name)

    def stop(self) -> None:
        self._running = False

    # ── Execução pública ───────────────────────────────────────────────────────

    async def run_once(self) -> None:
        """Executa um único ciclo completo e encerra (usado com --once)."""
        async with get_session() as session:
            await self._compute_all(session)

    async def run(self) -> None:
        """Loop periódico (padrão: 24h). Para com stop() ou CancelledError."""
        self._log.info(
            f"{self.worker_name}.starting",
            interval_h=self._interval / 3600,
            mode="loop",
        )
        while self._running:
            try:
                async with get_session() as session:
                    await self._compute_all(session)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._log.error(
                    f"{self.worker_name}.loop_error",
                    error=str(exc),
                    exc_info=True,
                )
            await asyncio.sleep(self._interval)

        self._log.info(f"{self.worker_name}.stopped")

    # ── Ciclo principal ────────────────────────────────────────────────────────

    async def _compute_all(self, session: AsyncSession) -> None:
        """
        Itera todas as instalações ativas e calcula o baseline de cada uma.

        Janela de 30 dias fechados em BRT: exclui o dia corrente incompleto
        para que o recálculo diário seja idempotente.
        """
        # Janela em BRT
        now_brt   = to_brt(datetime.now(timezone.utc))
        end_brt   = now_brt.replace(hour=0, minute=0, second=0, microsecond=0)
        start_brt = end_brt - timedelta(days=_WINDOW_DAYS)
        window_end_utc   = end_brt.astimezone(timezone.utc)
        window_start_utc = start_brt.astimezone(timezone.utc)

        result = await session.execute(_SQL_INSTALLATIONS)
        installations = result.fetchall()
        if not installations:
            self._log.info(f"{self.worker_name}.no_installations")
            return

        total_rows = 0

        for inst_id, slug in installations:
            try:
                rows_upserted = await self._compute_installation(
                    session, inst_id, slug,
                    window_start_utc, window_end_utc,
                )
                await session.commit()
                total_rows += rows_upserted
            except Exception as exc:
                await session.rollback()
                self._log.error(
                    f"{self.worker_name}.inst_error",
                    installation=slug,
                    error=str(exc),
                    exc_info=True,
                )

        self._log.info(
            f"{self.worker_name}.cycle_done",
            installations=len(installations),
            total_rows=total_rows,
            window_start=window_start_utc.isoformat(),
            window_end=window_end_utc.isoformat(),
        )

    # ── Pipeline por instalação ────────────────────────────────────────────────

    async def _compute_installation(
        self,
        session: AsyncSession,
        inst_id: int,
        slug: str,
        window_start_utc: datetime,
        window_end_utc: datetime,
    ) -> int:
        """
        Computa e faz UPSERT das linhas de baseline de uma instalação.

        Retorna o número de linhas gravadas (canal × período). Exceções
        propagadas para o chamador (_compute_all) que faz rollback isolado.
        """
        # 1. Capabilities — nunca por slug, sempre por dados
        caps = await get_installation_capabilities(
            inst_id, session, slug=slug
        )

        # 2. Counters na janela + 1h de margem para windowed_flow_series
        start_margin = window_start_utc - timedelta(hours=1)
        cnt_result = await session.execute(
            _SQL_FLOW_COUNTS,
            {
                "installation_id": inst_id,
                "start_margin":    start_margin,
                "window_end":      window_end_utc,
            },
        )
        count_rows = cnt_result.fetchall()   # (collected_at_utc, count_pulses, count2_pulses)

        if not count_rows:
            self._log.debug(
                f"{self.worker_name}.no_data",
                installation=slug,
            )
            return 0

        lpp = float(get_settings().flow_liter_per_pulse)

        # 3. Flow via janela deslizante de 1h (elimina spikes de pacotes históricos
        #    do Dragino — mesma lógica de baseline_worker e alert_worker)
        pts1 = [(ts, c1)  for ts, c1, _c2 in count_rows]
        pts2 = [(ts, c2)  for ts, _c1, c2 in count_rows]
        flow1_raw = windowed_flow_series(pts1, liter_per_pulse=lpp)
        flow2_raw = windowed_flow_series(pts2, liter_per_pulse=lpp)

        # 4. Filtrar para [window_start, window_end) e descartar artefatos
        def _in_window_clean(ts: datetime, v: float) -> bool:
            return window_start_utc <= ts < window_end_utc and 0.0 <= v <= _FLOW_HARD_CAP_LPH

        flow1: list[tuple[datetime, float]] = [
            (ts, v) for ts, v in flow1_raw if _in_window_clean(ts, v)
        ]
        flow2: list[tuple[datetime, float]] = [
            (ts, v) for ts, v in flow2_raw if _in_window_clean(ts, v)
        ]

        # 5. Cobertura baseada em dias-calendário BRT distintos com ≥1 leitura.
        #    Usa os timestamps dos counters (não dos flows, que podem ter menos
        #    pontos por filtragem pelo hard cap).
        window_ts = [
            ts for ts, _c1, _c2 in count_rows
            if window_start_utc <= ts < window_end_utc
        ]
        distinct_dates = {to_brt(ts).date() for ts in window_ts}
        distinct_days  = len(distinct_dates)
        coverage_pct   = 100.0 * distinct_days / _WINDOW_DAYS

        # expected_samples: metadado informativo para auditoria.
        # Permite distinguir "instalação com baixa amostragem" de "instalação nova".
        # NÃO é driver primário de confiança — a confiança vem de coverage_pct
        # (dias), conforme relatório seção 10.6 e behavior.classify_confidence.
        expected_samples: Optional[int] = None
        if distinct_days > 0:
            readings_per_day: dict[object, int] = {}
            for ts in window_ts:
                d = to_brt(ts).date()
                readings_per_day[d] = readings_per_day.get(d, 0) + 1
            median_rpd = statistics.median(readings_per_day.values())
            expected_samples = _WINDOW_DAYS * round(median_rpd)

        # 6. UPSERT por canal × período
        channel_series: dict[str, list[tuple[datetime, float]]] = {
            "flow1_lph": flow1,
            "flow2_lph": flow2,
        }
        rows_upserted = 0
        confidences_seen: list[str] = []

        for cap_attr, channel_role, metric_name in _CHANNELS:
            if not getattr(caps, cap_attr, False):
                continue

            series = channel_series[metric_name]
            if not series:
                continue

            for period in _PERIODS:
                # Segmentar série pelo período
                period_idx = [
                    i for i, (ts, _v) in enumerate(series)
                    if period in period_types_for(to_brt(ts))
                ]
                if len(period_idx) < _MIN_SAMPLES_GLOBAL:
                    continue

                vals = [series[i][1] for i in period_idx]
                tss  = [series[i][0] for i in period_idx]

                row = compute_baseline_row(
                    vals, tss,
                    metric=metric_name,
                    period=period,
                    window_days=_WINDOW_DAYS,
                    expected_samples=expected_samples,
                    coverage_pct=coverage_pct,
                )

                await session.execute(
                    _SQL_UPSERT,
                    {
                        "installation_id": inst_id,
                        "channel_role":    channel_role,
                        "metric_name":     metric_name,
                        "period_type":     period,
                        "window_start_at": window_start_utc,
                        "window_end_at":   window_end_utc,
                        **row,
                    },
                )
                rows_upserted += 1
                confidences_seen.append(row["confidence"])

        # ── Tank level baselines ─────────────────────────────────────────────
        tank_level_rows_upserted = 0
        lv_distinct_days = 0
        level_coverage_pct = 0.0

        if caps.can_alert_level:
            start_margin_level = window_start_utc - timedelta(hours=2)
            lvl_result = await session.execute(
                _SQL_LEVEL_PCT,
                {
                    "installation_id": inst_id,
                    "start_margin":    start_margin_level,
                    "window_end":      window_end_utc,
                },
            )
            level_rows = lvl_result.fetchall()
            level_points: list[tuple[datetime, float]] = [
                (ts, float(v)) for ts, v in level_rows
            ]

            if level_points:
                level_window_ts = [
                    ts for ts, _ in level_points
                    if window_start_utc <= ts < window_end_utc
                ]
                lv_distinct_days = len(
                    {to_brt(ts).date() for ts in level_window_ts}
                )
                level_coverage_pct = 100.0 * lv_distinct_days / _WINDOW_DAYS

                level_expected_samples: Optional[int] = None
                if lv_distinct_days > 0:
                    lv_rpd: dict[object, int] = {}
                    for ts in level_window_ts:
                        d = to_brt(ts).date()
                        lv_rpd[d] = lv_rpd.get(d, 0) + 1
                    lv_median_rpd = statistics.median(lv_rpd.values())
                    level_expected_samples = _WINDOW_DAYS * round(lv_median_rpd)

                drop_pph_series  = derive_level_drop_pph_series(level_points)
                drop_2h_series   = derive_level_drop_abs_2h_series(level_points)

                for metric_name_lv, series_lv in [
                    ("level_drop_pph",    drop_pph_series),
                    ("level_drop_abs_2h", drop_2h_series),
                ]:
                    for period in _PERIODS:
                        period_pts = [
                            (ts, v) for ts, v in series_lv
                            if period in period_types_for(to_brt(ts))
                        ]
                        if len(period_pts) < _MIN_SAMPLES_GLOBAL:
                            continue
                        row = compute_baseline_row(
                            [v for _, v in period_pts],
                            [ts for ts, _ in period_pts],
                            metric=metric_name_lv,
                            period=period,
                            window_days=_WINDOW_DAYS,
                            expected_samples=level_expected_samples,
                            coverage_pct=level_coverage_pct,
                        )
                        await session.execute(
                            _SQL_UPSERT,
                            {
                                "installation_id": inst_id,
                                "channel_role":    "tank_level",
                                "metric_name":     metric_name_lv,
                                "period_type":     period,
                                "window_start_at": window_start_utc,
                                "window_end_at":   window_end_utc,
                                **row,
                            },
                        )
                        tank_level_rows_upserted += 1
                        confidences_seen.append(row["confidence"])

        # ── Velocity baselines (pressão/nível) ───────────────────────────────
        # typical_variation_per_hour de magnitude direta — habilita o detector
        # variacao_rapida em pressão/nível. Sem margem (variação é ponto-a-ponto
        # dentro da janela). Não gera alertas de magnitude.
        velocity_rows_upserted = 0
        raw_channels = [
            (role, metric)
            for attr, role, metric in _RAW_METRIC_CHANNELS
            if getattr(caps, attr, False)
        ]
        if raw_channels:
            rm_result = await session.execute(
                _SQL_RAW_METRIC_SERIES,
                {
                    "installation_id": inst_id,
                    "metrics":         [metric for _role, metric in raw_channels],
                    "window_start":    window_start_utc,
                    "window_end":      window_end_utc,
                },
            )
            by_metric: dict[str, list[tuple[datetime, float]]] = {}
            for mn, ts, val in rm_result.fetchall():
                by_metric.setdefault(mn, []).append((ts, float(val)))

            for channel_role, metric_name_raw in raw_channels:
                series_raw = by_metric.get(metric_name_raw, [])
                if not series_raw:
                    continue
                cov_pct, exp_samples, _dd = _coverage_expected(
                    [ts for ts, _ in series_raw]
                )
                for period in _PERIODS:
                    period_pts = [
                        (ts, v) for ts, v in series_raw
                        if period in period_types_for(to_brt(ts))
                    ]
                    if len(period_pts) < _MIN_SAMPLES_GLOBAL:
                        continue
                    row = compute_baseline_row(
                        [v for _, v in period_pts],
                        [ts for ts, _ in period_pts],
                        metric=metric_name_raw,
                        period=period,
                        window_days=_WINDOW_DAYS,
                        expected_samples=exp_samples,
                        coverage_pct=cov_pct,
                    )
                    await session.execute(
                        _SQL_UPSERT,
                        {
                            "installation_id": inst_id,
                            "channel_role":    channel_role,
                            "metric_name":     metric_name_raw,
                            "period_type":     period,
                            "window_start_at": window_start_utc,
                            "window_end_at":   window_end_utc,
                            **row,
                        },
                    )
                    velocity_rows_upserted += 1
                    confidences_seen.append(row["confidence"])

        total_upserted = (
            rows_upserted + tank_level_rows_upserted + velocity_rows_upserted
        )
        self._log.info(
            f"{self.worker_name}.installation_done",
            installation=slug,
            rows_upserted=total_upserted,
            flow_rows=rows_upserted,
            tank_level_rows=tank_level_rows_upserted,
            velocity_rows=velocity_rows_upserted,
            distinct_days=distinct_days,
            coverage_pct=round(coverage_pct, 1),
            level_distinct_days=lv_distinct_days,
            level_coverage_pct=round(level_coverage_pct, 1),
            confidences=sorted(set(confidences_seen)),
        )
        return total_upserted


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Behavior baseline worker — computa baseline comportamental por instalação.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Executa um único ciclo (janela de 30 dias fechados) e encerra. "
            "Use para validação manual antes de habilitar o serviço systemd."
        ),
    )
    args = parser.parse_args()

    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)

    worker = BehaviorBaselineWorker()

    if args.once:
        worker._log.info(
            f"{worker.worker_name}.starting",
            mode="once",
        )
        await worker.run_once()
        worker._log.info(f"{worker.worker_name}.done")
    else:
        await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())
