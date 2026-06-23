"""
app/rate_limit.py — Instância global do SlowAPI Limiter.

Importado por main.py (registra no app) e pelos routers (decorators @limiter.limit).
Módulo independente para evitar import circular main ↔ routers.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
