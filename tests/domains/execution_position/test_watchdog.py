import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal

from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog, OrderTimeoutType, OrderDeadline
from apps.reference.core.time import get_clock


@pytest.fixture
def watchdog():
    wd = OrderTimeoutWatchdog(
        config={"ack_ttl_ms": 1000, "fill_ttl_ms": 5000, "check_interval_ms": 100, "rps_limit": 5}
    )
    return wd


def test_watchdog_init_and_start_stop(watchdog):
    assert watchdog.ack_ttl_ms == 1000
    assert watchdog.fill_ttl_ms == 5000
    assert not watchdog._started
    
    # Start without loop should be deferred safely
    watchdog.start()
    assert not watchdog._started
    
    # Late start without loop should be deferred
    watchdog.ensure_started()
    assert not watchdog._started
    
    # Stop should be safe
    watchdog.stop()


@pytest.mark.asyncio
async def test_watchdog_start_with_loop(watchdog):
    watchdog.start()
    assert watchdog._started
    assert watchdog._watchdog_task is not None
    
    watchdog.stop()
    assert not watchdog._started
    await asyncio.sleep(0) # let task cancel


@pytest.mark.asyncio
async def test_watchdog_disable(watchdog):
    watchdog.disable()
    assert not watchdog._enabled
    watchdog.start()
    assert not watchdog._started


