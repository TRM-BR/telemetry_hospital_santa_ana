"""
app/config.py — Configuração da aplicação telemetry.

Fontes (em ordem de prioridade crescente):
  1. Defaults codificados aqui.
  2. clients/<slug>.yaml — config não-secreta por prefeitura.
  3. Variáveis de ambiente TELEMETRY_* — segredos e overrides de deploy.

Uso:
    from app.config import get_settings
    settings = get_settings()
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    """Sobe a árvore de diretórios até encontrar CLAUDE.md (raiz do repo)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "CLAUDE.md").exists():
            return parent
    # Fallback: em Docker o path é mais curto; usa o mais alto disponível
    parents = list(here.parents)
    return parents[min(3, len(parents) - 1)]


def _load_client_yaml(slug: str) -> dict:
    """Carrega clients/<slug>.yaml relativo à raiz do app/repo."""
    here = Path(__file__).resolve()

    candidates = [
        # Layout Docker: /app/app/config.py -> /app/clients/<slug>.yaml
        here.parents[1] / "clients" / f"{slug}.yaml",
        # Fallback para execuções locais a partir da raiz do projeto/backend
        Path.cwd() / "clients" / f"{slug}.yaml",
        Path.cwd() / "backend" / "clients" / f"{slug}.yaml",
    ]

    for candidate in candidates:
        if candidate.exists():
            with candidate.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}

    return {}


