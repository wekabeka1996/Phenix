"""
Tests for timeout resilience in BinanceExecutionAdapter.

Phase 0 Hotfix: Validates that:
1. TimeoutConfig is properly initialized based on testnet/live
2. RetryConfig exponential backoff works
3. _request_with_retry handles timeout/network errors
"""
import asyncio
import time
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
import httpx


# ---------------------------------------------------------------------------
# Test: TimeoutConfig initialization
# ---------------------------------------------------------------------------

def test_execution_adapter_has_timeout_config():
    """Verify BinanceExecutionAdapter initializes TimeoutConfig."""
    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )
    from apps.reference.adapters.binance_adapter import TimeoutConfig

    # Create adapter in shadow mode (no API calls)
    adapter = BinanceExecutionAdapter(
        fsm=None,
        config={},
        shadow_mode=True,
    )

    assert hasattr(adapter, '_timeout_config')
    assert isinstance(adapter._timeout_config, TimeoutConfig)


def test_execution_adapter_uses_testnet_defaults():
    """Verify testnet detection uses testnet defaults (generous timeouts)."""
    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    with patch.dict('os.environ', {'USE_TESTNET': '1'}):
        adapter = BinanceExecutionAdapter(
            fsm=None,
            config={},
            shadow_mode=True,
        )

    # Testnet should have read timeout >= 20s
    assert adapter._timeout_config.read >= 20.0
    assert adapter._is_testnet is True


def test_execution_adapter_uses_config_timeout():
    """Verify adapter reads timeout from config dict."""
    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    # Pass config with adapter.timeouts
    config = {
        "adapter": {
            "timeouts": {
                "read": 120.0,
                "connect": 15.0,
            }
        }
    }
    adapter = BinanceExecutionAdapter(
        fsm=None,
        config=config,
        shadow_mode=True,
    )

    # Should use the config value
    assert adapter._timeout_config.read == 120.0
    assert adapter._timeout_config.connect == 15.0


def test_execution_adapter_has_retry_config():
    """Verify BinanceExecutionAdapter initializes RetryConfig."""
    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )
    from apps.reference.adapters.binance_adapter import RetryConfig

    adapter = BinanceExecutionAdapter(
        fsm=None,
        config={},
        shadow_mode=True,
    )

    assert hasattr(adapter, '_retry_config')
    assert isinstance(adapter._retry_config, RetryConfig)
    assert adapter._retry_config.max_retries >= 1


# ---------------------------------------------------------------------------
# Test: HTTP client uses TimeoutConfig
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_http_client_uses_timeout_config():
    """Verify get_http_client() creates client with TimeoutConfig."""
    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(
        fsm=None,
        config={},
        shadow_mode=True,
    )

    # Get HTTP client
    client = await adapter.get_http_client()

    # Verify timeout is set from TimeoutConfig
    assert client is not None
    assert client.timeout is not None
    # Check read timeout matches config
    assert client.timeout.read == adapter._timeout_config.read

    # Cleanup
    await adapter.stop_async()


# ---------------------------------------------------------------------------
# Test: _request_with_retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_with_retry_success_first_attempt():
    """Verify successful request on first attempt."""
    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(
        fsm=None,
        config={},
        shadow_mode=True,
    )

    # Mock HTTP client
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    adapter._http_client = mock_client

    response = await adapter._request_with_retry(
        "GET",
        "https://api.example.com/test",
        headers={"X-Test": "value"},
        log_ctx="TEST_REQUEST",
    )

    assert response.status_code == 200
    mock_client.get.assert_called_once()

    await adapter.stop_async()


@pytest.mark.asyncio
async def test_request_with_retry_retries_on_timeout():
    """Verify retry logic on timeout exceptions."""
    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(
        fsm=None,
        config={},
        shadow_mode=True,
    )

    # Mock HTTP client to fail twice then succeed
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("Timeout 1"),
            httpx.ReadTimeout("Timeout 2"),
            mock_response,
        ]
    )
    adapter._http_client = mock_client

    # Should succeed after retries
    response = await adapter._request_with_retry(
        "GET",
        "https://api.example.com/test",
        log_ctx="TEST_RETRY",
    )

    assert response.status_code == 200
    assert mock_client.get.call_count == 3  # 2 failures + 1 success

    await adapter.stop_async()


