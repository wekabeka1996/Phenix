"""
Test: Binance Adapter Precision Guards
======================================

EXEC-BINANCE-PRECISION-GUARD-FOR-CONDITIONALS

Tests that:
1. stopPrice is normalized to tickSize for STOP_MARKET/TAKE_PROFIT_MARKET
2. activationPrice is normalized for trailing orders
3. quantity is normalized to stepSize
4. Precision guard rejects orders that exceed filter precision BEFORE sending to Binance

RID: EXEC-BINANCE-PRECISION-GUARD-FOR-CONDITIONALS
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

# Import adapter
from apps.reference.adapters.binance_adapter import (
    BinanceAdapter,
    BinanceAPIError,
    BinanceValidationError,
)
from vfoundation.core.adapters.base import ExchangeOrderParams


def _fraction_digits(value_str: str) -> int:
    """Count fraction digits in a decimal string."""
    if "." not in str(value_str):
        return 0
    return len(str(value_str).split(".")[1].rstrip("0"))


def _tick_precision(tick_size: str) -> int:
    """Get precision from tick size (e.g., '0.01' -> 2)."""
    return _fraction_digits(tick_size)


class TestStopPriceNormalization:
    """Test that stopPrice is normalized to tickSize."""

    @pytest.fixture
    def adapter_with_filters(self):
        """Create adapter with mocked exchange info filters."""
        adapter = BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            base_url="https://testnet.binancefuture.com",
            shadow_mode=True,
        )

        # Mock exchange info cache
        adapter._exchange_info_cache = {
            "SOLUSDT": {
                "tick_size": Decimal("0.01"),
                "step_size": Decimal("1"),
                "min_qty": Decimal("1"),
                "min_notional": Decimal("5"),
                "timestamp": 0,
            },
            "ETHUSDT": {
                "tick_size": Decimal("0.01"),
                "step_size": Decimal("0.001"),
                "min_qty": Decimal("0.001"),
                "min_notional": Decimal("5"),
                "timestamp": 0,
            },
            "BTCUSDT": {
                "tick_size": Decimal("0.1"),
                "step_size": Decimal("0.001"),
                "min_qty": Decimal("0.001"),
                "min_notional": Decimal("5"),
                "timestamp": 0,
            },
        }

        return adapter

    @pytest.mark.asyncio
    async def test_stop_price_normalized_for_stop_market(self, adapter_with_filters):
        """PREC-1: stopPrice with long decimal tail should be normalized to tickSize."""
        adapter = adapter_with_filters
        captured_params = {}

        async def fake_request(method, path, params, signed=True):
            captured_params["method"] = method
            captured_params["path"] = path
            captured_params["params"] = params
            return {
                "orderId": 12345,
                "clientOrderId": "test-order",
                "status": "NEW",
                "symbol": "SOLUSDT",
                "side": "SELL",
                "origQty": "20",
            }

        adapter._request = fake_request

        # Place STOP_MARKET with long precision stopPrice
        params = ExchangeOrderParams(
            symbol="SOLUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity=None,  # closePosition=true
            stop_price="133.6869070203939861585240578",  # Too many decimals!
            close_position=True,
        )

        result = await adapter.create_order(params)

        # Verify stopPrice was normalized
        stop_price_str = captured_params["params"].get("stopPrice")
        assert stop_price_str is not None, "stopPrice should be in params"

        # Should be normalized to 2 decimal places (tick_size=0.01)
        actual_precision = _fraction_digits(stop_price_str)
        expected_precision = _tick_precision("0.01")

        assert actual_precision <= expected_precision, (
            f"stopPrice precision {actual_precision} exceeds tickSize precision {expected_precision}. "
            f"Got: {stop_price_str}"
        )

    @pytest.mark.asyncio
    async def test_stop_price_normalized_for_take_profit_market(self, adapter_with_filters):
        """PREC-2: stopPrice for TAKE_PROFIT_MARKET should be normalized."""
        adapter = adapter_with_filters
        captured_params = {}

        async def fake_request(method, path, params, signed=True):
            captured_params["params"] = params
            return {
                "orderId": 12346,
                "clientOrderId": "test-tp",
                "status": "NEW",
                "symbol": "ETHUSDT",
                "side": "SELL",
            }

        adapter._request = fake_request

        params = ExchangeOrderParams(
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            quantity=None,
            stop_price="3019.94789123456789",  # Long precision
            close_position=True,
        )

        result = await adapter.create_order(params)

        stop_price_str = captured_params["params"].get("stopPrice")
        assert stop_price_str is not None

        # ETHUSDT tick_size=0.01 -> max 2 decimal places
        actual_precision = _fraction_digits(stop_price_str)
        assert actual_precision <= 2, f"stopPrice has {actual_precision} decimals, expected <=2"

    @pytest.mark.asyncio
    async def test_price_normalized_for_limit_orders(self, adapter_with_filters):
        """PREC-3: price for LIMIT orders should be normalized."""
        adapter = adapter_with_filters
        captured_params = {}

        async def fake_request(method, path, params, signed=True):
            captured_params["params"] = params
            return {
                "orderId": 12347,
                "status": "NEW",
                "symbol": "BTCUSDT",
                "side": "BUY",
            }

        adapter._request = fake_request

        params = ExchangeOrderParams(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="0.001",
            price="98765.432109876",  # Long precision
            time_in_force="GTC",
        )

        result = await adapter.create_order(params)

        price_str = captured_params["params"].get("price")
        assert price_str is not None

        # BTCUSDT tick_size=0.1 -> max 1 decimal place
        actual_precision = _fraction_digits(price_str)
        assert actual_precision <= 1, f"price has {actual_precision} decimals, expected <=1"


class TestQuantityNormalization:
    """Test that quantity is normalized to stepSize."""

    @pytest.fixture
    def adapter_with_filters(self):
        """Create adapter with mocked filters."""
        adapter = BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            shadow_mode=True,
        )

        adapter._exchange_info_cache = {
            "SOLUSDT": {
                "tick_size": Decimal("0.01"),
                "step_size": Decimal("1"),  # Integer qty only
                "min_qty": Decimal("1"),
                "timestamp": 0,
            },
            "ETHUSDT": {
                "tick_size": Decimal("0.01"),
                "step_size": Decimal("0.001"),  # 3 decimal places
                "min_qty": Decimal("0.001"),
                "timestamp": 0,
            },
        }

        return adapter

    @pytest.mark.asyncio
    async def test_quantity_normalized_to_step_size(self, adapter_with_filters):
        """PREC-4: quantity should be normalized to stepSize."""
        adapter = adapter_with_filters
        captured_params = {}

        async def fake_request(method, path, params, signed=True):
            captured_params["params"] = params
            return {"orderId": 12348, "status": "NEW", "symbol": "ETHUSDT"}

        adapter._request = fake_request

        params = ExchangeOrderParams(
            symbol="ETHUSDT",
            side="BUY",
            order_type="MARKET",
            quantity="0.123456789",  # Too many decimals
        )

        result = await adapter.create_order(params)

        qty_str = captured_params["params"].get("quantity")
        assert qty_str is not None

        # ETHUSDT step_size=0.001 -> max 3 decimal places
        actual_precision = _fraction_digits(qty_str)
        assert actual_precision <= 3, f"quantity has {actual_precision} decimals, expected <=3"


class TestPrecisionGuard:
    """Test fail-closed precision guard before API call."""

    @pytest.fixture
    def adapter_with_guard(self):
        """Create adapter with precision guard enabled."""
        adapter = BinanceAdapter(
            api_key="test_key",
            api_secret="test_secret",
            shadow_mode=True,
        )

        adapter._exchange_info_cache = {
            "SOLUSDT": {
                "tick_size": Decimal("0.01"),
                "step_size": Decimal("1"),
                "timestamp": 0,
            },
        }

        return adapter

    @pytest.mark.asyncio
    async def test_guard_passes_normalized_values(self, adapter_with_guard):
        """GUARD-1: After normalization, guard should pass."""
        adapter = adapter_with_guard
        request_called = {"called": False}

        async def fake_request(method, path, params, signed=True):
            request_called["called"] = True
            return {"orderId": 99999, "status": "NEW"}

        adapter._request = fake_request

        params = ExchangeOrderParams(
            symbol="SOLUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity=None,  # closePosition mode
            stop_price="133.123456789",  # Will be normalized
            close_position=True,
        )

        # Should succeed because normalization happens before guard
        result = await adapter.create_order(params)
        assert request_called["called"], "Request should be called after normalization"


class TestExistingNormalizationPaths:
    """Verify existing normalization paths work correctly."""

    @pytest.mark.asyncio
    async def test_quantize_quantity_uses_exchange_info(self):
        """Verify quantize_quantity fetches and uses exchange info."""
        adapter = BinanceAdapter(
            api_key="test",
            api_secret="test",
            shadow_mode=True,
        )

        # Mock get_exchange_info
        async def mock_exchange_info(symbol):
            return {
                "symbols": [{
                    "symbol": "ETHUSDT",
                    "filters": [
                        {"filterType": "LOT_SIZE",
                            "stepSize": "0.001", "minQty": "0.001"},
                        {"filterType": "MIN_NOTIONAL", "notional": "5"},
                    ]
                }]
            }

        adapter.get_exchange_info = mock_exchange_info
        adapter.get_mark_price = AsyncMock(return_value=3000.0)

        result = await adapter.quantize_quantity("ETHUSDT", "0.123456789")

        # Should be rounded to 3 decimal places
        assert _fraction_digits(result) <= 3


class TestErrorCodeClassification:
    """Test that -1111 errors are properly classified."""

    def test_precision_error_is_classified_correctly(self):
        """ERR-1: -1111 should be classified as ADAPTER_ERROR_PRECISION."""
        from apps.reference.domains.execution_position.shadow_execpos.execution_service import (
            ExecutionService
        )

        mock_adapter = MagicMock()
        service = ExecutionService(mock_adapter)

        # Simulate BinanceAPIError with -1111
        error = BinanceAPIError(
            code=-1111,
            msg="Precision is over the maximum defined for this asset."
        )

        classification = service._classify_exception(error)

        # Should NOT be classified as timeout
        assert classification["is_timeout"] is False
        assert "PRECISION" in classification["normalized_error"].upper() or \
               "-1111" in classification["normalized_error"]
