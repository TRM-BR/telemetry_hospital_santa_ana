"""
app/services/telegram_message_formatter.py — Formata o alerta crítico em HTML.

Regras:
  - HTML do Telegram (parse_mode=HTML).
  - Escapa TODOS os campos dinâmicos (html.escape).
  - Tolerante a campos ausentes (nunca quebra).
  - Converte horário UTC → America/Sao_Paulo.
  - Curto, objetivo e acionável.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

_BR_TZ = ZoneInfo("America/Sao_Paulo")

# Rótulos amigáveis por alert_type (cai no próprio valor se não mapeado).
_ALERT_TYPE_LABELS: dict[str, str] = {
    "nivel": "Nível do reservatório",
    "consumo": "Consumo",
    "vazao": "Vazão",
    "pressao": "Pressão",
    "sensor": "Sensor",
    "infraestrutura": "Infraestrutura",
}


def _esc(value: Any) -> str:
    """Escapa um valor para HTML, tolerando None."""
    if value is None:
        return ""
    return html.escape(str(value))


def _format_timestamp_br(triggered_at_utc: Optional[datetime]) -> str:
    if triggered_at_utc is None:
        return "—"
    dt = triggered_at_utc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_BR_TZ).strftime("%d/%m/%Y %H:%M")


def _alert_type_label(alert_type: Optional[str], titulo: Optional[str]) -> str:
    if titulo:
        return titulo
    if not alert_type:
        return "Alerta"
    return _ALERT_TYPE_LABELS.get(alert_type, alert_type)


def _measurements_block(dados_relevantes: Optional[Mapping[str, Any]]) -> str:
    """Monta linhas 'chave: valor' a partir de dados_relevantes (se houver)."""
    if not dados_relevantes:
        return ""
    lines: list[str] = []
    for key, value in dados_relevantes.items():
        if value is None or isinstance(value, (dict, list)):
            continue
        if isinstance(value, float):
            value = round(value, 2)
        lines.append(f"{_esc(key)}: <b>{_esc(value)}</b>")
        if len(lines) >= 6:  # mantém a mensagem curta
            break
    return "\n".join(lines)


def format_critical_alert(
    *,
    installation_name: Optional[str],
    alert_type: Optional[str],
    titulo: Optional[str],
    human_summary: Optional[str],
    recommended_action: Optional[str],
    triggered_at_utc: Optional[datetime],
    dados_relevantes: Optional[Mapping[str, Any]] = None,
) -> str:
    """Retorna o corpo HTML da mensagem de alerta crítico."""
    parts: list[str] = [
        "<b>🚨 ALERTA CRÍTICO - Telemetria Barueri</b>",
        "",
        f"<b>Unidade:</b> {_esc(installation_name) or '—'}",
        f"<b>Tipo:</b> {_esc(_alert_type_label(alert_type, titulo))}",
        "<b>Severidade:</b> CRÍTICO",
        "",
        "<b>Resumo:</b>",
        _esc(human_summary) or "—",
    ]

    measurements = _measurements_block(dados_relevantes)
    if measurements:
        parts += ["", "<b>Medições:</b>", measurements]

    parts += [
        "",
        f"<b>Horário:</b> {_esc(_format_timestamp_br(triggered_at_utc))}",
        "<b>Status:</b> Aberto",
    ]

    if recommended_action:
        parts += ["", "<b>Ação recomendada:</b>", _esc(recommended_action)]

    return "\n".join(parts)