@pytest.mark.asyncio
async def test_request_with_retry_exhausted():
    """Verify exception raised when all retries exhausted."""
    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )
    from apps.reference.adapters.binance_adapter import RetryConfig

    adapter = BinanceExecutionAdapter(
        fsm=None,
        config={},
        shadow_mode=True,
    )
    # Use small retry config for faster test
    adapter._retry_config = RetryConfig(
        max_retries=2,
        initial_backoff_sec=0.01,  # Fast for testing
        max_backoff_sec=0.05,
    )

    # Mock HTTP client to always fail
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=httpx.ReadTimeout("Always timeout"))
    adapter._http_client = mock_client

    with pytest.raises(httpx.ReadTimeout):
        await adapter._request_with_retry(
            "GET",
            "https://api.example.com/test",
            log_ctx="TEST_EXHAUST",
        )

    # Should have tried max_retries + 1 times
    assert mock_client.get.call_count == 3  # initial + 2 retries

    await adapter.stop_async()


@pytest.mark.asyncio
async def test_request_with_retry_network_error():
    """Verify retry on network errors."""
    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(
        fsm=None,
        config={},
        shadow_mode=True,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("Network error"),
            mock_response,
        ]
    )
    adapter._http_client = mock_client

    response = await adapter._request_with_retry(
        "POST",
        "https://api.example.com/test",
        data={"key": "value"},
        log_ctx="TEST_NETWORK",
    )

    assert response.status_code == 200
    assert mock_client.post.call_count == 2

    await adapter.stop_async()


# ---------------------------------------------------------------------------
# Test: RetryConfig backoff delays
# ---------------------------------------------------------------------------

def test_retry_config_backoff_delays():
    """Verify exponential backoff delay calculation."""
    from apps.reference.adapters.binance_adapter import RetryConfig

    config = RetryConfig(
        max_retries=4,
        initial_backoff_sec=0.5,
        backoff_multiplier=2.0,
        max_backoff_sec=10.0,
    )

    delays = config.get_backoff_delays()

    # Expected: 0.5, 1.0, 2.0, 4.0
    assert len(delays) == 4
    assert delays[0] == 0.5
    assert delays[1] == 1.0
    assert delays[2] == 2.0
    assert delays[3] == 4.0


def test_retry_config_max_backoff_cap():
    """Verify backoff is capped at max_backoff_sec."""
    from apps.reference.adapters.binance_adapter import RetryConfig

    config = RetryConfig(
        max_retries=5,
        initial_backoff_sec=2.0,
        backoff_multiplier=3.0,
        max_backoff_sec=5.0,  # Cap
    )

    delays = config.get_backoff_delays()

    # Expected: 2.0, 5.0, 5.0, 5.0, 5.0 (capped at 5.0)
    assert all(d <= 5.0 for d in delays)
    assert delays[0] == 2.0
    assert delays[1] == 5.0  # 2 * 3 = 6, capped to 5


# ---------------------------------------------------------------------------
# Test: TimeoutConfig factory methods
# ---------------------------------------------------------------------------

def test_timeout_config_testnet_defaults():
    """Verify testnet defaults have generous timeouts."""
    from apps.reference.adapters.binance_adapter import TimeoutConfig

    testnet = TimeoutConfig.testnet_defaults()

    assert testnet.read >= 20.0  # Generous for slow testnet
    assert testnet.connect >= 5.0


def test_timeout_config_live_defaults():
    """Verify live defaults have tighter timeouts."""
    from apps.reference.adapters.binance_adapter import TimeoutConfig

    live = TimeoutConfig.live_defaults()
    testnet = TimeoutConfig.testnet_defaults()

    # Live should be tighter than testnet
    assert live.read <= testnet.read


