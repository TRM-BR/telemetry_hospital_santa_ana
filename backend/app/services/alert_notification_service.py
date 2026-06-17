"""
app/services/alert_notification_service.py — Enfileira notificações de alerta.

Cria linhas 'pending' em alert_notifications para cada usuário elegível quando
um alerta CRÍTICO novo é criado. NÃO envia nada aqui (envio é do worker).

Usuário elegível:
  - ativo (users.is_active);
  - com Telegram vinculado e ativo (user_telegram_links.is_active);
  - com preferência Telegram habilitada (enabled);
  - apto à instalação (installation_id NULL ou igual) e ao tipo (alert_type
    NULL ou igual).

Como todos os usuários têm acesso a todas as instalações, não há filtro extra
de acesso por instalação.

O caller controla o commit (em workers, via get_session() que faz auto-commit).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.severity import is_critical_severity
from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)


async def enqueue_critical_alert_user_notifications(
    db: AsyncSession, alert_event_id: int
) -> int:
    """
    Enfileira notificações Telegram para o alerta informado.

    Retorna o número de notificações criadas (0 se não-crítico ou sem
    destinatários). Idempotente: a constraint UNIQUE evita duplicar.
    """
    event = (
        await db.execute(
            text(
                """
                SELECT installation_id, severity, alert_type
                FROM alert_events
                WHERE id = :id
                """
            ),
            {"id": alert_event_id},
        )
    ).mappings().first()

    if event is None:
        return 0
    if not is_critical_severity(event["severity"]):
        return 0

    s = get_settings()
    result = await db.execute(
        text(
            """
            INSERT INTO alert_notifications (
                alert_event_id, user_id, channel, destination_type, destination_id,
                status, attempts, max_attempts, created_at, updated_at
            )
            SELECT DISTINCT ON (l.telegram_chat_id)
                :event_id, l.user_id, 'telegram', 'user',
                l.telegram_chat_id::text, 'pending', 0, :max_attempts, now(), now()
            FROM user_telegram_links l
            JOIN users u ON u.id = l.user_id
            JOIN user_alert_notification_preferences p
                 ON p.user_id = l.user_id AND p.channel = 'telegram'
            WHERE l.is_active = true
              AND u.is_active = true
              AND p.enabled = true
              AND (p.installation_id IS NULL OR p.installation_id = :installation_id)
              AND (p.alert_type IS NULL OR p.alert_type = :alert_type)
            ORDER BY l.telegram_chat_id, l.user_id
            ON CONFLICT (alert_event_id, channel, destination_id) DO NOTHING
            """
        ),
        {
            "event_id": alert_event_id,
            "installation_id": event["installation_id"],
            "alert_type": event["alert_type"],
            "max_attempts": s.telegram_max_retries,
        },
    )
    created = result.rowcount or 0
    if created:
        logger.info(
            "alert_notification.enqueued",
            alert_event_id=alert_event_id,
            created=created,
        )
    return created