def test_watchdog_track_and_ack(watchdog):
    with patch("apps.reference.domains.execution_position.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10000
        
        watchdog.track_order_placed("o1", "c1", "BTCUSDT")
        assert "o1" in watchdog.pending_orders
        
        deadline = watchdog.pending_orders["o1"]
        assert deadline.timeout_type == OrderTimeoutType.ACK_TIMEOUT
        assert deadline.deadline_ms == 11000 # 10000 + 1000
        
        # Ack it
        watchdog.on_order_ack("o1")
        assert "o1" not in watchdog.pending_orders
        assert "o1" in watchdog.acked_orders
        
        ack_deadline = watchdog.acked_orders["o1"]
        assert ack_deadline.timeout_type == OrderTimeoutType.FILL_TIMEOUT
        assert ack_deadline.deadline_ms == 15000 # 10000 + 5000


def test_watchdog_track_override_ttl(watchdog):
    with patch("apps.reference.domains.execution_position.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10000
        watchdog.track_order_placed("o1", "c1", "BTCUSDT", fill_ttl_override_ms=20000)
        watchdog.on_order_ack("o1")
        assert watchdog.acked_orders["o1"].deadline_ms == 30000 # 10000 + 20000


def test_watchdog_on_fill(watchdog):
    watchdog.pending_orders["o1"] = OrderDeadline("o1", "c1", "BTCUSDT", 0, OrderTimeoutType.ACK_TIMEOUT)
    watchdog.acked_orders["o2"] = OrderDeadline("o2", "c2", "BTCUSDT", 0, OrderTimeoutType.FILL_TIMEOUT)
    
    watchdog._poll_meta["o1"] = {}
    
    # Fill pending
    watchdog.on_order_fill("o1")
    assert "o1" not in watchdog.pending_orders
    assert "o1" not in watchdog._poll_meta
    
    # Fill acked
    watchdog.on_order_fill("o2")
    assert "o2" not in watchdog.acked_orders


def test_watchdog_on_cancel(watchdog):
    watchdog.pending_orders["o1"] = OrderDeadline("o1", "c1", "BTCUSDT", 0, OrderTimeoutType.ACK_TIMEOUT)
    watchdog._poll_meta["o1"] = {}
    
    watchdog.on_order_cancel("o1")
    assert "o1" not in watchdog.pending_orders
    assert "o1" not in watchdog._poll_meta


@pytest.mark.asyncio
async def test_watchdog_timeout_handling(watchdog):
    cb = MagicMock()
    watchdog.on_timeout_callback = cb
    
    with patch("apps.reference.domains.execution_position.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 20000
        
        # pending o1 expired at 10000
        watchdog.pending_orders["o1"] = OrderDeadline("o1", "c1", "BTC", 10000, OrderTimeoutType.ACK_TIMEOUT)
        
        # acked o2 not expired at 30000
        watchdog.acked_orders["o2"] = OrderDeadline("o2", "c2", "ETH", 30000, OrderTimeoutType.FILL_TIMEOUT)
        
        await watchdog._check_timeouts()
        
        # o1 should be removed
        assert "o1" not in watchdog.pending_orders
        assert "o2" in watchdog.acked_orders
        
        assert watchdog.timeout_count == 1
        cb.assert_called_once()
        assert cb.call_args[0][0].order_id == "o1"


@pytest.mark.asyncio
async def test_poll_order_statuses_filled(watchdog):
    get_order_fn = AsyncMock(return_value={"status": "FILLED", "executedQty": 1.0, "avgPrice": 50000, "clientOrderId": "c1"})
    emit_fn = AsyncMock()
    watchdog.set_hooks(get_order_fn, emit_fn)
    
    watchdog.pending_orders["o1"] = OrderDeadline("o1", "c1", "BTC", 30000, OrderTimeoutType.ACK_TIMEOUT)
    
    with patch("apps.reference.domains.execution_position.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10000
        
        # Poll should happen because next_poll_at is 0
        await watchdog._poll_order_statuses()
        
        get_order_fn.assert_called_once_with("BTC", "o1")
        emit_fn.assert_called_once_with("EVT:TRADE_EXECUTED", {
            "orderId": "o1", "symbol": "BTC", "quantity": 1.0, 
            "price": 50000.0, "client_order_id": "c1", "rid": None
        })
        
        # Should mark handled
        assert "o1" not in watchdog.pending_orders
        assert watchdog._poll_meta["o1"]["terminal"] is True


@pytest.mark.asyncio
async def test_poll_order_statuses_cancelled(watchdog):
    get_order_fn = AsyncMock(return_value={"status": "CANCELED", "clientOrderId": "c1"})
    emit_fn = AsyncMock()
    watchdog.set_hooks(get_order_fn, emit_fn)
    
    watchdog.acked_orders["o2"] = OrderDeadline("o2", "c1", "BTC", 30000, OrderTimeoutType.FILL_TIMEOUT)
    
    with patch("apps.reference.domains.execution_position.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10000
        
        await watchdog._poll_order_statuses()
        
        emit_fn.assert_called_once_with("EVT:ORDER_STATE_CHANGED", {
            "orderId": "o2", "symbol": "BTC", "status": "CANCELED", "client_order_id": "c1", "rid": None
        })
        
        assert "o2" not in watchdog.acked_orders
        assert watchdog._poll_meta["o2"]["terminal"] is True


@pytest.mark.asyncio
async def test_poll_order_statuses_backoff(watchdog):
    get_order_fn = AsyncMock(return_value={"status": "NEW"})
    emit_fn = AsyncMock()
    watchdog.set_hooks(get_order_fn, emit_fn)
    
    watchdog.pending_orders["o1"] = OrderDeadline("o1", "c1", "BTC", 30000, OrderTimeoutType.ACK_TIMEOUT)
    
    with patch("apps.reference.domains.execution_position.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10000
        
        await watchdog._poll_order_statuses()
        
        assert watchdog._poll_meta["o1"]["attempts"] == 1
        assert watchdog._poll_meta["o1"]["backoff_ms"] == 2000
        assert watchdog._poll_meta["o1"]["next_poll_at"] == 12000
        
        # Immediate second poll should be skipped due to backoff
        get_order_fn.reset_mock()
        await watchdog._poll_order_statuses()
        assert get_order_fn.call_count == 0


@pytest.mark.asyncio
async def test_poll_order_statuses_rps_limit(watchdog):
    get_order_fn = AsyncMock(return_value={"status": "NEW"})
    emit_fn = AsyncMock()
    watchdog.set_hooks(get_order_fn, emit_fn)
    
    # We set rps_limit = 2 for tracking
    watchdog._rps_limit = 2
    
    watchdog.pending_orders["o1"] = OrderDeadline("o1", "c1", "BTC", 30000, OrderTimeoutType.ACK_TIMEOUT)
    watchdog.pending_orders["o2"] = OrderDeadline("o2", "c2", "ETH", 30000, OrderTimeoutType.ACK_TIMEOUT)
    watchdog.pending_orders["o3"] = OrderDeadline("o3", "c3", "LTC", 30000, OrderTimeoutType.ACK_TIMEOUT)
    
    with patch("apps.reference.domains.execution_position.watchdog.get_clock") as mock_clock:
        mock_clock.return_value.now_ms.return_value = 10500 # within same second
        
        await watchdog._poll_order_statuses()
        
        # Only 2 out of 3 should have been polled
        assert get_order_fn.call_count == 2
        assert watchdog._rps_throttle_hits == 1
