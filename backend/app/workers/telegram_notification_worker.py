"""
app/workers/telegram_notification_worker.py — Envia notificações Telegram.

Consome a fila alert_notifications (channel='telegram'). Padrão de 2 transações
adaptado: a fila já carrega as colunas de retry, então o "claim" é um LEASE via
next_retry_at (evita worker concorrente pegar a mesma linha durante o envio); o
envio acontece FORA de transação; o resultado é gravado numa TX2 curta.

Modos:
  python -m app.workers.telegram_notification_worker --once   # uma varredura
  python -m app.workers.telegram_notification_worker          # contínuo
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_session
from app.logging import get_logger
from app.services import telegram_client
from app.services.telegram_message_formatter import format_critical_alert

logger = get_logger(__name__)

# Backoff (em minutos) por número de falhas acumuladas (attempts já incrementado).
_BACKOFF_MINUTES: dict[int, int] = {1: 1, 2: 5, 3: 15, 4: 30}
# Tempo de "lease": quanto a linha fica reservada após o claim antes de poder
# ser repescada (defesa contra crash entre claim e finalização).
_LEASE_SECONDS = 120


# ── Queries ─────────────────────────────────────────────────────────────────────

_SQL_CLAIM = text(
    """
    WITH due AS (
        SELECT id FROM alert_notifications
        WHERE channel = 'telegram'
          AND status IN ('pending', 'retry')
          AND (next_retry_at IS NULL OR next_retry_at <= now())
        ORDER BY created_at
        LIMIT :batch
        FOR UPDATE SKIP LOCKED
    )
    UPDATE alert_notifications n
    SET next_retry_at = :lease_until, updated_at = now()
    FROM due
    WHERE n.id = due.id
    RETURNING n.id
    """
)

_SQL_FETCH = text(
    """
    SELECT
        n.id, n.destination_id, n.attempts, n.max_attempts,
        e.installation_id, e.severity, e.alert_type, e.titulo,
        e.mensagem_usuario, e.message, e.recomendacao, e.dados_relevantes,
        e.triggered_at,
        i.name AS installation_name,
        l.is_active AS link_active
    FROM alert_notifications n
    JOIN alert_events e ON e.id = n.alert_event_id
    LEFT JOIN installations i ON i.id = e.installation_id
    LEFT JOIN user_telegram_links l
           ON l.user_id = n.user_id
          AND l.telegram_chat_id::text = n.destination_id
    WHERE n.id = ANY(:ids)
    """
)

_SQL_SENT = text(
    """
    UPDATE alert_notifications
    SET status='sent', sent_at=now(), provider_message_id=:mid,
        last_error=NULL, next_retry_at=NULL, updated_at=now()
    WHERE id=:id
    """
)

_SQL_SKIP = text(
    """
    UPDATE alert_notifications
    SET status='skipped', next_retry_at=NULL, last_error=:err, updated_at=now()
    WHERE id=:id
    """
)

_SQL_FAIL_OR_RETRY = text(
    """
    UPDATE alert_notifications
    SET status=:status, attempts=:attempts, last_error=:err,
        next_retry_at=:next_retry_at, updated_at=now()
    WHERE id=:id
    """
)


class TelegramNotificationWorker:
    worker_name = "telegram_notification_worker"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._running = True
        self._log = logger.bind(worker=self.worker_name)

    # ── Uma varredura ─────────────────────────────────────────────────────────

    async def run_once(self) -> int:
        """Processa um lote. Retorna o número de notificações tratadas."""
        s = self._settings
        if not s.telegram_alerts_enabled:
            self._log.debug(f"{self.worker_name}.disabled")
            return 0

        now = datetime.now(timezone.utc)
        lease_until = now + timedelta(seconds=_LEASE_SECONDS)

        # TX1 — claim com lease
        async with get_session() as session:
            result = await session.execute(
                _SQL_CLAIM, {"batch": s.worker_batch_size, "lease_until": lease_until}
            )
            ids = [r[0] for r in result.fetchall()]

        if not ids:
            return 0

        # Leitura dos dados para formatar a mensagem
        async with get_session() as session:
            rows = (
                await session.execute(_SQL_FETCH, {"ids": ids})
            ).mappings().all()

        # Envio FORA de transação; coleta de resultados.
        results: list[dict] = []
        for row in rows:
            results.append(await self._send_one(row))

        # TX2 — finaliza
        async with get_session() as session:
            for res in results:
                await self._finalize_one(session, res)

        self._log.info(f"{self.worker_name}.batch_done", processed=len(results))
        return len(results)

    async def _send_one(self, row) -> dict:
        """Tenta enviar uma notificação. Retorna o desfecho (sem tocar no banco)."""
        notif_id = row["id"]

        # Vínculo desativado depois do enfileiramento → não envia.
        if not row["link_active"]:
            return {"id": notif_id, "outcome": "skipped", "error": "vínculo inativo"}

        text_html = format_critical_alert(
            installation_name=row["installation_name"],
            alert_type=row["alert_type"],
            titulo=row["titulo"],
            human_summary=row["mensagem_usuario"] or row["message"],
            recommended_action=row["recomendacao"],
            triggered_at_utc=row["triggered_at"],
            dados_relevantes=row["dados_relevantes"],
        )

        try:
            message_id = await telegram_client.send_message(
                row["destination_id"], text_html
            )
            return {"id": notif_id, "outcome": "sent", "message_id": message_id}
        except telegram_client.TelegramSendError as exc:
            return {
                "id": notif_id,
                "outcome": "error",
                "error": str(exc)[:500],
                "attempts": int(row["attempts"]),
                "max_attempts": int(row["max_attempts"]),
            }

    async def _finalize_one(self, session, res: dict) -> None:
        notif_id = res["id"]
        outcome = res["outcome"]

        if outcome == "sent":
            await session.execute(
                _SQL_SENT, {"id": notif_id, "mid": res.get("message_id")}
            )
            return

        if outcome == "skipped":
            await session.execute(
                _SQL_SKIP, {"id": notif_id, "err": res.get("error")}
            )
            return

        # outcome == "error" → retry ou failed
        new_attempts = res["attempts"] + 1
        max_attempts = res["max_attempts"]
        if new_attempts >= max_attempts:
            status = "failed"
            next_retry_at = None
        else:
            status = "retry"
            minutes = _BACKOFF_MINUTES.get(new_attempts, 30)
            next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)

        await session.execute(
            _SQL_FAIL_OR_RETRY,
            {
                "id": notif_id,
                "status": status,
                "attempts": new_attempts,
                "err": res.get("error"),
                "next_retry_at": next_retry_at,
            },
        )

    # ── Loop contínuo ───────────────────────────────────────────────────────────

    async def run(self) -> None:
        s = self._settings
        self._log.info(
            f"{self.worker_name}.starting", sleep=s.telegram_worker_sleep_seconds
        )
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._log.error(
                    f"{self.worker_name}.loop_error", error=str(exc), exc_info=True
                )
            await asyncio.sleep(s.telegram_worker_sleep_seconds)
        self._log.info(f"{self.worker_name}.stopped")

    def stop(self) -> None:
        self._running = False


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def _main(once: bool) -> None:
    from app.logging import configure_logging

    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)
    worker = TelegramNotificationWorker()
    if once:
        await worker.run_once()
    else:
        await worker.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram notification worker")
    parser.add_argument(
        "--once", action="store_true", help="Processa um lote e sai (modo teste)."
    )
    args = parser.parse_args()
    asyncio.run(_main(args.once))
