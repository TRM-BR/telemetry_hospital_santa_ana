"""
Testes unitários para app/alerts/severity.py.

Casos de ouro (golden tests):
  - valor na metade inferior da banda → None (sem "atencao")
  - valor exatamente igual ao normal_high → None (não alerta)
  - valor na metade superior → moderado
  - acima de anomaly_high → alto
  - acima de 2× anomaly_high → crítico
  - teto por confiança "low" limita a moderado
  - teto por confiança "medium" limita a alto
  - severity_from_band_low entre anomaly e normal → None (sem "atencao")
"""
import pytest
from app.alerts.severity import (
    severity_from_band,
    severity_from_band_low,
    severity_from_ratio,
    severity_cap_by_confidence,
    min_severity,
    max_severity,
    SEVERITY_ORDER,
)


# ---------------------------------------------------------------------------
# severity_from_band — lado alto
# ---------------------------------------------------------------------------

class TestSeverityFromBand:
    """Régua de severidade pelo lado alto da faixa."""

    def test_within_normal_returns_none(self) -> None:
        sev, _ = severity_from_band(12.0, normal_high=12.0, anomaly_high=18.0, confidence="high")
        assert sev is None

    def test_below_normal_returns_none(self) -> None:
        sev, _ = severity_from_band(5.0, normal_high=12.0, anomaly_high=18.0, confidence="high")
        assert sev is None

    def test_lower_half_of_band_returns_none(self) -> None:
        # normal=10, anomaly=20, mid=15. Valor 13 está abaixo do mid — não dispara.
        sev, reason = severity_from_band(13.0, normal_high=10.0, anomaly_high=20.0, confidence="high")
        assert sev is None
        assert reason == "band_lower_half"

    def test_at_mid_boundary_returns_none(self) -> None:
        # 15 L/h, mid = (12+18)/2 = 15. Exatamente no limite → banda inferior → None.
        sev, _ = severity_from_band(15.0, normal_high=12.0, anomaly_high=18.0, confidence="high")
        assert sev is None

    def test_upper_half_of_band_is_moderado(self) -> None:
        # normal=10, anomaly=20, mid=15. Valor 17 está acima do mid.
        sev, _ = severity_from_band(17.0, normal_high=10.0, anomaly_high=20.0, confidence="high")
        assert sev == "moderado"

    def test_above_anomaly_is_alto(self) -> None:
        sev, _ = severity_from_band(25.0, normal_high=10.0, anomaly_high=20.0, confidence="high")
        assert sev == "alto"

    def test_2x_anomaly_is_critico(self) -> None:
        sev, _ = severity_from_band(40.0, normal_high=10.0, anomaly_high=20.0, confidence="high")
        assert sev == "critico"

    def test_just_above_anomaly_is_alto_not_critico(self) -> None:
        # 39.9 < 2×20 = 40 → alto
        sev, _ = severity_from_band(39.9, normal_high=10.0, anomaly_high=20.0, confidence="high")
        assert sev == "alto"

    def test_confidence_low_caps_at_moderado(self) -> None:
        # Sem teto: seria "alto" (acima da anomalia). Com low → moderado.
        sev, reason = severity_from_band(25.0, normal_high=10.0, anomaly_high=20.0, confidence="low")
        assert sev == "moderado"
        assert "capped_low" in reason

    def test_confidence_medium_caps_at_alto(self) -> None:
        # Sem teto: seria "crítico" (≥ 2×). Com medium → alto.
        sev, reason = severity_from_band(50.0, normal_high=10.0, anomaly_high=20.0, confidence="medium")
        assert sev == "alto"
        assert "capped_medium" in reason

    def test_confidence_high_does_not_cap_critico(self) -> None:
        sev, _ = severity_from_band(50.0, normal_high=10.0, anomaly_high=20.0, confidence="high")
        assert sev == "critico"

    def test_reason_code_within_normal(self) -> None:
        _, reason = severity_from_band(5.0, normal_high=12.0, anomaly_high=18.0, confidence="high")
        assert reason == "within_normal"

    def test_reason_code_band_lower_half(self) -> None:
        _, reason = severity_from_band(13.0, normal_high=10.0, anomaly_high=20.0, confidence="high")
        assert reason == "band_lower_half"

    def test_reason_code_above_anomaly(self) -> None:
        _, reason = severity_from_band(25.0, normal_high=10.0, anomaly_high=20.0, confidence="high")
        assert reason == "above_anomaly"

    def test_degenerate_baseline_returns_none(self) -> None:
        # anomaly_high <= normal_high → baseline degenerado → None (sem "atencao")
        # observed deve ser > normal_high para chegar ao ramo degenerado
        sev, reason = severity_from_band(20.0, normal_high=18.0, anomaly_high=10.0, confidence="high")
        assert sev is None
        assert reason == "degenerate_baseline"


# ---------------------------------------------------------------------------
# severity_from_band — lado baixo
# ---------------------------------------------------------------------------