def test_timeout_config_to_httpx_timeout():
    """Verify conversion to httpx.Timeout."""
    from apps.reference.adapters.binance_adapter import TimeoutConfig

    config = TimeoutConfig(connect=5.0, read=30.0, write=10.0, pool=5.0)
    httpx_timeout = config.to_httpx_timeout()

    assert isinstance(httpx_timeout, httpx.Timeout)
    assert httpx_timeout.connect == 5.0
    assert httpx_timeout.read == 30.0
    assert httpx_timeout.write == 10.0
    assert httpx_timeout.pool == 5.0


# ---------------------------------------------------------------------------
# Test: Integration with YAML config (from_config)
# ---------------------------------------------------------------------------

def test_timeout_config_from_yaml_v2_format():
    """Verify TimeoutConfig reads from YAML v2 adapter.timeouts structure."""
    from apps.reference.config_adapter import TimeoutConfig

    config = {
        "adapter": {
            "timeouts": {
                "connect": 15.0,
                "read": 45.0,
                "write": 12.0,
                "pool": 8.0,
            }
        }
    }

    timeout = TimeoutConfig.from_config(config)

    assert timeout.connect == 15.0
    assert timeout.read == 45.0
    assert timeout.write == 12.0
    assert timeout.pool == 8.0


def test_timeout_config_from_rest_timeout_sec():
    """Verify TimeoutConfig respects legacy rest_timeout_sec flat format."""
    from apps.reference.config_adapter import TimeoutConfig

    config = {"rest_timeout_sec": 60.0}

    timeout = TimeoutConfig.from_config(config)

    # Should use rest_timeout_sec for read, keep env defaults for others
    assert timeout.read >= 60.0


def test_timeout_config_from_none_uses_env_defaults():
    """Verify TimeoutConfig falls back to env-based defaults when no config."""
    from apps.reference.config_adapter import TimeoutConfig

    with patch.dict('os.environ', {'USE_TESTNET': '1'}):
        timeout = TimeoutConfig.from_config(None)
        assert timeout.read == 30.0  # testnet default

    with patch.dict('os.environ', {'USE_TESTNET': '0'}):
        timeout = TimeoutConfig.from_config(None)
        assert timeout.read == 10.0  # live default


def test_retry_config_from_yaml_v2_format():
    """Verify RetryConfig reads from YAML v2 adapter.retry structure."""
    from apps.reference.config_adapter import RetryConfig

    config = {
        "adapter": {
            "retry": {
                "max_retries": 5,
                "initial_backoff_sec": 1.0,
                "max_backoff_sec": 16.0,
                "backoff_multiplier": 3.0,
            }
        }
    }

    retry = RetryConfig.from_config(config)

    assert retry.max_retries == 5
    assert retry.initial_backoff_sec == 1.0
    assert retry.max_backoff_sec == 16.0
    assert retry.backoff_multiplier == 3.0


def test_retry_config_from_brackets_retry():
    """Verify RetryConfig can read from existing brackets.retry structure."""
    from apps.reference.config_adapter import RetryConfig

    # Existing YAML structure in system_config.yaml
    config = {
        "brackets": {
            "retry": {
                "max_attempts": 4,
                "backoff_ms": [200, 500, 1000],
            }
        }
    }

    retry = RetryConfig.from_config(config)

    assert retry.max_retries == 4
    assert retry.initial_backoff_sec == 0.2  # 200ms -> 0.2s


def test_adapter_reads_config_through_from_config():
    """Verify BinanceExecutionAdapter uses from_config to read YAML."""
    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    config = {
        "adapter": {
            "timeouts": {
                "read": 99.0,
            },
            "retry": {
                "max_retries": 7,
            }
        }
    }

    adapter = BinanceExecutionAdapter(
        fsm=None,
        config=config,
        shadow_mode=True,
    )

    assert adapter._timeout_config.read == 99.0
    assert adapter._retry_config.max_retries == 7


