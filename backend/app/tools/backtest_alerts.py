"""
app/tools/backtest_alerts.py — CLI read-only de backtest de alertas históricos.

Fase 19: Replays historical alert_events against the current detector logic
to classify whether each event would still be generated, suppressed, or changed
in severity by the current motor.

Uso:
    python -m app.tools.backtest_alerts \\
        --from 2026-06-07T00:00:00+00:00 \\
        --to   2026-06-08T00:00:00+00:00 \\
        --installation parque_caixa \\
        --rule queda_nivel \\
        --format table

IMPORTANTE: 100% read-only. Nenhum INSERT/UPDATE/DELETE é executado.
A transação PostgreSQL é aberta com SET TRANSACTION READ ONLY e validada
via SHOW transaction_read_only antes da primeira query de dados.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import _get_session_factory
from app.logging import configure_logging, get_logger
from app.services.alert_simulation_service import (
    build_context_as_of,
    simulate_point as simulate,
)
from app.workers.alert_worker import (
    DetectorResult,
    InstallationContext,
    SeriesPoint,
    _SEV_ORDER,
    _compute_drop_abs_2h_now,
    _compute_drop_pph_now,
    _current_period_type,
    behavior_ref,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Limitações conhecidas (impressas em ambas as saídas)
# ---------------------------------------------------------------------------

_LIMITATIONS: list[str] = [
    "Usa a baseline atual de installation_behavior_baselines, nao snapshot historico do dia do evento.",
    "Usa as capacidades hidraulicas atuais (get_installation_capabilities), nao snapshot historico.",
    "Simula decisao pontual no as_of, nao a maquina completa de transicao fired/resolved ao longo do tempo.",
    "Usa o mapeamento atual device_installations.valid_to IS NULL, coerente com 'se o motor atual rodasse'.",
    "Eventos antigos com dados_relevantes vazio (motor legado) podem ser reconstruidos parcialmente.",
    "overrides e active_snoozes ficam vazios — mesmo comportamento do worker em producao hoje.",
    "--from/--to sempre filtram por triggered_at, mesmo quando --as-of-mode=resolved_at.",
    "--status filtra a linha em alert_events, nao o estado atual em alert_state.",
]

# ---------------------------------------------------------------------------
# SQL — queries parametrizadas por :as_of (cópias locais das queries do worker)
# ---------------------------------------------------------------------------

_SQL_FETCH_EVENTS = text("""
    SELECT
        ae.id,
        ae.installation_id,
        ae.rule_key,
        ae.severity,
        ae.status,
        ae.alert_type,
        ae.triggered_at,
        ae.resolved_at,
        ae.titulo,
        ae.mensagem_usuario,
        ae.recomendacao,
        ae.current_value,
        ae.dados_relevantes,
        ae.message,
        i.slug,
        i.name,
        NULL::timestamptz AS learning_mode_until,
        NULL::timestamptz AS baseline_ready_at
    FROM alert_events ae
    JOIN installations i ON i.id = ae.installation_id
    WHERE ae.triggered_at >= :from_dt
      AND ae.triggered_at <  :to_dt
      AND (CAST(:slug AS text)     IS NULL OR i.slug      = CAST(:slug AS text))
      AND (CAST(:rule_key AS text) IS NULL OR ae.rule_key = CAST(:rule_key AS text))
      AND (CAST(:status AS text)   = 'all' OR ae.status   = CAST(:status AS text))
    ORDER BY i.slug, ae.triggered_at ASC
""")

# build_context_as_of e simulate foram extraídos para app.services.alert_simulation_service

# ---------------------------------------------------------------------------
# Contexto read-only
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _open_readonly_session():
    """
    Abre uma sessão PostgreSQL em modo READ ONLY.

    1. Emite SET TRANSACTION READ ONLY antes de qualquer SELECT.
    2. Valida com SHOW transaction_read_only — aborta se != 'on'.
    3. Garante rollback explícito no finally (nunca commit).
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            # Inicia a transação e seta read-only
            await session.execute(text("SET TRANSACTION READ ONLY"))

            # Valida que o PostgreSQL confirmou o modo
            ro_result = await session.execute(text("SHOW transaction_read_only"))
            ro_value = ro_result.scalar()
            if ro_value != "on":
                raise RuntimeError(
                    f"Falha ao garantir transacao read-only: "
                    f"transaction_read_only={ro_value!r} (esperado 'on'). "
                    "Abortando por seguranca."
                )
            yield session
        finally:
            await session.rollback()