class TestSeverityFromBandLow:
    """Régua de severidade pelo lado baixo (perfil continuous)."""

    def test_above_normal_low_returns_none(self) -> None:
        sev, _ = severity_from_band_low(10.0, normal_low=8.0, anomaly_low=3.0, confidence="high")
        assert sev is None

    def test_exactly_normal_low_returns_none(self) -> None:
        sev, _ = severity_from_band_low(8.0, normal_low=8.0, anomaly_low=3.0, confidence="high")
        assert sev is None

    def test_between_anomaly_and_normal_returns_none(self) -> None:
        # anomaly_low=3, normal_low=8. Valor 5 está entre eles → sem "atencao" → None.
        sev, reason = severity_from_band_low(5.0, normal_low=8.0, anomaly_low=3.0, confidence="high")
        assert sev is None
        assert reason == "slightly_below_normal_low"

    def test_below_anomaly_low_is_moderado(self) -> None:
        # abaixo de anomaly_low (3), mas não abaixo de 0.25×3=0.75
        sev, _ = severity_from_band_low(2.0, normal_low=8.0, anomaly_low=3.0, confidence="high")
        assert sev == "moderado"

    def test_far_below_anomaly_low_is_alto(self) -> None:
        # 0.5 < 0.25×3 = 0.75
        sev, _ = severity_from_band_low(0.5, normal_low=8.0, anomaly_low=3.0, confidence="high")
        assert sev == "alto"

    def test_zero_flow_is_critico(self) -> None:
        sev, reason = severity_from_band_low(0.0, normal_low=8.0, anomaly_low=3.0, confidence="high")
        assert sev == "critico"
        assert "zero_flow" in reason

    def test_no_positive_floor_returns_none(self) -> None:
        # anomaly_low=0 → não se aplica ao perfil
        sev, reason = severity_from_band_low(1.0, normal_low=8.0, anomaly_low=0.0, confidence="high")
        assert sev is None
        assert reason == "no_positive_floor"

    def test_none_baseline_returns_none(self) -> None:
        sev, reason = severity_from_band_low(5.0, normal_low=None, anomaly_low=None, confidence="high")
        assert sev is None
        assert reason == "incomplete_baseline"

    def test_confidence_low_caps_low_side(self) -> None:
        sev, reason = severity_from_band_low(0.5, normal_low=8.0, anomaly_low=3.0, confidence="low")
        # Sem teto: "alto". Com low → moderado.
        assert sev == "moderado"
        assert "capped_low" in reason


# ---------------------------------------------------------------------------
# severity_from_ratio
# ---------------------------------------------------------------------------

class TestSeverityFromRatio:

    def test_below_moderado_threshold_returns_none(self) -> None:
        assert severity_from_ratio(0.5) is None

    def test_at_moderado_threshold(self) -> None:
        assert severity_from_ratio(0.8) == "moderado"

    def test_at_alto_threshold(self) -> None:
        assert severity_from_ratio(1.5) == "alto"

    def test_at_critico_threshold(self) -> None:
        assert severity_from_ratio(3.0) == "critico"

    def test_custom_thresholds(self) -> None:
        assert severity_from_ratio(1.2, moderado=1.0, alto=2.0, critico=4.0) == "moderado"
        assert severity_from_ratio(2.5, moderado=1.0, alto=2.0, critico=4.0) == "alto"
        assert severity_from_ratio(5.0, moderado=1.0, alto=2.0, critico=4.0) == "critico"


# ---------------------------------------------------------------------------
# Helpers de severidade
# ---------------------------------------------------------------------------

class TestSeverityHelpers:

    def test_min_severity_returns_lower(self) -> None:
        assert min_severity("alto", "moderado") == "moderado"
        assert min_severity("critico", "moderado") == "moderado"
        assert min_severity("moderado", "moderado") == "moderado"

    def test_max_severity_returns_higher(self) -> None:
        assert max_severity("alto", "moderado") == "alto"
        assert max_severity("critico", "alto") == "critico"
        assert max_severity(None, "moderado") == "moderado"
        assert max_severity("alto", None) == "alto"
        assert max_severity(None, None) is None

    def test_severity_cap_by_confidence(self) -> None:
        assert severity_cap_by_confidence("low") == "moderado"
        assert severity_cap_by_confidence("medium") == "alto"
        assert severity_cap_by_confidence("high") == "critico"
        assert severity_cap_by_confidence("consolidated") == "critico"
        assert severity_cap_by_confidence("unknown") == "moderado"

    def test_severity_order_is_monotonic(self) -> None:
        assert SEVERITY_ORDER["moderado"] < SEVERITY_ORDER["alto"]
        assert SEVERITY_ORDER["alto"] < SEVERITY_ORDER["critico"]

    def test_atencao_not_in_severity_order(self) -> None:
        assert "atencao" not in SEVERITY_ORDER
