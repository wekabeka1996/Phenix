import pytest
import asyncio
import time
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog, OrderDeadline, OrderTimeoutType


@pytest.fixture
def watchdog():
    wd = OrderTimeoutWatchdog(check_interval_ms=100)
    return wd


@pytest.fixture
def mock_get_order():
    return AsyncMock()


@pytest.fixture
def mock_emit():
    return AsyncMock()


@pytest.mark.asyncio
async def test_set_hooks(watchdog, mock_get_order, mock_emit):
    watchdog.set_hooks(mock_get_order, mock_emit)
    assert watchdog.get_order_fn == mock_get_order
    assert watchdog.emit_fn == mock_emit


def test_check_rps_limit(watchdog):
    watchdog._rps_limit = 5
    watchdog._rps_window_start = 0

    # Mock time to be constant
    with patch("time.time", return_value=1000.0):
        # First 5 requests should pass
        for _ in range(5):
            assert watchdog._check_rps_limit() is True

        # 6th request should fail
        assert watchdog._check_rps_limit() is False

    # Move time forward
    with patch("time.time", return_value=1001.0):
        # Should be allowed again
        assert watchdog._check_rps_limit() is True


@pytest.mark.asyncio
async def test_poll_order_statuses_no_hooks(watchdog):
    # Should do nothing without hooks
    watchdog.pending_orders["order1"] = MagicMock()
    await watchdog._poll_order_statuses()
    # No error, just return


@pytest.mark.asyncio
async def test_poll_order_statuses_no_orders(watchdog, mock_get_order, mock_emit):
    watchdog.set_hooks(mock_get_order, mock_emit)
    await watchdog._poll_order_statuses()
    mock_get_order.assert_not_called()


@pytest.mark.asyncio
async def test_poll_order_statuses_backoff(watchdog, mock_get_order, mock_emit):
    watchdog.set_hooks(mock_get_order, mock_emit)
    watchdog.track_order_placed("order1", "client1", "BTCUSDT")

    # Set next poll time to future
    future_time = (time.time() * 1000) + 5000
    watchdog._poll_meta["order1"] = {
        "next_poll_at": future_time,
        "attempts": 0,
        "backoff_ms": 1000
    }

    await watchdog._poll_order_statuses()
    mock_get_order.assert_not_called()


@pytest.mark.asyncio
async def test_poll_order_statuses_filled(watchdog, mock_get_order, mock_emit):
    watchdog.set_hooks(mock_get_order, mock_emit)
    watchdog.track_order_placed("order1", "client1", "BTCUSDT")

    # Mock order status response
    mock_get_order.return_value = {
        "status": "FILLED",
        "executedQty": "1.0",
        "avgPrice": "50000.0",
        "clientOrderId": "client1",
        "side": "BUY"
    }

    await watchdog._poll_order_statuses()

    mock_get_order.assert_called_with("BTCUSDT", "order1")
    mock_emit.assert_called_once()
    args, _ = mock_emit.call_args
    assert args[0] == "EVT:TRADE_EXECUTED"
    assert args[1]["orderId"] == "order1"
    assert args[1]["quantity"] == "1.0"

    # Verify meta updated
    meta = watchdog._poll_meta["order1"]
    assert meta["terminal"] is True
    assert meta["attempts"] == 0


@pytest.mark.asyncio
async def test_poll_order_statuses_canceled(watchdog, mock_get_order, mock_emit):
    watchdog.set_hooks(mock_get_order, mock_emit)
    watchdog.track_order_placed("order1", "client1", "BTCUSDT")

    mock_get_order.return_value = {
        "status": "CANCELED",
        "executedQty": "0.0",
        "clientOrderId": "client1"
    }

    await watchdog._poll_order_statuses()

    mock_emit.assert_called_once()
    args, _ = mock_emit.call_args
    assert args[0] == "EVT:ORDER_STATE_CHANGED"
    assert args[1]["status"] == "CANCELED"

    # Verify removed from tracking
    assert "order1" not in watchdog.pending_orders