# ---------------------------------------------------------------------------
# Fetch de eventos
# ---------------------------------------------------------------------------

async def fetch_events(
    session: AsyncSession,
    *,
    from_dt: datetime,
    to_dt: datetime,
    slug: Optional[str],
    rule_key: Optional[str],
    status: str,
) -> list[Any]:
    """Retorna linhas de alert_events + dados de installations."""
    result = await session.execute(
        _SQL_FETCH_EVENTS,
        {
            "from_dt":  from_dt,
            "to_dt":    to_dt,
            "slug":     slug,
            "rule_key": rule_key,
            "status":   status,
        },
    )
    return result.fetchall()


# ---------------------------------------------------------------------------
# Seleção de as_of
# ---------------------------------------------------------------------------

def pick_as_of(event: Any, mode: str, now: datetime) -> tuple[datetime, str]:
    """
    Retorna (as_of, mode_used).

    Regras:
      triggered_at → sempre event.triggered_at
      resolved_at  → event.resolved_at se existir; cai para triggered_at
      auto         → resolved_at se status='resolvido' E resolved_at IS NOT NULL;
                     senão triggered_at
    """
    triggered = event.triggered_at
    resolved  = event.resolved_at

    # Sanidade: triggered_at no futuro
    if triggered > now:
        return triggered, "triggered_at_future_fallback"

    if mode == "triggered_at":
        return triggered, "triggered_at"

    if mode == "resolved_at":
        if resolved is not None:
            if resolved < triggered:
                logger.warning(
                    "backtest.resolved_before_triggered",
                    event_id=event.id,
                    triggered_at=triggered.isoformat(),
                    resolved_at=resolved.isoformat(),
                )
                return triggered, "triggered_at"
            return resolved, "resolved_at"
        return triggered, "triggered_at"

    if mode == "auto":
        if event.status == "resolvido" and resolved is not None:
            if resolved >= triggered:
                return resolved, "resolved_at"
        return triggered, "triggered_at"

    # fallback defensivo
    return triggered, "triggered_at"


# build_context_as_of importado de app.services.alert_simulation_service


# ---------------------------------------------------------------------------
# Coleta de evidências reais
# ---------------------------------------------------------------------------

def _last_value(series: list[SeriesPoint]) -> Optional[float]:
    """Último valor de uma série ou None."""
    return series[-1].value if series else None


