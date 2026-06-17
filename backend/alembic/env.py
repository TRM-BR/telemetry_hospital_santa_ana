"""
alembic/env.py — Ambiente Alembic com auto-detecção de schema.

Usa psycopg2 (driver síncrono) para as migrations.
URL lida de variáveis de ambiente TELEMETRY_* para não hardcodar segredos.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Adiciona backend/ ao sys.path para importar app.* ────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── Importa modelos para que Base.metadata os inclua ─────────────────────────
from app.db.base import Base  # noqa: E402  (modelos importados internamente)

# ── Configuração do Alembic ───────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _build_url() -> str:
    """
    Monta a URL síncrona (psycopg2) a partir das variáveis de ambiente.
    Evita importar Settings completo aqui para não depender de pyyaml no CI.
    """
    host = os.getenv("TELEMETRY_DB_HOST", "localhost")
    port = os.getenv("TELEMETRY_DB_PORT", "5432")
    name = os.getenv("TELEMETRY_DB_NAME", "telemetry_barueri_dev")
    user = os.getenv("TELEMETRY_DB_USER", "telemetry_app")
    password = os.getenv("TELEMETRY_DB_PASSWORD", "changeme")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def run_migrations_offline() -> None:
    """Gera SQL sem se conectar ao banco (útil para revisão de migrations)."""
    url = _build_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Conecta ao banco e aplica as migrations."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _build_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Alembic não precisa de pool
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