@pytest.mark.asyncio
async def test_poll_order_statuses_pending_backoff(watchdog, mock_get_order, mock_emit):
    watchdog.set_hooks(mock_get_order, mock_emit)
    watchdog.track_order_placed("order1", "client1", "BTCUSDT")

    mock_get_order.return_value = {
        "status": "NEW",
        "executedQty": "0.0"
    }

    # Initial backoff default is 1000

    await watchdog._poll_order_statuses()

    meta = watchdog._poll_meta["order1"]
    assert meta["attempts"] == 1
    assert meta["backoff_ms"] == 2000  # Doubled


@pytest.mark.asyncio
async def test_poll_order_statuses_not_found(watchdog, mock_get_order, mock_emit):
    watchdog.set_hooks(mock_get_order, mock_emit)
    watchdog.track_order_placed("order1", "client1", "BTCUSDT")

    mock_get_order.return_value = None

    await watchdog._poll_order_statuses()

    # Should treat as canceled/terminal
    meta = watchdog._poll_meta["order1"]
    assert meta["terminal"] is True
    assert "order1" not in watchdog.pending_orders


@pytest.mark.asyncio
async def test_poll_order_statuses_exception(watchdog, mock_get_order, mock_emit):
    watchdog.set_hooks(mock_get_order, mock_emit)
    watchdog.track_order_placed("order1", "client1", "BTCUSDT")

    mock_get_order.side_effect = Exception("API Error")

    await watchdog._poll_order_statuses()

    meta = watchdog._poll_meta["order1"]
    assert meta["attempts"] == 1
    assert meta["backoff_ms"] == 2000


def test_build_trade_payload(watchdog):
    order_status = {
        "clientOrderId": "client1",
        "side": "SELL",
        "executedQty": "0.5",
        "avgPrice": "50000.0",
        "updateTime": 1234567890
    }

    payload = watchdog._build_trade_payload(
        symbol="BTCUSDT",
        order_id="order1",
        order_status=order_status,
        executed_qty=Decimal("0.5")
    )

    assert payload["orderId"] == "order1"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["side"] == "sell"
    assert payload["quantity"] == "-0.5"  # Sell side negative
    assert payload["price"] == "50000.0"
    assert payload["ts"] == 1234567890


def test_build_trade_payload_price_fallback(watchdog):
    order_status = {
        "cummulativeQuoteQty": "100.0",
        "executedQty": "2.0",
        "avgPrice": "0"
    }

    payload = watchdog._build_trade_payload(
        symbol="BTCUSDT",
        order_id="order1",
        order_status=order_status,
        executed_qty=Decimal("2.0")
    )

    assert payload["price"] == "50.0"  # 100 / 2


@pytest.mark.asyncio
async def test_emit_via_hook_missing(watchdog):
    # Should handle missing emit_fn gracefully
    watchdog.emit_fn = None
    await watchdog._emit_via_hook("TEST", {}, "LOG_MSG")
    # No exception


@pytest.mark.asyncio
async def test_emit_via_hook_exception(watchdog, mock_emit):
    watchdog.emit_fn = mock_emit
    mock_emit.side_effect = Exception("Emit Error")

    # Should catch exception and log
    await watchdog._emit_via_hook("TEST", {}, "LOG_MSG")
    mock_emit.assert_called_once()


@pytest.mark.asyncio
async def test_lifecycle(watchdog):
    # Test start/stop
    watchdog.start()
    assert watchdog._started is True
    assert watchdog._watchdog_task is not None

    watchdog.stop()
    assert watchdog._started is False
    assert watchdog._watchdog_task is None


@pytest.mark.asyncio
async def test_ensure_started(watchdog):
    watchdog.ensure_started()
    assert watchdog._started is True
    task1 = watchdog._watchdog_task

    # Call again, should be idempotent
    watchdog.ensure_started()
    assert watchdog._watchdog_task is task1

    watchdog.stop()


@pytest.mark.asyncio
async def test_check_timeouts_ack(watchdog):
    # Setup callback
    callback = MagicMock()
    watchdog.on_timeout_callback = callback

    # Track order with short TTL
    watchdog.ack_ttl_ms = 100
    watchdog.track_order_placed("order1", "client1", "BTCUSDT")

    # Verify pending
    assert "order1" in watchdog.pending_orders

    # Wait for timeout
    with patch("time.time", return_value=time.time() + 1.0):
        await watchdog._check_timeouts()

    # Verify timeout handled
    assert "order1" not in watchdog.pending_orders
    callback.assert_called_once()
    deadline = callback.call_args[0][0]
    assert deadline.order_id == "order1"
    assert deadline.timeout_type == OrderTimeoutType.ACK_TIMEOUT


