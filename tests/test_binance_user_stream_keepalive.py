import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch, AsyncMock
from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter, LISTEN_KEY_KEEPALIVE_SECONDS


@pytest.fixture
def adapter():
    config = MagicMock()
    config.trading.trading_env = "test"
    adapter = BinanceExecutionAdapter(config=config, shadow_mode=True)
    adapter.api_key = "test_key"
    adapter.ws_listen_key = "test_listen_key"
    adapter._rest_timeout = 1.0
    return adapter


@pytest.mark.asyncio
async def test_keepalive_called_after_threshold(adapter):
    """Test that _refresh_listen_key is called when threshold is exceeded."""

    # Set last keepalive to be older than threshold
    adapter._last_listen_key_keepalive_at = time.time(
    ) - (LISTEN_KEY_KEEPALIVE_SECONDS + 100)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock successful response
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_client.put.return_value = mock_resp

        success = await adapter._refresh_listen_key()

        assert success is True
        # Verify PUT called
        mock_client.put.assert_called_once()
        args, kwargs = mock_client.put.call_args
        assert "listenKey" in kwargs["params"]
        assert kwargs["params"]["listenKey"] == "test_listen_key"

        # Verify timestamp updated (approximate)
        assert adapter._last_listen_key_keepalive_at > time.time() - 10


@pytest.mark.asyncio
async def test_keepalive_handles_missing_listen_key_with_reconnect(adapter):
    """Test that -1125 error returns False to trigger reconnect."""

    adapter._last_listen_key_keepalive_at = time.time(
    ) - (LISTEN_KEY_KEEPALIVE_SECONDS + 100)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock error response -1125
        mock_resp = MagicMock()
        mock_resp.is_success = False
        mock_resp.json.return_value = {
            "code": -1125, "msg": "ListenKey does not exist"}
        mock_client.put.return_value = mock_resp

        success = await adapter._refresh_listen_key()

        assert success is False
        # Timestamp should NOT be updated on failure (so it retries or reconnects)
        # In our implementation, we return False to break the loop, so timestamp update doesn't matter as much,
        # but strictly it shouldn't be updated.
        assert adapter._last_listen_key_keepalive_at < time.time() - \
            LISTEN_KEY_KEEPALIVE_SECONDS


@pytest.mark.asyncio
async def test_keepalive_handles_transient_error(adapter):
    """Test that other errors return True to avoid killing connection immediately."""

    adapter._last_listen_key_keepalive_at = time.time(
    ) - (LISTEN_KEY_KEEPALIVE_SECONDS + 100)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock generic error 500
        mock_resp = MagicMock()
        mock_resp.is_success = False
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.json.side_effect = Exception("Not JSON")
        mock_client.put.return_value = mock_resp

        success = await adapter._refresh_listen_key()

        assert success is True  # Should return True to keep connection alive
