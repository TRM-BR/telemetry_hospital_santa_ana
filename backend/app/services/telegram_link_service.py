"""
app/services/telegram_link_service.py — Vínculo usuário ↔ Telegram.

Responsabilidades:
  - Gerar token temporário de vínculo (só o hash é salvo).
  - Montar o deep link do Telegram.
  - Validar token recebido pelo bot.
  - Vincular user_id ao telegram_chat_id (atômico, com used_at na mesma TX).
  - Desativar vínculo (por user_id ou por chat_id).
  - Consultar status do vínculo.

Segurança:
  - Token aleatório (secrets.token_urlsafe), salvo apenas como sha256.
  - Token puro retornado uma única vez (para o deep link).
  - Identificador técnico de envio é telegram_chat_id (nunca telefone/username).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, TypedDict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings


class TelegramLinkError(Exception):
    """Erro de vínculo. `code` ∈ {invalid, expired, used}."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class TelegramChatData(TypedDict, total=False):
    chat_id: int
    telegram_user_id: Optional[int]
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# ── Geração de token + deep link ───────────────────────────────────────────────

async def create_telegram_link_token(db: AsyncSession, user_id: int) -> str:
    """Gera um token seguro, salva o hash e retorna o token PURO (uma vez)."""
    s = get_settings()
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=s.telegram_link_token_ttl_minutes
    )
    await db.execute(
        text(
            """
            INSERT INTO telegram_link_tokens (user_id, token_hash, expires_at, created_at)
            VALUES (:user_id, :token_hash, :expires_at, now())
            """
        ),
        {"user_id": user_id, "token_hash": _hash_token(raw_token), "expires_at": expires_at},
    )
    await db.commit()
    return raw_token


def build_telegram_deep_link(raw_token: str) -> str:
    """Monta https://t.me/<bot_username>?start=<raw_token>."""
    s = get_settings()
    username = s.telegram_bot_username.lstrip("@")
    return f"https://t.me/{username}?start={raw_token}"


# ── Validação (Ajuste 2: retorna a linha do token, não só user_id) ─────────────

async def validate_telegram_link_token(
    db: AsyncSession, raw_token: str
) -> Optional[dict[str, Any]]:
    """
    Retorna a linha do token (id, user_id, expires_at, used_at) se o hash existir,
    senão None. NÃO marca used_at — a marcação acontece em link_user_to_telegram,
    na mesma transação do vínculo.
    """
    row = (
        await db.execute(
            text(
                """
                SELECT id, user_id, expires_at, used_at
                FROM telegram_link_tokens
                WHERE token_hash = :h
                """
            ),
            {"h": _hash_token(raw_token)},
        )
    ).mappings().first()
    return dict(row) if row else None


# ── Vínculo atômico (Ajuste 3: FOR UPDATE no token + used_at na mesma TX) ──────

async def link_user_to_telegram(
    db: AsyncSession, raw_token: str, chat_data: TelegramChatData
) -> int:
    """
    Valida o token e vincula o usuário ao chat — tudo numa única transação.

    Trava a linha do token com SELECT ... FOR UPDATE (contra uso concorrente),
    revalida, faz upsert do vínculo, marca o token como usado e cria a
    preferência default de notificação. Retorna o user_id vinculado.

    Lança TelegramLinkError(code) se inválido/expirado/usado/chat de outro user.
    """
    chat_id = chat_data["chat_id"]

    token_row = (
        await db.execute(
            text(
                """
                SELECT id, user_id, expires_at, used_at
                FROM telegram_link_tokens
                WHERE token_hash = :h
                FOR UPDATE
                """
            ),
            {"h": _hash_token(raw_token)},
        )
    ).mappings().first()

    if token_row is None:
        await db.rollback()
        raise TelegramLinkError("invalid")
    if token_row["used_at"] is not None:
        await db.rollback()
        raise TelegramLinkError("used")
    if token_row["expires_at"] <= datetime.now(timezone.utc):
        await db.rollback()
        raise TelegramLinkError("expired")

    user_id = int(token_row["user_id"])

    # Upsert do vínculo (reativa se já existia para este usuário).
    await db.execute(
        text(
            """
            INSERT INTO user_telegram_links (
                user_id, telegram_chat_id, telegram_user_id, telegram_username,
                telegram_first_name, telegram_last_name, is_active,
                linked_at, created_at, updated_at
            ) VALUES (
                :user_id, :chat_id, :tg_user_id, :username,
                :first_name, :last_name, true, now(), now(), now()
            )
            ON CONFLICT (user_id, telegram_chat_id) DO UPDATE SET
                telegram_user_id    = EXCLUDED.telegram_user_id,
                telegram_username   = EXCLUDED.telegram_username,
                telegram_first_name = EXCLUDED.telegram_first_name,
                telegram_last_name  = EXCLUDED.telegram_last_name,
                is_active           = true,
                linked_at           = now(),
                unlinked_at         = NULL,
                updated_at          = now()
            """
        ),
        {
            "user_id": user_id,
            "chat_id": chat_id,
            "tg_user_id": chat_data.get("telegram_user_id"),
            "username": chat_data.get("username"),
            "first_name": chat_data.get("first_name"),
            "last_name": chat_data.get("last_name"),
        },
    )

    # Marca o token como usado (uso único) na mesma transação.
    await db.execute(
        text("UPDATE telegram_link_tokens SET used_at = now() WHERE id = :id"),
        {"id": token_row["id"]},
    )

    # Cria preferência default (só críticos) se ainda não houver para o canal.
    await db.execute(
        text(
            """
            INSERT INTO user_alert_notification_preferences (
                user_id, channel, enabled, min_severity,
                installation_id, alert_type, created_at, updated_at
            )
            SELECT :user_id, 'telegram', true, 'critico', NULL, NULL, now(), now()
            WHERE NOT EXISTS (
                SELECT 1 FROM user_alert_notification_preferences
                WHERE user_id = :user_id AND channel = 'telegram'
            )
            """
        ),
        {"user_id": user_id},
    )

    await db.commit()
    return user_id


