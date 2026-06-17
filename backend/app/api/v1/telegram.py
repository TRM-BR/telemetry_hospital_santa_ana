"""
/api/v1 — Integração Telegram.

Rotas autenticadas do usuário logado:
  - POST   /me/telegram/link    → gera token + deep link
  - GET    /me/telegram/status  → status do vínculo
  - DELETE /me/telegram         → desativa o vínculo

Webhook público (validado por secret header):
  - POST   /telegram/webhook    → recebe updates do bot (/start, /stop, /status)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.api.deps import CurrentUser, DbDep
from app.config import get_settings
from app.logging import get_logger
from app.schemas.telegram import TelegramLinkResponse, TelegramStatusResponse
from app.services import telegram_client
from app.services.telegram_message_formatter import format_critical_alert
from app.services.telegram_link_service import (
    TelegramLinkError,
    build_telegram_deep_link,
    create_telegram_link_token,
    get_user_telegram_status,
    is_chat_linked,
    link_user_to_telegram,
    unlink_telegram_by_chat_id,
    unlink_user_telegram,
    unlink_user_telegram_link,
)

logger = get_logger(__name__)

router = APIRouter(tags=["telegram"])


# ── Mensagens do bot (texto exato do produto) ──────────────────────────────────

MSG_LINKED = (
    "Pronto. Seu Telegram foi vinculado ao sistema de telemetria.\n\n"
    "A partir de agora, você poderá receber avisos críticos da unidade de "
    "Barueri."
)
MSG_EXPIRED = (
    "Esse link expirou.\n\n"
    "Abra o sistema de telemetria e toque novamente em “Ativar Telegram”."
)
MSG_INVALID = (
    "Não consegui validar esse link.\n\n"
    "Abra o sistema de telemetria e gere um novo acesso em “Ativar Telegram”."
)
MSG_STOPPED = (
    "Notificações do Telegram desativadas.\n\n"
    "Você pode ativar novamente pelo sistema de telemetria."
)
MSG_STATUS_LINKED = (
    "Seu Telegram está vinculado e ativo para receber alertas críticos."
)
MSG_STATUS_UNLINKED = (
    "Seu Telegram ainda não está vinculado.\n\n"
    "Abra o sistema de telemetria e toque em “Ativar Telegram”."
)


def _build_linked_example_alert() -> str:
    return format_critical_alert(
        installation_name="EXEMPLO - Secretaria de Construção",
        alert_type="consumo",
        titulo="EXEMPLO - Consumo ininterrupto",
        human_summary=(
            "Consumo ininterrupto há 3 dias. O consumo médio permaneceu "
            "alto, em torno de 50 L/h, e não zerou nem durante a madrugada."
        ),
        recommended_action=(
            "É recomendado verificar a unidade para identificar "
            "possíveis vazamentos, uso indevido ou algum ponto de consumo aberto "
            "continuamente."
        ),
        triggered_at_utc=datetime.now(timezone.utc),
        dados_relevantes={
            "Dias com consumo contínuo": "3 dias",
            "Consumo médio": "50 L/h",
            "Madrugada": "não zerou",
        },
    )


# ── Rotas do usuário logado ─────────────────────────────────────────────────────

@router.post("/me/telegram/link", response_model=TelegramLinkResponse)
async def create_telegram_link(user_payload: CurrentUser, db: DbDep):
    """Gera um token temporário e devolve o deep link do Telegram."""
    s = get_settings()
    if not s.telegram_alerts_enabled:
        raise HTTPException(status_code=503, detail="Integração Telegram desabilitada.")
    if not s.telegram_bot_username:
        raise HTTPException(status_code=503, detail="Bot do Telegram não configurado.")

    user_id = int(user_payload["sub"])
    raw_token = await create_telegram_link_token(db, user_id)
    return TelegramLinkResponse(
        status="pending",
        telegram_url=build_telegram_deep_link(raw_token),
        expires_in_minutes=s.telegram_link_token_ttl_minutes,
    )


@router.get("/me/telegram/status", response_model=TelegramStatusResponse)
async def telegram_status(user_payload: CurrentUser, db: DbDep):
    user_id = int(user_payload["sub"])
    data = await get_user_telegram_status(db, user_id)
    return TelegramStatusResponse(**data)


@router.delete("/me/telegram/{link_id}", response_model=TelegramStatusResponse)
async def disable_telegram_link(link_id: int, user_payload: CurrentUser, db: DbDep):
    """Desativa um id de Telegram específico do usuário."""
    user_id = int(user_payload["sub"])
    await unlink_user_telegram_link(db, user_id, link_id)
    data = await get_user_telegram_status(db, user_id)
    return TelegramStatusResponse(**data)


@router.delete("/me/telegram", response_model=TelegramStatusResponse)
async def disable_telegram(user_payload: CurrentUser, db: DbDep):
    """Desativa todos os ids de Telegram do usuário."""
    user_id = int(user_payload["sub"])
    await unlink_user_telegram(db, user_id)
    return TelegramStatusResponse(
        linked=False,
        active=False,
        status_label="Telegram não vinculado",
        telegram_username=None,
        connections=[],
    )


# ── Webhook público ─────────────────────────────────────────────────────────────

async def _reply(chat_id: int, text: str) -> None:
    """Envia uma resposta ao chat, sem deixar o webhook falhar por erro de envio."""
    try:
        await telegram_client.send_message(chat_id, text)
    except telegram_client.TelegramSendError as exc:
        logger.warning("telegram_webhook.reply_failed", error=str(exc))


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    db: DbDep,
    secret_header: Annotated[
        str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")
    ] = None,
):
    """
    Recebe updates do Telegram. Sempre responde 200 (salvo secret inválido),
    para o Telegram não reenviar em loop.
    """
    s = get_settings()
    if not s.telegram_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook não configurado.")
    if secret_header != s.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Secret inválido.")

    try:
        update: dict[str, Any] = await request.json()
    except Exception:
        return {"ok": True}

    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return {"ok": True}

    text_in = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None or not text_in:
        return {"ok": True}

    sender = message.get("from") or {}

    try:
        if text_in.startswith("/start"):
            parts = text_in.split(maxsplit=1)
            raw_token = parts[1].strip() if len(parts) > 1 else ""
            if not raw_token:
                await _reply(chat_id, MSG_INVALID)
                return {"ok": True}
            try:
                await link_user_to_telegram(
                    db,
                    raw_token,
                    {
                        "chat_id": chat_id,
                        "telegram_user_id": sender.get("id"),
                        "username": sender.get("username"),
                        "first_name": sender.get("first_name"),
                        "last_name": sender.get("last_name"),
                    },
                )
                await _reply(chat_id, MSG_LINKED)
                await _reply(chat_id, _build_linked_example_alert())
            except TelegramLinkError as exc:
                if exc.code == "expired":
                    await _reply(chat_id, MSG_EXPIRED)
                else:  # invalid | used
                    await _reply(chat_id, MSG_INVALID)

        elif text_in.startswith("/stop"):
            await unlink_telegram_by_chat_id(db, chat_id)
            await _reply(chat_id, MSG_STOPPED)

        elif text_in.startswith("/status"):
            linked = await is_chat_linked(db, chat_id)
            await _reply(chat_id, MSG_STATUS_LINKED if linked else MSG_STATUS_UNLINKED)

        # Outros textos: ignora silenciosamente.
    except Exception as exc:  # nunca deixa o webhook estourar p/ o Telegram
        logger.error("telegram_webhook.error", error=str(exc), exc_info=True)

    return {"ok": True}
