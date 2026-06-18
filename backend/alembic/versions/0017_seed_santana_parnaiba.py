"""Seed — instalação Hospital Santa Ana (Santana do Parnaíba).

Cria APENAS a instalação hospital_santa_ana.
Devices NÃO são criados aqui — nascem automaticamente quando o primeiro
payload válido chega (autodetecção no parse_worker).

Idempotente (ON CONFLICT DO NOTHING).
Slug-guarded: executa só quando client_slug == 'santana_parnaiba'.
Sem histórico de dados, sem calibrações, sem IMEIs hardcoded.

Revision ID: 0017
Revises: 0016
"""
from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# Proteção: executa seed somente no ambiente correto.
_TARGET_SLUG = "santana_parnaiba"


def _slug() -> str:
    return os.getenv("TELEMETRY_CLIENT_SLUG", "").strip() or _TARGET_SLUG


def upgrade() -> None:
    if _slug() != _TARGET_SLUG:
        # Banco não é do Hospital Santa Ana — pula seed.
        return

    conn = op.get_bind()

    # ── Instalação ────────────────────────────────────────────────────────────
    conn.execute(
        sa.text("""
            INSERT INTO installations (
                slug, name, group_name, notes, is_active, created_at, updated_at
            ) VALUES (
                'hospital_santa_ana',
                'Hospital Santa Ana',
                'Santana do Parnaíba',
                'Hospital Santa Ana - Santana do Parnaíba/SP',
                true,
                now(),
                now()
            )
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                group_name = EXCLUDED.group_name,
                notes = EXCLUDED.notes,
                is_active = EXCLUDED.is_active,
                updated_at = now()
        """)
    )


def downgrade() -> None:
    if _slug() != _TARGET_SLUG:
        return

    conn = op.get_bind()
    # Remove instalação (só se não houver devices vinculados)
    conn.execute(
        sa.text("""
            DELETE FROM installations
            WHERE slug = 'hospital_santa_ana'
              AND NOT EXISTS (
                  SELECT 1 FROM device_installations di
                  JOIN installations i ON i.id = di.installation_id
                  WHERE i.slug = 'hospital_santa_ana'
              )
        """)
    )
