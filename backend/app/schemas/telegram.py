"""
app/schemas/telegram.py — DTOs da integração Telegram.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class TelegramLinkResponse(BaseModel):
    status: str = "pending"
    telegram_url: str
    expires_in_minutes: int


class TelegramConnection(BaseModel):
    id: int
    telegram_username: Optional[str] = None
    telegram_first_name: Optional[str] = None
    linked_at: str


class TelegramStatusResponse(BaseModel):
    linked: bool
    active: bool
    status_label: str
    telegram_username: Optional[str] = None
    connections: list[TelegramConnection] = []
