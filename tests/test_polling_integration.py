"""
Integration test for polling-based bracket placement.
Tests full flow: track_order → polling detects FILLED → FSM places brackets.
"""
import asyncio
import logging
from unittest.mock import AsyncMock, Mock, patch
import pytest

logging.basicConfig(level=logging.INFO)


@pytest.mark.asyncio
async def test_polling_detects_fill_and_triggers_brackets():
    """Test that polling loop detects FILLED order and triggers bracket placement."""

    # Import after path setup
    from apps.reference.adapters.binance_adapter import BinanceAdapter
    from vfoundation.core.protocol import Message

    # Mock FSM
    mock_fsm = Mock()
    mock_fsm.handle = Mock(return_value=None)

    # Create adapter
    adapter = BinanceAdapter(
        api_key="test_key",
        api_secret="test_secret",
        base_url="https://testnet.binancefuture.com"
    )
    adapter.fsm_core = mock_fsm
    adapter.exec_fsm = mock_fsm  # Set exec_fsm for polling to call handle

    # Mock REST API responses
    async def mock_get_open_orders(symbol):
        # First call: order exists
        if not hasattr(mock_get_open_orders, 'call_count'):
            mock_get_open_orders.call_count = 0
        mock_get_open_orders.call_count += 1

        if mock_get_open_orders.call_count == 1:
            return [{"orderId": "12345", "symbol": "BTCUSDT", "status": "NEW"}]
        else:
            # Second call: order disappeared (filled)
            return []

    async def mock_get_order_status(symbol, order_id):
        return "FILLED", {"status": "FILLED", "orderId": order_id, "symbol": symbol}

    adapter.get_open_orders = mock_get_open_orders
    adapter._get_order_status = mock_get_order_status

    # Start polling
    adapter._polling_active = True

    # Track an order
    order_response = {
        "orderId": "12345",
        "symbol": "BTCUSDT",
        "status": "NEW",
        "clientOrderId": "test_client_id",
        "side": "BUY",
        "positionSide": "LONG",
        "type": "MARKET",
        "origQty": "0.001"
    }
    adapter.track_order(order_response)

    # Wait for 1 polling cycle (should start on track_order)
    assert adapter._polling_task is not None, "Polling task should be created"

    # Wait for polling to detect fill
    await asyncio.sleep(0.8)  # 2 polling cycles + processing time

    # Cancel polling
    adapter.stop()

    # Verify FSM.handle() was called with TRADE_EXECUTED
    assert mock_fsm.handle.called, "FSM.handle() should be called"
    call_args = mock_fsm.handle.call_args[0][0]

    assert isinstance(call_args, Message), "Should pass Message object"
    assert call_args.verb == "TRADE_EXECUTED", "Verb should be TRADE_EXECUTED"
    assert call_args.pld["symbol"] == "BTCUSDT", "Symbol should match"
    assert call_args.pld["status"] == "FILLED", "Status should be FILLED"

    print("✅ Polling integration test PASSED")


@pytest.mark.asyncio
async def test_polling_handles_cancelled_orders():
    """Test that polling doesn't emit events for cancelled non-entry orders."""

    from apps.reference.adapters.binance_adapter import BinanceAdapter

    # Mock FSM
    mock_fsm = Mock()
    mock_fsm.handle = Mock(return_value=None)
    mock_order_guardian = Mock()
    mock_order_guardian.cleanup_orphans = AsyncMock()
    mock_fsm.order_guardian = mock_order_guardian

    # Create adapter
    adapter = BinanceAdapter(
        api_key="test_key",
        api_secret="test_secret",
        base_url="https://testnet.binancefuture.com"
    )
    adapter.fsm_core = mock_fsm
    adapter.exec_fsm = mock_fsm  # Set exec_fsm for polling

    # Mock REST responses - order cancelled
    async def mock_get_open_orders(symbol):
        return []  # Order disappeared

    async def mock_get_order_status(symbol, order_id):
        return "CANCELED", {"status": "CANCELED", "orderId": order_id, "symbol": symbol}

    adapter.get_open_orders = mock_get_open_orders
    adapter._get_order_status = mock_get_order_status

    # Track NON-ENTRY order (should not trigger cleanup)
    adapter._polling_active = True
    order_response = {
        "orderId": "12345",
        "symbol": "BTCUSDT",
        "status": "NEW",
        "clientOrderId": "SL_123457",  # SL prefix - not ENTRY
        "side": "BUY",
        "positionSide": "LONG",
        "type": "MARKET",
        "origQty": "0.001"
    }
    adapter.track_order(order_response)

    # Wait for polling
    await asyncio.sleep(0.8)
    adapter.stop()

    # FSM.handle() should NOT be called for cancelled orders
    assert not mock_fsm.handle.called, "FSM.handle() should NOT be called for cancelled orders"

    # cleanup_orphans should NOT be called for cancelled orders (only for FILLED orders)
    mock_order_guardian.cleanup_orphans.assert_not_called()

    print("✅ Cancelled non-entry order handling test PASSED")


@pytest.mark.asyncio
async def test_polling_cancels_brackets_on_entry_cancelled():
    """Test that polling cancels TP/SL brackets when entry order is cancelled."""

    from apps.reference.adapters.binance_adapter import BinanceAdapter

    # Mock FSM
    mock_fsm = Mock()
    mock_fsm.handle = Mock(return_value=None)
    mock_order_guardian = Mock()
    mock_order_guardian.cleanup_orphans = AsyncMock()
    mock_fsm.order_guardian = mock_order_guardian

    # Create adapter
    adapter = BinanceAdapter(
        api_key="test_key",
        api_secret="test_secret",
        base_url="https://testnet.binancefuture.com"
    )
    adapter.fsm_core = mock_fsm
    adapter.exec_fsm = mock_fsm  # Set exec_fsm for polling

    # Mock REST responses - entry order cancelled
    async def mock_get_open_orders(symbol):
        return []  # Order disappeared

    async def mock_get_order_status(symbol, order_id):
        return "CANCELED", {"status": "CANCELED", "orderId": order_id, "symbol": symbol}

    adapter.get_open_orders = mock_get_open_orders
    adapter._get_order_status = mock_get_order_status

    # Track ENTRY order (this should trigger cleanup)
    adapter._polling_active = True
    order_response = {
        "orderId": "12345",
        "symbol": "BTCUSDT",
        "status": "NEW",
        "clientOrderId": "ENTRY_123456",  # ENTRY prefix triggers cleanup
        "side": "BUY",
        "positionSide": "LONG",
        "type": "MARKET",
        "origQty": "0.001"
    }
    adapter.track_order(order_response)

    # Wait for polling
    await asyncio.sleep(0.8)
    adapter.stop()

    # FSM.handle() should NOT be called for cancelled orders
    assert not mock_fsm.handle.called, "FSM.handle() should NOT be called for cancelled orders"

    # cleanup_orphans should be called (no symbol parameter needed)
    mock_order_guardian.cleanup_orphans.assert_called_once()

    print("✅ Entry cancelled bracket cleanup test PASSED")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
