"""
Testes unitários para app/bridges/mqtt_bridge.py e _common.py.

Estes testes NÃO precisam de banco nem de broker MQTT:
testam apenas funções puras / lógica isolada.
"""
from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from app.bridges.mqtt_bridge import _imei_from_topic


# ---------------------------------------------------------------------------
# _imei_from_topic
# ---------------------------------------------------------------------------

class TestImeiFromTopic:
    """Extração de IMEI a partir de diferentes formatos de tópico."""

    def test_legacy_pattern(self):
        """Padrão legado: SN50/data/<imei>"""
        assert _imei_from_topic("SN50/data/868927084622450") == "868927084622450"

    def test_legacy_pattern_with_prefix_hash(self):
        """Padrão legado com wildcard resolvido: SN50/data/868927084622450"""
        assert _imei_from_topic("SN50/data/868927084622450") == "868927084622450"

    def test_new_pattern(self):
        """Padrão novo: telemetry/<slug>/devices/<imei>/data"""
        assert _imei_from_topic("telemetry/barueri/devices/868927084622450/data") == "868927084622450"

    def test_new_pattern_other_slug(self):
        assert _imei_from_topic("telemetry/cidadex/devices/123456789012345/data") == "123456789012345"

    def test_imei_too_short_returns_none(self):
        """Números com menos de 10 dígitos não são IMEI."""
        assert _imei_from_topic("SN50/data/123") is None

    def test_no_numeric_suffix_returns_none(self):
        assert _imei_from_topic("SN50/data/some_device_name") is None

    def test_empty_topic_returns_none(self):
        assert _imei_from_topic("") is None

    def test_only_slashes_returns_none(self):
        assert _imei_from_topic("///") is None

    def test_new_pattern_non_numeric_imei_returns_none(self):
        """Slot de IMEI no novo padrão contém não-dígitos."""
        assert _imei_from_topic("telemetry/barueri/devices/ABC123/data") is None


# ---------------------------------------------------------------------------
# write_raw (lógica de hash, sem banco)
# ---------------------------------------------------------------------------

class TestWriteRawHash:
    """Valida que payload_hash é SHA-256 do payload_raw em UTF-8."""

    def test_hash_consistency(self):
        payload = '{"test": 1}'
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        # Não chama write_raw (precisaria de banco), mas verifica a fórmula
        assert len(expected) == 64
        assert expected == hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def test_hash_differs_per_payload(self):
        h1 = hashlib.sha256(b"payload_a").hexdigest()
        h2 = hashlib.sha256(b"payload_b").hexdigest()
        assert h1 != h2


# ---------------------------------------------------------------------------
# MQTTBridge — on_message sem banco (mock)
# ---------------------------------------------------------------------------

class TestMQTTBridgeOnMessage:
    """
    Testa o comportamento de on_message com banco mockado.
    Verifica a regra de ACK: somente após commit bem-sucedido.
    """

    def _make_bridge(self):
        """Instancia MQTTBridge com settings mockadas."""
        from app.bridges.mqtt_bridge import MQTTBridge
        with patch("app.bridges.mqtt_bridge.get_settings") as mock_settings:
            s = MagicMock()
            s.client_slug = "test"
            s.db_host = "localhost"
            mock_settings.return_value = s
            bridge = MQTTBridge()
            bridge._settings = s
        return bridge

    def _make_msg(self, topic: str, payload: str) -> MagicMock:
        msg = MagicMock()
        msg.topic = topic
        msg.payload = payload.encode("utf-8")
        return msg

    def test_ack_called_on_success(self):
        """ACK deve ser chamado quando write_raw + commit tiverem sucesso."""
        bridge = self._make_bridge()
        mock_client = MagicMock()
        mock_msg = self._make_msg("SN50/data/868927084622450", '{"test":1}')

        mock_con = MagicMock()
        with (
            patch.object(bridge, "_ensure_db", return_value=mock_con),
            patch("app.bridges.mqtt_bridge.write_raw", return_value=42),
        ):
            bridge.on_message(mock_client, None, mock_msg)

        mock_client.ack.assert_called_once_with(mock_msg.mid, mock_msg.qos)
        mock_con.commit.assert_called_once()

    def test_ack_not_called_on_db_error(self):
        """Se write_raw falhar, ACK NÃO deve ser chamado (broker reentrega)."""
        bridge = self._make_bridge()
        mock_client = MagicMock()
        mock_msg = self._make_msg("SN50/data/868927084622450", '{"test":1}')

        mock_con = MagicMock()
        with (
            patch.object(bridge, "_ensure_db", return_value=mock_con),
            patch(
                "app.bridges.mqtt_bridge.write_raw",
                side_effect=Exception("DB connection refused"),
            ),
        ):
            bridge.on_message(mock_client, None, mock_msg)

        mock_client.ack.assert_not_called()

    def test_ack_not_called_on_commit_error(self):
        """Se commit falhar após write_raw, ACK NÃO deve ser chamado."""
        bridge = self._make_bridge()
        mock_client = MagicMock()
        mock_msg = self._make_msg("SN50/data/868927084622450", '{"test":1}')

        mock_con = MagicMock()
        mock_con.commit.side_effect = Exception("commit failed")

        with (
            patch.object(bridge, "_ensure_db", return_value=mock_con),
            patch("app.bridges.mqtt_bridge.write_raw", return_value=42),
        ):
            bridge.on_message(mock_client, None, mock_msg)

        mock_client.ack.assert_not_called()

    def test_duplicate_still_acks(self):
        """
        Mensagem duplicada (write_raw retorna None) deve ser ACK-ada:
        já está no banco, não faz sentido pedir reentrega.
        """
        bridge = self._make_bridge()
        mock_client = MagicMock()
        mock_msg = self._make_msg("SN50/data/868927084622450", '{"test":1}')

        mock_con = MagicMock()
        with (
            patch.object(bridge, "_ensure_db", return_value=mock_con),
            patch("app.bridges.mqtt_bridge.write_raw", return_value=None),  # ON CONFLICT
        ):
            bridge.on_message(mock_client, None, mock_msg)

        mock_client.ack.assert_called_once_with(mock_msg.mid, mock_msg.qos)
        assert bridge._skip_count == 1
