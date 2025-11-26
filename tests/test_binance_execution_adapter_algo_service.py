import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter


@pytest.fixture
def adapter():
    config = MagicMock()
    config.trading.trading_env = "test"
    # Default flag OFF
    config.execution.use_algo_service_for_conditionals = False

    adapter = BinanceExecutionAdapter(config=config, shadow_mode=True)
    adapter.api_key = "test_key"
    adapter.api_secret = "test_secret"
    adapter._rest_timeout = 1.0

    # Mock profile for quantization
    profile = MagicMock()
    profile.precision_quantity = 3
    profile.precision_price = 2
    profile.step_size = 0.001
    profile.tick_size = 0.01
    profile.min_qty = 0.001
    profile.min_price = 0.01
    profile.min_notional = 5.0
    adapter._instrument_profiles["BTCUSDT"] = profile

    # Mock _build_signed_request which seems to be missing in static analysis or inherited dynamically
    adapter._build_signed_request = MagicMock(
        return_value=({}, {}, "pre_sign", "sig"))
    adapter._get_signed_params = MagicMock(side_effect=lambda p: p)

    return adapter


@pytest.mark.asyncio
async def test_conditional_orders_use_rest_when_flag_false(adapter):
    """Test that conditional orders use legacy endpoint when flag is False."""
    adapter.use_algo_service_for_conditionals = False

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock success response
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.json.return_value = {"orderId": 123, "status": "NEW"}
        mock_client.post.return_value = mock_resp

        await adapter._place_binance_order_async(
            symbol="BTCUSDT",
            side="BUY",
            quantity="0.1",
            order_type="STOP_MARKET",
            stop_price="50000"
        )

        # Verify POST to /fapi/v1/order
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        url = args[0]
        assert "/fapi/v1/order" in url
        assert "/fapi/v1/algoOrder" not in url


@pytest.mark.asyncio
async def test_conditional_orders_use_algo_service_when_flag_true(adapter):
    """Test that conditional orders use Algo Service when flag is True."""
    adapter.use_algo_service_for_conditionals = True

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock success response from Algo Service
        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_resp.json.return_value = {
            "algoId": 999, "clientAlgoOrderId": "test_algo_id"}
        mock_client.post.return_value = mock_resp

        result = await adapter._place_binance_order_async(
            symbol="BTCUSDT",
            side="BUY",
            quantity="0.1",
            order_type="STOP_MARKET",
            stop_price="50000",
            idempotent_key="test_algo_id"
        )

        # Verify POST to /fapi/v1/algoOrder
        mock_client.post.assert_called_once()
        args, kwargs = mock_client.post.call_args
        url = args[0]
        assert "/fapi/v1/algoOrder" in url

        # Verify result mapping
        assert result["orderId"] == 999
        assert result["algo_service"] is True


@pytest.mark.asyncio
async def test_algo_service_failure_is_fail_closed(adapter):
    """Test that Algo Service failure raises exception (fail-closed)."""
    adapter.use_algo_service_for_conditionals = True

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        # Mock failure response
        mock_resp = MagicMock()
        mock_resp.is_success = False
        mock_resp.json.return_value = {"code": -2021, "msg": "Algo error"}
        mock_client.post.return_value = mock_resp

        with pytest.raises(RuntimeError) as excinfo:
            await adapter._place_binance_order_async(
                symbol="BTCUSDT",
                side="BUY",
                quantity="0.1",
                order_type="STOP_MARKET",
                stop_price="50000"
            )

        assert "ADAPTER_ERROR_ALGO_SERVICE" in str(excinfo.value)
