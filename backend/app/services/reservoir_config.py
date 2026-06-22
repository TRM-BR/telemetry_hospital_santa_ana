"""Serviço de configuração de reservatório por instalação.

Carrega de reservoir_groups se a tabela existir; cai em DEFAULT_CFG caso contrário.
Fallback estrito: só captura UndefinedTable (SQLSTATE 42P01). Outros erros propagam.
"""
from __future__ import annotations

from typing import Optional

import sqlalchemy.exc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.processing.derivations.reservoir import ReservoirConfig

DEFAULT_CFG = ReservoirConfig(
    tank_capacity_l=10_000.0,
    tank_count=4,
    group_capacity_l=40_000.0,
    height_reference_m=1.648,
    diameter_base_m=2.78,
)


async def load_groups(db: AsyncSession, installation_id: int) -> list[dict]:
    """Carrega grupos de reservoir_groups ordenados por position.

    Retorna [] apenas se a tabela não existir (SQLSTATE 42P01).
    Qualquer outro erro de banco propaga.
    """
    try:
        rows = (await db.execute(
            text("""
                SELECT
                    id,
                    position,
                    group_name,
                    tank_count,
                    tank_capacity_l,
                    group_capacity_l,
                    height_reference_m,
                    diameter_base_m,
                    hydraulically_equalized
                FROM reservoir_groups
                WHERE installation_id = :installation_id
                ORDER BY position
            """),
            {"installation_id": installation_id},
        )).mappings().fetchall()
        return [dict(r) for r in rows]
    except sqlalchemy.exc.ProgrammingError as exc:
        cause = exc.__cause__
        if hasattr(cause, "sqlstate") and cause.sqlstate == "42P01":
            # Tabela ainda não existe — migration pendente. Usar DEFAULT_CFG.
            return []
        raise


def group_to_cfg(group: dict) -> ReservoirConfig:
    return ReservoirConfig(
        tank_capacity_l=float(group["tank_capacity_l"]),
        tank_count=int(group["tank_count"]),
        group_capacity_l=float(group["group_capacity_l"]),
        height_reference_m=float(group["height_reference_m"]),
        diameter_base_m=float(group.get("diameter_base_m") or 2.78),
    )


def resolve_device_cfg(
    reservoir_group_id: Optional[int],
    groups: list[dict],
    device_index: int,
) -> ReservoirConfig:
    """Resolve config para um device.

    Prioridade: reservoir_group_id → posição por device_index → DEFAULT_CFG.
    """
    if reservoir_group_id is not None:
        for g in groups:
            if g["id"] == reservoir_group_id:
                return group_to_cfg(g)
    if device_index < len(groups):
        return group_to_cfg(groups[device_index])
    return DEFAULT_CFG