def test_timeout_config_from_config_v2_domains_execution():
    """Verify TimeoutConfig reads from config_v2.domains.execution.adapter path."""
    from apps.reference.config_adapter import TimeoutConfig

    # This is the actual structure when config is loaded via ConfigLoader
    config = {
        "config_v2": {
            "domains": {
                "execution": {
                    "adapter": {
                        "timeouts": {
                            "connect": 12.0,
                            "read": 42.0,
                            "write": 8.0,
                            "pool": 6.0,
                        }
                    }
                }
            }
        }
    }

    timeout = TimeoutConfig.from_config(config)

    assert timeout.connect == 12.0
    assert timeout.read == 42.0
    assert timeout.write == 8.0
    assert timeout.pool == 6.0


def test_retry_config_from_config_v2_domains_execution():
    """Verify RetryConfig reads from config_v2.domains.execution.adapter path."""
    from apps.reference.config_adapter import RetryConfig

    config = {
        "config_v2": {
            "domains": {
                "execution": {
                    "adapter": {
                        "retry": {
                            "max_retries": 6,
                            "initial_backoff_sec": 0.25,
                            "max_backoff_sec": 4.0,
                            "backoff_multiplier": 1.5,
                        }
                    }
                }
            }
        }
    }

    retry = RetryConfig.from_config(config)

    assert retry.max_retries == 6
    assert retry.initial_backoff_sec == 0.25
    assert retry.max_backoff_sec == 4.0
    assert retry.backoff_multiplier == 1.5


# ---------------------------------------------------------------------------
# Test: WebSocketReconnectConfig
# ---------------------------------------------------------------------------

def test_ws_reconnect_config_defaults():
    """Verify WebSocketReconnectConfig has sensible defaults."""
    from apps.reference.config_adapter import WebSocketReconnectConfig

    config = WebSocketReconnectConfig()

    assert config.initial_delay_sec == 1.0
    assert config.max_delay_sec == 60.0  # Updated default
    assert config.multiplier == 2.0
    assert config.reset_after_success is True


def test_ws_reconnect_config_get_next_delay():
    """Verify exponential backoff calculation."""
    from apps.reference.config_adapter import WebSocketReconnectConfig

    config = WebSocketReconnectConfig(
        initial_delay_sec=1.0,
        max_delay_sec=10.0,
        multiplier=2.0,
    )

    # First delay: 1s
    delay = config.initial_delay_sec
    assert delay == 1.0

    # Second delay: 2s
    delay = config.get_next_delay(delay)
    assert delay == 2.0

    # Third delay: 4s
    delay = config.get_next_delay(delay)
    assert delay == 4.0

    # Fourth delay: 8s
    delay = config.get_next_delay(delay)
    assert delay == 8.0

    # Fifth delay: capped at 10s
    delay = config.get_next_delay(delay)
    assert delay == 10.0

    # Stays at cap
    delay = config.get_next_delay(delay)
    assert delay == 10.0


def test_ws_reconnect_config_from_config():
    """Verify WebSocketReconnectConfig reads from YAML config."""
    from apps.reference.config_adapter import WebSocketReconnectConfig

    config = {
        "adapter": {
            "websocket": {
                "initial_delay_sec": 2.0,
                "max_delay_sec": 60.0,
                "multiplier": 1.5,
                "reset_after_success": False,
            }
        }
    }

    ws_cfg = WebSocketReconnectConfig.from_config(config)

    assert ws_cfg.initial_delay_sec == 2.0
    assert ws_cfg.max_delay_sec == 60.0
    assert ws_cfg.multiplier == 1.5
    assert ws_cfg.reset_after_success is False


def test_ws_reconnect_config_from_config_v2_path():
    """Verify WebSocketReconnectConfig reads from config_v2.domains.execution.adapter path."""
    from apps.reference.config_adapter import WebSocketReconnectConfig

    config = {
        "config_v2": {
            "domains": {
                "execution": {
                    "adapter": {
                        "websocket": {
                            "initial_delay_sec": 0.5,
                            "max_delay_sec": 15.0,
                            "multiplier": 3.0,
                            "reset_after_success": True,
                        }
                    }
                }
            }
        }
    }

    ws_cfg = WebSocketReconnectConfig.from_config(config)

    assert ws_cfg.initial_delay_sec == 0.5
    assert ws_cfg.max_delay_sec == 15.0
    assert ws_cfg.multiplier == 3.0
    assert ws_cfg.reset_after_success is True


