"""
app/alerts/rendering.py — Renderer único de mensagens de alerta.

Centraliza a montagem de titulo, mensagem_usuario, recomendacao e
dados_relevantes para todos os detectores comportamentais, eliminando
a duplicação entre alert_worker.py e api/v1/alerts.py.

Uso esperado:
    from app.alerts.rendering import render_band_alert, recommendation_by_severity
"""
from __future__ import annotations

from typing import Any, Optional


# ---------------------------------------------------------------------------
# Helpers de formatação pt-BR
# ---------------------------------------------------------------------------

def fmt(v: Optional[float], decimals: int = 1) -> str:
    """Formata número com vírgula decimal (pt-BR). None → '—'."""
    if v is None:
        return "—"
    fmt_str = f"{v:.{decimals}f}"
    return fmt_str.replace(".", ",")


def fmt_pct(v: Optional[float]) -> str:
    """Formata percentual inteiro. None → '—'."""
    if v is None:
        return "—"
    return f"{v:.0f}"


def fmt_duration(minutes: float) -> str:
    """Formata duração em horas (≥60 min) ou minutos."""
    if minutes >= 60:
        return f"{minutes / 60:.0f}h"
    return f"{minutes:.0f} min"


# ---------------------------------------------------------------------------
# Rótulos de reason_code → frase para o bullet de classificação
# ---------------------------------------------------------------------------

_REASON_LABELS: dict[str, str] = {
    "within_normal":            "dentro do padrão normal da instalação",
    "band_lower_half":          "acima do normal, mas ainda longe do limite de anomalia",
    "band_upper_half":          "bem acima do normal, próximo do limite de anomalia",
    "above_anomaly":            "ultrapassou o limite de anomalia da instalação",
    "at_least_2x_anomaly":      "atingiu 2× ou mais o limite de anomalia",
    "degenerate_baseline":      "baseline com faixas inconsistentes (anômalo ≤ normal)",
    "slightly_below_normal_low":"abaixo do normal esperado para fluxo contínuo",
    "below_anomaly_low":        "abaixo do limite inferior de anomalia",
    "far_below_anomaly_low":    "muito abaixo do limite inferior — possível interrupção",
    "zero_flow_continuous":     "sem fluxo em canal que deveria ser contínuo",
    "safety_fallback":          "critério de segurança absoluto ativado (sem baseline)",
    # Noturno / ininterrupto
    "night_no_rest":            "fluxo noturno sem repouso — suspeita de vazamento",
    "continuous_flow_long":     "fluxo ininterrupto por longa janela de tempo",
    # Queda de nível
    "level_drop_sustained":     "queda acelerada de nível, tendência confirmada",
    # Nível baixo / autonomia
    "level_low_absolute":       "nível abaixo do limiar de segurança",
    "autonomy_low_absolute":    "autonomia insuficiente para o período",
}


def reason_label(code: str) -> str:
    base = code.split("|")[0]
    return _REASON_LABELS.get(base, code)


# ---------------------------------------------------------------------------
# Recomendação proporcional à severidade
# ---------------------------------------------------------------------------

_RECOMMENDATIONS: dict[str, str] = {
    "atencao":  "Monitorar tendência.",
    "moderado": "Verificar pontos de uso e horários de consumo.",
    "alto":     "Inspecionar a instalação em campo.",
    "critico":  "Ação imediata: risco operacional.",
}


def recommendation_by_severity(severity: str) -> str:
    return _RECOMMENDATIONS.get(severity, "Monitorar tendência.")


# ---------------------------------------------------------------------------
# Renderer principal — alertas comportamentais de faixa (alta/baixa)
# ---------------------------------------------------------------------------

