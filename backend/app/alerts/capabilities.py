"""
app/alerts/capabilities.py — Capacidades hidráulicas inferidas dos dados.

O motor de alertas decide quais detectores se aplicam a uma instalação com base
nas **capacidades reais da remota, inferidas dos dados** (parsed_measurements),
e NUNCA por nome/slug. O slug só é usado para log/debug.

Capacidades inferidas (janela de 30 dias, restrita ao dispositivo corrente):
  - pressão 1 (rua)          ← pressure_raw válido
  - canal de caixa           ← pressure2_raw > 0 OU temperature2 > 0 em ≥ _MIN_VALID leituras
                               Firmware que escreve zeros perpétuos (sem sensor instalado)
                               não ativa este canal. Mod=2 (street-only) → NULL → False.
  - pressão 2 válida (caixa) ← pressure2_raw > 0 recente (_RECENT_DAYS)
  - temperatura 2 válida     ← temperature2 > 0 recente (_RECENT_DAYS)
  - contador 1 (entrada rua) ← count_pulses variou (delta > 0)
  - contador 2 (saída caixa) ← count2_pulses variou (delta > 0)

Regra-chave de canal de caixa:
  has_tank_channel é inferido pela VALIDADE das leituras de p2/t2 (não só pela
  presença estrutural das colunas). Isso garante:
  - Instalações sem sensor de caixa físico (firmware escreve 0.0) nunca geram
    alertas de caixa — has_tank_channel=False mesmo que as colunas existam.
  - Instalações mod=1 reais (caixa existe) têm has_tank_channel=True assim que
    acumulam ≥_MIN_VALID leituras com p2 ou t2 > 0.
  - troca de dispositivo mod=1→mod=2 zera o canal de caixa após _WINDOW_DAYS

  A query filtra pelo dispositivo ATUAL via JOIN com device_installations
  (valid_to IS NULL), isolando dados de dispositivos anteriores.

Escopo V1 (poucas unidades em Barueri): 1 query por instalação sob demanda, com
cache em memória + TTL. Sem batch/cache persistente/tabela nova. Organizado para
evoluir para cálculo em lote quando o número de unidades crescer.

Debug:
    python -m app.alerts.capabilities
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Parâmetros de inferência
# ---------------------------------------------------------------------------

_WINDOW_DAYS = 30          # janela histórica analisada
_MIN_VALID = 20            # leituras válidas mínimas p/ considerar um canal presente
_MIN_SAMPLES_MED = 50      # amostras p/ confiança "medium" e detecção de contador
_MIN_SAMPLES_HIGH = 200    # amostras p/ confiança "high"
_RECENT_DAYS = 7           # canal de caixa deve ter leitura válida (>0) nos últimos N dias
_CACHE_TTL_SECONDS = 6 * 3600  # 6h


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InstallationCapabilities:
    # presença bruta de canais
    has_pressure1: bool
    has_pressure2: bool              # leituras válidas recentes de pressure2 (>0, janela _RECENT_DAYS)
    has_temperature1: bool
    has_temperature2: bool           # leituras válidas recentes de temperature2 (>0, janela _RECENT_DAYS)
    has_counter1: bool
    has_counter2: bool
    has_tank_channel: bool           # canal físico de caixa no dispositivo corrente (mod=1)
                                     # True quando t2/p2 presentes nas colunas, mesmo zerados.
                                     # False para mod=2 (street-only): colunas ficam NULL.
    # papel hidráulico inferido
    has_street_pressure: bool        # pressão 1 = rua
    has_tank_pressure: bool          # canal de caixa estrutural (= has_tank_channel)
    has_street_inlet_counter: bool   # contador 1 = entrada da rua
    has_tank_outlet_counter: bool    # contador 2 = saída da caixa
    # permissões de alerta (capacidade ∧ confiança suficiente)
    can_alert_street_pressure: bool
    can_alert_tank: bool             # caixa sem pressão
    can_alert_tank_sensor: bool      # falha do sensor da caixa
    can_alert_level: bool
    can_alert_flow_inlet: bool
    can_alert_flow_outlet: bool
    # metadados
    confidence: str                  # "high" | "medium" | "low"
    sample_count: int
    evidence: dict[str, Any] = field(default_factory=dict)


# Capacidade vazia/conservadora (instalação sem dados ou incerta):
# só comunicação + técnicos básicos; nenhum alerta hidráulico complexo.
EMPTY_CAPABILITIES = InstallationCapabilities(
    has_pressure1=False, has_pressure2=False,
    has_temperature1=False, has_temperature2=False,
    has_counter1=False, has_counter2=False,
    has_tank_channel=False,
    has_street_pressure=False, has_tank_pressure=False,
    has_street_inlet_counter=False, has_tank_outlet_counter=False,
    can_alert_street_pressure=False, can_alert_tank=False,
    can_alert_tank_sensor=False, can_alert_level=False,
    can_alert_flow_inlet=False, can_alert_flow_outlet=False,
    confidence="low", sample_count=0, evidence={},
)


# ---------------------------------------------------------------------------
# Helpers de canal (usados pelos detectores)
# ---------------------------------------------------------------------------

def inlet_flow_metric(cap: InstallationCapabilities) -> Optional[str]:
    """Canal de ENTRADA da rua (contador 1)."""
    return "flow1_lph" if cap.has_street_inlet_counter else None


def outlet_flow_metric(cap: InstallationCapabilities) -> Optional[str]:
    """Canal de SAÍDA da caixa (contador 2)."""
    return "flow2_lph" if cap.has_tank_outlet_counter else None


def consumption_metric(cap: InstallationCapabilities) -> Optional[str]:
    """
    Canal de "consumo" para detectores de anomalia:
      - se há saída da caixa → flow2 (consumo após a caixa);
      - senão, se há entrada da rua → flow1 (consumo direto da rua).
    Nunca usa flow_total cegamente.
    """
    return outlet_flow_metric(cap) or inlet_flow_metric(cap)


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SQL_CAPABILITIES = text("""
    SELECT
        COUNT(*) AS sample_count,
        COUNT(*) FILTER (WHERE pm.pressure_raw  IS NOT NULL AND pm.pressure_raw  <> 0) AS p1_valid,
        COUNT(*) FILTER (WHERE pm.pressure2_raw IS NOT NULL AND pm.pressure2_raw <> 0) AS p2_valid,
        COUNT(*) FILTER (WHERE pm.temperature   IS NOT NULL AND pm.temperature   <> 0) AS t1_valid,
        COUNT(*) FILTER (WHERE pm.temperature2  IS NOT NULL AND pm.temperature2  <> 0) AS t2_valid,
        COUNT(*) FILTER (WHERE pm.temperature2 IS NOT NULL OR pm.pressure2_raw IS NOT NULL)
                                                                                  AS t2_or_p2_present,
        MAX(pm.collected_at_utc) FILTER (WHERE pm.pressure2_raw IS NOT NULL AND pm.pressure2_raw <> 0)
                                                                                  AS last_p2_at,
        MAX(pm.collected_at_utc) FILTER (WHERE pm.temperature2  IS NOT NULL AND pm.temperature2  <> 0)
                                                                                  AS last_t2_at,
        MIN(pm.count_pulses)  AS count1_min,
        MAX(pm.count_pulses)  AS count1_max,
        MIN(pm.count2_pulses) AS count2_min,
        MAX(pm.count2_pulses) AS count2_max,
        MIN(pm.collected_at_utc) AS first_sample_at,
        MAX(pm.collected_at_utc) AS last_sample_at
    FROM parsed_measurements pm
    JOIN device_installations di
      ON di.device_id        = pm.device_id
     AND di.installation_id  = pm.installation_id
     AND di.valid_to         IS NULL
    WHERE pm.installation_id = :installation_id
      AND pm.collected_at_utc >= now() - :window * INTERVAL '1 day'