def test_adapter_has_ws_reconnect_config():
    """Verify BinanceExecutionAdapter initializes WebSocketReconnectConfig."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ.setdefault("BINANCE_API_KEY", "test_key")
    os.environ.setdefault("BINANCE_API_SECRET", "test_secret")

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )
    from apps.reference.config_adapter import WebSocketReconnectConfig

    adapter = BinanceExecutionAdapter(shadow_mode=True)

    assert hasattr(adapter, "_ws_reconnect_config")
    assert isinstance(adapter._ws_reconnect_config, WebSocketReconnectConfig)
    assert adapter._ws_reconnect_config.initial_delay_sec == 1.0
    assert adapter._ws_reconnect_config.max_delay_sec == 60.0  # Updated default


# ===========================================================================
# Phase 4: Extended Tests for Real Network Conditions
# ===========================================================================


# ---------------------------------------------------------------------------
# Test: _signed_request_with_retry wrapper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_signed_request_with_retry_success():
    """Verify _signed_request_with_retry works for successful request."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ.setdefault("BINANCE_API_KEY", "test_key")
    os.environ.setdefault("BINANCE_API_SECRET", "test_secret")

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(shadow_mode=True)

    # Mock HTTP client
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"orderId": 12345, "status": "NEW"}
    mock_response.is_success = True

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.delete = AsyncMock(return_value=mock_response)
    adapter._http_client = mock_client

    # Test GET
    response = await adapter._signed_request_with_retry(
        "GET",
        "/fapi/v1/order",
        {"symbol": "BTCUSDT", "orderId": "12345"},
        log_ctx="TEST_GET",
    )
    assert response.status_code == 200

    # Test POST
    response = await adapter._signed_request_with_retry(
        "POST",
        "/fapi/v1/order",
        {"symbol": "BTCUSDT", "side": "BUY"},
        log_ctx="TEST_POST",
    )
    assert response.status_code == 200

    # Test DELETE
    response = await adapter._signed_request_with_retry(
        "DELETE",
        "/fapi/v1/order",
        {"symbol": "BTCUSDT", "orderId": "12345"},
        log_ctx="TEST_DELETE",
    )
    assert response.status_code == 200

    await adapter.stop_async()


@pytest.mark.asyncio
async def test_signed_request_with_retry_handles_timeout():
    """Verify _signed_request_with_retry retries on timeout."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ.setdefault("BINANCE_API_KEY", "test_key")
    os.environ.setdefault("BINANCE_API_SECRET", "test_secret")

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(shadow_mode=True)

    # Mock response for success after retries
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"orderId": 12345}
    mock_response.is_success = True

    mock_client = AsyncMock()
    # Fail twice, then succeed
    mock_client.get = AsyncMock(
        side_effect=[
            httpx.ReadTimeout("timeout 1"),
            httpx.ReadTimeout("timeout 2"),
            mock_response,
        ]
    )
    adapter._http_client = mock_client

    # Should succeed after retries
    response = await adapter._signed_request_with_retry(
        "GET",
        "/fapi/v1/order",
        {"symbol": "BTCUSDT"},
        log_ctx="TEST_RETRY",
    )

    assert response.status_code == 200
    assert mock_client.get.call_count == 3

    await adapter.stop_async()


@pytest.mark.asyncio
async def test_signed_request_with_retry_handles_api_error():
    """Verify _signed_request_with_retry handles API errors gracefully."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ["BINANCE_API_KEY"] = "test_key"
    os.environ["BINANCE_API_SECRET"] = "test_secret"

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(shadow_mode=True)
    adapter.api_key = "test_key"
    adapter.api_secret = "test_secret"

    # Response: some API error
    error_response = MagicMock(spec=httpx.Response)
    error_response.status_code = 400
    error_response.is_success = False
    error_response.json.return_value = {"code": -1000, "msg": "Unknown error"}
    error_response.text = '{"code": -1000, "msg": "Unknown error"}'

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=error_response)
    adapter._http_client = mock_client

    # Should return error response, not raise
    response = await adapter._signed_request_with_retry(
        "GET",
        "/fapi/v1/order",
        {"symbol": "BTCUSDT"},
        log_ctx="TEST_API_ERROR",
    )

    # Returns error response (400), doesn't retry indefinitely
    assert response.status_code == 400
    assert mock_client.get.call_count >= 1

    await adapter.stop_async()


