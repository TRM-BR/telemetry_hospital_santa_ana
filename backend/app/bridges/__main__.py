"""
Entrypoint da bridge MQTT.

Uso:
    # A partir da raiz do repo, com venv ativo:
    python -m app.bridges.mqtt_bridge

Ou via script de conveniência:
    cd backend && python -m app.bridges
"""
from app.config import get_settings
from app.logging import configure_logging
from app.bridges.mqtt_bridge import MQTTBridge


def main() -> None:
    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)
    MQTTBridge().run()


if __name__ == "__main__":
    main()
