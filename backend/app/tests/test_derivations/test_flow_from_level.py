"""Testes unitários para flow_from_level — funções puras, sem DB."""
from __future__ import annotations

import pytest
from app.processing.derivations.flow_from_level import (
    net_flow_hourly,
    net_flow_series,
    volume_l,
)

CAP = 40_000.0  # L
H = 3_600_000   # 1 hora em ms
TZ = "America/Sao_Paulo"


def ms(h: float) -> int:
    """t=0 + h horas em ms."""
    return int(h * H)


class TestVolumeL:
    def test_zero(self):
        assert volume_l(0.0, CAP) == 0.0

    def test_full(self):
        assert volume_l(100.0, CAP) == pytest.approx(CAP)

    def test_half(self):
        assert volume_l(50.0, CAP) == pytest.approx(20_000.0)


class TestNetFlowSeries:
    def test_empty(self):
        assert net_flow_series([], CAP) == []

    def test_single_point(self):
        assert net_flow_series([(ms(0), 50.0)], CAP) == []

    def test_filling(self):
        # 50% → 75% em 1 hora = +10.000 L/h
        pts = [(ms(0), 50.0), (ms(1), 75.0)]
        result = net_flow_series(pts, CAP)
        assert len(result) == 1
        ts, flow = result[0]
        assert ts == ms(1)
        assert flow == pytest.approx(10_000.0, rel=1e-3)

    def test_consuming(self):
        # 80% → 60% em 1 hora = -8.000 L/h
        pts = [(ms(0), 80.0), (ms(1), 60.0)]
        result = net_flow_series(pts, CAP)
        assert len(result) == 1
        _, flow = result[0]
        assert flow == pytest.approx(-8_000.0, rel=1e-3)

    def test_no_point_in_window(self):
        # Ponto 2 está a 30 min do ponto 1, mas janela é 1h; ponto 0 está a 2h
        # Só há ponto 0 (t=0) e ponto 1 (t=0.5h) e ponto 2 (t=1h)
        pts = [(ms(0), 50.0), (ms(0.5), 60.0), (ms(1), 70.0)]
        # ponto 1 (t=0.5h): threshold = -0.5h → j=0 ✓ (0 <= -0.5? No, ms(0)=0 > ms(0.5)-H = -H/2)
        # Hmm, threshold for i=1 (t=0.5h) = 0.5h - 1h = -0.5h → j = bisect_right(ts, -H/2) - 1 = -1 → skip
        # threshold for i=2 (t=1h) = 0h → j = bisect_right(ts, 0) - 1 = 0 (ts[0]=0 <= 0) → j=0 ✓
        result = net_flow_series(pts, CAP)
        assert len(result) == 1
        ts_out, flow = result[0]
        assert ts_out == ms(1)
        # vol(70%) - vol(50%) = 28000 - 20000 = 8000 L em 1h = 8000 L/h
        assert flow == pytest.approx(8_000.0, rel=1e-3)

    def test_multiple_points_same_sign(self):
        # Subindo de 0% a 100% em 4 horas, 1 ponto por hora
        pts = [(ms(i), i * 25.0) for i in range(5)]
        result = net_flow_series(pts, CAP)
        # Esperado: 4 pontos, cada um com 10.000 L/h
        flows = [v for _, v in result]
        assert all(abs(f - 10_000.0) < 1.0 for f in flows)

    def test_sign_flip(self):
        # Enche depois descarrega
        pts = [
            (ms(0), 30.0),
            (ms(1), 60.0),  # +12.000 L/h
            (ms(2), 40.0),  # -8.000 L/h
        ]
        result = net_flow_series(pts, CAP)
        assert len(result) == 2
        _, f1 = result[0]
        _, f2 = result[1]
        assert f1 > 0
        assert f2 < 0


class TestNetFlowHourly:
    def _pts_steady(self, pct_per_hour: float, start_pct: float = 50.0, hours: int = 4) -> list[tuple[int, float]]:
        """Série com 1 ponto por hora variando pct_per_hour% a cada hora."""
        import datetime as dt
        # Âncora: 2024-01-15 12:00 BRT (15:00 UTC)
        anchor_utc = dt.datetime(2024, 1, 15, 15, 0, 0, tzinfo=dt.timezone.utc)
        return [
            (int((anchor_utc + dt.timedelta(hours=i)).timestamp() * 1000), start_pct + i * pct_per_hour)
            for i in range(hours + 1)
        ]

    def test_empty(self):
        assert net_flow_hourly([], CAP, TZ) == []

    def test_filling_hourly(self):
        # +25%/h = +10.000 L/h
        pts = self._pts_steady(25.0, start_pct=0.0, hours=4)
        result = net_flow_hourly(pts, CAP, TZ)
        # Deve ter ~4 balds horários; todos positivos
        flows = [v for _, v in result]
        assert len(flows) >= 4
        assert all(f > 0 for f in flows if abs(f) > 1)

    def test_consuming_hourly(self):
        # -25%/h = -10.000 L/h
        pts = self._pts_steady(-25.0, start_pct=100.0, hours=4)
        result = net_flow_hourly(pts, CAP, TZ)
        flows = [v for _, v in result]
        assert len(flows) >= 4
        assert all(f < 0 for f in flows if abs(f) > 1)

    def test_timestamps_are_ms(self):
        pts = self._pts_steady(10.0)
        result = net_flow_hourly(pts, CAP, TZ)
        assert all(isinstance(t, int) for t, _ in result)
        # epoch ms → 2024 deve estar nessa faixa
        assert all(1_700_000_000_000 < t < 1_800_000_000_000 for t, _ in result)

    def test_single_point_returns_empty(self):
        import datetime as dt
        anchor = dt.datetime(2024, 1, 15, 15, 0, 0, tzinfo=dt.timezone.utc)
        pts = [(int(anchor.timestamp() * 1000), 50.0)]
        result = net_flow_hourly(pts, CAP, TZ)
        # Sem intervalo entre pontos → nenhum balde tem vol0 e vol1
        assert result == []