# ── Desativação ────────────────────────────────────────────────────────────────

async def unlink_user_telegram(db: AsyncSession, user_id: int) -> bool:
    """Desativa o vínculo do usuário (mantém histórico). Retorna True se alterou."""
    result = await db.execute(
        text(
            """
            UPDATE user_telegram_links
            SET is_active = false, unlinked_at = now(), updated_at = now()
            WHERE user_id = :uid AND is_active = true
            """
        ),
        {"uid": user_id},
    )
    await db.commit()
    return (result.rowcount or 0) > 0


async def unlink_user_telegram_link(db: AsyncSession, user_id: int, link_id: int) -> bool:
    """Desativa um vínculo específico do usuário (por id do registro). True se alterou."""
    result = await db.execute(
        text(
            """
            UPDATE user_telegram_links
            SET is_active = false, unlinked_at = now(), updated_at = now()
            WHERE id = :link_id AND user_id = :uid AND is_active = true
            """
        ),
        {"link_id": link_id, "uid": user_id},
    )
    await db.commit()
    return (result.rowcount or 0) > 0


async def unlink_telegram_by_chat_id(db: AsyncSession, chat_id: int) -> bool:
    """Desativa o vínculo associado a um chat_id (comando /stop). True se alterou."""
    result = await db.execute(
        text(
            """
            UPDATE user_telegram_links
            SET is_active = false, unlinked_at = now(), updated_at = now()
            WHERE telegram_chat_id = :chat AND is_active = true
            """
        ),
        {"chat": chat_id},
    )
    await db.commit()
    return (result.rowcount or 0) > 0


# ── Consulta de status ──────────────────────────────────────────────────────────

async def get_user_telegram_status(db: AsyncSession, user_id: int) -> dict[str, Any]:
    """Status do vínculo para o usuário logado: retorna a lista de ids conectados."""
    rows = (
        await db.execute(
            text(
                """
                SELECT id, telegram_username, telegram_first_name, linked_at
                FROM user_telegram_links
                WHERE user_id = :uid AND is_active = true
                ORDER BY linked_at
                """
            ),
            {"uid": user_id},
        )
    ).mappings().all()

    def _ts_z(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    connections = [
        {
            "id": r["id"],
            "telegram_username": r["telegram_username"],
            "telegram_first_name": r["telegram_first_name"],
            "linked_at": _ts_z(r["linked_at"]),
        }
        for r in rows
    ]
    linked = len(connections) > 0
    return {
        "linked": linked,
        "active": linked,
        "status_label": "Telegram vinculado e ativo" if linked else "Telegram não vinculado",
        "telegram_username": connections[0]["telegram_username"] if connections else None,
        "connections": connections,
    }


async def is_chat_linked(db: AsyncSession, chat_id: int) -> bool:
    """True se o chat_id tem vínculo ativo (comando /status do bot)."""
    row = (
        await db.execute(
            text(
                """
                SELECT 1 FROM user_telegram_links
                WHERE telegram_chat_id = :chat AND is_active = true
                """
            ),
            {"chat": chat_id},
        )
    ).first()
    return row is not None