def collect_real_evidence(
    ctx: InstallationContext,
    rule_key: str,
    as_of: datetime,
    baseline_ready: bool,
    is_stale: bool,
    in_learning: bool,
) -> dict[str, Any]:
    """
    Monta bloco de evidências reais para o instante as_of.
    Campos gerais + específicos por rule_key.
    """
    level_series  = ctx.series.get("level_pct",    [])
    flow1_series  = ctx.series.get("flow1_lph",    [])
    flow2_series  = ctx.series.get("flow2_lph",    [])
    press_series  = ctx.series.get("pressure",     [])
    press2_series = ctx.series.get("pressure2",    [])

    ev: dict[str, Any] = {
        # Geral
        "as_of":              as_of.isoformat(),
        "latest_ts":          ctx.latest_ts.isoformat() if ctx.latest_ts else None,
        "is_stale":           is_stale,
        "baseline_ready":     baseline_ready,
        "in_learning":        in_learning,
        "behavior_last_computed": (
            ctx.behavior_last_computed.isoformat()
            if ctx.behavior_last_computed else None
        ),
        "level_pct_at_as_of":    _last_value(level_series),
        "pressure_at_as_of":     _last_value(press_series),
        "pressure2_at_as_of":    _last_value(press2_series),
        "flow1_lph_at_as_of":    _last_value(flow1_series),
        "flow2_lph_at_as_of":    _last_value(flow2_series),
        "points_in_series": {
            k: len(v) for k, v in ctx.series.items()
        },
        "capabilities": {
            "has_tank_pressure":        getattr(ctx.capabilities, "has_tank_pressure",        None),
            "has_street_pressure":      getattr(ctx.capabilities, "has_street_pressure",      None),
            "has_street_inlet_counter": getattr(ctx.capabilities, "has_street_inlet_counter", None),
            "has_tank_outlet_counter":  getattr(ctx.capabilities, "has_tank_outlet_counter",  None),
            "can_alert_flow":           getattr(ctx.capabilities, "can_alert_flow",           None),
            "can_alert_level":          getattr(ctx.capabilities, "can_alert_level",          None),
            "confidence":               getattr(ctx.capabilities, "confidence",               None),
        } if ctx.capabilities else {},
    }

    # Específico de queda_nivel (Fase 20)
    if rule_key == "queda_nivel" and len(level_series) >= 4:
        period_type = _current_period_type(as_of)
        drop_pph    = _compute_drop_pph_now(level_series, as_of)
        drop_abs_2h = _compute_drop_abs_2h_now(level_series, as_of)

        # Janela de 2h para contextualizar start/end
        cutoff_2h   = as_of.timestamp() - 2.0 * 3600
        window_2h   = [p for p in level_series if p.ts.timestamp() >= cutoff_2h]
        level_start = window_2h[0].value  if len(window_2h) >= 2 else None
        level_end   = window_2h[-1].value if len(window_2h) >= 2 else None
        win_start_ts = window_2h[0].ts.isoformat()  if len(window_2h) >= 2 else None
        win_end_ts   = window_2h[-1].ts.isoformat() if len(window_2h) >= 2 else None

        # Lookup de baselines tank_level
        ref_pph    = behavior_ref(ctx, "tank_level", "level_drop_pph",    period_type)
        ref_abs_2h = behavior_ref(ctx, "tank_level", "level_drop_abs_2h", period_type)

        def _baseline_summary(ref: Optional[dict]) -> Optional[dict]:
            if not ref:
                return None
            return {
                "normal_high":          ref.get("normal_high"),
                "anomaly_high":         ref.get("anomaly_high"),
                "baseline_confidence":  ref.get("confidence"),
                "profile_type":         ref.get("profile_type"),
                "sample_count":         ref.get("sample_count"),
            }

        ev.update({
            "period_type":              period_type,
            "observed_level_drop_pph":  drop_pph,
            "observed_level_drop_abs_2h": drop_abs_2h,
            "level_start_window":       level_start,
            "level_end_window":         level_end,
            "level_window_start_at":    win_start_ts,
            "level_window_end_at":      win_end_ts,
            "baseline_pph":             _baseline_summary(ref_pph),
            "baseline_abs_2h":          _baseline_summary(ref_abs_2h),
            "metric_used":              None,  # preenchido depois do simulate
        })

    # Específico de pressao_rua_baixa
    elif rule_key == "pressao_rua_baixa":
        # Contagem de pontos abaixo de threshold nas últimas 4h
        cutoff_4h = as_of.timestamp() - 4.0 * 3600
        window_press = [p for p in press_series if p.ts.timestamp() >= cutoff_4h]
        # p10 do baseline como referência (best-effort)
        ref_p10: Optional[float] = None
        bl = ctx.baselines.get("pressure")
        if bl:
            ref_p10 = bl.get("p10")
        threshold = ref_p10 if ref_p10 else 5.0
        points_below = sum(1 for p in window_press if p.value < threshold)

        ev.update({
            "points_below_threshold": points_below,
            "window_start_at": window_press[0].ts.isoformat() if window_press else None,
            "window_end_at":   window_press[-1].ts.isoformat() if window_press else None,
            "ref_p10_mca":     ref_p10,
        })

    # Específico de alertas comportamentais de vazão
    elif rule_key in (
        "consumo_acima_media", "vazamento_pos_caixa",
        "vazao_noturna", "consumo_sem_repouso", "pico_consumo",
    ):
        period_type = _current_period_type(as_of)
        ev.update({
            "period_type":           period_type,
            "metric_used":           None,   # preenchido depois do simulate
            "observed_value":        None,
            "normal_high":           None,
            "anomaly_high":          None,
            "excess_over_normal":    None,
            "excess_over_anomaly":   None,
            "baseline_confidence":   None,
        })

    return ev


# ---------------------------------------------------------------------------
# Bloco original
# ---------------------------------------------------------------------------

