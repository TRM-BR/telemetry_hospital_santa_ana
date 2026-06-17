"""
app/main.py — Bootstrap da aplicação FastAPI telemetry.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1 import router as v1_router
from app.config import get_settings
from app.logging import configure_logging, get_logger

logger = get_logger(__name__)

# Rate limiter global — chave por IP remoto
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)
    logger.info("telemetry.api.starting", environment=s.environment, client=s.client_slug)
    yield
    logger.info("telemetry.api.stopped")


def create_app() -> FastAPI:
    s = get_settings()

    app = FastAPI(
        title="Telemetry API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # restringir por env em produção via nginx
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