@pytest.mark.asyncio
async def test_check_timeouts_fill(watchdog):
    callback = MagicMock()
    watchdog.on_timeout_callback = callback

    watchdog.fill_ttl_ms = 100
    watchdog.track_order_placed("order1", "client1", "BTCUSDT")
    watchdog.on_order_ack("order1")

    assert "order1" in watchdog.acked_orders

    with patch("time.time", return_value=time.time() + 1.0):
        await watchdog._check_timeouts()

    assert "order1" not in watchdog.acked_orders
    callback.assert_called_once()
    deadline = callback.call_args[0][0]
    assert deadline.timeout_type == OrderTimeoutType.FILL_TIMEOUT


@pytest.mark.asyncio
async def test_handle_timeout_async_callback(watchdog):
    async_callback = AsyncMock()
    watchdog.on_timeout_callback = async_callback

    deadline = OrderDeadline(
        order_id="order1",
        client_order_id="client1",
        symbol="BTCUSDT",
        deadline_ms=0,
        timeout_type=OrderTimeoutType.ACK_TIMEOUT
    )
    watchdog.pending_orders["order1"] = deadline

    await watchdog._handle_timeout(deadline)

    async_callback.assert_called_once_with(deadline)
    assert "order1" not in watchdog.pending_orders


def test_get_metrics(watchdog):
    watchdog.track_order_placed("order1", "client1", "BTCUSDT")
    watchdog.timeout_count = 5

    metrics = watchdog.get_metrics()

    assert metrics["pending_orders_count"] == 1
    assert metrics["total_timeouts"] == 5
    assert metrics["rest_polls_total"] == 0


@pytest.mark.asyncio
async def test_watchdog_loop_runs(watchdog):
    # Test that loop runs and calls check_timeouts
    watchdog.check_interval_ms = 10
    watchdog._check_timeouts = AsyncMock()

    watchdog.start()
    await asyncio.sleep(0.05)
    watchdog.stop()

    assert watchdog._check_timeouts.call_count >= 1


@pytest.mark.asyncio
async def test_watchdog_loop_handles_exception(watchdog):
    watchdog.check_interval_ms = 10
    # Side effect: raise exception once, then run normally
    watchdog._check_timeouts = AsyncMock(
        side_effect=[Exception("Loop Error"), None, None, None])

    # Patch logger to avoid traceback printing issues
    with patch("apps.reference.domains.execution_position.watchdog.LOG") as mock_log:
        watchdog.start()
        await asyncio.sleep(0.05)
        watchdog.stop()

        # Wait a bit for the task to cancel
        await asyncio.sleep(0.01)

    # Should continue running after exception
    assert watchdog._check_timeouts.call_count >= 2
    # Verify error was logged
    mock_log.error.assert_called()


def test_watchdog_accepts_timeout_config():
    class TimeoutCfg:
        ack_ttl_ms = 1500
        fill_ttl_ms = 4500
        check_interval_ms = 250
        source = "unit.test.timeouts"

    watchdog = OrderTimeoutWatchdog(timeout_config=TimeoutCfg())

    assert watchdog.ack_ttl_ms == 1500
    assert watchdog.fill_ttl_ms == 4500
    assert watchdog.check_interval_ms == 250
    assert watchdog.timeout_source == "unit.test.timeouts"


def test_watchdog_update_timeouts_runtime():
    watchdog = OrderTimeoutWatchdog()

    watchdog.update_timeouts(
        ack_ttl_ms=2222,
        fill_ttl_ms=3333,
        check_interval_ms=444,
        source="runtime.override",
    )

    assert watchdog.ack_ttl_ms == 2222
    assert watchdog.fill_ttl_ms == 3333
    assert watchdog.check_interval_ms == 444

    metrics = watchdog.get_metrics()
    assert metrics["timeout_source"] == "runtime.override"
