"""
EXEC-R2-J: Tests for BinanceAdapter time sync and retry semantics.

Coverage:
- -1021 handling (legacy tests)
- Time drift logging thresholds
- get_open_orders retry/backoff policy
"""
import logging
import time
from collections import deque

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from apps.reference.domains.execution_position.binance_execution_adapter import (
    BinanceExecutionAdapter,
    GET_OPEN_ORDERS_MAX_ATTEMPTS,
    GET_OPEN_ORDERS_FALLBACK_REASON,
)


@pytest.fixture
def adapter():
    """Create BinanceExecutionAdapter with mocked credentials."""
    adapter = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )
    return adapter


@pytest.mark.asyncio
async def test_time_sync_retry_success(adapter):
    """
    EXEC-R2-J: Test -1021 → resync → retry succeeds.

    Scenario:
    1. Place order → Binance returns -1021 (timestamp outside recvWindow)
    2. Adapter calls _sync_time_with_server() to resync time
    3. Adapter rebuilds request with fresh timestamp
    4. Retry succeeds (200 OK)

    Expected: Order placed successfully after time sync + retry
    """
    symbol = "BTCUSDT"
    side = "BUY"
    quantity = "0.01"
    order_type = "MARKET"

    # Mock successful order response (after retry)
    success_response = {
        "orderId": 123456789,
        "symbol": symbol,
        "status": "NEW",
        "clientOrderId": "test_order_12345",
        "side": side,
        "type": order_type,
        "origQty": quantity,
    }

    # Mock time sync to update server_time_offset
    async def mock_sync_time():
        adapter.server_time_offset = 50  # 50ms offset after sync

    adapter._sync_time_with_server = AsyncMock(side_effect=mock_sync_time)

    # Mock HTTP client behavior
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # First call: -1021 error
        first_response = MagicMock()
        first_response.is_success = False
        first_response.status_code = 400
        first_response.json.return_value = {
            "code": -1021,
            "msg": "Timestamp for this request is outside of the recvWindow."
        }

        # Second call (after retry): success
        second_response = MagicMock()
        second_response.is_success = True
        second_response.status_code = 200
        second_response.json.return_value = success_response

        mock_client.post = AsyncMock(
            side_effect=[first_response, second_response])

        # Place order (will trigger -1021 → resync → retry)
        result = await adapter._place_binance_order_async(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
        )

    # Verify: time sync was called after -1021
    adapter._sync_time_with_server.assert_awaited_once()

    # Verify: HTTP client.post called twice (first -1021, then retry success)
    assert mock_client.post.await_count == 2, "Expected 2 HTTP calls (error + retry)"

    # Verify: result is successful order
    assert result["orderId"] == success_response["orderId"]
    assert result["status"] == "NEW"


@pytest.mark.asyncio
async def test_time_sync_retry_failure_structured_error(adapter):
    """
    EXEC-R2-J: Test -1021 → resync → retry still -1021 → structured error.

    Scenario:
    1. Place order → Binance returns -1021
    2. Adapter resyncs time + rebuilds request
    3. Retry STILL returns -1021 (time sync failed)
    4. Adapter raises RuntimeError with structured message (timestamp, offset, recvWindow)

    Expected: RuntimeError raised with diagnostic info, NO infinite retry loop
    """
    symbol = "ETHUSDT"
    side = "SELL"
    quantity = "1.0"
    order_type = "LIMIT"
    price = "2000.0"

    # Mock time sync
    async def mock_sync_time():
        adapter.server_time_offset = 100  # Updated offset

    adapter._sync_time_with_server = AsyncMock(side_effect=mock_sync_time)

    # Mock HTTP client behavior
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Both calls return -1021 (time sync failure)
        error_response = MagicMock()
        error_response.is_success = False
        error_response.status_code = 400
        error_response.json.return_value = {
            "code": -1021,
            "msg": "Timestamp for this request is outside of the recvWindow."
        }

        mock_client.post = AsyncMock(return_value=error_response)

        # Place order → expect RuntimeError with structured message
        with pytest.raises(RuntimeError) as exc_info:
            await adapter._place_binance_order_async(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=price,
            )

    # Verify: time sync was called
    adapter._sync_time_with_server.assert_awaited_once()

    # Verify: HTTP client.post called exactly twice (no infinite loop)
    assert mock_client.post.await_count == 2, "Expected 2 HTTP calls (error + retry), no infinite loop"

    # Verify: structured error message contains diagnostic info
    error_msg = str(exc_info.value)
    assert "Time sync failed after retry" in error_msg, "Expected structured error message"
    assert "timestamp=" in error_msg, "Expected timestamp in error"
    assert "offset=" in error_msg, "Expected offset in error"
    assert "recvWindow=" in error_msg, "Expected recvWindow in error"


@pytest.mark.asyncio
async def test_recvwindow_is_5000ms(adapter):
    """
    EXEC-R2-J: Verify recvWindow is 5000ms (conservative, from EP-ADAPTER-TIME-SYNC-FIX-S20).

    Scenario:
    1. Inspect _get_signed_params to ensure recvWindow = 5000
    2. Place mock order to verify recvWindow in request params

    Expected: recvWindow = 5000ms in all signed requests
    """
    # Mock HTTP client to capture params
    captured_params = []

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Capture params from post call
        async def capture_post(url, params=None, **kwargs):
            captured_params.append(params)
            response = MagicMock()
            response.is_success = True
            response.status_code = 200
            response.json.return_value = {
                "orderId": 999,
                "symbol": "BTCUSDT",
                "status": "NEW",
            }
            return response

        mock_client.post = AsyncMock(side_effect=capture_post)

        # Place order to trigger signed request
        await adapter._place_binance_order_async(
            symbol="BTCUSDT",
            side="BUY",
            quantity="0.01",
            order_type="MARKET",
        )

    # Verify: recvWindow in captured params
    assert len(captured_params) > 0, "Expected at least one HTTP call"
    params = captured_params[0]
    assert "recvWindow" in params, "Expected recvWindow in params"
    assert params["recvWindow"] == "5000", f"Expected recvWindow=5000, got {params['recvWindow']}"