@pytest.mark.asyncio
async def test_signed_request_with_retry_exhausted_retries():
    """Verify _signed_request_with_retry raises after exhausting retries."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ.setdefault("BINANCE_API_KEY", "test_key")
    os.environ.setdefault("BINANCE_API_SECRET", "test_secret")

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )
    from apps.reference.config_adapter import TIMEOUT_EXCEPTIONS

    adapter = BinanceExecutionAdapter(shadow_mode=True)

    mock_client = AsyncMock()
    # Always timeout
    mock_client.get = AsyncMock(
        side_effect=httpx.ReadTimeout("persistent timeout"))
    adapter._http_client = mock_client

    # Should raise after all retries exhausted
    with pytest.raises(TIMEOUT_EXCEPTIONS):
        await adapter._signed_request_with_retry(
            "GET",
            "/fapi/v1/order",
            {"symbol": "BTCUSDT"},
            log_ctx="TEST_EXHAUST",
        )

    # Should have tried 1 initial + max_retries times = 4 total for max_retries=3
    # Actually the wrapper uses max_retries as total attempts
    expected_attempts = adapter._retry_config.max_retries + 1  # initial + retries
    assert mock_client.get.call_count == expected_attempts

    await adapter.stop_async()


# ---------------------------------------------------------------------------
# Test: Network error scenarios
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_signed_request_handles_connection_error():
    """Verify _signed_request_with_retry handles ConnectionError."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ.setdefault("BINANCE_API_KEY", "test_key")
    os.environ.setdefault("BINANCE_API_SECRET", "test_secret")

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(shadow_mode=True)

    # Success response after connection error
    success_response = MagicMock(spec=httpx.Response)
    success_response.status_code = 200
    success_response.is_success = True
    success_response.json.return_value = {"orderId": 12345}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[
            httpx.ConnectError("connection refused"),
            success_response,
        ]
    )
    adapter._http_client = mock_client

    response = await adapter._signed_request_with_retry(
        "GET",
        "/fapi/v1/order",
        {"symbol": "BTCUSDT"},
        log_ctx="TEST_CONNECT_ERROR",
    )

    assert response.status_code == 200
    assert mock_client.get.call_count == 2

    await adapter.stop_async()


@pytest.mark.asyncio
async def test_signed_request_handles_remote_protocol_error():
    """Verify _signed_request_with_retry handles RemoteProtocolError."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ.setdefault("BINANCE_API_KEY", "test_key")
    os.environ.setdefault("BINANCE_API_SECRET", "test_secret")

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(shadow_mode=True)

    success_response = MagicMock(spec=httpx.Response)
    success_response.status_code = 200
    success_response.is_success = True
    success_response.json.return_value = {"orderId": 12345}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=[
            httpx.RemoteProtocolError("server disconnected"),
            success_response,
        ]
    )
    adapter._http_client = mock_client

    response = await adapter._signed_request_with_retry(
        "POST",
        "/fapi/v1/order",
        {"symbol": "BTCUSDT", "side": "BUY"},
        log_ctx="TEST_PROTOCOL_ERROR",
    )

    assert response.status_code == 200
    assert mock_client.post.call_count == 2

    await adapter.stop_async()


# ---------------------------------------------------------------------------
# Test: Latency simulation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_with_slow_response():
    """Verify handling of slow but successful responses."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ.setdefault("BINANCE_API_KEY", "test_key")
    os.environ.setdefault("BINANCE_API_SECRET", "test_secret")

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(shadow_mode=True)

    async def slow_response(*args, **kwargs):
        await asyncio.sleep(0.1)  # 100ms delay
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.is_success = True
        response.json.return_value = {"orderId": 12345}
        return response

    mock_client = AsyncMock()
    mock_client.get = slow_response
    adapter._http_client = mock_client

    start = time.time()
    response = await adapter._signed_request_with_retry(
        "GET",
        "/fapi/v1/order",
        {"symbol": "BTCUSDT"},
        log_ctx="TEST_SLOW",
    )
    elapsed = time.time() - start

    assert response.status_code == 200
    assert elapsed >= 0.1  # Should take at least 100ms

    await adapter.stop_async()


