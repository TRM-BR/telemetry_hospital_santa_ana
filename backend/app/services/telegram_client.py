"""
app/services/telegram_client.py — Cliente mínimo da Telegram Bot API.

Responsabilidades:
  - Enviar mensagens via sendMessage (HTTP POST, chat_id, parse_mode).
  - Timeout configurável.
  - Retornar provider_message_id em sucesso.
  - Lançar TelegramSendError (tratável) em erro, com mensagem SANITIZADA.
  - NUNCA logar nem vazar o token do bot.
"""
from __future__ import annotations

from typing import Union

import httpx

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

_API_BASE = "https://api.telegram.org"


class TelegramSendError(Exception):
    """Falha ao enviar mensagem pelo Telegram (mensagem já sanitizada)."""


def _sanitize(text: str, token: str) -> str:
    """Remove o token do bot de qualquer string antes de logar/propagar."""
    if token and token in text:
        text = text.replace(token, "***")
    return text


async def send_message(
    chat_id: Union[int, str],
    text: str,
    parse_mode: str | None = None,
) -> str:
    """
    Envia uma mensagem de texto para um chat do Telegram.

    Retorna o message_id (str) em caso de sucesso.
    Lança TelegramSendError em qualquer falha — a mensagem da exceção nunca
    contém o token do bot.
    """
    s = get_settings()
    token = s.telegram_bot_token
    if not token:
        raise TelegramSendError("telegram_bot_token não configurado")

    url = f"{_API_BASE}/bot{token}/sendMessage"
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode or s.telegram_parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=s.telegram_timeout_seconds) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        # str(exc) pode conter a URL (e portanto o token) — sanitiza.
        raise TelegramSendError(_sanitize(str(exc), token)) from None

    if resp.status_code != 200:
        # body do Telegram traz {ok, error_code, description} — sem token.
        detail = _sanitize(resp.text[:300], token)
        raise TelegramSendError(f"HTTP {resp.status_code}: {detail}")

    try:
        data = resp.json()
    except ValueError:
        raise TelegramSendError("resposta inválida da Bot API") from None

    if not data.get("ok"):
        detail = _sanitize(str(data.get("description", "erro desconhecido")), token)
        raise TelegramSendError(detail)

    message_id = data.get("result", {}).get("message_id")
    return str(message_id)
