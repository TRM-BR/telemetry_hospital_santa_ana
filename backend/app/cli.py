"""
app/cli.py — Comandos administrativos da Telemetry API.

Uso:
    python -m app.cli create-admin --username admin --email admin@example.com
    python -m app.cli set-role --identifier admin --role approver

Comandos:
  create-admin   Cria o usuário admin inicial (bootstrap).
  set-role       Promove ou rebaixa um usuário (viewer ↔ approver, qualquer → admin).
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import func, or_, select, update

from app.db.session import get_session
from app.db.models.user import User
from app.logging import configure_logging, get_logger
from app.services.auth import hash_password, validate_password_strength

configure_logging(log_level="INFO", log_format="console")
logger = get_logger(__name__)

VALID_ROLES = ("viewer", "approver", "admin")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _find_user(session, identifier: str) -> User | None:
    result = await session.execute(
        select(User).where(
            or_(
                User.username == identifier,
                func.lower(User.email) == identifier.lower(),
            )
        )
    )
    return result.scalar_one_or_none()


def _get_password(prompt: str = "Senha: ") -> str:
    """Obtém senha do env ou via prompt seguro (getpass)."""
    password = os.environ.get("TELEMETRY_BOOTSTRAP_ADMIN_PASSWORD", "")
    if password:
        print("(usando TELEMETRY_BOOTSTRAP_ADMIN_PASSWORD)")
        return password
    password = getpass.getpass(prompt)
    confirm = getpass.getpass("Confirmar senha: ")
    if password != confirm:
        print("ERRO: As senhas não coincidem.", file=sys.stderr)
        sys.exit(1)
    return password


# ── Comando: create-admin ─────────────────────────────────────────────────────

async def _create_admin(username: str, email: str, force: bool) -> None:
    async with get_session() as session:
        existing = await _find_user(session, username)
        email_conflict = await _find_user(session, email)

        if existing and not force:
            print(f"ERRO: Usuário '{username}' já existe. Use --force para redefinir a senha.", file=sys.stderr)
            sys.exit(1)
        if email_conflict and email_conflict.username != username and not force:
            print(f"ERRO: Email '{email}' já cadastrado.", file=sys.stderr)
            sys.exit(1)

        password = _get_password("Senha do admin: ")
        try:
            validate_password_strength(password, username=username, email=email)
        except ValueError as exc:
            print(f"ERRO: Senha fraca — {exc}", file=sys.stderr)
            sys.exit(1)

        hashed = hash_password(password)

        if existing:
            await session.execute(
                update(User)
                .where(User.id == existing.id)
                .values(
                    hashed_password=hashed,
                    role="admin",
                    account_status="approved",
                    is_active=True,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            logger.info(
                "cli.create_admin.updated",
                user_id=existing.id,
                username=username,
                origin="cli",
            )
            print(f"Admin '{username}' atualizado com sucesso.")
        else:
            user = User(
                username=username,
                email=email,
                hashed_password=hashed,
                role="admin",
                account_status="approved",
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(
                "cli.create_admin.created",
                user_id=user.id,
                username=username,
                email=email,
                origin="cli",
            )
            print(f"Admin '{username}' criado com sucesso (id={user.id}).")


# ── Comando: set-role ─────────────────────────────────────────────────────────

async def _set_role(identifier: str, new_role: str) -> None:
    if new_role not in VALID_ROLES:
        print(f"ERRO: Role inválido '{new_role}'. Válidos: {', '.join(VALID_ROLES)}", file=sys.stderr)
        sys.exit(1)

    async with get_session() as session:
        user = await _find_user(session, identifier)
        if not user:
            print(f"ERRO: Usuário '{identifier}' não encontrado.", file=sys.stderr)
            sys.exit(1)

        previous_role = user.role
        if previous_role == new_role:
            print(f"Usuário '{user.username}' já tem role '{new_role}'. Nada alterado.")
            return

        await session.execute(
            update(User)
            .where(User.id == user.id)
            .values(role=new_role, updated_at=datetime.now(timezone.utc))
        )
        await session.commit()

        logger.info(
            "cli.set_role",
            user_id=user.id,
            username=user.username,
            previous_role=previous_role,
            new_role=new_role,
            timestamp=datetime.now(timezone.utc).isoformat(),
            origin="cli",
        )
        print(
            f"Role de '{user.username}' alterado: {previous_role} → {new_role}  "
            f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}]"
        )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Telemetry CLI — comandos administrativos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-admin
    p_admin = subparsers.add_parser("create-admin", help="Criar/atualizar o usuário admin inicial")
    p_admin.add_argument("--username", required=True, help="Nome de usuário do admin")
    p_admin.add_argument("--email",    required=True, help="Email do admin")
    p_admin.add_argument("--force",    action="store_true", help="Redefine a senha se já existir")

    # set-role
    p_role = subparsers.add_parser("set-role", help="Promover ou rebaixar papel de um usuário")
    p_role.add_argument("--identifier", required=True, help="Username ou email do usuário")
    p_role.add_argument("--role",       required=True, choices=VALID_ROLES, help="Novo papel")

    args = parser.parse_args()

    if args.command == "create-admin":
        asyncio.run(_create_admin(args.username, args.email, args.force))
    elif args.command == "set-role":
        asyncio.run(_set_role(args.identifier, args.role))


if __name__ == "__main__":
    main()