class Settings(BaseSettings):
    """
    Configuração consolidada. Segredos vêm de variáveis de ambiente
    (TELEMETRY_*). Valores não-secretos vêm do client YAML ou defaults.
    """

    model_config = SettingsConfigDict(
        env_prefix="TELEMETRY_",
        env_file=None,        # carregado manualmente via load_settings_from_env_file
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Identificação ────────────────────────────────────────────────────────
    client_slug: str = Field("santana_parnaiba", description="Slug do cliente (ex.: santana_parnaiba)")
    environment: str = Field("dev", description="Ambiente: dev | hml | prod")

    # ── PostgreSQL ───────────────────────────────────────────────────────────
    db_host: str = Field("localhost")
    db_port: int = Field(5432)
    db_name: str = Field("telemetry_santana_parnaiba_dev")
    db_user: str = Field("telemetry_app")
    db_password: str = Field("changeme")
    db_pool_size: int = Field(5)
    db_pool_max_overflow: int = Field(2)

    # ── MQTT ─────────────────────────────────────────────────────────────────
    mqtt_host: str = Field("localhost")
    mqtt_port: int = Field(1883)
    mqtt_tls: bool = Field(False)
    mqtt_ca_cert_path: Optional[str] = Field(None)
    mqtt_username: str = Field("telemetry_bridge")
    mqtt_password: str = Field("changeme")
    mqtt_client_id: str = Field("telemetry-bridge-santana_parnaiba")
    mqtt_keepalive: int = Field(30)
    mqtt_topic_prefix: str = Field("SN50_analog/data")  # fallback se telemetry_topics ausente

    # ── MQTT analógico — tópicos e templates (SN50_analog / DTN-200-FPS0) ────
    # telemetry_topics: lista de tópicos que a bridge ASSINA (telemetria).
    # command_topic_template: template para PUBLICAR comandos (outbound; nunca assinado).
    telemetry_topics: list[str] = Field(
        default_factory=lambda: ["SN50_analog/data"],
        description="Tópicos MQTT que a bridge assina para telemetria.",
    )
    command_topic_template: str = Field(
        "SN50_analog/{imei}/CMD",
        description="Template para publicar comandos outbound. Nunca assinado.",
    )

    # ── Workers ──────────────────────────────────────────────────────────────
    worker_batch_size: int = Field(50)
    worker_idle_seconds: int = Field(5)
    worker_stuck_threshold_seconds: int = Field(300)
    worker_max_attempts: int = Field(5)
    worker_alert_interval_seconds: int = Field(30)  # alert_worker re-avalia a cada N segundos

    # ── Física do sensor (constantes de campo) ───────────────────────────────
    level_max_m: float = Field(
        4.0,
        description=(
            "Escala máxima do sensor em metros (20 mA = level_max_m). "
            "Fonte real: analog_profiles[model].level_max_m no YAML do cliente. "
            "Este campo é fallback global — não é lido diretamente pelo derive_worker."
        ),
    )
    flow_liter_per_pulse: float = Field(
        1.0,
        description=(
            "Litros por pulso do medidor de vazão (valor de fábrica). "
            "Override via TELEMETRY_FLOW_LITER_PER_PULSE ou clients/<slug>.yaml."
        ),
    )

    # ── Calibration worker ────────────────────────────────────────────────────
    calib_n_low: int = Field(
        50,
        description="Quantidade dos N menores valores de pressure2 para calcular ref_min_mca.",
    )
    calib_n_high: int = Field(
        50,
        description="Quantidade dos N maiores valores de pressure2 para calcular ref_max_mca.",
    )
    calib_window_days: int = Field(
        30,
        description="Janela em dias para buscar leituras históricas de pressure2.",
    )
    calib_min_span_mca: float = Field(
        0.5,
        description=(
            "Span mínimo (ref_max_mca - ref_min_mca) em MCA para aceitar o resultado. "
            "Evita calibração degenerada quando o reservatório esteve sempre cheio ou vazio."
        ),
    )
    calib_poll_seconds: float = Field(
        7200.0,
        description="Intervalo em segundos entre execuções do calibration_worker (default: 2h).",
    )
    calib_version: str = Field(
        "v1",
        description="Rótulo de versão gravado em calibrations.calc_version.",
    )

    # ── Instalação default (usada pelo seed e autodetecção) ──────────────────
    installation_slug: str = Field(
        "hospital_santa_ana",
        description="Slug da instalação principal deste tenant.",
    )
    installation_name: str = Field(
        "Hospital Santa Ana",
        description="Nome de exibição da instalação principal.",
    )

    # ── Autodetecção de devices ────────────────────────────────────────────────
    device_autodetect_enabled: bool = Field(
        True,
        description="Liga autodetecção: device criado no 1º payload válido.",
    )
    device_autodetect_attach_installation_slug: str = Field(
        "hospital_santa_ana",
        description="Instalação à qual devices autodetectados são vinculados.",
    )
    device_autodetect_default_status: str = Field(
        "auto_detected",
        description="Status inicial de devices autodetectados.",
    )
    device_autodetect_label_template: str = Field(
        "Remota {imei_suffix}",
        description="Label provisório; {imei_suffix} = últimos 4 dígitos do IMEI.",
    )

    # ── Autodetecção de devices de energia (SM-3EGW / /param_energ) ──────────
    energy_autodetect_attach_installation_slug: str = Field(
        "escola",
        description="Instalação à qual devices de energia autodetectados são vinculados.",
    )
    energy_autodetect_label_template: str = Field(
        "Medidor {external_id}",
        description="Label provisório; {external_id} = campo 'id' do payload SM-3EGW.",
    )
    energy_autodetect_model: str = Field(
        "SM-3EGW",
        description="Model gravado no device autodetectado via /param_energ.",
    )

    # ── Perfis analógicos por modelo (dict livre, lido do YAML) ─────────────
    # Estrutura: { "DTN-200-FPS0": { current_min_ma, current_max_ma, ... } }
    analog_profiles: dict[str, Any] = Field(
        default_factory=dict,
        description="Perfis de escala analógica por modelo de device.",
    )

    # ── Limiares de alerta de pressão da rua (Copasa nominal: 30 MCA) ────────
    street_pressure_moderado_mca: float = Field(
        15.0,
        description="Pressão da rua abaixo deste valor → moderado. Override via YAML/ENV.",
    )
    street_pressure_alto_mca: float = Field(
        10.0,
        description="Pressão da rua abaixo deste valor → alto.",
    )
    street_pressure_critico_mca: float = Field(
        5.0,
        description="Pressão da rua abaixo deste valor → crítico.",
    )

    # ── API ───────────────────────────────────────────────────────────────────
    api_secret_key: str = Field("changeme-use-openssl-rand-hex-32")
    api_jwt_algorithm: str = Field("HS256")
    api_access_token_expire_minutes: int = Field(480)

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Em produção, definir TELEMETRY_CORS_ORIGINS como lista de origens permitidas.
    # Ex.: TELEMETRY_CORS_ORIGINS=["https://hospital-santa-ana.trmbrasil.cloud"]
    # Em dev/hml pode-se usar ["*"] mas nunca em prod.
    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        description=(
            "Origens CORS permitidas. Em produção, especificar domínios exatos. "
            "Env: TELEMETRY_CORS_ORIGINS (JSON list)."
        ),
    )

    # ── Email / SMTP ──────────────────────────────────────────────────────────
    # Quando MAIL_HOST estiver vazio, ConsoleEmailSender é usado (dev/test).
    mail_host: str = Field("", description="Servidor SMTP. Vazio → log no console.")
    mail_port: int = Field(587)
    mail_user: str = Field("")
    mail_password: str = Field("")
    mail_from: str = Field("telemetry@example.com")
    mail_starttls: bool = Field(True)
    # TTL dos códigos OTP em minutos
    mail_otp_ttl_minutes: int = Field(15)

    # ── Telegram (alertas críticos) ───────────────────────────────────────────
    # Todas as vars ganham o prefixo TELEMETRY_ em runtime
    # (ex.: TELEMETRY_TELEGRAM_BOT_TOKEN).
    telegram_alerts_enabled: bool = Field(
        False, description="Liga/desliga toda a integração Telegram."
    )
    telegram_bot_token: str = Field(
        "", description="Token do bot (BotFather). Segredo — nunca logar."
    )
    telegram_bot_username: str = Field(
        "", description="Username do bot sem @, usado no deep link t.me/<username>."
    )
    telegram_parse_mode: str = Field("HTML", description="parse_mode do sendMessage.")
    telegram_timeout_seconds: int = Field(10, description="Timeout HTTP da Bot API.")
    telegram_max_retries: int = Field(
        5, description="Máximo de tentativas de envio por notificação (max_attempts)."
    )
    telegram_link_token_ttl_minutes: int = Field(
        15, description="Validade do token temporário de vínculo, em minutos."
    )
    telegram_worker_sleep_seconds: int = Field(
        10, description="Intervalo do telegram_notification_worker em modo contínuo."
    )
    telegram_webhook_secret: str = Field(
        "", description="Secret esperado no header X-Telegram-Bot-Api-Secret-Token."
    )
    frontend_base_url: str = Field(
        "", description="URL base do frontend (links de volta ao sistema nas mensagens)."
    )

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = Field("INFO")
    log_format: str = Field("json")  # json | console

    # ── Computed ─────────────────────────────────────────────────────────────
    @property
    def db_url_async(self) -> str:
        """URL assíncrona para asyncpg (uso em app)."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def db_url_sync(self) -> str:
        """URL síncrona para psycopg2 (uso em Alembic)."""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @model_validator(mode="after")
    def _override_from_yaml(self) -> "Settings":
        """
        Aplica overrides não-secretos do clients/<slug>.yaml.
        Variáveis de ambiente sempre ganham (já aplicadas pelo pydantic-settings).
        """
        data = _load_client_yaml(self.client_slug)
        if not data:
            return self

        db = data.get("database", {})
        mqtt = data.get("mqtt", {})
        workers = data.get("workers", {})

        # DB (sem senha — segredo fica na ENV)
        if db.get("host") and not os.getenv("TELEMETRY_DB_HOST"):
            object.__setattr__(self, "db_host", db["host"])
        if db.get("port") and not os.getenv("TELEMETRY_DB_PORT"):
            object.__setattr__(self, "db_port", int(db["port"]))
        if db.get("name") and not os.getenv("TELEMETRY_DB_NAME"):
            object.__setattr__(self, "db_name", db["name"])
        if db.get("user") and not os.getenv("TELEMETRY_DB_USER"):
            object.__setattr__(self, "db_user", db["user"])
        if db.get("pool_size") and not os.getenv("TELEMETRY_DB_POOL_SIZE"):
            object.__setattr__(self, "db_pool_size", int(db["pool_size"]))

        # MQTT (sem senha)
        if mqtt.get("host") and not os.getenv("TELEMETRY_MQTT_HOST"):
            object.__setattr__(self, "mqtt_host", mqtt["host"])
        if mqtt.get("port") and not os.getenv("TELEMETRY_MQTT_PORT"):
            object.__setattr__(self, "mqtt_port", int(mqtt["port"]))
        if "tls" in mqtt and not os.getenv("TELEMETRY_MQTT_TLS"):
            object.__setattr__(self, "mqtt_tls", bool(mqtt["tls"]))
        if mqtt.get("ca_cert_path") and not os.getenv("TELEMETRY_MQTT_CA_CERT_PATH"):
            object.__setattr__(self, "mqtt_ca_cert_path", mqtt["ca_cert_path"])
        if mqtt.get("username") and not os.getenv("TELEMETRY_MQTT_USERNAME"):
            object.__setattr__(self, "mqtt_username", mqtt["username"])
        if mqtt.get("client_id") and not os.getenv("TELEMETRY_MQTT_CLIENT_ID"):
            object.__setattr__(self, "mqtt_client_id", mqtt["client_id"])
        if mqtt.get("keepalive") and not os.getenv("TELEMETRY_MQTT_KEEPALIVE"):
            object.__setattr__(self, "mqtt_keepalive", int(mqtt["keepalive"]))
        if mqtt.get("topic_prefix") and not os.getenv("TELEMETRY_MQTT_TOPIC_PREFIX"):
            object.__setattr__(self, "mqtt_topic_prefix", mqtt["topic_prefix"])
        if mqtt.get("telemetry_topics") and not os.getenv("TELEMETRY_TELEMETRY_TOPICS"):
            topics = mqtt["telemetry_topics"]
            if isinstance(topics, list):
                object.__setattr__(self, "telemetry_topics", topics)
        if mqtt.get("command_topic_template") and not os.getenv("TELEMETRY_COMMAND_TOPIC_TEMPLATE"):
            object.__setattr__(self, "command_topic_template", str(mqtt["command_topic_template"]))

        # Workers
        if workers.get("batch_size") and not os.getenv("TELEMETRY_WORKER_BATCH_SIZE"):
            object.__setattr__(self, "worker_batch_size", int(workers["batch_size"]))
        if workers.get("idle_seconds") and not os.getenv("TELEMETRY_WORKER_IDLE_SECONDS"):
            object.__setattr__(self, "worker_idle_seconds", int(workers["idle_seconds"]))

        # Instalação principal
        inst = data.get("installation", {})
        if inst.get("slug") and not os.getenv("TELEMETRY_INSTALLATION_SLUG"):
            object.__setattr__(self, "installation_slug", str(inst["slug"]))
        if inst.get("name") and not os.getenv("TELEMETRY_INSTALLATION_NAME"):
            object.__setattr__(self, "installation_name", str(inst["name"]))

        # Autodetecção de devices
        autodetect = data.get("device_autodetect", {})
        if "enabled" in autodetect and not os.getenv("TELEMETRY_DEVICE_AUTODETECT_ENABLED"):
            object.__setattr__(self, "device_autodetect_enabled", bool(autodetect["enabled"]))
        if autodetect.get("attach_installation_slug") and not os.getenv(
            "TELEMETRY_DEVICE_AUTODETECT_ATTACH_INSTALLATION_SLUG"
        ):
            object.__setattr__(
                self,
                "device_autodetect_attach_installation_slug",
                str(autodetect["attach_installation_slug"]),
            )
        if autodetect.get("default_status") and not os.getenv("TELEMETRY_DEVICE_AUTODETECT_DEFAULT_STATUS"):
            object.__setattr__(self, "device_autodetect_default_status", str(autodetect["default_status"]))
        if autodetect.get("label_template") and not os.getenv("TELEMETRY_DEVICE_AUTODETECT_LABEL_TEMPLATE"):
            object.__setattr__(self, "device_autodetect_label_template", str(autodetect["label_template"]))

        # Autodetecção de devices de energia
        energy_autodetect = data.get("energy_autodetect", {})
        if energy_autodetect.get("attach_installation_slug") and not os.getenv(
            "TELEMETRY_ENERGY_AUTODETECT_ATTACH_INSTALLATION_SLUG"
        ):
            object.__setattr__(
                self,
                "energy_autodetect_attach_installation_slug",
                str(energy_autodetect["attach_installation_slug"]),
            )
        if energy_autodetect.get("label_template") and not os.getenv(
            "TELEMETRY_ENERGY_AUTODETECT_LABEL_TEMPLATE"
        ):
            object.__setattr__(
                self, "energy_autodetect_label_template", str(energy_autodetect["label_template"])
            )
        if energy_autodetect.get("model") and not os.getenv("TELEMETRY_ENERGY_AUTODETECT_MODEL"):
            object.__setattr__(self, "energy_autodetect_model", str(energy_autodetect["model"]))

        # Perfis analógicos por modelo
        if data.get("analog_profiles"):
            object.__setattr__(self, "analog_profiles", dict(data["analog_profiles"]))

        # Limiares de pressão da rua
        # Lê "street_pressure_moderado_mca" (novo) ou "street_pressure_attention_mca" (legado)
        ad = data.get("alert_defaults", {})
        new_mod = ad.get("street_pressure_moderado_mca") or ad.get("street_pressure_attention_mca")
        if new_mod and not os.getenv("TELEMETRY_STREET_PRESSURE_MODERADO_MCA"):
            object.__setattr__(self, "street_pressure_moderado_mca", float(new_mod))
        if "street_pressure_alto_mca" in ad and not os.getenv("TELEMETRY_STREET_PRESSURE_ALTO_MCA"):
            object.__setattr__(self, "street_pressure_alto_mca", float(ad["street_pressure_alto_mca"]))
        if "street_pressure_critico_mca" in ad and not os.getenv("TELEMETRY_STREET_PRESSURE_CRITICO_MCA"):
            object.__setattr__(self, "street_pressure_critico_mca", float(ad["street_pressure_critico_mca"]))

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Retorna a instância singleton de Settings.
    Em testes, use: get_settings.cache_clear() antes de redefinir ENVs.
    """
    return Settings()