""")

_SQL_ACTIVE_INSTALLATIONS = text("""
    SELECT DISTINCT
        i.id,
        i.slug,
        i.name
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


# ---------------------------------------------------------------------------
# Cache em memória (V1 — simples, com TTL)
# ---------------------------------------------------------------------------

# inst_id → (expira_em_monotonic, capabilities)
_CACHE: dict[int, tuple[float, InstallationCapabilities]] = {}


def clear_cache() -> None:
    """Limpa o cache (usado no boot / testes)."""
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Inferência
# ---------------------------------------------------------------------------

def _as_int(v: Any) -> int:
    return int(v) if v is not None else 0


def _as_float(v: Any) -> Optional[float]:
    return float(v) if v is not None else None


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def _compute_capabilities(row: Any, now_utc: datetime) -> InstallationCapabilities:
    """Deriva capacidades a partir da linha agregada da query.

    `now_utc` deve ser timezone-aware (UTC) para comparação com os timestamps
    retornados pelo banco.
    """
    sample_count = _as_int(row.sample_count)
    p1_valid = _as_int(row.p1_valid)
    p2_valid = _as_int(row.p2_valid)
    t1_valid = _as_int(row.t1_valid)
    t2_valid = _as_int(row.t2_valid)
    t2_or_p2_present = _as_int(row.t2_or_p2_present)

    last_p2_at = row.last_p2_at   # datetime (tz-aware) | None
    last_t2_at = row.last_t2_at   # datetime (tz-aware) | None

    c1_min = _as_float(row.count1_min)
    c1_max = _as_float(row.count1_max)
    c2_min = _as_float(row.count2_min)
    c2_max = _as_float(row.count2_max)
    count1_delta = (c1_max - c1_min) if (c1_min is not None and c1_max is not None) else 0.0
    count2_delta = (c2_max - c2_min) if (c2_min is not None and c2_max is not None) else 0.0

    # Confiança pela quantidade de amostras
    if sample_count >= _MIN_SAMPLES_HIGH:
        confidence = "high"
    elif sample_count >= _MIN_SAMPLES_MED:
        confidence = "medium"
    else:
        confidence = "low"
    reliable = confidence != "low"

    recent_cutoff = now_utc - timedelta(days=_RECENT_DAYS)

    # Canal de caixa: exige leituras VÁLIDAS (>0) de p2 ou t2.
    # Firmware que preenche zeros perpétuos (sem sensor instalado) → False.
    # Mod=2 (street-only): colunas ficam NULL → p2_valid=0, t2_valid=0 → False.
    has_tank_channel = (p2_valid >= _MIN_VALID or t2_valid >= _MIN_VALID)

    # Presença bruta de canais
    has_pressure1 = p1_valid >= _MIN_VALID
    # has_pressure2 / has_temperature2 exigem leituras válidas (>0) E recentes.
    # Zero não conta como "válido" — mas a existência da coluna (even zero) já
    # é capturada por has_tank_channel.
    has_pressure2 = (
        p2_valid >= _MIN_VALID
        and last_p2_at is not None
        and last_p2_at >= recent_cutoff
    )
    has_temperature1 = t1_valid >= _MIN_VALID
    has_temperature2 = (
        t2_valid >= _MIN_VALID
        and last_t2_at is not None
        and last_t2_at >= recent_cutoff
    )
    # Contador detectado por DELTA (variação), não por DISTINCT
    has_counter1 = count1_delta > 0 and sample_count >= _MIN_SAMPLES_MED
    has_counter2 = count2_delta > 0 and sample_count >= _MIN_SAMPLES_MED

    # Papel hidráulico
    has_street_pressure = has_pressure1
    # Canal de caixa: inferido por leituras VÁLIDAS (>0). Sensor falho ou
    # instalação sem caixa física → has_tank_channel=False → sem alertas de caixa.
    has_tank_pressure = has_tank_channel
    has_street_inlet_counter = has_counter1
    has_tank_outlet_counter = has_counter2

    # Permissões de alerta:
    # - can_alert_tank_sensor: basta ter canal físico (sensor pode estar falhando → zerado)
    # - can_alert_tank: canal físico + confiança (caixa existe mas pode estar vazia)
    # - can_alert_level: canal físico + leitura VÁLIDA recente (precisa de valor para estimar nível)
    can_alert_street_pressure = has_street_pressure and reliable
    can_alert_tank_sensor = has_tank_channel and reliable
    can_alert_tank = has_tank_channel and reliable
    can_alert_level = has_tank_channel and (has_pressure2 or has_temperature2) and reliable
    can_alert_flow_inlet = has_street_inlet_counter and reliable
    can_alert_flow_outlet = has_tank_outlet_counter and reliable

    evidence = {
        "p1_valid": p1_valid, "p2_valid": p2_valid,
        "t1_valid": t1_valid, "t2_valid": t2_valid,
        "t2_or_p2_present": t2_or_p2_present,
        "last_p2_at": _iso(last_p2_at), "last_t2_at": _iso(last_t2_at),
        "count1_min": c1_min, "count1_max": c1_max, "count1_delta": count1_delta,
        "count2_min": c2_min, "count2_max": c2_max, "count2_delta": count2_delta,
        "first_sample_at": _iso(row.first_sample_at),
        "last_sample_at": _iso(row.last_sample_at),
    }

    return InstallationCapabilities(
        has_pressure1=has_pressure1, has_pressure2=has_pressure2,
        has_temperature1=has_temperature1, has_temperature2=has_temperature2,
        has_counter1=has_counter1, has_counter2=has_counter2,
        has_tank_channel=has_tank_channel,
        has_street_pressure=has_street_pressure, has_tank_pressure=has_tank_pressure,
        has_street_inlet_counter=has_street_inlet_counter,
        has_tank_outlet_counter=has_tank_outlet_counter,
        can_alert_street_pressure=can_alert_street_pressure,
        can_alert_tank=can_alert_tank,
        can_alert_tank_sensor=can_alert_tank_sensor,
        can_alert_level=can_alert_level,
        can_alert_flow_inlet=can_alert_flow_inlet,
        can_alert_flow_outlet=can_alert_flow_outlet,
        confidence=confidence, sample_count=sample_count, evidence=evidence,
    )


