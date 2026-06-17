"""
app/workers/alert_trigger.py — Fila em memória de instalações com dados novos.

O derive_worker sinaliza quais instalações tiveram métricas gravadas.
O alert_worker drena essa fila para avaliação imediata, sem esperar o ciclo
completo — disparo event-driven dentro do mesmo processo.

Sem Redis, sem colunas novas no banco, sem migrations.
Vive apenas no processo em execução; o alert_worker normal em loop funciona
como rede de segurança se este mecanismo falhar por reinicialização.

Uso:
    # No derive_worker, após commit da TX2:
    await mark_dirty(install_id)

    # No alert_worker, no início do loop:
    dirty = await drain_dirty()
    if dirty:
        await _evaluate_installations(dirty)  # prioritário
"""
from __future__ import annotations

import asyncio

_pending: set[int] = set()
_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def mark_dirty(installation_id: int) -> None:
    """Sinaliza que a instalação tem dados novos e precisa de avaliação de alertas."""
    async with _get_lock():
        _pending.add(installation_id)


async def drain_dirty() -> frozenset[int]:
    """
    Retorna e limpa o conjunto de instalações com dados novos.
    Thread-safe via asyncio.Lock.
    """
    async with _get_lock():
        result: frozenset[int] = frozenset(_pending)
        _pending.clear()
        return result


async def pending_count() -> int:
    """Retorna quantas instalações estão aguardando avaliação."""
    async with _get_lock():
        return len(_pending)
