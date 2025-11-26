"""
EXEC-R2-J: Tests for BinanceAdapter -4116 duplicate idempotency

Tests verify that -4116 (ClientOrderId is duplicated) error is handled idempotently:
1. If order exists with NEW/PARTIALLY_FILLED → return success (no new ID generation)
2. If order not found → return error (no retry)
3. If order exists but FILLED/CANCELED → return error (cannot recover)

CRITICAL: Tests verify NO new clientOrderId generation (previous behavior created duplicate TP/SL)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from apps.reference.domains.execution_position.binance_execution_adapter import (
    BinanceExecutionAdapter,
)


@pytest.fixture
def adapter():
    """Create BinanceExecutionAdapter with mocked credentials."""
    adapter = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )
    # Mock time sync to avoid actual API calls
    adapter._sync_time_with_server = AsyncMock()
    adapter.server_time_offset = 0
    return adapter


@pytest.mark.asyncio
async def test_duplicate_idempotent_success(adapter):
    """
    EXEC-R2-J: Test -4116 with order found in NEW status → idempotent success.

    Scenario:
    1. Attempt to place TP order → Binance returns -4116 duplicate error
    2. Adapter calls get_order_by_client_id → returns order with status=NEW
    3. Adapter returns success with existing order (NO new ID generation, NO retry)

    Expected: success=True, order data returned
    """
    symbol = "BTCUSDT"
    client_order_id = "TP_BTCUSDT_LONG_12345"
    existing_order = {
        "orderId": 987654321,
        "symbol": symbol,
        "status": "NEW",
        "clientOrderId": client_order_id,
        "price": "50000.0",
        "origQty": "0.01",
        "executedQty": "0.0",
    }

    # Mock get_order_by_client_id to return existing order with NEW status
    adapter.get_order_by_client_id = AsyncMock(return_value=existing_order)

    # Mock _handle_bracket_error to call real -4116 logic
    # Simulate -4116 error path by calling handler directly
    params = {
        "symbol": symbol,
        "clientOrderId": client_order_id,
        "side": "BUY",
        "type": "TAKE_PROFIT_MARKET",
        "quantity": "0.01",
        "stopPrice": "51000.0",
    }

    # Directly call -4116 handler logic (simulate error code path)
    with patch.object(adapter, "_get_signed_params", return_value=params):
        success, result = await adapter._handle_bracket_error(
            error_code=-4116,
            error_msg="ClientOrderId is duplicated",
            params=params,
            idempotent_key=client_order_id,
            client_order_id=client_order_id,
            url="https://testnet.binancefuture.com/fapi/v1/order",
            headers={"X-MBX-APIKEY": "test_key"},
        )

    # Verify: idempotent success
    assert success is True, "Expected success=True for duplicate with NEW status"
    assert result == existing_order, "Expected existing order data returned"

    # Verify: get_order_by_client_id was called with correct params
    adapter.get_order_by_client_id.assert_awaited_once_with(
        symbol, client_order_id)


@pytest.mark.asyncio
async def test_duplicate_order_not_found(adapter):
    """
    EXEC-R2-J: Test -4116 with order NOT FOUND → error (no retry).

    Scenario:
    1. Attempt to place TP order → Binance returns -4116 duplicate error
    2. Adapter calls get_order_by_client_id → returns None (order not found)
    3. Adapter returns error (cannot recover, no new ID generation)

    Expected: success=False, error logged
    """
    symbol = "ETHUSDT"
    client_order_id = "SL_ETHUSDT_SHORT_67890"

    # Mock get_order_by_client_id to return None (order not found)
    adapter.get_order_by_client_id = AsyncMock(return_value=None)

    params = {
        "symbol": symbol,
        "clientOrderId": client_order_id,
        "side": "SELL",
        "type": "STOP_MARKET",
        "quantity": "1.0",
        "stopPrice": "1800.0",
    }

    with patch.object(adapter, "_get_signed_params", return_value=params):
        success, result = await adapter._handle_bracket_error(
            error_code=-4116,
            error_msg="ClientOrderId is duplicated",
            params=params,
            idempotent_key=client_order_id,
            client_order_id=client_order_id,
            url="https://testnet.binancefuture.com/fapi/v1/order",
            headers={"X-MBX-APIKEY": "test_key"},
        )

    # Verify: error (cannot recover)
    assert success is False, "Expected success=False when order not found"
    assert result is None, "Expected None result on error"

    # Verify: get_order_by_client_id was called
    adapter.get_order_by_client_id.assert_awaited_once_with(
        symbol, client_order_id)


@pytest.mark.asyncio
async def test_duplicate_order_already_filled(adapter):
    """
    EXEC-R2-J: Test -4116 with order FILLED → error (cannot recover).

    Scenario:
    1. Attempt to place TP order → Binance returns -4116 duplicate error
    2. Adapter calls get_order_by_client_id → returns order with status=FILLED
    3. Adapter returns error (order already filled, cannot reuse)

    Expected: success=False, error logged
    """
    symbol = "SOLUSDT"
    client_order_id = "TP_SOLUSDT_LONG_11111"
    existing_order = {
        "orderId": 123123123,
        "symbol": symbol,
        "status": "FILLED",  # Already executed
        "clientOrderId": client_order_id,
        "price": "100.0",
        "origQty": "10.0",
        "executedQty": "10.0",
        "avgPrice": "100.5",
    }

    # Mock get_order_by_client_id to return FILLED order
    adapter.get_order_by_client_id = AsyncMock(return_value=existing_order)

    params = {
        "symbol": symbol,
        "clientOrderId": client_order_id,
        "side": "SELL",
        "type": "TAKE_PROFIT_MARKET",
        "quantity": "10.0",
        "stopPrice": "105.0",
    }

    with patch.object(adapter, "_get_signed_params", return_value=params):
        success, result = await adapter._handle_bracket_error(
            error_code=-4116,
            error_msg="ClientOrderId is duplicated",
            params=params,
            idempotent_key=client_order_id,
            client_order_id=client_order_id,
            url="https://testnet.binancefuture.com/fapi/v1/order",
            headers={"X-MBX-APIKEY": "test_key"},
        )

    # Verify: error (cannot recover from FILLED status)
    assert success is False, "Expected success=False when order status=FILLED"
    assert result is None, "Expected None result on error"

    # Verify: get_order_by_client_id was called
    adapter.get_order_by_client_id.assert_awaited_once_with(
        symbol, client_order_id)


@pytest.mark.asyncio
async def test_duplicate_order_partially_filled_success(adapter):
    """
    EXEC-R2-J: Test -4116 with PARTIALLY_FILLED → idempotent success.

    Scenario:
    1. Attempt to place bracket order → Binance returns -4116
    2. Adapter finds order with status=PARTIALLY_FILLED (still active)
    3. Adapter returns success (idempotent, order exists and active)

    Expected: success=True, order data returned
    """
    symbol = "BNBUSDT"
    client_order_id = "SL_BNBUSDT_SHORT_22222"
    existing_order = {
        "orderId": 555555555,
        "symbol": symbol,
        "status": "PARTIALLY_FILLED",
        "clientOrderId": client_order_id,
        "price": "300.0",
        "origQty": "5.0",
        "executedQty": "2.0",  # Partially executed
    }

    adapter.get_order_by_client_id = AsyncMock(return_value=existing_order)

    params = {
        "symbol": symbol,
        "clientOrderId": client_order_id,
        "side": "BUY",
        "type": "STOP_MARKET",
        "quantity": "5.0",
        "stopPrice": "295.0",
    }

    with patch.object(adapter, "_get_signed_params", return_value=params):
        success, result = await adapter._handle_bracket_error(
            error_code=-4116,
            error_msg="ClientOrderId is duplicated",
            params=params,
            idempotent_key=client_order_id,
            client_order_id=client_order_id,
            url="https://testnet.binancefuture.com/fapi/v1/order",
            headers={"X-MBX-APIKEY": "test_key"},
        )

    # Verify: idempotent success (PARTIALLY_FILLED is active)
    assert success is True, "Expected success=True for PARTIALLY_FILLED status"
    assert result == existing_order, "Expected existing order data"
    adapter.get_order_by_client_id.assert_awaited_once_with(
        symbol, client_order_id)
