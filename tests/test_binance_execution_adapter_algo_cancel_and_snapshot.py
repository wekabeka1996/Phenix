
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal
from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter


@pytest.mark.asyncio
async def test_cancel_conditional_via_algo_service():
    adapter = BinanceExecutionAdapter(
        config={"execution": {"use_algo_service_for_conditionals": True}})
    adapter.api_key = "test_key"
    adapter.api_secret = "test_secret"
    adapter._rest_timeout = 1.0

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock successful delete
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {"code": 200, "msg": "success"}
        mock_client.delete.return_value = mock_response

        result = await adapter._cancel_conditional_via_algo_service("BTCUSDT", algo_order_id="12345")

        assert result["code"] == 200
        mock_client.delete.assert_called_once()
        # Verify params in call args
        call_args = mock_client.delete.call_args
        # params are in kwargs
        params = call_args.kwargs["params"]
        assert params["algoId"] == "12345"
        assert params["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_cancel_conditional_idempotent_success():
    adapter = BinanceExecutionAdapter(
        config={"execution": {"use_algo_service_for_conditionals": True}})
    adapter.api_key = "test_key"
    adapter.api_secret = "test_secret"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock -2011 error
        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.json.return_value = {
            "code": -2011, "msg": "Unknown order sent."}
        mock_client.delete.return_value = mock_response

        result = await adapter._cancel_conditional_via_algo_service("BTCUSDT", algo_order_id="12345")

        assert result["status"] == "CANCELED"
        assert result["code"] == 200


@pytest.mark.asyncio
async def test_load_open_algo_orders_snapshot():
    adapter = BinanceExecutionAdapter(
        config={"execution": {"use_algo_service_for_conditionals": True}})
    adapter.api_key = "test_key"
    adapter.api_secret = "test_secret"
    adapter.algo_order_index = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock successful get
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "orders": [
                {
                    "algoId": 123,
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "type": "STOP_MARKET",
                    "origQty": "1.0",
                    "stopPrice": "50000",
                    "clientAlgoOrderId": "client_123"
                }
            ]
        }
        mock_client.get.return_value = mock_response

        orders = await adapter.load_open_algo_orders_snapshot()

        assert len(orders) == 1
        adapter.algo_order_index.register_new_algo_order.assert_called_once()
        call_args = adapter.algo_order_index.register_new_algo_order.call_args
        assert call_args.kwargs["algo_order_id"] == "123"
        assert call_args.kwargs["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_cancel_binance_order_async_routes_to_algo_service():
    adapter = BinanceExecutionAdapter(
        config={"execution": {"use_algo_service_for_conditionals": True}})
    adapter.algo_order_index = MagicMock()
    adapter._cancel_conditional_via_algo_service = AsyncMock(
        return_value={"status": "success"})

    # Mock index lookup
    adapter.algo_order_index.get_by_algo_id.return_value = True

    await adapter._cancel_binance_order_async("BTCUSDT", "12345")

    adapter._cancel_conditional_via_algo_service.assert_called_once_with(
        "BTCUSDT", algo_order_id="12345")
