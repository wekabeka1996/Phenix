import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError
from vfoundation.core.adapters.base import ExchangeOrderParams
from decimal import Decimal


@pytest.fixture
def adapter_with_cache():
    """Create adapter with pre-populated cache to avoid extra _request calls."""
    adapter = BinanceAdapter(api_key="test", api_secret="test")
    # Pre-populate cache so _get_symbol_filters doesn't call exchangeInfo
    adapter._exchange_info_cache = {
        "BTCUSDT": {
            "tick_size": Decimal("0.01"),
            "step_size": Decimal("0.001"),
            "timestamp": 9999999999.0,  # Far future
        }
    }
    return adapter


@pytest.mark.asyncio
async def test_create_order_recovers_duplicate_client_order_id(adapter_with_cache):
    """
    Test that create_order recovers from -4116 error by fetching the existing order.
    """
    # Setup
    adapter = adapter_with_cache
    adapter._request = AsyncMock()

    # Mock _request to raise -4116 on first call (POST), then return order on second call (GET)
    duplicate_error = BinanceAPIError(
        code=-4116, msg="ClientOrderId is duplicated")

    existing_order_response = {
        "orderId": "12345",
        "clientOrderId": "my_unique_id",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "origQty": "0.1",
        "executedQty": "0.0",
        "price": "50000",
        "status": "NEW",
        "time": 1600000000000
    }

    adapter._request.side_effect = [
        duplicate_error,      # POST /fapi/v1/order -> fails
        existing_order_response  # GET /fapi/v1/order -> succeeds
    ]

    params = ExchangeOrderParams(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="0.1",
        price="50000",
        client_order_id="my_unique_id"
    )

    # Execute
    response = await adapter.create_order(params)

    # Verify
    assert response.order_id == "12345"
    assert response.client_order_id == "my_unique_id"
    assert response.status == "NEW"

    # Verify calls
    assert adapter._request.call_count == 2

    # Check first call (POST)
    call1 = adapter._request.call_args_list[0]
    assert call1[0][0] == "POST"
    assert call1[0][2]["newClientOrderId"] == "my_unique_id"

    # Check second call (GET)
    call2 = adapter._request.call_args_list[1]
    assert call2[0][0] == "GET"
    assert call2[0][2]["origClientOrderId"] == "my_unique_id"


@pytest.mark.asyncio
async def test_create_order_raises_other_errors(adapter_with_cache):
    """
    Test that create_order raises other errors normally.
    """
    adapter = adapter_with_cache
    adapter._request = AsyncMock()

    other_error = BinanceAPIError(
        code=-2010, msg="Account has insufficient balance")
    adapter._request.side_effect = other_error

    params = ExchangeOrderParams(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="0.1",
        price="50000",
        client_order_id="my_unique_id"
    )

    with pytest.raises(BinanceAPIError) as excinfo:
        await adapter.create_order(params)

    assert excinfo.value.code == -2010
    assert adapter._request.call_count == 1


@pytest.mark.asyncio
async def test_create_order_raises_if_recovery_fails(adapter_with_cache):
    """
    Test that create_order raises original error if recovery fails.
    """
    adapter = adapter_with_cache
    adapter._request = AsyncMock()

    duplicate_error = BinanceAPIError(
        code=-4116, msg="ClientOrderId is duplicated")
    recovery_error = Exception("Network error during recovery")

    adapter._request.side_effect = [
        duplicate_error,
        recovery_error
    ]

    params = ExchangeOrderParams(
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="0.1",
        price="50000",
        client_order_id="my_unique_id"
    )

    with pytest.raises(BinanceAPIError) as excinfo:
        await adapter.create_order(params)

    assert excinfo.value.code == -4116
    assert adapter._request.call_count == 2