@pytest.mark.asyncio
async def test_backoff_timing_is_respected():
    """Verify exponential backoff timing between retries."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ.setdefault("BINANCE_API_KEY", "test_key")
    os.environ.setdefault("BINANCE_API_SECRET", "test_secret")

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(shadow_mode=True)
    # Use fast backoff for test
    adapter._retry_config.initial_backoff_sec = 0.05
    adapter._retry_config.max_backoff_sec = 0.2
    adapter._retry_config.backoff_multiplier = 2.0

    success_response = MagicMock(spec=httpx.Response)
    success_response.status_code = 200
    success_response.is_success = True
    success_response.json.return_value = {"orderId": 12345}

    call_times = []

    async def track_calls(*args, **kwargs):
        call_times.append(time.time())
        if len(call_times) < 3:
            raise httpx.ReadTimeout("timeout")
        return success_response

    mock_client = AsyncMock()
    mock_client.get = track_calls
    adapter._http_client = mock_client

    await adapter._signed_request_with_retry(
        "GET",
        "/fapi/v1/order",
        {"symbol": "BTCUSDT"},
        log_ctx="TEST_BACKOFF",
    )

    assert len(call_times) == 3
    # First backoff: ~50ms
    delay1 = call_times[1] - call_times[0]
    assert delay1 >= 0.04  # Allow some tolerance
    # Second backoff: ~100ms
    delay2 = call_times[2] - call_times[1]
    assert delay2 >= 0.08  # Should be approximately double

    await adapter.stop_async()


# ---------------------------------------------------------------------------
# Test: Cancel order with retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_binance_order_async_uses_retry_wrapper():
    """Verify _cancel_binance_order_async uses _signed_request_with_retry."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ["BINANCE_API_KEY"] = "test_key"
    os.environ["BINANCE_API_SECRET"] = "test_secret"

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(shadow_mode=True)
    # Ensure API credentials are set directly on adapter
    adapter.api_key = "test_key"
    adapter.api_secret = "test_secret"

    # Track calls to _signed_request_with_retry
    call_log = []

    async def tracking_wrapper(*args, **kwargs):
        call_log.append((args, kwargs))
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.is_success = True
        response.json.return_value = {"orderId": 12345, "status": "CANCELED"}
        return response

    adapter._signed_request_with_retry = tracking_wrapper
    adapter._sync_time_with_server = AsyncMock(return_value=True)

    # Use the actual method name
    result = await adapter._cancel_binance_order_async("BTCUSDT", "12345")

    assert result is not None
    # Result should indicate success
    assert result.get("success") is True or "orderId" in result
    assert len(call_log) == 1
    args, kwargs = call_log[0]
    assert args[0] == "DELETE"  # Method
    assert "/fapi/v1/order" in args[1]  # Endpoint

    await adapter.stop_async()


