"""
Gate de regressão — endpoint GET /installations/{slug}/energy/dashboard.

Verifica:
  1. Slug desconhecido → 404 (sem fallback para hospital_santa_ana).
  2. SQL de resolução de instalação não contém 'hospital_santa_ana' hard-coded.
  3. Instalação existente sem devices → resposta vazia (não erro 500).
  4. Contrato de resposta: campos obrigatórios presentes.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.engine import Row

from app.api.v1.energy import EnergyDashboardResponse, get_energy_dashboard, _SQL_INSTALLATION


# ---------------------------------------------------------------------------
# Helper — mock de DbDep (AsyncSession)
# ---------------------------------------------------------------------------

def _make_db(inst_row=None, dev_row=None, lat_row=None) -> AsyncMock:
    """Cria mock de AsyncSession com respostas configuráveis."""
    db = AsyncMock()

    # mappings().first() chain para _SQL_INSTALLATION e _SQL_DEVICE
    def _mappings_first(row):
        result = MagicMock()
        result.mappings.return_value.first.return_value = row
        return result

    # fetchall() chain para _SQL_SERIES e _SQL_BARS
    def _fetchall_empty():
        result = MagicMock()
        result.fetchall.return_value = []
        return result

    # Ordem das chamadas:
    # 1. execute(_SQL_INSTALLATION) → mappings().first()
    # 2. execute(_SQL_DEVICE)       → mappings().first()
    # 3. execute(_SQL_LATEST)       → mappings().first()
    # 4. execute(_SQL_SERIES)       → fetchall()
    # 5. execute(_SQL_BARS)         → fetchall()
    calls = [
        _mappings_first(inst_row),
        _mappings_first(dev_row),
        _mappings_first(lat_row),
        _fetchall_empty(),
        _fetchall_empty(),
    ]
    db.execute = AsyncMock(side_effect=calls)
    return db


def _inst(slug: str = "escola", name: str = "Escola Teste") -> dict:
    return {"id": 1, "slug": slug, "name": name, "kind": "energy", "is_active": True}


def _dev() -> dict:
    return {"device_id": 42, "label": "Medidor", "model": "SM-3EGW", "device_status": "active"}


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

class TestNoFallback:
    """Gate crítico: endpoint NÃO faz fallback para hospital_santa_ana."""

    def test_sql_installation_query_has_no_hospital_hardcode(self):
        """SQL de resolução não contém 'hospital_santa_ana' hard-coded."""
        query_text = str(_SQL_INSTALLATION)
        assert "hospital_santa_ana" not in query_text

    @pytest.mark.asyncio
    async def test_unknown_slug_raises_404(self):
        """Slug inexistente → 404 imediato, sem tentar hospital_santa_ana."""
        db = _make_db(inst_row=None)  # nenhuma instalação encontrada

        with pytest.raises(HTTPException) as exc_info:
            await get_energy_dashboard(slug="slug_inexistente", db=db, _user={})

        assert exc_info.value.status_code == 404
        # Apenas 1 execute chamado (resolução de slug) — não tentou alternativa
        assert db.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_hospital_slug_raises_404_when_kind_mismatch_not_registered(self):
        """hospital_santa_ana sem energy_measurements → também deve dar 404
        se o slug não estiver registrado como energy."""
        db = _make_db(inst_row=None)  # hospital_santa_ana não é energy slug

        with pytest.raises(HTTPException) as exc_info:
            await get_energy_dashboard(slug="hospital_santa_ana", db=db, _user={})

        assert exc_info.value.status_code == 404


class TestEmptyInstallation:
    """Instalação encontrada, mas sem devices vinculados → resposta vazia."""

    @pytest.mark.asyncio
    async def test_no_device_returns_empty_response(self):
        db = _make_db(inst_row=_inst(), dev_row=None)

        result = await get_energy_dashboard(slug="escola", db=db, _user={}, hours=24)

        assert isinstance(result, EnergyDashboardResponse)
        assert result.installation_slug == "escola"
        assert result.online is False
        assert result.latest.active_power_total_w is None
        assert result.bars == []
        # series retorna dict com chaves mas listas vazias (sem device → sem dados)
        from app.api.v1.energy import _SERIES_COLS
        assert set(result.series.keys()) == set(_SERIES_COLS)
        assert all(v == [] for v in result.series.values())


class TestResponseContract:
    """Contrato de resposta com instalação e device presentes."""

    @pytest.mark.asyncio
    async def test_fields_present_when_no_measurements(self):
        """Sem energy_measurements ainda: resposta válida com latest vazio."""
        db = _make_db(inst_row=_inst(), dev_row=_dev(), lat_row=None)

        result = await get_energy_dashboard(slug="escola", db=db, _user={}, hours=24)

        assert result.installation_slug == "escola"
        assert result.installation_name == "Escola Teste"
        assert result.hours == 24
        assert result.last_seen_utc is None
        assert result.online is False
        assert isinstance(result.bars, list)
        assert isinstance(result.series, dict)
        # Todas as colunas de série presentes (mesmo vazias)
        from app.api.v1.energy import _SERIES_COLS
        for col in _SERIES_COLS:
            assert col in result.series

    @pytest.mark.asyncio
    async def test_hours_param_respected(self):
        db = _make_db(inst_row=_inst(), dev_row=_dev(), lat_row=None)
        result = await get_energy_dashboard(slug="escola", db=db, _user={}, hours=48)
        assert result.hours == 48
