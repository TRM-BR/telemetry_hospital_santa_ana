"""
app/workers/_runner.py — Padrão 2-TX com watchdog interno.

Toda lógica de claim/release/watchdog fica aqui.
Os workers concretos (parse, derive, alert) herdam WorkerRunner
e implementam apenas process_batch().

Padrão de 2 transações:

  TX1 (curta — claim):
    SELECT id FROM <origem>
      WHERE status IN ('pending', 'temporary_error')
        AND (last_attempt_at IS NULL OR last_attempt_at < now() - backoff)
      ORDER BY received_at_utc
      LIMIT batch_size
      FOR UPDATE SKIP LOCKED;
    UPDATE <origem>
      SET status='processing', processing_since=now(),
          worker_id=<self_id>, attempts=attempts+1;
    COMMIT;

  (processa fora de transação)

  TX2 (curta — finaliza):
    INSERT INTO <destino> ... ON CONFLICT DO NOTHING;
    UPDATE <origem>
      SET status='done', error_message=NULL, processing_since=NULL
      WHERE id=<x> AND worker_id=<self_id> AND status='processing';
    -- se rowcount=0 → watchdog já reclamou → ROLLBACK
    COMMIT;

Watchdog (dentro do próprio worker):
  SELECT id FROM <origem>
    WHERE status='processing'
      AND processing_since < now() - stuck_threshold
      AND worker_id=<self_id>;
  UPDATE ... SET status='pending', processing_since=NULL, worker_id=NULL;
"""
from __future__ import annotations

import asyncio
import socket
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.logging import get_logger

logger = get_logger(__name__)


class WorkerRunner(ABC):
    """
    Base para workers que consomem uma fila no banco.

    Subclasses implementam:
      - source_table: str — tabela de origem (ex.: 'raw_messages')
      - status_column: str — coluna de status (ex.: 'parse_status')
      - worker_name: str — nome para logging (ex.: 'parse_worker')
      - process_batch(session, ids) -> list[int] — IDs processados com sucesso
    """

    # ── Obrigatórios nas subclasses ─────────────────────────────────────────
    worker_name: str = "worker"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._worker_id = f"{self.worker_name}-{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self._running = True
        self._log = logger.bind(worker_id=self._worker_id, worker=self.worker_name)

    # ── Interface para subclasses ───────────────────────────────────────────

    @abstractmethod
    async def process_batch(
        self,
        session: AsyncSession,
        row_ids: list[int],
    ) -> list[int]:
        """
        Processa um lote de IDs já em status='processing'.

        Deve inserir os resultados na tabela destino usando
        ON CONFLICT DO NOTHING. Retorna a lista de IDs que
        foram finalizados com sucesso (para o worker atualizar
        o status para 'done').

        NÃO deve commitar — o runner cuida do commit da TX2.
        """
        ...

    @abstractmethod
    async def claim_batch(self, session: AsyncSession) -> list[int]:
        """
        TX1: faz SELECT FOR UPDATE SKIP LOCKED e marca como 'processing'.
        Retorna os IDs reclamados. Deve commitar antes de retornar.
        """
        ...

    @abstractmethod
    async def finalize_batch(
        self,
        session: AsyncSession,
        done_ids: list[int],
        error_ids: list[tuple[int, str, bool]],
    ) -> None:
        """
        TX2: atualiza status para 'done', 'temporary_error' ou 'permanent_error'.

        error_ids: lista de (id, error_message, is_permanent)
        """
        ...

    @abstractmethod
    async def reset_stuck(self, session: AsyncSession) -> int:
        """
        Watchdog: devolve para 'pending' os registros que ficaram em
        'processing' além do stuck_threshold com worker_id == self._worker_id.
        Retorna a contagem de linhas resetadas.
        """
        ...

    # ── Loop principal ──────────────────────────────────────────────────────

    async def run(self) -> None:
        """Loop principal do worker. Chame com asyncio.run()."""
        s = self._settings
        idle_sleep = s.worker_idle_seconds
        self._log.info(f"{self.worker_name}.starting", batch_size=s.worker_batch_size)

        while self._running:
            try:
                async with get_session() as session:
                    # Watchdog antes de cada ciclo
                    stuck = await self.reset_stuck(session)
                    if stuck:
                        self._log.warning(f"{self.worker_name}.stuck_reset", count=stuck)

                # TX1 — claim
                async with get_session() as session:
                    ids = await self.claim_batch(session)

                if not ids:
                    await asyncio.sleep(idle_sleep)
                    continue

                self._log.info(f"{self.worker_name}.batch_claimed", count=len(ids))

                # Processar fora de transação
                done_ids: list[int] = []
                error_ids: list[tuple[int, str, bool]] = []

                async with get_session() as session:
                    try:
                        done_ids = await self.process_batch(session, ids)
                        error_ids = [
                            (i, "not returned by process_batch", False)
                            for i in ids if i not in done_ids
                        ]
                    except Exception as exc:
                        self._log.error(
                            f"{self.worker_name}.batch_error",
                            error=str(exc),
                            exc_info=True,
                        )
                        error_ids = [(i, str(exc), False) for i in ids]
                        done_ids = []

                # TX2 — finaliza
                async with get_session() as session:
                    await self.finalize_batch(session, done_ids, error_ids)

                self._log.info(
                    f"{self.worker_name}.batch_done",
                    done=len(done_ids),
                    errors=len(error_ids),
                )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._log.error(
                    f"{self.worker_name}.loop_error",
                    error=str(exc),
                    exc_info=True,
                )
                await asyncio.sleep(idle_sleep)

        self._log.info(f"{self.worker_name}.stopped")

    def stop(self) -> None:
        self._running = False
