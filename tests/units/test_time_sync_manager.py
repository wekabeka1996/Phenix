"""
Unit tests for TimeSyncManager.

Tests:
- Configuration loading from YAML
- Cache validity
- Sync with mocked HTTP responses
- Error handling
- Background sync lifecycle
- Verification that adapters load configs correctly
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apps.reference.adapters.time_sync_manager import (
    TimeSyncError,
    TimeSyncManager,
    TimeSyncState,
)
from apps.reference.config_adapter import (
    Error1021RetryConfig,
    TimeSyncConfig,
    WebSocketReconnectConfig,
    OpenOrdersConfig,
    resolve_time_sync_config,
    resolve_websocket_reconnect_config,
    resolve_open_orders_config,
)


@pytest.fixture
def time_sync_config() -> TimeSyncConfig:
    """Create a test TimeSyncConfig."""
    return TimeSyncConfig(
        recv_window_mainnet_ms=5000,
        recv_window_testnet_ms=20000,
        interval_sec=30,
        cache_valid_sec=25,
        max_drift_warn_ms=500,
        max_drift_hard_limit_ms=60000,
        sync_max_attempts=5,
        sync_backoff_base_sec=0.5,
        sync_timeout_sec=10.0,
        error_1021=Error1021RetryConfig(
            max_retries=2,
            backoff_base_sec=0.3,
            backoff_multiplier=2.0,
            force_sync_before_retry=True,
        ),
    )


@pytest.fixture
def mock_http_client() -> AsyncMock:
    """Create a mocked httpx.AsyncClient."""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


@pytest.fixture
def time_sync_manager(
    time_sync_config: TimeSyncConfig, mock_http_client: AsyncMock
) -> TimeSyncManager:
    """Create a TimeSyncManager with test config and mocked client."""
    manager = TimeSyncManager(
        config=time_sync_config,
        http_client=mock_http_client,
        base_url="https://demo-fapi.binance.com",
        is_testnet=True,
    )
    return manager


class TestTimeSyncConfig:
    """Tests for TimeSyncConfig dataclass."""

    def test_get_recv_window_testnet(self, time_sync_config: TimeSyncConfig):
        """Test recvWindow for testnet."""
        assert time_sync_config.get_recv_window(is_testnet=True) == 20000

    def test_get_recv_window_mainnet(self, time_sync_config: TimeSyncConfig):
        """Test recvWindow for mainnet."""
        assert time_sync_config.get_recv_window(is_testnet=False) == 5000

    def test_is_offset_valid_fresh(self, time_sync_config: TimeSyncConfig):
        """Test offset validity when cache is fresh."""
        last_sync = time.monotonic()
        now = last_sync + 10  # 10 seconds later
        assert time_sync_config.is_offset_valid(last_sync, now) is True

    def test_is_offset_valid_stale(self, time_sync_config: TimeSyncConfig):
        """Test offset validity when cache is stale."""
        last_sync = time.monotonic()
        now = last_sync + 30  # 30 seconds later (> cache_valid_sec=25)
        assert time_sync_config.is_offset_valid(last_sync, now) is False

    def test_should_warn_drift(self, time_sync_config: TimeSyncConfig):
        """Test drift warning threshold."""
        assert time_sync_config.should_warn_drift(400) is False
        assert time_sync_config.should_warn_drift(600) is True

    def test_exceeds_hard_limit(self, time_sync_config: TimeSyncConfig):
        """Test drift hard limit."""
        assert time_sync_config.exceeds_hard_limit(50000) is False
        assert time_sync_config.exceeds_hard_limit(70000) is True


class TestTimeSyncManager:
    """Tests for TimeSyncManager class."""

    def test_initialization(
        self, time_sync_manager: TimeSyncManager, time_sync_config: TimeSyncConfig
    ):
        """Test manager initializes with correct config."""
        assert time_sync_manager.config == time_sync_config
        assert time_sync_manager.offset_ms == 0
        assert time_sync_manager.is_initialized is False

    def test_recv_window_property(self, time_sync_manager: TimeSyncManager):
        """Test recv_window_ms property for testnet."""
        assert time_sync_manager.recv_window_ms == 20000

    def test_is_cache_valid_initial(self, time_sync_manager: TimeSyncManager):
        """Test cache validity before first sync."""
        assert time_sync_manager.is_cache_valid() is False

    def test_set_http_client(self, time_sync_manager: TimeSyncManager):
        """Test setting HTTP client."""
        new_client = AsyncMock(spec=httpx.AsyncClient)
        time_sync_manager.set_http_client(new_client)
        assert time_sync_manager._http_client is new_client
        assert time_sync_manager._owns_client is False

    @pytest.mark.asyncio
    async def test_sync_success(
        self, time_sync_manager: TimeSyncManager, mock_http_client: AsyncMock
    ):
        """Test successful time sync."""
        # Mock server response
        server_time = int(time.time() * 1000) + 100  # Server 100ms ahead
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"serverTime": server_time}
        mock_http_client.get = AsyncMock(return_value=mock_response)

        # Perform sync
        await time_sync_manager.sync(force=True)

        # Verify state updated
        assert time_sync_manager.is_initialized is True
        # Should be close to 100ms
        assert abs(time_sync_manager.offset_ms) < 1000

    @pytest.mark.asyncio
    async def test_sync_failure_returns_false(
        self, time_sync_manager: TimeSyncManager, mock_http_client: AsyncMock
    ):
        """Test sync failure returns False (not raises exception)."""
        # Mock failure
        mock_http_client.get = AsyncMock(
            side_effect=Exception("Network error"))

        result = await time_sync_manager.sync(force=True)

        assert result is False
        assert time_sync_manager.is_initialized is False

    @pytest.mark.asyncio
    async def test_sync_uses_cache(
        self, time_sync_manager: TimeSyncManager, mock_http_client: AsyncMock
    ):
        """Test sync uses cache when valid."""
        # First sync
        server_time = int(time.time() * 1000) + 100
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"serverTime": server_time}
        mock_http_client.get = AsyncMock(return_value=mock_response)

        await time_sync_manager.sync(force=True)
        first_call_count = mock_http_client.get.call_count

        # Second sync (should use cache)
        await time_sync_manager.sync(force=False)
        assert mock_http_client.get.call_count == first_call_count  # No new calls

    @pytest.mark.asyncio
    async def test_get_timestamp(
        self, time_sync_manager: TimeSyncManager, mock_http_client: AsyncMock
    ):
        """Test get_timestamp returns correct value."""
        # Setup: successful sync
        server_time = int(time.time() * 1000) + 500
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"serverTime": server_time}
        mock_http_client.get = AsyncMock(return_value=mock_response)

        timestamp = await time_sync_manager.get_timestamp()

        # Timestamp should be now + offset
        expected = int(time.time() * 1000) + time_sync_manager.offset_ms
        assert abs(timestamp - expected) < 100  # Within 100ms tolerance

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(
        self, time_sync_manager: TimeSyncManager, mock_http_client: AsyncMock
    ):
        """Test start/stop lifecycle."""
        # Mock successful sync
        server_time = int(time.time() * 1000) + 100
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"serverTime": server_time}
        mock_http_client.get = AsyncMock(return_value=mock_response)

        # Start
        await time_sync_manager.start()
        assert time_sync_manager._running is True
        assert time_sync_manager._background_task is not None

        # Give background task a moment to start
        await asyncio.sleep(0.1)

        # Stop
        await time_sync_manager.stop()
        assert time_sync_manager._running is False

    def test_sync_blocking(
        self, time_sync_config: TimeSyncConfig
    ):
        """Test sync_blocking for WS thread context."""
        # Create manager without http client (will use requests)
        manager = TimeSyncManager(
            config=time_sync_config,
            http_client=None,
            base_url="https://demo-fapi.binance.com",
            is_testnet=True,
        )

        # Mock requests.get
        with patch("requests.get") as mock_get:
            server_time = int(time.time() * 1000) + 200
            mock_response = MagicMock()
            mock_response.ok = True
            mock_response.json.return_value = {"serverTime": server_time}
            mock_get.return_value = mock_response

            manager.sync_blocking()

            assert manager.is_initialized is True
            assert abs(manager.offset_ms) < 1000


class TestError1021RetryConfig:
    """Tests for Error1021RetryConfig."""

    def test_defaults(self):
        """Test default values."""
        config = Error1021RetryConfig()
        assert config.max_retries == 2
        assert config.backoff_base_sec == 0.3
        assert config.backoff_multiplier == 2.0
        assert config.force_sync_before_retry is True

    def test_custom_values(self):
        """Test custom configuration."""
        config = Error1021RetryConfig(
            max_retries=3,
            backoff_base_sec=0.5,
            backoff_multiplier=1.5,
            force_sync_before_retry=False,
        )
        assert config.max_retries == 3
        assert config.backoff_base_sec == 0.5
        assert config.backoff_multiplier == 1.5
        assert config.force_sync_before_retry is False


class TestConfigLoadingFromYAML:
    """Tests for loading configuration from YAML (execution.yaml)."""

    def test_time_sync_config_from_dict(self):
        """Test TimeSyncConfig loading from dict config."""
        config_dict = {
            "adapter": {
                "time_sync": {
                    "recv_window_mainnet_ms": 6000,
                    "recv_window_testnet_ms": 25000,
                    "interval_sec": 45,
                    "cache_valid_sec": 40,
                    "max_drift_warn_ms": 600,
                    "sync_max_attempts": 7,
                    "sync_backoff_base_sec": 0.8,
                    "sync_timeout_sec": 15.0,
                    "error_1021": {
                        "max_retries": 4,
                        "backoff_base_sec": 0.5,
                    }
                }
            }
        }

        cfg = resolve_time_sync_config(config_dict)

        assert cfg.recv_window_mainnet_ms == 6000
        assert cfg.recv_window_testnet_ms == 25000
        assert cfg.interval_sec == 45
        assert cfg.cache_valid_sec == 40
        assert cfg.sync_max_attempts == 7
        assert cfg.sync_backoff_base_sec == 0.8
        assert cfg.sync_timeout_sec == 15.0
        assert cfg.error_1021.max_retries == 4

    def test_time_sync_config_defaults_when_missing(self):
        """Test TimeSyncConfig uses defaults when config is None."""
        cfg = resolve_time_sync_config(None)

        # Should use testnet defaults (USE_TESTNET=1 by default)
        assert cfg.recv_window_mainnet_ms == 5000
        assert cfg.recv_window_testnet_ms == 60000  # Increased for testnet high latency
        assert cfg.sync_max_attempts == 5
        assert cfg.sync_timeout_sec == 10.0

    def test_websocket_config_from_dict(self):
        """Test WebSocketReconnectConfig loading from dict config."""
        config_dict = {
            "adapter": {
                "websocket": {
                    "initial_delay_sec": 2.0,
                    "max_delay_sec": 120.0,
                    "multiplier": 3.0,
                    "listen_key_keepalive_sec": 1800,
                }
            }
        }

        cfg = resolve_websocket_reconnect_config(config_dict)

        assert cfg.initial_delay_sec == 2.0
        assert cfg.max_delay_sec == 120.0
        assert cfg.multiplier == 3.0
        assert cfg.listen_key_keepalive_sec == 1800

    def test_websocket_config_defaults(self):
        """Test WebSocketReconnectConfig defaults."""
        cfg = WebSocketReconnectConfig()

        assert cfg.initial_delay_sec == 1.0
        assert cfg.max_delay_sec == 60.0  # Updated from 30 to 60
        assert cfg.multiplier == 2.0
        assert cfg.listen_key_keepalive_sec == 2700  # 45 minutes

    def test_open_orders_config_from_dict(self):
        """Test OpenOrdersConfig loading from dict config."""
        config_dict = {
            "adapter": {
                "open_orders": {
                    "max_attempts": 5,
                    "backoff_ms": [100, 300, 700],
                    "fallback_reason": "CUSTOM_REASON",
                }
            }
        }

        cfg = resolve_open_orders_config(config_dict)

        assert cfg.max_attempts == 5
        assert cfg.backoff_ms == (100, 300, 700)
        assert cfg.fallback_reason == "CUSTOM_REASON"

    def test_open_orders_config_defaults(self):
        """Test OpenOrdersConfig defaults."""
        cfg = OpenOrdersConfig()

        assert cfg.max_attempts == 3
        assert cfg.backoff_ms == (200, 500)
        assert cfg.fallback_reason == "API_ORDERS_FAILED"

    def test_time_sync_manager_uses_config_values(self):
        """Test TimeSyncManager uses config values for sync parameters."""
        config = TimeSyncConfig(
            sync_max_attempts=3,
            sync_backoff_base_sec=1.0,
            sync_timeout_sec=5.0,
        )

        manager = TimeSyncManager(
            config=config,
            http_client=None,
            base_url="https://demo-fapi.binance.com",
            is_testnet=True,
        )

        # Verify config is stored
        assert manager._config.sync_max_attempts == 3
        assert manager._config.sync_backoff_base_sec == 1.0
        assert manager._config.sync_timeout_sec == 5.0
