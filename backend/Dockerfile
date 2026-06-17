# ── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Instala só o necessário para compilar extensões C (bcrypt, psycopg2, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
# Instala todas as dependências de produção em /install
RUN pip install --no-cache-dir --prefix=/install ".[standard]" 2>/dev/null || \
    pip install --no-cache-dir --prefix=/install .

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Runtime: libpq para psycopg2-binary, libffi para cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libffi8 \
    && rm -rf /var/lib/apt/lists/*

# Copia libs instaladas do builder
COPY --from=builder /install /usr/local

# Copia código do backend
COPY . .

# Usuário não-root
RUN useradd -m -u 1000 telemetry
USER telemetry

# Healthcheck via endpoint /api/v1/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--no-access-log"]
