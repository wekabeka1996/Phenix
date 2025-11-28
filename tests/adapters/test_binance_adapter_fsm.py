import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from typing import Any

from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError
from vfoundation.core.adapters.base import ExchangeOrderParams, ExchangeOrderResponse

@pytest.mark.asyncio
class TestBinanceAdapterFSM:

    @pytest.fixture
    def adapter(self):
        adapter = BinanceAdapter(api_key="test", api_secret="test", shadow_mode=True)
        # Mock create_order to avoid network calls
        adapter.create_order = AsyncMock()
        return adapter

    async def test_place_order_fsm_market(self, adapter):
        """Test FSM placement of MARKET order."""
        # Arrange
        dec_msg = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.1",
            "type": "MARKET",
            "clientOrderId": "test-cid"
        }

        adapter.create_order.return_value = ExchangeOrderResponse(
            order_id="123",
            client_order_id="test-cid",
            symbol="BTCUSDT",
            side="BUY",
            quantity="0.1",
            filled_qty="0",
            price="0",
            status="NEW",
            timestamp_ms=1000
        )

        # Act
        result = await adapter.place_order_fsm(dec_msg)

        # Assert
        assert result["success"] is True
        assert result["orderId"] == "123"

        # Verify create_order call
        adapter.create_order.assert_called_once()
        call_args = adapter.create_order.call_args[0][0]
        assert isinstance(call_args, ExchangeOrderParams)
        assert call_args.symbol == "BTCUSDT"
        assert call_args.side == "BUY"
        assert call_args.order_type == "MARKET"
        assert call_args.quantity == "0.1"
        assert call_args.client_order_id == "test-cid"

    async def test_place_order_fsm_limit(self, adapter):
        """Test FSM placement of LIMIT order."""
        # Arrange
        dec_msg = {
            "symbol": "ETHUSDT",
            "side": "SELL",
            "qty": "1.5",
            "type": "LIMIT",
            "price": "2000.50",
            "timeInForce": "IOC",
            "reduceOnly": True
        }

        adapter.create_order.return_value = ExchangeOrderResponse(
            order_id="456",
            client_order_id=None,
            symbol="ETHUSDT",
            side="SELL",
            quantity="1.5",
            filled_qty="0",
            price="2000.50",
            status="NEW",
            timestamp_ms=1000
        )

        # Act
        await adapter.place_order_fsm(dec_msg)

        # Assert
        call_args = adapter.create_order.call_args[0][0]
        assert call_args.symbol == "ETHUSDT"
        assert call_args.side == "SELL"
        assert call_args.order_type == "LIMIT"
        assert call_args.quantity == "1.5"
        assert call_args.price == "2000.50"
        assert call_args.time_in_force == "IOC"
        assert call_args.reduce_only is True

    async def test_place_order_fsm_bracket_retry(self, adapter):
        """Test retry logic for bracket error -2021 (would trigger)."""
        # Arrange
        dec_msg = {
            "symbol": "BTCUSDT",
            "side": "SELL",
            "qty": "0.1",
            "type": "STOP_MARKET",
            "stopPrice": "50000"
        }

        # First call raises -2021
        error_2021 = BinanceAPIError(code=-2021, msg="Order would immediately trigger")

        # Second call (retry) succeeds
        success_response = ExchangeOrderResponse(
            order_id="999",
            client_order_id=None,
            symbol="BTCUSDT",
            side="SELL",
            quantity="0.1",
            filled_qty="0",
            price="0",
            status="NEW",
            timestamp_ms=1000
        )

        # Capture args at the moment of call to avoid mutation issues
        captured_args = []
        async def side_effect(params):
            import copy
            captured_args.append(copy.deepcopy(params))
            if len(captured_args) == 1:
                raise error_2021
            return success_response

        adapter.create_order.side_effect = side_effect

        # Act
        result = await adapter.place_order_fsm(dec_msg)

        # Assert
        assert result["success"] is True
        assert result["fallback"] == "MARKET_CONVERSION"

        # Verify calls
        assert adapter.create_order.call_count == 2

        # First call: STOP_MARKET
        args1 = captured_args[0]
        assert args1.order_type == "STOP_MARKET"
        assert args1.stop_price == "50000"

        # Second call: MARKET (fallback)
        args2 = captured_args[1]
        assert args2.order_type == "MARKET"
        assert args2.stop_price is None
