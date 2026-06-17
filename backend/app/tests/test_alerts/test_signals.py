"""
Testes unitários para app/alerts/signals.py.

Casos de ouro:
  - sustained: spike isolado NÃO dispara; série sustentada dispara.
  - robust_high: p90 da janela (não o máximo isolado).
  - smoothed_slope: detecta tendência real, ignora spikes.
  - drop_per_hour: positivo=caindo, None=subindo.
  - nights_without_rest: conta noites consecutivas sem repouso.
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from app.alerts.signals import (
    sustained,
    sustained_above,
    robust_high,
    smoothed_slope,
    drop_per_hour,
    nights_without_rest,
    days_since_last_rest,
    max_continuous_flow_minutes,
)


# ---------------------------------------------------------------------------
# Fixture: SeriesPoint mínimo (duck-typing)
# ---------------------------------------------------------------------------

@dataclass
class SP:
    ts: datetime
    value: float


UTC = timezone.utc
BRT = timezone(timedelta(hours=-3))

_T0 = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)  # meio-dia UTC


def _pts(values: list[float], interval_min: float = 5.0) -> list[SP]:
    """Gera série com espaçamento uniforme a partir de _T0."""
    return [
        SP(ts=_T0 + timedelta(minutes=i * interval_min), value=v)
        for i, v in enumerate(values)
    ]


# ---------------------------------------------------------------------------
# sustained
# ---------------------------------------------------------------------------

class TestSustained:

    def test_spike_alone_does_not_trigger(self) -> None:
        # 1 ponto alto num histórico baixo → não sustentado
        pts = _pts([5.0, 5.0, 20.0])  # único spike
        now = pts[-1].ts
        assert not sustained(pts, lambda v: v > 15.0, min_readings=3, window_minutes=15.0, now=now)

    def test_sustained_series_triggers(self) -> None:
        # 4 pontos todos acima de 15 → sustentado
        pts = _pts([16.0, 17.0, 18.0, 16.5])
        now = pts[-1].ts
        assert sustained(pts, lambda v: v > 15.0, min_readings=3, window_minutes=30.0, now=now)

    def test_insufficient_points_returns_false(self) -> None:
        pts = _pts([16.0, 17.0])  # só 2 pontos
        now = pts[-1].ts
        assert not sustained(pts, lambda v: v > 15.0, min_readings=3, window_minutes=30.0, now=now)

    def test_empty_series_returns_false(self) -> None:
        assert not sustained([], lambda v: v > 10.0, min_readings=1, window_minutes=10.0)

    def test_partial_coverage_below_threshold(self) -> None:
        # 50% dos pontos satisfazem, coverage_frac=0.75 → False
        pts = _pts([16.0, 5.0, 16.0, 5.0])
        now = pts[-1].ts
        assert not sustained(
            pts, lambda v: v > 15.0,
            min_readings=3, window_minutes=30.0, coverage_frac=0.75, now=now
        )

    def test_partial_coverage_above_threshold(self) -> None:
        # 75% dos pontos satisfazem, coverage_frac=0.75 → True
        pts = _pts([16.0, 16.0, 16.0, 5.0])
        now = pts[-1].ts
        assert sustained(
            pts, lambda v: v > 15.0,
            min_readings=3, window_minutes=30.0, coverage_frac=0.75, now=now
        )

    def test_sustained_above_shorthand(self) -> None:
        pts = _pts([16.0, 17.0, 18.0, 16.5])
        now = pts[-1].ts
        assert sustained_above(pts, 15.0, min_readings=3, window_minutes=30.0, now=now)

    def test_old_points_outside_window_ignored(self) -> None:
        # Pontos altos mas fora da janela temporal
        pts = _pts([16.0, 17.0, 18.0])  # 0, 5, 10 min após _T0
        # Usamos now = 1 hora depois — os pontos ficam a 50–60 min, fora de uma janela de 20 min
        now = _T0 + timedelta(minutes=60)
        assert not sustained(pts, lambda v: v > 15.0, min_readings=2, window_minutes=20.0, now=now)


# ---------------------------------------------------------------------------
# robust_high
# ---------------------------------------------------------------------------

class TestRobustHigh:

    def test_returns_p90_not_max(self) -> None:
        # 10 pontos em 10..19 → p90 ≈ 18.1, não 19
        pts = _pts(list(range(10, 20)))
        val = robust_high(pts, percentile=90.0)
        assert val is not None
        assert val < 19.0
        assert val > 17.0

    def test_single_spike_not_returned_at_p90_with_many_low(self) -> None:
        # 9 pontos em 5.0, 1 pico em 50.0 → p90 muito abaixo do pico
        pts = _pts([5.0] * 9 + [50.0])
        val = robust_high(pts, percentile=90.0)
        assert val is not None
        assert val < 50.0  # o pico isolado não domina o p90

    def test_empty_returns_none(self) -> None:
        assert robust_high([]) is None

    def test_single_point(self) -> None:
        pts = _pts([42.0])
        assert robust_high(pts) == 42.0

    def test_uniform_series(self) -> None:
        pts = _pts([10.0] * 10)
        assert robust_high(pts) == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# smoothed_slope / drop_per_hour
# ---------------------------------------------------------------------------

class TestSmoothedSlope:

    def _rising_series(self) -> list[SP]:
        """Série claramente subindo: 10 → 20 em 2h."""
        return [
            SP(ts=_T0 + timedelta(minutes=i * 15), value=10.0 + i)
            for i in range(9)
        ]

    def _falling_series(self) -> list[SP]:
        """Série claramente caindo: 20 → 10 em 2h."""
        return [
            SP(ts=_T0 + timedelta(minutes=i * 15), value=20.0 - i)
            for i in range(9)
        ]

    def _flat_with_spike_start(self) -> list[SP]:
        """Série estável com spike no início (seria falso positivo na diferença de pontas)."""
        # Ponto 0 alto (spike), depois 8 pontos estáveis e subindo levemente.
        vals = [30.0] + [10.0 + i * 0.5 for i in range(8)]
        return [
            SP(ts=_T0 + timedelta(minutes=i * 15), value=v)
            for i, v in enumerate(vals)
        ]

    def test_rising_series_has_positive_slope(self) -> None:
        s = smoothed_slope(self._rising_series(), lookback_hours=2.0)
        assert s is not None
        assert s > 0

    def test_falling_series_has_negative_slope(self) -> None:
        s = smoothed_slope(self._falling_series(), lookback_hours=2.0)
        assert s is not None
        assert s < 0

    def test_drop_per_hour_on_falling_series_is_positive(self) -> None:
        d = drop_per_hour(self._falling_series(), lookback_hours=2.0)
        assert d is not None
        assert d > 0

    def test_drop_per_hour_on_rising_series_is_none(self) -> None:
        # Série subindo → drop_per_hour retorna None
        d = drop_per_hour(self._rising_series(), lookback_hours=2.0)
        assert d is None

    def test_spike_at_start_does_not_cause_false_drop(self) -> None:
        # Esta é a cura do falso positivo de "queda de nível":
        # diferença de pontas (30 - último) daria queda, mas a tendência real é subindo.
        pts = self._flat_with_spike_start()
        slope = smoothed_slope(pts, lookback_hours=2.5)
        # Tendência suavizada deve ser positiva (subindo) ou próxima de zero
        if slope is not None:
            assert slope >= -1.0, "Slope should not indicate a strong drop when series is rising"

    def test_insufficient_points_returns_none(self) -> None:
        pts = _pts([10.0, 9.0])  # apenas 2 pontos
        assert smoothed_slope(pts, lookback_hours=1.0) is None

    def test_empty_series_returns_none(self) -> None:
        assert smoothed_slope([]) is None


# ---------------------------------------------------------------------------
# nights_without_rest
# ---------------------------------------------------------------------------

class TestNightsWithoutRest:

    def _night_pts(self, night_offset: int, values: list[float]) -> list[SP]:
        """Gera pontos dentro da janela 00h–05h BRT de `night_offset` dias atrás."""
        # _T0 é meio-dia UTC = 09h BRT. Para gerar noite BRT anterior:
        # Noite de hoje em BRT: 00h–06h BRT = 03h–09h UTC
        today_brt = _T0.astimezone(BRT).date()
        night_date = today_brt - timedelta(days=night_offset)
        night_brt_start = datetime(
            night_date.year, night_date.month, night_date.day,
            2, 0, tzinfo=BRT,  # 02h BRT está dentro de 00h–06h
        )
        interval = timedelta(minutes=30)
        return [
            SP(ts=night_brt_start + timedelta(minutes=i * 30), value=v)
            for i, v in enumerate(values)
        ]

    def test_one_night_without_rest(self) -> None:
        pts = self._night_pts(0, [5.0, 6.0, 7.0, 5.5])  # sempre acima de 1.0
        count = nights_without_rest(pts, rest_threshold=1.0, min_night_points=3, now=_T0)
        assert count == 1

    def test_night_with_rest_gives_zero(self) -> None:
        pts = self._night_pts(0, [5.0, 0.5, 6.0, 5.5])  # um ponto em repouso
        count = nights_without_rest(pts, rest_threshold=1.0, min_night_points=3, now=_T0)
        assert count == 0

    def test_empty_series_gives_zero(self) -> None:
        assert nights_without_rest([], now=_T0) == 0

    def test_two_consecutive_nights_without_rest(self) -> None:
        pts = (
            self._night_pts(0, [5.0, 6.0, 7.0])
            + self._night_pts(1, [4.0, 5.0, 6.0])
        )
        count = nights_without_rest(pts, rest_threshold=1.0, min_night_points=3, now=_T0)
        assert count == 2

    def test_breaks_on_first_night_with_rest(self) -> None:
        # Noite 0 sem repouso, noite 1 COM repouso, noite 2 sem repouso.
        # Deve retornar 1 (para na noite 1).
        pts = (
            self._night_pts(0, [5.0, 6.0, 7.0])
            + self._night_pts(1, [0.5, 5.0, 6.0])  # repouso
            + self._night_pts(2, [5.0, 6.0, 7.0])
        )
        count = nights_without_rest(pts, rest_threshold=1.0, min_night_points=3, now=_T0)
        assert count == 1


# ---------------------------------------------------------------------------
# days_since_last_rest
# ---------------------------------------------------------------------------

class TestDaysSinceLastRest:

    def _pt(self, hours_ago: float, value: float) -> SP:
        return SP(ts=_T0 - timedelta(hours=hours_ago), value=value)

    def test_empty_series_returns_none(self) -> None:
        assert days_since_last_rest([], now=_T0) is None

    def test_zeroed_10h_ago_returns_0(self) -> None:
        pts = [self._pt(48, 20.0), self._pt(10, 0.5), self._pt(1, 15.0)]
        assert days_since_last_rest(pts, rest_threshold=1.0, now=_T0) == 0

    def test_zeroed_36h_ago_returns_1(self) -> None:
        pts = [self._pt(72, 20.0), self._pt(36, 0.5), self._pt(2, 15.0)]
        assert days_since_last_rest(pts, rest_threshold=1.0, now=_T0) == 1

    def test_zeroed_77h_ago_returns_3(self) -> None:
        pts = [self._pt(168, 20.0), self._pt(77, 0.5), self._pt(5, 15.0)]
        assert days_since_last_rest(pts, rest_threshold=1.0, now=_T0) == 3

    def test_never_zeroed_returns_none(self) -> None:
        # 30 dias de pontos, todos acima de 1.0
        pts = [self._pt(h, 10.0) for h in range(720, 0, -24)]
        assert days_since_last_rest(pts, rest_threshold=1.0, lookback_days=30, now=_T0) is None

    def test_zeroed_outside_lookback_window_returns_none(self) -> None:
        # Zerou há 10 dias, mas janela é só 7 dias
        pts = [self._pt(240, 0.5), self._pt(1, 15.0)]
        assert days_since_last_rest(pts, rest_threshold=1.0, lookback_days=7, now=_T0) is None


# ---------------------------------------------------------------------------
# max_continuous_flow_minutes
# ---------------------------------------------------------------------------

class TestMaxContinuousFlow:

    def test_single_run(self) -> None:
        # 4 pontos de fluxo contínuo a 5min de intervalo = 15 min de run
        pts = _pts([5.0, 5.0, 5.0, 5.0])
        result = max_continuous_flow_minutes(pts, rest_threshold=1.0, lookback_hours=1.0)
        assert result == pytest.approx(15.0)

    def test_interrupted_run(self) -> None:
        # 3 pontos de fluxo, 1 repouso, 2 de fluxo → maior run = 10 min
        pts = _pts([5.0, 5.0, 5.0, 0.5, 5.0, 5.0])
        result = max_continuous_flow_minutes(pts, rest_threshold=1.0, lookback_hours=1.0)
        assert result == pytest.approx(10.0)

    def test_all_at_rest(self) -> None:
        pts = _pts([0.5, 0.3, 0.5])
        result = max_continuous_flow_minutes(pts, rest_threshold=1.0)
        assert result == 0.0

    def test_empty_series(self) -> None:
        assert max_continuous_flow_minutes([]) == 0.0