def render_band_alert(
    *,
    severity: str,
    reason_code: str,
    channel_label: str,
    observed: float,
    unit: str,
    period_type: str,
    normal_bound: Optional[float],
    anomaly_bound: Optional[float],
    confidence: str,
    window_minutes: Optional[float] = None,
    extra_lines: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Monta titulo, mensagem_usuario, recomendacao e dados_relevantes para um
    alerta comportamental de faixa (fora_da_faixa_alta, fora_da_faixa_baixa,
    vazao_noturna, etc.).

    Returns:
        dict com chaves: titulo, mensagem_usuario, recomendacao, dados_relevantes.
    """
    side = "alta" if "below" not in reason_code and "low" not in reason_code.lower() else "baixa"

    # Título diferenciado por severidade e lado
    if side == "alta":
        if observed > (anomaly_bound or 0):
            titulo = "Consumo acima do limite de anomalia desta instalação"
        else:
            titulo = "Consumo acima do padrão normal desta instalação"
    else:
        if "zero" in reason_code:
            titulo = "Ausência de fluxo em canal de fluxo contínuo"
        elif "far_below" in reason_code:
            titulo = "Consumo anormalmente baixo — possível interrupção"
        else:
            titulo = "Consumo abaixo do padrão esperado (fluxo contínuo)"

    # Mensagem em tópicos (bullets)
    lines: list[str] = [f"• Canal: {channel_label}"]
    lines.append(f"• Valor observado: {fmt(observed)} {unit}")

    if side == "alta":
        if normal_bound is not None:
            lines.append(f"• Máximo normal ({period_type}): {fmt(normal_bound)} {unit}")
        if anomaly_bound is not None:
            lines.append(f"• Limite de anomalia: {fmt(anomaly_bound)} {unit}")
        if normal_bound is not None:
            excess = observed - normal_bound
            pct = (excess / normal_bound * 100) if normal_bound > 0 else None
            pct_str = f" (+{fmt_pct(pct)}%)" if pct is not None else ""
            lines.append(f"• Excesso sobre o normal: +{fmt(excess)} {unit}{pct_str}")
        if anomaly_bound is not None and observed > anomaly_bound:
            eoa = observed - anomaly_bound
            pct = (eoa / anomaly_bound * 100) if anomaly_bound > 0 else None
            pct_str = f" (+{fmt_pct(pct)}%)" if pct is not None else ""
            lines.append(f"• Excesso sobre o limite anômalo: +{fmt(eoa)} {unit}{pct_str}")
    else:
        if normal_bound is not None:
            lines.append(f"• Mínimo normal ({period_type}): {fmt(normal_bound)} {unit}")
        if anomaly_bound is not None:
            lines.append(f"• Limite inferior de anomalia: {fmt(anomaly_bound)} {unit}")
        if anomaly_bound is not None and observed < anomaly_bound:
            deficit = anomaly_bound - observed
            lines.append(f"• Déficit abaixo do limite anômalo: {fmt(deficit)} {unit}")

    if window_minutes is not None:
        lines.append(f"• Janela analisada: {fmt_duration(window_minutes)}")

    if extra_lines:
        lines.extend(extra_lines)

    lines.append(f"• Confiança da baseline: {confidence}")
    lines.append(f"• Classificação: {severity} — {reason_label(reason_code)}")

    mensagem = "\n".join(lines)
    recomendacao = recommendation_by_severity(severity)

    dados: dict[str, Any] = {
        "reason":          reason_code,
        "observed_value":  round(observed, 2),
        "observed_unit":   unit,
        "period_type":     period_type,
        "confidence":      confidence,
        "severity_reason": reason_code,
    }
    if normal_bound is not None:
        dados["normal_bound"] = round(normal_bound, 2)
    if anomaly_bound is not None:
        dados["anomaly_bound"] = round(anomaly_bound, 2)

    return {
        "titulo":           titulo,
        "mensagem_usuario": mensagem,
        "recomendacao":     recomendacao,
        "dados_relevantes": dados,
    }


# ---------------------------------------------------------------------------
# Renderer de nível
# ---------------------------------------------------------------------------

def render_level_alert(
    *,
    severity: str,
    reason_code: str,
    nivel_atual: Optional[float],
    drop_rate: Optional[float] = None,
    drop_unit: str = "p.p./h",
    confidence: str = "n/a",
    window_minutes: Optional[float] = None,
) -> dict[str, Any]:
    """Monta campos de alerta de queda/nível para queda_nivel."""
    if drop_rate is not None and drop_rate > 0:
        titulo = "Queda acelerada de nível — investigar causa"
    else:
        titulo = "Nível da caixa em queda"

    lines: list[str] = []
    if nivel_atual is not None:
        lines.append(f"• Nível atual: {fmt(nivel_atual)}%")
    if drop_rate is not None:
        lines.append(f"• Taxa de queda: {fmt(drop_rate)} {drop_unit}")
    if window_minutes is not None:
        lines.append(f"• Janela analisada: {fmt_duration(window_minutes)}")
    if confidence != "n/a":
        lines.append(f"• Confiança da baseline: {confidence}")
    lines.append(f"• Classificação: {severity} — {reason_label(reason_code)}")

    dados: dict[str, Any] = {
        "reason":          reason_code,
        "severity_reason": reason_code,
        "confidence":      confidence,
        "channel_role":    "tank_level",
    }
    if nivel_atual is not None:
        dados["level_pct_atual"] = round(nivel_atual, 1)
    if drop_rate is not None:
        dados["observed_value"] = round(drop_rate, 2)
        dados["observed_unit"]  = drop_unit

    rec_map = {
        "atencao":  "Acompanhar próximas leituras. Se a queda persistir, investigar.",
        "moderado": "Verificar se houve consumo esperado. Acompanhar tendência.",
        "alto":     "Investigar consumo anormal ou possível vazamento.",
        "critico":  "Inspecionar pontos de saída. Possível rompimento de tubulação.",
    }

    return {
        "titulo":           titulo,
        "mensagem_usuario": "\n".join(lines),
        "recomendacao":     rec_map.get(severity, "Monitorar tendência."),
        "dados_relevantes": dados,
    }


# ---------------------------------------------------------------------------
# Renderer de vazamento
# ---------------------------------------------------------------------------

def render_leak_alert(
    *,
    rule_key: str,
    severity: str,
    reason_code: str,
    channel_label: str,
    nights_without_rest: Optional[int] = None,
    continuous_minutes: Optional[float] = None,
    flow_value: Optional[float] = None,
    unit: str = "L/h",
) -> dict[str, Any]:
    """Monta campos de alerta de suspeita de vazamento."""
    if rule_key == "consumo_ininterrupto":
        titulo = "Consumo ininterrupto — suspeita de vazamento"
        lines = [f"• Canal: {channel_label}"]
        if continuous_minutes is not None:
            lines.append(f"• Duração ininterrupta: {fmt_duration(continuous_minutes)}")
        if flow_value is not None:
            lines.append(f"• Vazão média: {fmt(flow_value)} {unit}")
        lines.append("• Fluxo contínuo sem nenhum período de repouso")
    elif rule_key == "vazamento_noturno":
        titulo = "Vazão noturna sem repouso — suspeita de vazamento"
        lines = [f"• Canal: {channel_label}"]
        if nights_without_rest is not None:
            lines.append(f"• Noites consecutivas sem repouso: {nights_without_rest}")
        if flow_value is not None:
            lines.append(f"• Vazão mínima noturna: {fmt(flow_value)} {unit}")
        lines.append("• Consumo noturno nunca cessa — padrão anormal de vazamento")
    else:
        titulo = "Suspeita de vazamento"
        lines = [f"• Canal: {channel_label}"]

    lines.append(f"• Classificação: {severity} — {reason_label(reason_code)}")

    dados: dict[str, Any] = {
        "reason":          reason_code,
        "severity_reason": reason_code,
        "channel_label":   channel_label,
    }
    if nights_without_rest is not None:
        dados["nights_without_rest"] = nights_without_rest
    if continuous_minutes is not None:
        dados["continuous_minutes"] = round(continuous_minutes, 1)
    if flow_value is not None:
        dados["observed_value"] = round(flow_value, 2)
        dados["observed_unit"]  = unit

    rec_map = {
        "atencao":  "Monitorar nas próximas 24h. Se persistir, verificar em campo.",
        "moderado": "Verificar pontos de saída e medidores. Pode ser vazamento.",
        "alto":     "Inspecionar a instalação. Alta probabilidade de vazamento.",
        "critico":  "Ação imediata: vazamento provável ou confirmado.",
    }

    return {
        "titulo":           titulo,
        "mensagem_usuario": "\n".join(lines),
        "recomendacao":     rec_map.get(severity, "Monitorar tendência."),
        "dados_relevantes": dados,
    }