@pytest.mark.asyncio
async def test_get_order_uses_retry_wrapper():
    """Verify get_order uses _signed_request_with_retry."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ["BINANCE_API_KEY"] = "test_key"
    os.environ["BINANCE_API_SECRET"] = "test_secret"

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(shadow_mode=True)
    # Ensure API credentials are set
    adapter.api_key = "test_key"
    adapter.api_secret = "test_secret"

    call_log = []

    async def tracking_wrapper(*args, **kwargs):
        call_log.append((args, kwargs))
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.is_success = True
        response.json.return_value = {"orderId": 12345, "status": "NEW"}
        return response

    adapter._signed_request_with_retry = tracking_wrapper
    adapter._sync_time_with_server = AsyncMock(return_value=True)

    result = await adapter.get_order("BTCUSDT", "12345")

    assert result is not None
    assert result["orderId"] == 12345
    assert len(call_log) == 1
    args, kwargs = call_log[0]
    assert args[0] == "GET"

    await adapter.stop_async()


# ---------------------------------------------------------------------------
# Test: Concurrent requests handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_requests_with_timeouts():
    """Verify concurrent requests handle timeouts independently."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ.setdefault("BINANCE_API_KEY", "test_key")
    os.environ.setdefault("BINANCE_API_SECRET", "test_secret")

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(shadow_mode=True)

    call_count = 0

    async def mixed_responses(*args, **kwargs):
        nonlocal call_count
        call_count += 1

        # Alternate between timeout and success
        if call_count % 2 == 1:
            raise httpx.ReadTimeout("timeout")

        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.is_success = True
        response.json.return_value = {"orderId": call_count}
        return response

    mock_client = AsyncMock()
    mock_client.get = mixed_responses
    adapter._http_client = mock_client

    # Run multiple concurrent requests
    tasks = [
        adapter._signed_request_with_retry(
            "GET", "/fapi/v1/order", {"symbol": f"TEST{i}"}, log_ctx=f"CONCURRENT_{i}")
        for i in range(3)
    ]

    results = await asyncio.gather(*tasks)

    # All should eventually succeed
    assert len(results) == 3
    for r in results:
        assert r.status_code == 200

    await adapter.stop_async()


# ---------------------------------------------------------------------------
# Test: Error classification
# ---------------------------------------------------------------------------

def test_timeout_exceptions_tuple_complete():
    """Verify TIMEOUT_EXCEPTIONS contains all relevant timeout types."""
    from apps.reference.config_adapter import TIMEOUT_EXCEPTIONS
    import httpx
    import httpcore

    # Verify key timeout types are included
    assert httpx.ReadTimeout in TIMEOUT_EXCEPTIONS
    assert httpx.ConnectTimeout in TIMEOUT_EXCEPTIONS
    assert httpx.WriteTimeout in TIMEOUT_EXCEPTIONS

    # httpcore types (underlying library)
    assert httpcore.ReadTimeout in TIMEOUT_EXCEPTIONS


def test_network_exceptions_tuple_complete():
    """Verify NETWORK_EXCEPTIONS contains relevant network error types."""
    from apps.reference.config_adapter import NETWORK_EXCEPTIONS, TIMEOUT_EXCEPTIONS
    import httpx
    import httpcore

    # Verify key network error types
    assert httpx.ConnectError in TIMEOUT_EXCEPTIONS or httpx.ConnectError in NETWORK_EXCEPTIONS
    assert ConnectionError in NETWORK_EXCEPTIONS


# ---------------------------------------------------------------------------
# Test: Stale mode integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adapter_provides_timeout_error_info():
    """Verify adapter returns structured error info on timeout."""
    import os
    os.environ["USE_TESTNET"] = "1"
    os.environ["BINANCE_API_KEY"] = "test_key"
    os.environ["BINANCE_API_SECRET"] = "test_secret"

    from apps.reference.domains.execution_position.binance_execution_adapter import (
        BinanceExecutionAdapter,
    )

    adapter = BinanceExecutionAdapter(shadow_mode=True)
    # Set credentials directly
    adapter.api_key = "test_key"
    adapter.api_secret = "test_secret"

    # Mock time sync to avoid real network
    adapter._sync_time_with_server = AsyncMock(return_value=True)

    # Mock _signed_request_with_retry to raise timeout
    async def raise_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("persistent timeout")

    adapter._signed_request_with_retry = raise_timeout

    # _cancel_binance_order_async should catch timeout and return error structure
    result = await adapter._cancel_binance_order_async("BTCUSDT", "12345")

    # Should return structured error
    assert result is not None
    assert result.get("success") is False
    # Should have timeout indicator
    assert "error_kind" in result or "is_timeout" in result or "error" in result

    await adapter.stop_async()
