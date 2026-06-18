"""
Smoke test — garante que app.main importa e a app FastAPI monta.

Cobre toda a cadeia de routers (admin → alert_simulation_service → capabilities/
alert_worker), que regrediu quando capabilities.py/alert_worker.py foram
adaptados para o motor analógico. Pega ImportError de compatibilidade no CI.
"""
from __future__ import annotations


def test_import_app_main():
    import app.main  # noqa: F401

    assert app.main.app is not None


def test_create_app():
    from app.main import create_app

    app = create_app()
    assert app is not None
    # Routers montados sem erro de import na cadeia
    assert app.routes


def test_legacy_capabilities_exports():
    """capabilities.py deve continuar exportando a API legada (compat)."""
    from app.alerts.capabilities import (  # noqa: F401
        InstallationCapabilities,
        get_installation_capabilities,
    )


def test_new_device_capabilities_exports():
    """A lógica per-device permanece disponível em device_capabilities.py."""
    from app.alerts.device_capabilities import (  # noqa: F401
        DeviceCapabilities,
        get_device_capabilities,
    )
