"""
EP-STAB-PERCENT-PRICE: Test -4024 (PERCENT_PRICE) error handler in BinanceAdapter

Tests recovery flow:
1. Detect -4024 error with stopPrice
2. Fetch mark price
3. Validate/adjust stopPrice against price band
4. Retry with adjusted price
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter


@pytest.fixture
def mock_config():
    """Mock configuration for BinanceExecutionAdapter."""
    config = MagicMock()
    config.trading.execution.exposure.leverage_defaults = {"ETHUSDT": 125}
    config.trading.instruments = {}
    return config


@pytest.mark.asyncio
async def test_percent_price_handler_adjusts_stop_price_outside_band(mock_config):
    """
    Test -4024 handler: stopPrice outside band → clamp to 8% safe band → retry succeeds

    Scenario:
    - Entry: 3087.70 (LONG)
    - Calculated SL: 2900.00 (6.08% below) - slightly outside 10% band
    - Mark price: 3087.70
    - Band: [2778.93, 3396.47] (±10%)
    - Safe band: [2840.68, 3335.22] (±8%)
    - Expected adjustment: 2900.00 → 2840.68 (clamped to safe band)
    - Retry succeeds
    """
    adapter = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
        shadow_mode=False,
        config=mock_config
    )

    # Mock _get_mark_price_async to return mark price
    with patch.object(adapter, '_get_mark_price_async', new_callable=AsyncMock) as mock_get_mark:
        mock_get_mark.return_value = Decimal("3087.70")

        # Mock _get_signed_params
        with patch.object(adapter, '_get_signed_params') as mock_signed:
            mock_signed.return_value = {
                "symbol": "ETHUSDT", "timestamp": "123"}

            # Mock httpx.AsyncClient - POST succeeds after adjustment
            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client

                # Response: success after adjustment (handler already received -4024, now retries)
                mock_response_success = MagicMock()
                mock_response_success.is_success = True
                mock_response_success.json = MagicMock(return_value={
                    "orderId": "7474573155",
                    "status": "NEW",
                    "clientOrderId": "test_sl",
                    "symbol": "ETHUSDT"
                })

                mock_client.post.return_value = mock_response_success

                # Call _handle_bracket_error
                params = {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "type": "STOP_MARKET",
                    "quantity": "0.061",
                    # Outside 10% band (should be adjusted)
                    "stopPrice": "2900.00",
                    "reduceOnly": "true"
                }

                success, response = await adapter._handle_bracket_error(
                    error_code=-4024,
                    error_msg="Limit price can't be lower than 2778.93.",
                    params=params,
                    idempotent_key="test_sl",
                    client_order_id="test_sl",
                    url="https://demo-fapi.binance.com/fapi/v1/order",
                    headers={"X-MBX-APIKEY": "test_key"}
                )

                # Verify recovery succeeded
                assert success is True
                assert response is not None
                assert response["orderId"] == "7474573155"

                # Verify mark price was fetched
                mock_get_mark.assert_called_once_with("ETHUSDT")

                # Verify stopPrice was adjusted (should be clamped to 8% safe band)
                adjusted_stop_price = Decimal(params["stopPrice"])
                mark_price = Decimal("3087.70")
                safe_band_lower = mark_price * Decimal("0.92")  # 8% below

                # Adjustment should bring stopPrice within safe band
                assert adjusted_stop_price >= safe_band_lower
                # Still below entry (valid SL for LONG)
                assert adjusted_stop_price < mark_price


@pytest.mark.asyncio
async def test_percent_price_handler_no_adjustment_needed(mock_config):
    """
    Test -4024 handler: stopPrice inside band → retry without adjustment → succeeds

    Scenario:
    - Entry: 3087.70 (LONG)
    - Calculated SL: 3000.00 (2.84% below) - inside 10% band
    - Mark price: 3087.70
    - Band: [2778.93, 3396.47] (±10%)
    - No adjustment needed
    - Retry succeeds (transient Binance issue)
    """
    adapter = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
        shadow_mode=False,
        config=mock_config
    )

    with patch.object(adapter, '_get_mark_price_async', new_callable=AsyncMock) as mock_get_mark:
        mock_get_mark.return_value = Decimal("3087.70")

        with patch.object(adapter, '_get_signed_params') as mock_signed:
            mock_signed.return_value = {
                "symbol": "ETHUSDT", "timestamp": "123"}

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client

                # Success on retry (no adjustment needed)
                mock_response_success = MagicMock()
                mock_response_success.is_success = True
                mock_response_success.json = MagicMock(return_value={
                    "orderId": "7474573156",
                    "status": "NEW"
                })

                mock_client.post.return_value = mock_response_success

                params = {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "type": "STOP_MARKET",
                    "stopPrice": "3000.00",  # Inside band, valid
                }

                success, response = await adapter._handle_bracket_error(
                    error_code=-4024,
                    error_msg="Limit price can't be lower than 2778.93.",
                    params=params,
                    idempotent_key="test_sl2",
                    client_order_id="test_sl2",
                    url="https://demo-fapi.binance.com/fapi/v1/order",
                    headers={"X-MBX-APIKEY": "test_key"}
                )

                assert success is True
                assert response["orderId"] == "7474573156"

                # Verify stopPrice unchanged (inside band)
                assert params["stopPrice"] == "3000.00"


@pytest.mark.asyncio
async def test_percent_price_handler_mark_price_fetch_fails(mock_config):
    """
    Test -4024 handler: mark price fetch fails → recovery fails

    Scenario:
    - -4024 error occurs
    - _get_mark_price_async returns None (API error)
    - Recovery fails (can't validate without mark price)
    """
    adapter = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
        shadow_mode=False,
        config=mock_config
    )

    with patch.object(adapter, '_get_mark_price_async', new_callable=AsyncMock) as mock_get_mark:
        mock_get_mark.return_value = None  # Fetch fails

        params = {
            "symbol": "ETHUSDT",
            "stopPrice": "3000.00"
        }

        success, response = await adapter._handle_bracket_error(
            error_code=-4024,
            error_msg="Limit price error",
            params=params,
            idempotent_key="test_sl3",
            client_order_id="test_sl3",
            url="https://demo-fapi.binance.com/fapi/v1/order",
            headers={"X-MBX-APIKEY": "test_key"}
        )

        # Recovery should fail if mark price unavailable
        assert success is False
        assert response is None


@pytest.mark.asyncio
async def test_get_mark_price_async_success(mock_config):
    """
    Test _get_mark_price_async: successful fetch from /fapi/v1/premiumIndex
    """
    adapter = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
        shadow_mode=False,
        config=mock_config
    )

    with patch.object(adapter, '_sync_time_with_server'):
        with patch.object(adapter, '_get_signed_params') as mock_signed:
            mock_signed.return_value = {
                "symbol": "ETHUSDT", "timestamp": "123"}

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client

                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json = MagicMock(return_value={
                    "symbol": "ETHUSDT",
                    "markPrice": "3087.70",
                    "indexPrice": "3087.65"
                })

                mock_client.get.return_value = mock_response

                mark_price = await adapter._get_mark_price_async("ETHUSDT")

                assert mark_price == Decimal("3087.70")
                mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_mark_price_async_shadow_mode(mock_config):
    """
    Test _get_mark_price_async: shadow mode returns mock value
    """
    adapter = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
        shadow_mode=True,  # Shadow mode
        config=mock_config
    )

    mark_price = await adapter._get_mark_price_async("ETHUSDT")

    # Shadow mode should return mock value
    assert mark_price == Decimal("3000.0")


@pytest.mark.asyncio
async def test_get_mark_price_async_api_error(mock_config):
    """
    Test _get_mark_price_async: API error returns None
    """
    adapter = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
        shadow_mode=False,
        config=mock_config
    )

    with patch.object(adapter, '_sync_time_with_server'):
        with patch.object(adapter, '_get_signed_params') as mock_signed:
            mock_signed.return_value = {
                "symbol": "ETHUSDT", "timestamp": "123"}

            with patch('httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value.__aenter__.return_value = mock_client

                # API returns error
                mock_response = MagicMock()
                mock_response.status_code = 500
                mock_response.text = "Internal server error"

                mock_client.get.return_value = mock_response

                mark_price = await adapter._get_mark_price_async("ETHUSDT")

                assert mark_price is None
