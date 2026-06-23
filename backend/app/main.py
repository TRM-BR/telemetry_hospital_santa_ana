"""
app/main.py — Bootstrap da aplicação FastAPI telemetry.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.logging import configure_logging, get_logger
from app.rate_limit import limiter

logger = get_logger(__name__)

_INSECURE_SECRET_PREFIXES = ("changeme", "", "secret", "placeholder", "replace")


def _validate_production_config(s) -> None:
    """Aborta o boot se configurações inseguras forem detectadas em produção."""
    if s.environment != "prod":
        return

    key = s.api_secret_key.strip().lower()
    if not key or any(key.startswith(p) for p in _INSECURE_SECRET_PREFIXES):
        raise RuntimeError(
            "ERRO DE SEGURANÇA: TELEMETRY_API_SECRET_KEY não foi configurado com um valor seguro. "
            "Gere um secret real: openssl rand -hex 32"
        )

    if s.cors_origins == ["*"]:
        raise RuntimeError(
            "ERRO DE SEGURANÇA: TELEMETRY_CORS_ORIGINS=* não é permitido em produção. "
            "Defina as origens exatas permitidas."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)
    _validate_production_config(s)
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

    # CORS — origens lidas da config (restringir em produção via TELEMETRY_CORS_ORIGINS)
    allow_credentials = s.cors_origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.v1 import router as v1_router
    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()
