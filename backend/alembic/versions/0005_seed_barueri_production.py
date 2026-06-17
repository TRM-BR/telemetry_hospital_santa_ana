"""Seed de produção Barueri — instalações, dispositivos e vínculos.

Revision ID: 0005
Revises: 0004

Seeding:
  4 installations  (escola, parque_caixa, parque_entrada, secretaria_construcao)
  4 devices        (IMEIs confirmados do legado UNIT_IMEI_MAP)
  4 device_installations (valid_from='2020-01-01', valid_to=NULL)

Mapeamento IMEI → instalação (fonte: legado routes.py + mock/server.cjs):
  868927084624514 → escola
  868927084622450 → parque_caixa
  868927084623946 → parque_entrada
  868927084622021 → secretaria_construcao

Dispositivos de teste (NÃO vinculados a instalação):
  860631079035573  (remota_vector  — nunca em produção)
  868927084623920  (remota_2_vector — eventualmente envia dados, sem vínculo)

Backfill:
  Atualiza installation_id em parsed_measurements existentes usando os vínculos
  recém-criados (cobertura temporal: valid_from <= collected_at_utc).
"""
from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# ─── Instalações ──────────────────────────────────────────────────────────────
_INSTALLATIONS = [
    ("escola",                  "Escola Municipal"),
    ("parque_caixa",            "Parque - Caixa D'Agua"),
    ("parque_entrada",          "Parque - Entrada"),
    ("secretaria_construcao",   "Secretaria de Construcao"),
]

# ─── Dispositivos de produção ─────────────────────────────────────────────────
_DEVICES = [
    "868927084624514",  # escola
    "868927084622450",  # parque_caixa
    "868927084623946",  # parque_entrada
    "868927084622021",  # secretaria_construcao
]

# ─── Vínculos: (imei, slug) ───────────────────────────────────────────────────
_LINKS = [
    ("868927084624514", "escola"),
    ("868927084622450", "parque_caixa"),
    ("868927084623946", "parque_entrada"),
    ("868927084622021", "secretaria_construcao"),
]


def upgrade() -> None:
    # 1. Instalações (idempotente via ON CONFLICT)
    for slug, name in _INSTALLATIONS:
        op.execute(f"""
            INSERT INTO installations (slug, name, is_active, created_at)
            VALUES ('{slug}', $${name}$$, true, now())
            ON CONFLICT (slug) DO NOTHING
        """)

    # 2. Dispositivos (idempotente — parse_worker já pode tê-los auto-registrado)
    for imei in _DEVICES:
        op.execute(f"""
            INSERT INTO devices (imei, model, is_active, created_at)
            VALUES ('{imei}', 'dragino_sn50v3_nb', true, now())
            ON CONFLICT (imei) DO UPDATE
              SET model = 'dragino_sn50v3_nb'
        """)

    # 3. Vínculos device_installations
    #    Usa CTE para obter IDs sem depender de sequences específicas.
    #    ON CONFLICT no índice parcial (device_id WHERE valid_to IS NULL):
    #    se já existir vínculo ativo para esse device, mantém o existente.
    for imei, slug in _LINKS:
        op.execute(f"""
            INSERT INTO device_installations
                (device_id, installation_id, valid_from, created_at)
            SELECT
                d.id,
                i.id,
                '2020-01-01T00:00:00+00:00'::TIMESTAMPTZ,
                now()
            FROM devices d, installations i
            WHERE d.imei = '{imei}'
              AND i.slug = '{slug}'
              AND NOT EXISTS (
                SELECT 1 FROM device_installations di2
                WHERE di2.device_id = d.id AND di2.valid_to IS NULL
              )
        """)

    # 4. Backfill installation_id em parsed_measurements já existentes
    #    (parse_worker histórico gravou installation_id=NULL)
    op.execute("""
        UPDATE parsed_measurements pm
        SET installation_id = di.installation_id
        FROM device_installations di
        WHERE di.device_id = pm.device_id
          AND di.valid_from <= pm.collected_at_utc
          AND (di.valid_to IS NULL OR di.valid_to > pm.collected_at_utc)
          AND pm.installation_id IS NULL
    """)


def downgrade() -> None:
    # Remove vínculos criados aqui (somente os criados com valid_from='2020-01-01')
    op.execute("""
        DELETE FROM device_installations
        WHERE valid_from = '2020-01-01T00:00:00+00:00'
          AND device_id IN (
            SELECT id FROM devices
            WHERE imei IN (
              '868927084624514',
              '868927084622450',
              '868927084623946',
              '868927084622021'
            )
          )
    """)

    # Remove instalações (somente se não houver dados dependentes)
    slugs = ", ".join(f"'{s}'" for s, _ in _INSTALLATIONS)
    op.execute(f"""
        DELETE FROM installations WHERE slug IN ({slugs})
          AND NOT EXISTS (
            SELECT 1 FROM alert_state WHERE installation_id = installations.id
          )
    """)
