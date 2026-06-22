"""Configuração nominal de reservatório por grupo hidráulico.

Cria:
  - reservoir_groups: config por grupo (instalação, capacidade, altura útil, etc.)
  - devices: colunas opcionais de override de escala do sensor + FK reservoir_group_id

Seed slug-guarded (ON CONFLICT DO NOTHING): 2 grupos de hospital_santa_ana.

ATENÇÃO: esta migration foi AUTORADA mas NÃO aplicada.
Execute `alembic upgrade head` apenas com autorização explícita.

Revision ID: 0018
Revises: 0017
"""
from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_TARGET_SLUG = "santana_parnaiba"


def _slug() -> str:
    return os.getenv("TELEMETRY_CLIENT_SLUG", "").strip() or _TARGET_SLUG


def upgrade() -> None:
    # ── Tabela reservoir_groups ───────────────────────────────────────────────
    op.create_table(
        "reservoir_groups",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "installation_id",
            sa.BigInteger(),
            sa.ForeignKey("installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("group_name", sa.Text(), nullable=True),
        sa.Column("tank_count", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("tank_capacity_l", sa.Double(), nullable=False, server_default="10000"),
        sa.Column("group_capacity_l", sa.Double(), nullable=False, server_default="40000"),
        sa.Column("hydraulically_equalized", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("height_reference_m", sa.Double(), nullable=False, server_default="1.648"),
        sa.Column("diameter_base_m", sa.Double(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("installation_id", "position", name="uq_reservoir_groups_inst_pos"),
    )

    # ── devices: override de escala do sensor + FK para grupo ────────────────
    op.add_column("devices", sa.Column("sensor_zero_ma", sa.Double(), nullable=True))
    op.add_column("devices", sa.Column("sensor_span_ma", sa.Double(), nullable=True))
    op.add_column("devices", sa.Column("sensor_full_scale_m", sa.Double(), nullable=True))
    op.add_column("devices", sa.Column("reservoir_group_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_devices_reservoir_group",
        "devices",
        "reservoir_groups",
        ["reservoir_group_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── Seed: 2 grupos de hospital_santa_ana ─────────────────────────────────
    if _slug() != _TARGET_SLUG:
        return

    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO reservoir_groups (
                installation_id, position, group_name,
                tank_count, tank_capacity_l, group_capacity_l,
                hydraulically_equalized, height_reference_m, diameter_base_m,
                created_at, updated_at
            )
            SELECT
                i.id, g.position, g.group_name,
                4, 10000.0, 40000.0,
                true, 1.648, 2.78,
                now(), now()
            FROM installations i
            CROSS JOIN (
                VALUES (0, 'Grupo 1'), (1, 'Grupo 2')
            ) AS g(position, group_name)
            WHERE i.slug = 'hospital_santa_ana'
            ON CONFLICT (installation_id, position) DO NOTHING
        """)
    )


def downgrade() -> None:
    op.drop_constraint("fk_devices_reservoir_group", "devices", type_="foreignkey")
    op.drop_column("devices", "reservoir_group_id")
    op.drop_column("devices", "sensor_full_scale_m")
    op.drop_column("devices", "sensor_span_ma")
    op.drop_column("devices", "sensor_zero_ma")
    op.drop_table("reservoir_groups")
