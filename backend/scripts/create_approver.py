"""
scripts/create_approver.py — Cria o usuário aprovador inicial.

Uso:
    python -m scripts.create_approver --email aprovador@barueri.sp.gov.br
    python -m scripts.create_approver --email ... --username aprovador --seed-dev

  --seed-dev : usa senha padrão Trocar@123 (APENAS para ambientes de dev/hml).
               Em produção, a senha será solicitada interativamente.

Idempotente: se o username já existir com role='approver', não faz nada.

ATENÇÃO: não rodar em produção sem autorização explícita.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

# Garante que o pacote app é encontrado quando rodado de backend/
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.models.user import User
from app.services.auth import hash_password, validate_password_strength


async def run(username: str, email: str, password: str) -> None:
    s = get_settings()
    engine = create_async_engine(s.db_url_async, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # type: ignore[call-overload]

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == username))
        existing = result.scalar_one_or_none()

        if existing is not None:
            if existing.role == "approver":
                print(f"[INFO] Usuário '{username}' já existe com role='approver'. Nada a fazer.")
                return
            else:
                print(
                    f"[ERRO] Usuário '{username}' já existe com role='{existing.role}'. "
                    "Altere manualmente se necessário."
                )
                sys.exit(1)

        try:
            validate_password_strength(password, username=username, email=email)
        except ValueError as exc:
            print(f"[ERRO] Senha fraca: {exc}")
            sys.exit(1)

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            role="approver",
            account_status="active",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        print(f"[OK] Usuário '{username}' criado com role='approver' e email '{email}'.")
        print("[OK] Altere a senha após o primeiro login.")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria o usuário aprovador inicial.")
    parser.add_argument("--username", default="aprovador", help="Username (default: aprovador)")
    parser.add_argument("--email", required=True, help="Email do aprovador")
    parser.add_argument(
        "--seed-dev",
        action="store_true",
        help="Usa senha padrão Trocar@123 (apenas dev/hml)",
    )
    args = parser.parse_args()

    if args.seed_dev:
        password = "Trocar@123"
        print(f"[DEV] Usando senha padrão: {password}")
    else:
        password = getpass.getpass(f"Senha para '{args.username}': ")
        confirm = getpass.getpass("Confirme a senha: ")
        if password != confirm:
            print("[ERRO] As senhas não coincidem.")
            sys.exit(1)

    asyncio.run(run(args.username, args.email, password))


if __name__ == "__main__":
    main()
