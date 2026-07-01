"""Add dedup_hash to raw_messages; swap unique dedup index.

Janela curta — bridge deve estar parada antes desta migration.

Steps (atomic):
  1. ADD COLUMN dedup_hash VARCHAR(64) NULL
  2. Backfill: dedup_hash = payload_hash para todas as linhas existentes
  3. DROP INDEX uq_raw_origin_topic_hash  (dedup por payload_hash)
  4. CREATE UNIQUE INDEX uq_raw_dedup (origin, topic, dedup_hash)

Após esta migration + deploy do código novo da bridge, o dedup de energia
usa sha256(payload_raw | received_at_second), evitando descartar heartbeats
com payload idêntico. SN50 continua com dedup_hash = payload_hash (sem mudança
de comportamento).

payload_hash permanece coluna de auditoria pura — não muda.

Revision ID: 0020
Revises: 0019
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Coluna nullable — segura antes do código novo estar no ar
    op.add_column(
        "raw_messages",
        sa.Column("dedup_hash", sa.String(64), nullable=True),
    )

    # 2. Backfill: linhas existentes usam payload_hash como dedup_hash
    op.execute("UPDATE raw_messages SET dedup_hash = payload_hash WHERE dedup_hash IS NULL")

    # 3. Remove índice unique antigo (payload_hash)
    op.drop_index("uq_raw_origin_topic_hash", table_name="raw_messages")

    # 4. Novo índice unique: (origin, topic, dedup_hash)
    #    Cobre todas as linhas (backfill garante que não há NULL após esta migration).
    op.create_index(
        "uq_raw_dedup",
        "raw_messages",
        ["origin", "topic", "dedup_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_raw_dedup", table_name="raw_messages")
    op.create_index(
        "uq_raw_origin_topic_hash",
        "raw_messages",
        ["origin", "topic", "payload_hash"],
        unique=True,
    )
    op.drop_column("raw_messages", "dedup_hash")