@pytest.mark.asyncio
async def test_time_sync_warnings_only_on_material_change(monkeypatch, caplog, adapter):
    """Verify time drift WARNs trigger only for material changes or hard-limit breaches."""

    offsets = deque([1_000, 1_200, 15_000])  # ms deltas for sequential syncs

    class StubAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            if not offsets:
                raise RuntimeError("No offsets left")
            offset_ms = offsets.popleft()
            resp = MagicMock()
            resp.is_success = True
            resp.status_code = 200
            resp.json.return_value = {
                "serverTime": int(time.time() * 1000) + offset_ms,
            }
            return resp

    monkeypatch.setattr(
        "apps.reference.domains.execution_position.binance_execution_adapter.httpx.AsyncClient",
        lambda *args, **kwargs: StubAsyncClient(),
    )

    caplog.set_level(logging.WARNING)
    await adapter._sync_time_with_server()
    await adapter._sync_time_with_server()
    await adapter._sync_time_with_server()

    warnings = [
        rec for rec in caplog.records if "Time drift" in rec.getMessage()]
    assert len(
        warnings) == 1, "Expected a single warning when drift jumps materially"


@pytest.mark.asyncio
async def test_get_open_orders_empty_response_returns_immediately(monkeypatch, adapter):
    """Empty openOrders response should not trigger retries or errors."""

    adapter.shadow_mode = False
    adapter._sync_time_with_server = AsyncMock()
    call_counter = {"count": 0}

    class EmptyResponseClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            call_counter["count"] += 1
            resp = MagicMock()
            resp.is_success = True
            resp.status_code = 200
            resp.json.return_value = []
            return resp

    monkeypatch.setattr(
        "apps.reference.domains.execution_position.binance_execution_adapter.httpx.AsyncClient",
        lambda *a, **k: EmptyResponseClient(),
    )

    orders = await adapter.get_open_orders(symbol="BTCUSDT")
    assert orders == []
    assert call_counter["count"] == 1, "Empty response should not trigger retries"


@pytest.mark.asyncio
async def test_get_open_orders_retries_then_raises(monkeypatch, adapter):
    """Adapter should retry transient failures up to the canonical limit and then raise."""

    adapter.shadow_mode = False
    adapter._sync_time_with_server = AsyncMock()

    class DummyGuard:
        def __init__(self):
            self.reasons = []

        def enter_fallback_mode(self, reason):
            self.reasons.append(reason)

    adapter.fsm = type("FSM", (), {"exposure_guard": DummyGuard()})()

    call_counter = {"count": 0}

    class ErrorResponseClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            call_counter["count"] += 1
            resp = MagicMock()
            resp.is_success = False
            resp.status_code = 500
            resp.text = "boom"
            return resp

    monkeypatch.setattr(
        "apps.reference.domains.execution_position.binance_execution_adapter.httpx.AsyncClient",
        lambda *a, **k: ErrorResponseClient(),
    )

    with pytest.raises(RuntimeError) as excinfo:
        await adapter.get_open_orders(symbol="ETHUSDT")

    assert "ADAPTER_GET_OPEN_ORDERS_FAILED" in str(excinfo.value)
    assert call_counter["count"] == GET_OPEN_ORDERS_MAX_ATTEMPTS
    assert adapter.fsm.exposure_guard.reasons == [
        GET_OPEN_ORDERS_FALLBACK_REASON]


@pytest.mark.asyncio
async def test_get_open_orders_timesync_1021_enters_fallback_and_returns_empty(monkeypatch, adapter):
    """
    Timestamp/recvWindow (-1021) errors on openOrders should enter fallback mode
    but return an empty list instead of raising, so runtime can proceed with a
    conservative mirror (no open orders).
    """

    adapter.shadow_mode = False
    adapter._sync_time_with_server = AsyncMock()

    class DummyGuard:
        def __init__(self):
            self.reasons = []

        def enter_fallback_mode(self, reason):
            self.reasons.append(reason)

    adapter.fsm = type("FSM", (), {"exposure_guard": DummyGuard()})()

    call_counter = {"count": 0}

    class TimestampErrorClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            call_counter["count"] += 1
            resp = MagicMock()
            resp.is_success = False
            resp.status_code = 400
            resp.text = '{"code":-1021,"msg":"Timestamp for this request is outside of the recvWindow."}'
            resp.json.return_value = {
                "code": -1021,
                "msg": "Timestamp for this request is outside of the recvWindow.",
            }
            return resp

    monkeypatch.setattr(
        "apps.reference.domains.execution_position.binance_execution_adapter.httpx.AsyncClient",
        lambda *a, **k: TimestampErrorClient(),
    )

    # Should NOT raise; instead, fallback mode is entered and [] returned
    orders = await adapter.get_open_orders(symbol="ETHUSDT")

    assert orders == []
    assert call_counter["count"] == GET_OPEN_ORDERS_MAX_ATTEMPTS
    assert adapter.fsm.exposure_guard.reasons == ["API_ORDERS_TIME_SYNC_FAILED"]