async def get_installation_capabilities(
    installation_id: int,
    session: AsyncSession,
    slug: Optional[str] = None,
    *,
    use_cache: bool = True,
) -> InstallationCapabilities:
    """
    Retorna as capacidades inferidas de uma instalação (com cache + TTL).

    `slug` é usado apenas para log/debug — nunca para decisão.
    """
    now = time.monotonic()
    if use_cache:
        cached = _CACHE.get(installation_id)
        if cached is not None and cached[0] > now:
            return cached[1]

    result = await session.execute(
        _SQL_CAPABILITIES,
        {"installation_id": installation_id, "window": _WINDOW_DAYS},
    )
    row = result.fetchone()

    now_utc = datetime.now(timezone.utc)
    caps = _compute_capabilities(row, now_utc) if row is not None else EMPTY_CAPABILITIES

    if use_cache:
        _CACHE[installation_id] = (now + _CACHE_TTL_SECONDS, caps)

    logger.info(
        "capabilities.computed",
        installation=slug, installation_id=installation_id,
        confidence=caps.confidence, sample_count=caps.sample_count,
        has_street_pressure=caps.has_street_pressure,
        has_tank_pressure=caps.has_tank_pressure,
        has_street_inlet_counter=caps.has_street_inlet_counter,
        has_tank_outlet_counter=caps.has_tank_outlet_counter,
    )
    return caps