def build_original_block(event: Any) -> dict[str, Any]:
    """Normaliza a linha de alert_events em dict serializável."""
    return {
        "event_id":                  event.id,
        "slug":                      event.slug,
        "installation_id":           event.installation_id,
        "rule_key":                  event.rule_key,
        "status":                    event.status,
        "alert_type":                event.alert_type,
        "original_severity":         event.severity,
        "triggered_at":              event.triggered_at.isoformat(),
        "resolved_at":               event.resolved_at.isoformat() if event.resolved_at else None,
        "original_current_value":    float(event.current_value) if event.current_value is not None else None,
        "original_dados_relevantes": event.dados_relevantes,
        "titulo":                    event.titulo,
        "mensagem_usuario":          event.mensagem_usuario,
        "recomendacao":              event.recomendacao,
        "message":                   event.message,
    }


# simulate importado de app.services.alert_simulation_service como simulate_point

# ---------------------------------------------------------------------------
# Bloco simulado
# ---------------------------------------------------------------------------

def build_simulated_block(
    results: list[DetectorResult], rule_key: str
) -> Optional[dict[str, Any]]:
    """
    Extrai o DetectorResult que corresponde a rule_key.
    Retorna None se a regra não existe no motor atual.
    """
    match = next((r for r in results if r.rule_key == rule_key), None)
    if match is None:
        return None

    dr = match.dados_relevantes or {}
    return {
        "simulated_active":           match.is_active,
        "simulated_severity":         match.severity,
        "simulated_reason":           match.reason,
        "simulated_current_value":    match.current_value,
        "simulated_titulo":           match.titulo,
        "simulated_mensagem_usuario": match.mensagem_usuario,
        "simulated_recomendacao":     match.recomendacao,
        "simulated_dados_relevantes": dr,
        "simulated_metric_used":             dr.get("metric_used"),
        "simulated_observed_value":          dr.get("observed_value"),
        "simulated_normal_high":             dr.get("normal_high"),
        "simulated_anomaly_high":            dr.get("anomaly_high"),
        "simulated_severity_reason":         dr.get("severity_reason"),
        "simulated_excess_over_normal":      dr.get("excess_over_normal"),
        "simulated_excess_over_anomaly":     dr.get("excess_over_anomaly"),
        "simulated_period_type":             dr.get("period_type"),
        "simulated_baseline_confidence":     dr.get("baseline_confidence"),
        "simulated_composite_evidence":      bool(dr.get("composite_evidence", False)),
        "simulated_composite_evidence_factors": dr.get("composite_evidence_factors", []),
    }


# ---------------------------------------------------------------------------
# Classificação de comparação
# ---------------------------------------------------------------------------

def _rank(severity: Optional[str]) -> int:
    return _SEV_ORDER.get(severity or "", -1)


def _severity_detail_reason(simulated: Optional[dict]) -> str:
    """Frase humana baseada no severity_reason do resultado simulado."""
    if not simulated:
        return "sem resultado simulado"
    sr = simulated.get("simulated_severity_reason") or ""
    if sr == "within_normal_profile":
        return "queda dentro da baseline comportamental da instalacao"
    if sr in ("incomplete_baseline", "no_behavior_baseline",
               "no_tank_level_behavior_baseline"):
        return "sem baseline comportamental aplicavel; motor antigo usava threshold fixo"
    if "capped_below_critico" in sr:
        return "rebaixado para 'alto' por politica da Fase 20 (critico e responsabilidade de nivel_baixo)"
    if sr in ("capped_low", "capped_medium"):
        return "rebaixado pelo cap de confidence da baseline"
    if sr == "peak_capped_moderate":
        return "rebaixado por politica de pico_consumo sem evidencia composta forte"
    if sr:
        return sr
    # sem severity_reason: motivo genérico
    if simulated.get("simulated_active") is False:
        return "motor atual nao ativou o detector neste instante"
    return "comparacao inconclusiva"


