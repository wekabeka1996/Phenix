import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock
from apps.reference.domains.execution_position.watchdog import OrderTimeoutWatchdog, OrderTimeoutType

@pytest.mark.asyncio
async def test_watchdog_polling_stops_timeout_fix():
    """
    Verify that detecting a fill via REST polling immediately stops timeout tracking.
    This test confirms the fix for the issue where orders were cancelled due to timeout
    even after being detected as filled by the polling mechanism.
    """
    # 1. Setup Watchdog
    # Short TTLs for testing
    watchdog = OrderTimeoutWatchdog(
        ack_ttl_ms=1000,
        fill_ttl_ms=2000,
        check_interval_ms=100
    )
    
    # Mock callbacks
    mock_get_order = AsyncMock()
    mock_emit = AsyncMock()
    mock_timeout_callback = MagicMock()
    
    watchdog.set_hooks(get_order_fn=mock_get_order, emit_fn=mock_emit)
    watchdog.on_timeout_callback = mock_timeout_callback
    
    # 2. Track an order
    order_id = "test_order_fix_1"
    symbol = "ETHUSDT"
    
    # Simulate placing order
    watchdog.track_order_placed(order_id, "client_id_1", symbol)
    
    # Simulate ACK received -> moves to acked_orders (tracking FILL timeout)
    watchdog.on_order_ack(order_id)
    
    # Verify it is being tracked
    assert order_id in watchdog.acked_orders
    assert order_id not in watchdog.pending_orders
    
    # 3. Simulate REST Polling detecting a FILL
    # This simulates the scenario where WebSocket missed the fill, but REST found it.
    mock_get_order.return_value = {
        "status": "FILLED",
        "executedQty": "0.053",
        "avgPrice": "3000.00",
        "clientOrderId": "client_id_1"
    }
    
    # Force a poll check manually (bypassing the loop for deterministic testing)
    await watchdog._poll_order_statuses()
    
    # 4. Verification of the FIX
    
    # A. Check that emit_fn was called (EVT:TRADE_EXECUTED)
    mock_emit.assert_called_once()
    args = mock_emit.call_args[0]
    assert args[0] == "EVT:TRADE_EXECUTED"
    assert args[1]["orderId"] == order_id
    assert args[1]["quantity"] == 0.053
    
    # B. CRITICAL ASSERTION: Check that order is REMOVED from tracking
    # Before the fix, this would fail because the order remained in acked_orders
    assert order_id not in watchdog.acked_orders, "Order should be removed from acked_orders after polling detects fill"
    assert order_id not in watchdog.pending_orders
    
    # 5. Verify no timeout occurs
    # Simulate time passing beyond the fill_ttl
    # We manually call _check_timeouts which would trigger the callback if the order was still tracked
    
    # Fast forward time (conceptually, though we just check the list is empty)
    await watchdog._check_timeouts()
    
    # Timeout callback should NOT have been called
    mock_timeout_callback.assert_not_called()

@pytest.mark.asyncio
async def test_watchdog_polling_idempotency():
    """
    Verify that subsequent polls do not re-process the same filled order.
    """
    watchdog = OrderTimeoutWatchdog()
    mock_get_order = AsyncMock()
    mock_emit = AsyncMock()
    watchdog.set_hooks(get_order_fn=mock_get_order, emit_fn=mock_emit)
    
    order_id = "test_order_idem"
    watchdog.track_order_placed(order_id, "cid", "BTCUSDT")
    watchdog.on_order_ack(order_id)
    
    mock_get_order.return_value = {
        "status": "FILLED",
        "executedQty": "0.1",
        "avgPrice": "50000"
    }
    
    # First poll
    await watchdog._poll_order_statuses()
    assert mock_emit.call_count == 1
    assert order_id not in watchdog.acked_orders
    
    # Second poll (should skip because meta['terminal'] is True)
    await watchdog._poll_order_statuses()
    
    # Should still be 1, not 2
    assert mock_emit.call_count == 1
