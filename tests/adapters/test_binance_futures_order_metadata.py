"""
Unit tests for Binance Futures adapter order metadata mapping.

EP-STAB-ADAPT-ORD-META: Validates that get_open_orders() returns
full Binance metadata (order_type, reduce_only, close_position, stop_price,
working_type, position_side) for unified ExitOrderKind classification.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from vfoundation.core.adapters.base import ExchangeOrderResponse
from apps.reference.adapters.binance_adapter import BinanceAdapter


class TestBinanceFuturesOrderMetadata:
    """Test suite for order metadata mapping in BinanceAdapter.get_open_orders()"""

    @pytest.fixture
    def adapter(self):
        """Instantiate BinanceAdapter with mocked HTTP session."""
        return BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            base_url="https://testnet.binancefuture.com",
        )

    @pytest.mark.asyncio
    async def test_limit_reduce_only_order(self, adapter):
        """
        EP-STAB-ADAPT-ORD-META Test Case 1:
        LIMIT + reduceOnly=true → reduce_only=True, order_type="LIMIT", close_position=False
        """
        # Mock Binance API response for a LIMIT order with reduceOnly
        mock_response = [
            {
                "orderId": 123456,
                "clientOrderId": "test_limit_001",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "LIMIT",
                "origType": "LIMIT",
                "origQty": "0.1",
                "executedQty": "0",
                "price": "42000",
                "status": "NEW",
                "time": 1700000000000,
                "reduceOnly": True,
                "closePosition": False,
                "stopPrice": None,
                "workingType": None,
                "positionSide": "LONG",
            }
        ]

        adapter._request = AsyncMock(return_value=mock_response)

        # Call get_open_orders
        orders = await adapter.get_open_orders()

        # Assertions
        assert len(orders) == 1
        order = orders[0]
        assert order.order_id == "123456"
        assert order.client_order_id == "test_limit_001"
        assert order.symbol == "BTCUSDT"
        assert order.side == "SELL"
        assert order.quantity == "0.1"
        assert order.status == "NEW"

        # EP-STAB-ADAPT-ORD-META: Verify new metadata fields
        assert order.order_type == "LIMIT"
        assert order.reduce_only is True
        assert order.close_position is False
        assert order.stop_price is None
        assert order.working_type is None
        assert order.position_side == "LONG"

    @pytest.mark.asyncio
    async def test_stop_market_order_with_stop_price(self, adapter):
        """
        EP-STAB-ADAPT-ORD-META Test Case 2:
        STOP_MARKET + stopPrice → order_type="STOP_MARKET", stop_price set, reduce_only=True
        """
        mock_response = [
            {
                "orderId": 654321,
                "clientOrderId": "test_stop_001",
                "symbol": "ETHUSDT",
                "side": "BUY",
                "type": "STOP_MARKET",
                "origType": "STOP_MARKET",
                "origQty": "1.0",
                "executedQty": "0",
                "price": None,
                "status": "NEW",
                "time": 1700000001000,
                "reduceOnly": True,
                "closePosition": False,
                "stopPrice": "1800",
                "workingType": "MARK_PRICE",
                "positionSide": "LONG",
            }
        ]

        adapter._request = AsyncMock(return_value=mock_response)

        orders = await adapter.get_open_orders()

        assert len(orders) == 1
        order = orders[0]

        # EP-STAB-ADAPT-ORD-META: Verify STOP_MARKET classification
        assert order.order_type == "STOP_MARKET"
        assert order.stop_price == "1800"
        assert order.working_type == "MARK_PRICE"
        assert order.reduce_only is True
        assert order.close_position is False
        assert order.position_side == "LONG"

    @pytest.mark.asyncio
    async def test_market_close_position_order(self, adapter):
        """
        EP-STAB-ADAPT-ORD-META Test Case 3:
        MARKET + closePosition=true → close_position=True, order_type="MARKET", reduce_only as per exchange
        """
        mock_response = [
            {
                "orderId": 789012,
                "clientOrderId": "test_close_001",
                "symbol": "BNBUSDT",
                "side": "SELL",
                "type": "MARKET",
                "origType": "MARKET",
                "origQty": "10.0",
                "executedQty": "0",
                "price": None,
                "status": "NEW",
                "time": 1700000002000,
                "reduceOnly": False,  # closePosition also available
                "closePosition": True,
                "stopPrice": None,
                "workingType": None,
                "positionSide": "SHORT",
            }
        ]

        adapter._request = AsyncMock(return_value=mock_response)

        orders = await adapter.get_open_orders()

        assert len(orders) == 1
        order = orders[0]

        # EP-STAB-ADAPT-ORD-META: Verify FLAT_CLOSE classification via closePosition
        assert order.order_type == "MARKET"
        assert order.close_position is True
        assert order.reduce_only is False
        assert order.stop_price is None
        assert order.position_side == "SHORT"

    @pytest.mark.asyncio
    async def test_to_dict_includes_metadata(self, adapter):
        """
        Verify that ExchangeOrderResponse.to_dict() includes new metadata fields.
        """
        response = ExchangeOrderResponse(
            order_id="123",
            client_order_id="cli_001",
            symbol="BTCUSDT",
            side="BUY",
            quantity="0.5",
            filled_qty="0",
            price="42000",
            status="NEW",
            timestamp_ms=1700000000000,
            order_type="STOP_MARKET",
            reduce_only=True,
            close_position=False,
            stop_price="41000",
            working_type="MARK_PRICE",
            position_side="LONG",
        )

        result_dict = response.to_dict()

        # EP-STAB-ADAPT-ORD-META: Verify to_dict includes all fields
        assert result_dict["type"] == "STOP_MARKET"
        assert result_dict["origType"] == "STOP_MARKET"
        assert result_dict["reduceOnly"] is True
        assert result_dict["closePosition"] is False
        assert result_dict["stopPrice"] == "41000"
        assert result_dict["workingType"] == "MARK_PRICE"
        assert result_dict["positionSide"] == "LONG"

    @pytest.mark.asyncio
    async def test_multiple_orders_with_mixed_types(self, adapter):
        """
        Test that multiple orders with different metadata combinations
        are properly mapped.
        """
        mock_response = [
            {
                "orderId": 1,
                "clientOrderId": "entry_001",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": "LIMIT",
                "origQty": "1.0",
                "executedQty": "0",
                "price": "40000",
                "status": "NEW",
                "time": 1700000000000,
                "reduceOnly": False,
                "closePosition": False,
                "stopPrice": None,
                "workingType": None,
                "positionSide": "BOTH",
            },
            {
                "orderId": 2,
                "clientOrderId": "tp_001",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "origQty": "0.5",
                "executedQty": "0",
                "price": None,
                "status": "NEW",
                "time": 1700000001000,
                "reduceOnly": True,
                "closePosition": False,
                "stopPrice": "50000",
                "workingType": "MARK_PRICE",
                "positionSide": "LONG",
            },
            {
                "orderId": 3,
                "clientOrderId": "sl_001",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "STOP_MARKET",
                "origQty": "0.5",
                "executedQty": "0",
                "price": None,
                "status": "NEW",
                "time": 1700000002000,
                "reduceOnly": True,
                "closePosition": False,
                "stopPrice": "35000",
                "workingType": "MARK_PRICE",
                "positionSide": "LONG",
            },
        ]

        adapter._request = AsyncMock(return_value=mock_response)

        orders = await adapter.get_open_orders()

        assert len(orders) == 3

        # Entry order (LIMIT, no exit flags)
        assert orders[0].order_type == "LIMIT"
        assert orders[0].reduce_only is False
        assert orders[0].close_position is False

        # TP order
        assert orders[1].order_type == "TAKE_PROFIT_MARKET"
        assert orders[1].reduce_only is True
        assert orders[1].stop_price == "50000"

        # SL order
        assert orders[2].order_type == "STOP_MARKET"
        assert orders[2].reduce_only is True
        assert orders[2].stop_price == "35000"

    @pytest.mark.asyncio
    async def test_missing_optional_fields_default_correctly(self, adapter):
        """
        Test that missing optional fields default to None/False correctly.
        """
        mock_response = [
            {
                "orderId": 999,
                "clientOrderId": "minimal_001",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": "LIMIT",
                "origQty": "0.1",
                "executedQty": "0",
                "price": "42000",
                "status": "NEW",
                "time": 1700000000000,
                # Missing optional fields: reduceOnly, closePosition, stopPrice, workingType, positionSide
            }
        ]

        adapter._request = AsyncMock(return_value=mock_response)

        orders = await adapter.get_open_orders()

        assert len(orders) == 1
        order = orders[0]

        # EP-STAB-ADAPT-ORD-META: Verify defaults
        assert order.reduce_only is False
        assert order.close_position is False
        assert order.stop_price is None
        assert order.working_type is None
        assert order.position_side is None

    @pytest.mark.asyncio
    async def test_classification_with_legacy_origtype_fallback(self, adapter):
        """
        Test that when 'type' field is missing, 'origType' is used as fallback.
        """
        mock_response = [
            {
                "orderId": 555,
                "clientOrderId": "fallback_001",
                "symbol": "BTCUSDT",
                "side": "SELL",
                # 'type' is missing, use 'origType'
                "origType": "STOP_LIMIT",
                "origQty": "0.1",
                "executedQty": "0",
                "price": "41000",
                "status": "NEW",
                "time": 1700000000000,
                "reduceOnly": True,
                "closePosition": False,
                "stopPrice": "40000",
                "workingType": "MARK_PRICE",
                "positionSide": "LONG",
            }
        ]

        adapter._request = AsyncMock(return_value=mock_response)

        orders = await adapter.get_open_orders()

        assert len(orders) == 1
        order = orders[0]

        # EP-STAB-ADAPT-ORD-META: Verify origType fallback
        assert order.order_type == "STOP_LIMIT"
        assert order.stop_price == "40000"