def classify_comparison(
    original: dict[str, Any],
    simulated: Optional[dict[str, Any]],
    as_of_mode_used: str,
    is_stale: bool,
    has_data: bool,
) -> dict[str, str]:
    """
    Classifica a comparação entre evento original e simulação.

    Retorna {"category": <str>, "comparison_reason": <str>}.
    """
    orig_sev    = original.get("original_severity")
    orig_status = original.get("status")

    # 1. Regra não existe no motor atual
    if simulated is None:
        return {
            "category": "rule_not_in_current_engine",
            "comparison_reason": "regra nao existe no motor atual",
        }

    sim_active = simulated.get("simulated_active", False)
    sim_sev    = simulated.get("simulated_severity")

    # 2. Dados insuficientes
    if not has_data:
        return {
            "category": "inconclusive",
            "comparison_reason": "nao havia dados suficientes no as_of para reconstruir a decisao",
        }

    # 3. REGRA DURA: as_of=resolved_at + simulado inativo → resolved_or_inactive
    if as_of_mode_used == "resolved_at" and not sim_active:
        return {
            "category": "resolved_or_inactive",
            "comparison_reason": (
                "as_of=resolved_at: motor atual tambem ve condicao inativa neste instante "
                "(esperado para evento ja resolvido)"
            ),
        }

    # 4. Original resolvido + simulado inativo
    if orig_status == "resolvido" and not sim_active:
        return {
            "category": "resolved_or_inactive",
            "comparison_reason": "ambos consideram inativo no as_of",
        }

    # 5. Simulado inativo + original ativo + mode=triggered_at → suprimido
    if not sim_active and orig_status == "ativo" and as_of_mode_used == "triggered_at":
        return {
            "category": "suppressed_by_new_logic",
            "comparison_reason": _severity_detail_reason(simulated),
        }

    # 6. Simulado inativo (modo auto com triggered_at) + original ativo
    if not sim_active and orig_status == "ativo":
        return {
            "category": "suppressed_by_new_logic",
            "comparison_reason": _severity_detail_reason(simulated),
        }

    # 7. Ambos ativos — comparar severidade
    if sim_active:
        if sim_sev == orig_sev:
            return {
                "category": "same",
                "comparison_reason": "regra atual confirmou a mesma severidade",
            }
        if _rank(sim_sev) < _rank(orig_sev):
            return {
                "category": "severity_reduced",
                "comparison_reason": _severity_detail_reason(simulated),
            }
        if _rank(sim_sev) > _rank(orig_sev):
            return {
                "category": "severity_increased",
                "comparison_reason": "motor atual classificou em severidade superior",
            }

    # 8. Original sem severidade + simulado ativo
    if orig_sev is None and sim_active:
        return {
            "category": "new_alert",
            "comparison_reason": "motor atual gera alerta onde o original nao tinha severidade",
        }

    return {
        "category": "inconclusive",
        "comparison_reason": "comparacao inconclusiva",
    }


# ---------------------------------------------------------------------------
# Saída tabular
# ---------------------------------------------------------------------------

_COL_WIDTHS = {
    "slug":       16,
    "as_of":      19,
    "rule_key":   20,
    "status":     11,
    "orig_sev":    9,
    "sim_active": 10,
    "sim_sev":     8,
    "metric":     18,
    "observed":    8,
    "normal":      6,
    "anomaly":     7,
    "comparison": 23,
    "reason":     42,
}


def _trunc(s: str, width: int) -> str:
    if len(s) <= width:
        return s.ljust(width)
    return s[: width - 1] + "…"


