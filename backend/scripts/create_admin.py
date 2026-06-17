#!/usr/bin/env python3
"""
scripts/create_admin.py — Cria ou atualiza o usuário admin no banco.

Uso dentro do container:
    python scripts/create_admin.py
    python scripts/create_admin.py --username admin --password MinhaSenhaSegura --role admin

Uso direto via docker exec (do host):
    docker exec telemetry-api python scripts/create_admin.py
    docker exec telemetry-api python scripts/create_admin.py --password MinhaSenhaSegura
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

sys.path.insert(0, "/app")  # caminho dentro do container Docker

from app.config import get_settings
from app.services.auth import hash_password


async def run(username: str, password: str, role: str, email: str) -> None:
    s = get_settings()
    engine = create_async_engine(s.db_url_async, echo=False)

    async with AsyncSession(engine) as db:
        # Mostra usuários existentes
        r = await db.execute(text("SELECT id, username, role, is_active FROM users ORDER BY id"))
        existing = r.fetchall()
        if existing:
            print("Usuários existentes:")
            for row in existing:
                print(f"  id={row.id}  username={row.username!r}  role={row.role}  active={row.is_active}")
        else:
            print("Nenhum usuário na tabela.")

        hashed = hash_password(password)

        await db.execute(
            text("""
                INSERT INTO users (username, hashed_password, role, is_active, email)
                VALUES (:u, :h, :r, true, :e)
                ON CONFLICT (username) DO UPDATE
                    SET hashed_password = :h,
                        role            = :r,
                        is_active       = true,
                        email           = COALESCE(EXCLUDED.email, users.email)
            """),
            {"u": username, "h": hashed, "r": role, "e": email},
        )
        await db.commit()

    await engine.dispose()
    print(f"\nUsuário '{username}' criado/atualizado com sucesso.")
    print(f"  role     : {role}")
    print(f"  password : {password}")
    print(f"  active   : true")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria/atualiza usuário admin no banco telemetry.")
    parser.add_argument("--username", default="admin",     help="Username (default: admin)")
    parser.add_argument("--password", default="admin123",  help="Senha (default: admin123)")
    parser.add_argument("--role",     default="admin",     help="Role (default: admin)")
    parser.add_argument("--email",    default="admin@barueri.gov.br", help="Email")
    args = parser.parse_args()

    asyncio.run(run(args.username, args.password, args.role, args.email))


if __name__ == "__main__":
    main()