# ---------------------------------------------------------------------------
# Dump de debug — python -m app.alerts.capabilities
# ---------------------------------------------------------------------------

async def _dump() -> None:
    from app.config import get_settings
    from app.logging import configure_logging

    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)

    async with get_session() as session:
        insts = (await session.execute(_SQL_ACTIVE_INSTALLATIONS)).fetchall()
        if not insts:
            print("Nenhuma instalação ativa de produção encontrada.")
            return

        for inst_id, slug, name in insts:
            caps = await get_installation_capabilities(
                inst_id, session, slug=slug, use_cache=False
            )
            print("=" * 70)
            print(f"installation_id : {inst_id}")
            print(f"slug            : {slug}")
            print(f"name            : {name}")
            print(f"sample_count    : {caps.sample_count}")
            print(f"confidence      : {caps.confidence}")
            print("-- canais brutos --")
            print(f"  has_pressure1   : {caps.has_pressure1}")
            print(f"  has_pressure2   : {caps.has_pressure2}  (válido recente, >0)")
            print(f"  has_temperature1: {caps.has_temperature1}")
            print(f"  has_temperature2: {caps.has_temperature2}  (válido recente, >0)")
            print(f"  has_counter1    : {caps.has_counter1}")
            print(f"  has_counter2    : {caps.has_counter2}")
            print(f"  has_tank_channel: {caps.has_tank_channel}  (presença estrutural t2/p2)")
            print("-- papel hidráulico --")
            print(f"  has_street_pressure     : {caps.has_street_pressure}")
            print(f"  has_tank_pressure       : {caps.has_tank_pressure}")
            print(f"  has_street_inlet_counter: {caps.has_street_inlet_counter}")
            print(f"  has_tank_outlet_counter : {caps.has_tank_outlet_counter}")
            print("-- permissões de alerta --")
            print(f"  can_alert_street_pressure: {caps.can_alert_street_pressure}")
            print(f"  can_alert_tank           : {caps.can_alert_tank}")
            print(f"  can_alert_tank_sensor    : {caps.can_alert_tank_sensor}")
            print(f"  can_alert_level          : {caps.can_alert_level}")
            print(f"  can_alert_flow_inlet     : {caps.can_alert_flow_inlet}")
            print(f"  can_alert_flow_outlet    : {caps.can_alert_flow_outlet}")
            print(f"evidence        : {caps.evidence}")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(_dump())