def _fmt_num(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.1f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(v)


def emit_table(
    rows: list[dict[str, Any]],
    summary: dict[str, int],
    limitations: list[str],
    ro_confirmed: str,
) -> None:
    w = _COL_WIDTHS
    sep = (
        "-" * w["slug"] + "+"
        + "-" * w["as_of"] + "+"
        + "-" * w["rule_key"] + "+"
        + "-" * w["status"] + "+"
        + "-" * w["orig_sev"] + "+"
        + "-" * w["sim_active"] + "+"
        + "-" * w["sim_sev"] + "+"
        + "-" * w["metric"] + "+"
        + "-" * w["observed"] + "+"
        + "-" * w["normal"] + "+"
        + "-" * w["anomaly"] + "+"
        + "-" * w["comparison"] + "+"
        + "-" * w["reason"]
    )
    header = (
        _trunc("slug",        w["slug"])      + "|"
        + _trunc("as_of(UTC)", w["as_of"])    + "|"
        + _trunc("rule_key",  w["rule_key"])  + "|"
        + _trunc("orig_stat", w["status"])    + "|"
        + _trunc("orig_sev",  w["orig_sev"])  + "|"
        + _trunc("sim_active",w["sim_active"])+ "|"
        + _trunc("sim_sev",   w["sim_sev"])   + "|"
        + _trunc("metric_used",w["metric"])   + "|"
        + _trunc("observed",  w["observed"])  + "|"
        + _trunc("normal",    w["normal"])    + "|"
        + _trunc("anomaly",   w["anomaly"])   + "|"
        + _trunc("comparison",w["comparison"])+ "|"
        + "reason"
    )
    print(header)
    print(sep)

    for r in rows:
        orig   = r.get("original", {})
        sim    = r.get("simulated") or {}
        comp   = r.get("comparison", {})
        as_of_str = r.get("as_of", "")
        if as_of_str:
            try:
                dt = datetime.fromisoformat(as_of_str)
                as_of_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        metric_used = (
            sim.get("simulated_metric_used")
            or r.get("real_evidence", {}).get("metric_used")
            or "—"
        )
        line = (
            _trunc(orig.get("slug", ""),           w["slug"])       + "|"
            + _trunc(as_of_str,                    w["as_of"])      + "|"
            + _trunc(orig.get("rule_key", ""),     w["rule_key"])   + "|"
            + _trunc(orig.get("status", ""),       w["status"])     + "|"
            + _trunc(orig.get("original_severity") or "—", w["orig_sev"]) + "|"
            + _trunc(str(sim.get("simulated_active", "—")), w["sim_active"]) + "|"
            + _trunc(sim.get("simulated_severity") or "—", w["sim_sev"]) + "|"
            + _trunc(str(metric_used),             w["metric"])     + "|"
            + _trunc(_fmt_num(sim.get("simulated_observed_value")), w["observed"]) + "|"
            + _trunc(_fmt_num(sim.get("simulated_normal_high")),    w["normal"])   + "|"
            + _trunc(_fmt_num(sim.get("simulated_anomaly_high")),   w["anomaly"])  + "|"
            + _trunc(comp.get("category", "—"),    w["comparison"]) + "|"
            + (comp.get("comparison_reason") or "—")
        )
        print(line)

    print()
    print("─── Resumo por categoria " + "─" * 26)
    categories = [
        "same", "suppressed_by_new_logic", "severity_reduced",
        "severity_increased", "new_alert", "resolved_or_inactive",
        "rule_not_in_current_engine", "inconclusive",
    ]
    total = sum(summary.values())
    for cat in categories:
        n = summary.get(cat, 0)
        print(f"  {cat:<28}: {n}")
    print(f"{'TOTAL':<30}: {total}")

    print()
    print("─── Limitacoes " + "─" * 36)
    for i, lim in enumerate(limitations, 1):
        print(f"  {i}. {lim}")

    print()
    print("─── Confirmacao " + "─" * 35)
    print(f"  read_only_transaction = {ro_confirmed}")
    print(f"  rows_written          = 0")
    print(f"  nothing_written_to_db = True")


# ---------------------------------------------------------------------------
# Saída JSON
# ---------------------------------------------------------------------------

def emit_json(
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
    summary: dict[str, int],
    limitations: list[str],
    ro_confirmed: str,
) -> None:
    payload = {
        "meta": meta,
        "limitations": limitations,
        "summary": {
            "total": sum(summary.values()),
            "by_category": summary,
        },
        "results": rows,
        "read_only_confirmation": {
            "transaction_read_only": ro_confirmed,
            "rows_written": 0,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m app.tools.backtest_alerts",
        description=(
            "Backtest retrospectivo de alertas historicos (100%% read-only). "
            "Replica cada evento de alert_events contra o motor atual e classifica "
            "se seria gerado, suprimido ou alterado em severidade."
        ),
    )
    p.add_argument(
        "--from", dest="from_dt", required=True,
        metavar="DATETIME",
        help="Inicio da janela (ISO 8601 com timezone, filtra triggered_at). "
             "Exemplo: 2026-06-07T00:00:00+00:00",
    )
    p.add_argument(
        "--to", dest="to_dt", required=True,
        metavar="DATETIME",
        help="Fim da janela (ISO 8601 com timezone, exclusive, filtra triggered_at).",
    )
    p.add_argument(
        "--installation", dest="installation", default=None,
        metavar="SLUG",
        help="Filtrar por installation slug (opcional).",
    )
    p.add_argument(
        "--rule", dest="rule_key", default=None,
        metavar="RULE_KEY",
        help="Filtrar por rule_key (ex.: queda_nivel).",
    )
    p.add_argument(
        "--status", dest="status", default="all",
        choices=["ativo", "resolvido", "all"],
        help="Filtrar por status do evento (default: all).",
    )
    p.add_argument(
        "--format", dest="fmt", default="table",
        choices=["table", "json"],
        help="Formato de saida (default: table).",
    )
    p.add_argument(
        "--as-of-mode", dest="as_of_mode", default="triggered_at",
        choices=["triggered_at", "resolved_at", "auto"],
        help=(
            "Como escolher o instante de simulacao por evento (default: triggered_at). "
            "triggered_at: responde 'o motor atual teria gerado este alerta no disparo?' "
            "resolved_at: usa resolved_at (cai para triggered_at se nulo). "
            "auto: resolved_at se status=resolvido E resolved_at nao nulo; senao triggered_at."
        ),
    )
    p.add_argument(
        "--log-level", dest="log_level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nivel de log (default: WARNING para nao poluir a saida).",
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(argv: list[str]) -> int:
    args = parse_args(argv)

    configure_logging(log_level=args.log_level, log_format="console")

    # Em modo JSON, redirecionar logs para stderr para não poluir o stdout
    if args.fmt == "json":
        for _handler in logging.getLogger().handlers:
            if isinstance(_handler, logging.StreamHandler):
                _handler.stream = sys.stderr

    # Validar datas
    try:
        from_dt = datetime.fromisoformat(args.from_dt)
        to_dt   = datetime.fromisoformat(args.to_dt)
    except ValueError as exc:
        print(f"Erro: data invalida — {exc}", file=sys.stderr)
        return 1

    if from_dt.tzinfo is None:
        print("Erro: --from precisa de timezone (ex.: 2026-06-07T00:00:00+00:00)", file=sys.stderr)
        return 1
    if to_dt.tzinfo is None:
        print("Erro: --to precisa de timezone.", file=sys.stderr)
        return 1
    if from_dt >= to_dt:
        print("Erro: --from deve ser anterior a --to.", file=sys.stderr)
        return 1

    # Normalizar para UTC aware
    from_dt = from_dt.astimezone(timezone.utc)
    to_dt   = to_dt.astimezone(timezone.utc)
    now     = datetime.now(timezone.utc)

    ro_confirmed = "?"
    output_rows: list[dict[str, Any]] = []
    summary: dict[str, int] = {
        "same": 0,
        "suppressed_by_new_logic": 0,
        "severity_reduced": 0,
        "severity_increased": 0,
        "new_alert": 0,
        "resolved_or_inactive": 0,
        "rule_not_in_current_engine": 0,
        "inconclusive": 0,
    }

    async with _open_readonly_session() as session:
        # Validar read-only após abertura
        ro_result = await session.execute(text("SHOW transaction_read_only"))
        ro_confirmed = ro_result.scalar() or "?"

        if ro_confirmed != "on":
            print(
                f"ERRO CRITICO: transacao nao esta em modo read-only "
                f"(transaction_read_only={ro_confirmed!r}). Abortando.",
                file=sys.stderr,
            )
            return 2

        # Fetch eventos
        event_rows = await fetch_events(
            session,
            from_dt=from_dt,
            to_dt=to_dt,
            slug=args.installation,
            rule_key=args.rule_key,
            status=args.status,
        )

        if not event_rows:
            if args.fmt == "json":
                emit_json(
                    rows=[],
                    meta={
                        "from": from_dt.isoformat(),
                        "to":   to_dt.isoformat(),
                        "filters": {
                            "installation_slug": args.installation,
                            "rule_key": args.rule_key,
                            "status": args.status,
                        },
                        "as_of_mode": args.as_of_mode,
                        "generated_at": now.isoformat(),
                        "read_only": True,
                        "events_found": 0,
                    },
                    summary=summary,
                    limitations=_LIMITATIONS,
                    ro_confirmed=ro_confirmed,
                )
            else:
                print(
                    f"Nenhum evento encontrado para os filtros fornecidos "
                    f"(janela: {from_dt} → {to_dt})."
                )
            return 0

        # Processar cada evento
        for event in event_rows:
            event_id = event.id
            as_of, mode_used = pick_as_of(event, args.as_of_mode, now)
            orig_block = build_original_block(event)
            sp_name = f"sp_ev_{event_id}"

            # ── Reconstruir contexto (usa DB) — protegido por SAVEPOINT ────────
            # Se uma query falhar, a transação fica "aborted" no Postgres.
            # ROLLBACK TO SAVEPOINT restaura o estado sem perder as outras queries.
            ctx: Any = None
            try:
                await session.execute(text(f"SAVEPOINT {sp_name}"))
                ctx, baseline_ready, is_stale, in_learning = await build_context_as_of(
                    session,
                    inst_id=event.installation_id,
                    slug=event.slug,
                    as_of=as_of,
                )
                await session.execute(text(f"RELEASE SAVEPOINT {sp_name}"))
            except Exception as exc:
                logger.warning(
                    "backtest.context_error",
                    event_id=event_id, rule_key=event.rule_key, error=str(exc),
                )
                # Recuperar transação via savepoint
                try:
                    await session.execute(text(f"ROLLBACK TO SAVEPOINT {sp_name}"))
                    await session.execute(text(f"RELEASE SAVEPOINT {sp_name}"))
                except Exception as sp_exc:
                    logger.error(
                        "backtest.savepoint_rollback_failed",
                        event_id=event_id, error=str(sp_exc),
                    )
                comp = {
                    "category": "inconclusive",
                    "comparison_reason": f"erro ao reconstruir contexto: {exc}",
                }
                summary["inconclusive"] += 1
                output_rows.append({
                    "as_of":           as_of.isoformat(),
                    "as_of_mode_used": mode_used,
                    "original":        orig_block,
                    "real_evidence":   {"error": str(exc)},
                    "simulated":       None,
                    "comparison":      comp,
                })
                continue

            # ── Processamento em memória (sem DB) ───────────────────────────────
            has_data = ctx.latest_ts is not None and bool(ctx.series)
            real_ev = collect_real_evidence(
                ctx, event.rule_key, as_of,
                baseline_ready, is_stale, in_learning,
            )
            sim_results = simulate(ctx, as_of, baseline_ready, is_stale, in_learning)
            sim_block   = build_simulated_block(sim_results, event.rule_key)

            # Complementar evidência com metric_used do simulado
            if sim_block and sim_block.get("simulated_metric_used"):
                if "metric_used" in real_ev:
                    real_ev["metric_used"] = sim_block["simulated_metric_used"]

            comp = classify_comparison(
                orig_block, sim_block, mode_used, is_stale, has_data,
            )
            cat = comp.get("category", "inconclusive")
            summary[cat] = summary.get(cat, 0) + 1

            output_rows.append({
                "as_of":           as_of.isoformat(),
                "as_of_mode_used": mode_used,
                "original":        orig_block,
                "real_evidence":   real_ev,
                "simulated":       sim_block,
                "comparison":      comp,
            })

        # --- fim do loop ---

    # Emitir saída (fora da sessão, que já foi fechada com rollback)
    meta = {
        "from": from_dt.isoformat(),
        "to":   to_dt.isoformat(),
        "filters": {
            "installation_slug": args.installation,
            "rule_key":          args.rule_key,
            "status":            args.status,
        },
        "as_of_mode":   args.as_of_mode,
        "generated_at": now.isoformat(),
        "read_only":    True,
        "events_found": len(output_rows),
    }

    if args.fmt == "json":
        emit_json(
            rows=output_rows,
            meta=meta,
            summary=summary,
            limitations=_LIMITATIONS,
            ro_confirmed=ro_confirmed,
        )
    else:
        # Aviso para modos que usam resolved_at
        resolved_at_count = sum(
            1 for r in output_rows if r.get("as_of_mode_used") == "resolved_at"
        )
        if resolved_at_count > 0:
            print(
                f"AVISO: {resolved_at_count} evento(s) simulados em resolved_at. "
                "A comparacao nesse instante reflete o fim do evento, nao a geracao.\n"
            )

        emit_table(
            rows=output_rows,
            summary=summary,
            limitations=_LIMITATIONS,
            ro_confirmed=ro_confirmed,
        )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
