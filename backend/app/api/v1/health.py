"""
/api/v1/health — Endpoints de saúde do serviço e do pipeline de dados.

GET /health          — liveness básico (sem autenticação, sem DB).
GET /health/pipeline — estado do pipeline de ingestão (sem autenticação, com DB).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbDep
from app.config import get_settings

router = APIRouter()

# ---------------------------------------------------------------------------
# Thresholds operacionais do pipeline
# ---------------------------------------------------------------------------

# raw_messages mais antigas que isso sem parse → parse_worker parado
_PARSE_LAG_WARN_MIN: float = 30.0
# derived_metrics mais antigas que isso → derive_worker parado
_DERIVE_LAG_WARN_MIN: float = 4 * 60.0
# raw_messages: ausência de ingestão por mais que isso → bridge parada
_INGEST_STALE_WARN_MIN: float = 4 * 60.0
# behavior_baseline: não recalculado há mais de 26h → timer quebrado
_BEHAVIOR_STALE_WARN_H: float = 26.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_z(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _age_min(dt: datetime | None, now: datetime) -> float | None:
    if dt is None:
        return None
    return (now - dt).total_seconds() / 60.0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    """Liveness check — sem banco, sem autenticação."""
    s = get_settings()
    return {
        "ok": True,
        "service": "telemetry-api",
        "client": s.client_slug,
        "env": s.environment,
    }


@router.get("/health/pipeline")
async def pipeline_health(db: DbDep):
    """
    Estado do pipeline de ingestão e processamento.
    Sem autenticação — destinado a monitores externos (Uptime Kuma, cron, etc.).

    Verifica:
      raw_ingest       — bridge MQTT está gravando em raw_messages.
      parse_worker     — parse_worker está processando raw_messages pendentes.
      derive_worker    — derive_worker está produzindo derived_metrics.
      behavior_baseline — behavior_baseline_worker rodou nas últimas 26h.
    """
    now = datetime.now(timezone.utc)
    checks: dict[str, Any] = {}

    # ── 1. raw_ingest: última mensagem bruta recebida ─────────────────────────
    r = await db.execute(text("SELECT MAX(received_at_utc) FROM raw_messages"))
    last_raw: datetime | None = r.scalar()
    raw_age = _age_min(last_raw, now)
    checks["raw_ingest"] = {
        "ok": raw_age is not None and raw_age < _INGEST_STALE_WARN_MIN,
        "description": "Bridge MQTT gravando raw_messages",
        "last_at": _ts_z(last_raw),
        "age_minutes": round(raw_age, 1) if raw_age is not None else None,
        "threshold_minutes": _INGEST_STALE_WARN_MIN,
    }

    # ── 2. parse_worker: pendências antigas ──────────────────────────────────
    r2 = await db.execute(text("""
        SELECT COUNT(*) AS cnt,
               MIN(received_at_utc) AS oldest
        FROM raw_messages
        WHERE parse_status IN ('pending', 'temporary_error')
    """))
    row2 = r2.fetchone()
    pending_cnt = int(row2.cnt or 0)
    oldest_pending: datetime | None = row2.oldest
    oldest_age = _age_min(oldest_pending, now)
    parse_ok = pending_cnt == 0 or (oldest_age is not None and oldest_age < _PARSE_LAG_WARN_MIN)
    checks["parse_worker"] = {
        "ok": parse_ok,
        "description": "parse_worker processando raw_messages",
        "pending_count": pending_cnt,
        "oldest_pending_age_minutes": round(oldest_age, 1) if oldest_age is not None else None,
        "threshold_minutes": _PARSE_LAG_WARN_MIN,
    }

    # ── 3. derive_worker: último derived_metric produzido ────────────────────
    r3 = await db.execute(text("SELECT MAX(derived_at_utc) FROM derived_metrics"))
    last_derived: datetime | None = r3.scalar()
    derive_age = _age_min(last_derived, now)
    checks["derive_worker"] = {
        "ok": derive_age is not None and derive_age < _DERIVE_LAG_WARN_MIN,
        "description": "derive_worker produzindo derived_metrics",
        "last_at": _ts_z(last_derived),
        "age_minutes": round(derive_age, 1) if derive_age is not None else None,
        "threshold_minutes": _DERIVE_LAG_WARN_MIN,
    }

    # ── 4. behavior_baseline_worker: último recálculo ─────────────────────────
    r4 = await db.execute(
        text("SELECT MAX(computed_at) FROM installation_behavior_baselines")
    )
    last_baseline: datetime | None = r4.scalar()
    baseline_age_h = (
        (now - last_baseline).total_seconds() / 3600.0
        if last_baseline is not None else None
    )
    # None (nunca rodou) → ok=True: worker ainda não foi ativado, não é falha
    baseline_ok = last_baseline is None or (
        baseline_age_h is not None and baseline_age_h < _BEHAVIOR_STALE_WARN_H
    )
    checks["behavior_baseline_worker"] = {
        "ok": baseline_ok,
        "description": "behavior_baseline_worker recalculando baselines",
        "last_at": _ts_z(last_baseline),
        "age_hours": round(baseline_age_h, 1) if baseline_age_h is not None else None,
        "threshold_hours": _BEHAVIOR_STALE_WARN_H,
        "note": "null = worker nunca rodou (normal antes da primeira ativação)",
    }

    overall_ok = all(c["ok"] for c in checks.values())
    return {
        "ok": overall_ok,
        "generated_at": _ts_z(now),
        "checks": checks,
    }
