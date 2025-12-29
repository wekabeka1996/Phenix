"""
Tests for Binance Adapter Precision Normalization (EXEC-BINANCE-PRECISION-GUARD).

These tests verify that:
1. stopPrice is normalized to tickSize before sending to Binance
2. price is normalized to tickSize
3. quantity is normalized to stepSize
4. _to_decimal handles various input types correctly
5. _round_step rounds correctly to tick/step size
"""
import pytest
from decimal import Decimal, ROUND_DOWN
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

# Import the adapter
from apps.reference.adapters.binance_adapter import BinanceAdapter


class TestPrecisionHelpers:
    """Test precision helper methods."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance for testing."""
        adapter = BinanceAdapter(shadow_mode=True)
        return adapter

    # ─────────────────────────────────────────────────────────────
    # _to_decimal tests
    # ─────────────────────────────────────────────────────────────

    def test_to_decimal_from_string(self, adapter):
        """String with many decimals should convert to Decimal."""
        result = adapter._to_decimal("878.0897999999999910869519226")
        assert isinstance(result, Decimal)
        assert result == Decimal("878.0897999999999910869519226")

    def test_to_decimal_from_int(self, adapter):
        """Integer should convert to Decimal."""
        result = adapter._to_decimal(100)
        assert result == Decimal("100")

    def test_to_decimal_from_float(self, adapter):
        """Float should convert to Decimal (via str)."""
        result = adapter._to_decimal(123.456)
        assert isinstance(result, Decimal)

    def test_to_decimal_from_decimal(self, adapter):
        """Decimal should pass through."""
        d = Decimal("999.123")
        # Note: current impl converts via str, so Decimal becomes str then Decimal
        result = adapter._to_decimal(d)
        assert result == Decimal("999.123")

    def test_to_decimal_from_dict_with_markPrice(self, adapter):
        """Dict with markPrice should extract it."""
        d = {"markPrice": "91000.50"}
        result = adapter._to_decimal(d)
        assert result == Decimal("91000.50")

    def test_to_decimal_from_dict_with_price(self, adapter):
        """Dict with price should extract it."""
        d = {"price": "878.08"}
        result = adapter._to_decimal(d)
        assert result == Decimal("878.08")

    def test_to_decimal_none_raises(self, adapter):
        """None should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be None"):
            adapter._to_decimal(None)

    def test_to_decimal_empty_dict_raises(self, adapter):
        """Empty dict should raise ValueError."""
        with pytest.raises(ValueError, match="no 'markPrice' or 'price'"):
            adapter._to_decimal({})

    # ─────────────────────────────────────────────────────────────
    # _round_step tests
    # ─────────────────────────────────────────────────────────────

    def test_round_step_basic(self, adapter):
        """Basic rounding to tick size."""
        # 878.0897... with tick_size=0.01 should become 878.08
        price = Decimal("878.0897999999999910869519226")
        tick_size = Decimal("0.01")
        result = adapter._round_step(price, tick_size, ROUND_DOWN)
        assert result == Decimal("878.08")

    def test_round_step_larger_tick(self, adapter):
        """Rounding with larger tick size (BTC)."""
        price = Decimal("91433.6789")
        tick_size = Decimal("0.1")
        result = adapter._round_step(price, tick_size, ROUND_DOWN)
        assert result == Decimal("91433.6")

    def test_round_step_integer_tick(self, adapter):
        """Rounding with integer tick size."""
        price = Decimal("234.5678")
        tick_size = Decimal("1")
        result = adapter._round_step(price, tick_size, ROUND_DOWN)
        assert result == Decimal("234")

    def test_round_step_small_tick(self, adapter):
        """Rounding with very small tick size."""
        price = Decimal("0.12345678")
        tick_size = Decimal("0.00001")
        result = adapter._round_step(price, tick_size, ROUND_DOWN)
        assert result == Decimal("0.12345")

    def test_round_step_exact_multiple(self, adapter):
        """Price that is exact multiple of tick should not change."""
        price = Decimal("100.50")
        tick_size = Decimal("0.01")
        result = adapter._round_step(price, tick_size, ROUND_DOWN)
        assert result == Decimal("100.50")

    def test_round_step_zero_tick(self, adapter):
        """Zero tick size should return original price."""
        price = Decimal("123.456789")
        tick_size = Decimal("0")
        result = adapter._round_step(price, tick_size, ROUND_DOWN)
        assert result == Decimal("123.456789")


class TestNormalizePriceAsync:
    """Test async _normalize_price method."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with mocked exchange info."""
        adapter = BinanceAdapter(shadow_mode=True)
        # Pre-populate cache to avoid API call
        adapter._exchange_info_cache["BNBUSDT"] = {
            "tick_size": Decimal("0.01"),
            "step_size": Decimal("0.01"),
            "min_qty": Decimal("0.01"),
            "min_notional": Decimal("5"),
            "timestamp": 9999999999.0,  # Far future
        }
        adapter._exchange_info_cache["BTCUSDT"] = {
            "tick_size": Decimal("0.1"),
            "step_size": Decimal("0.001"),
            "min_qty": Decimal("0.001"),
            "min_notional": Decimal("5"),
            "timestamp": 9999999999.0,
        }
        adapter._exchange_info_cache["SOLUSDT"] = {
            "tick_size": Decimal("0.01"),
            "step_size": Decimal("1"),
            "min_qty": Decimal("1"),
            "min_notional": Decimal("5"),
            "timestamp": 9999999999.0,
        }
        return adapter

    @pytest.mark.asyncio
    async def test_normalize_bnb_stopPrice_28_decimals(self, adapter):
        """
        CRITICAL: The exact case from production logs.
        stop_price='878.0897999999999910869519226' should become '878.08'
        """
        raw_price = "878.0897999999999910869519226"
        result = await adapter._normalize_price("BNBUSDT", raw_price)
        assert result == "878.08"

    @pytest.mark.asyncio
    async def test_normalize_bnb_tp_price_28_decimals(self, adapter):
        """TP price with many decimals."""
        raw_price = "931.8503999999999905412551016"
        result = await adapter._normalize_price("BNBUSDT", raw_price)
        assert result == "931.85"

    @pytest.mark.asyncio
    async def test_normalize_btc_price(self, adapter):
        """BTC with 0.1 tick size."""
        raw_price = "91433.6789123"
        result = await adapter._normalize_price("BTCUSDT", raw_price)
        assert result == "91433.6"

    @pytest.mark.asyncio
    async def test_normalize_from_decimal_input(self, adapter):
        """Decimal input should also normalize."""
        raw_price = Decimal("878.0897999999999910869519226")
        result = await adapter._normalize_price("BNBUSDT", raw_price)
        assert result == "878.08"

    @pytest.mark.asyncio
    async def test_normalize_from_float_input(self, adapter):
        """Float input should also normalize (via str conversion)."""
        raw_price = 878.08979  # Float approximation
        result = await adapter._normalize_price("BNBUSDT", raw_price)
        # Should round to tick_size=0.01
        assert result in ("878.08", "878.09")  # Float precision may vary

    @pytest.mark.asyncio
    async def test_normalize_none_returns_none(self, adapter):
        """None input should return None."""
        result = await adapter._normalize_price("BNBUSDT", None)
        assert result is None

    @pytest.mark.asyncio
    async def test_normalize_exact_price_unchanged(self, adapter):
        """Price already at correct precision stays the same."""
        result = await adapter._normalize_price("BNBUSDT", "900.00")
        assert result == "900"  # .normalize() removes trailing zeros


class TestNormalizeQuantityAsync:
    """Test async _normalize_quantity method."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with mocked exchange info."""
        adapter = BinanceAdapter(shadow_mode=True)
        adapter._exchange_info_cache["SOLUSDT"] = {
            "tick_size": Decimal("0.01"),
            "step_size": Decimal("1"),  # SOL has integer qty
            "min_qty": Decimal("1"),
            "min_notional": Decimal("5"),
            "timestamp": 9999999999.0,
        }
        adapter._exchange_info_cache["BNBUSDT"] = {
            "tick_size": Decimal("0.01"),
            "step_size": Decimal("0.01"),
            "min_qty": Decimal("0.01"),
            "min_notional": Decimal("5"),
            "timestamp": 9999999999.0,
        }
        return adapter

    @pytest.mark.asyncio
    async def test_normalize_sol_qty_fractional(self, adapter):
        """SOL qty 1.5 should become 1 (stepSize=1)."""
        result = await adapter._normalize_quantity("SOLUSDT", "1.5")
        assert result == "1"

    @pytest.mark.asyncio
    async def test_normalize_bnb_qty_many_decimals(self, adapter):
        """BNB qty with many decimals."""
        result = await adapter._normalize_quantity("BNBUSDT", "0.173456789")
        assert result == "0.17"

    @pytest.mark.asyncio
    async def test_normalize_none_returns_none(self, adapter):
        """None input should return None."""
        result = await adapter._normalize_quantity("BNBUSDT", None)
        assert result is None


class TestValidatePrecision:
    """Test _validate_precision guard."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance."""
        return BinanceAdapter(shadow_mode=True)

    def test_validate_correct_precision_passes(self, adapter):
        """Correct precision should not raise."""
        params = {"stopPrice": "878.08", "quantity": "0.17"}
        filters = {"tick_size": Decimal("0.01"), "step_size": Decimal("0.01")}
        # Should not raise
        adapter._validate_precision("BNBUSDT", params, filters)

    def test_validate_bad_price_precision_raises(self, adapter):
        """Incorrect price precision should raise BinanceValidationError."""
        from apps.reference.adapters.binance_adapter import BinanceValidationError

        params = {"stopPrice": "878.089"}  # 3 decimals but tick=0.01
        filters = {"tick_size": Decimal("0.01"), "step_size": Decimal("0.01")}

        with pytest.raises(BinanceValidationError, match="PRECISION_GUARD"):
            adapter._validate_precision("BNBUSDT", params, filters)

    def test_validate_bad_quantity_precision_raises(self, adapter):
        """Incorrect quantity precision should raise."""
        from apps.reference.adapters.binance_adapter import BinanceValidationError

        params = {"quantity": "1.5"}  # but step=1
        filters = {"tick_size": Decimal("0.01"), "step_size": Decimal("1")}

        with pytest.raises(BinanceValidationError, match="PRECISION_GUARD"):
            adapter._validate_precision("SOLUSDT", params, filters)


class TestCreateOrderNormalization:
    """Integration test: create_order should normalize before sending."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with mocked _request."""
        adapter = BinanceAdapter(shadow_mode=True)
        adapter._exchange_info_cache["BNBUSDT"] = {
            "tick_size": Decimal("0.01"),
            "step_size": Decimal("0.01"),
            "min_qty": Decimal("0.01"),
            "min_notional": Decimal("5"),
            "timestamp": 9999999999.0,
        }
        return adapter

    @pytest.mark.asyncio
    async def test_create_order_normalizes_stopPrice(self, adapter):
        """
        CRITICAL: create_order should normalize stopPrice before sending to Binance.
        This is the exact scenario from production.
        """
        from vfoundation.core.adapters.base import ExchangeOrderParams

        # Mock the _request to capture what gets sent
        captured_params = {}

        async def mock_request(method, path, params):
            captured_params.update(params)
            return {"orderId": 12345, "status": "NEW"}

        adapter._request = mock_request

        # Create params with raw Decimal-like stopPrice (28 decimals)
        params = ExchangeOrderParams(
            symbol="BNBUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity=None,  # closePosition
            close_position=True,
            stop_price="878.0897999999999910869519226",  # Raw from runtime
        )

        await adapter.create_order(params)

        # The stopPrice sent to Binance should be normalized
        assert captured_params.get("stopPrice") == "878.08"
        assert captured_params.get("closePosition") == "true"

    @pytest.mark.asyncio
    async def test_create_order_normalizes_price_and_quantity(self, adapter):
        """LIMIT order should normalize price and quantity."""
        from vfoundation.core.adapters.base import ExchangeOrderParams

        captured_params = {}

        async def mock_request(method, path, params):
            captured_params.update(params)
            return {"orderId": 12345, "status": "NEW"}

        adapter._request = mock_request

        params = ExchangeOrderParams(
            symbol="BNBUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="0.173456789",  # Should become 0.17
            price="900.123456",  # Should become 900.12
            time_in_force="GTC",
        )

        await adapter.create_order(params)

        assert captured_params.get("price") == "900.12"
        assert captured_params.get("quantity") == "0.17"


class TestGetSymbolFilters:
    """Test _get_symbol_filters with cache."""

    @pytest.fixture
    def adapter(self):
        return BinanceAdapter(shadow_mode=True)

    @pytest.mark.asyncio
    async def test_returns_cached_filters(self, adapter):
        """Should return cached filters without API call."""
        # Pre-populate cache
        adapter._exchange_info_cache["TESTUSDT"] = {
            "tick_size": Decimal("0.001"),
            "step_size": Decimal("0.1"),
            "timestamp": 9999999999.0,
        }

        result = await adapter._get_symbol_filters("TESTUSDT")
        assert result["tick_size"] == Decimal("0.001")
        assert result["step_size"] == Decimal("0.1")

    @pytest.mark.asyncio
    async def test_returns_defaults_on_missing(self, adapter):
        """Should return defaults if symbol not in cache and API fails."""
        # Mock get_exchange_info to raise
        async def mock_fail(*args, **kwargs):
            raise Exception("Network error")

        adapter.get_exchange_info = mock_fail

        result = await adapter._get_symbol_filters("UNKNOWNUSDT")

        # Should return defaults
        assert "tick_size" in result
        assert "step_size" in result
        assert result["tick_size"] == Decimal("0.01")  # default


class TestEdgeCases:
    """Edge cases and regression tests."""

    @pytest.fixture
    def adapter(self):
        adapter = BinanceAdapter(shadow_mode=True)
        adapter._exchange_info_cache["BNBUSDT"] = {
            "tick_size": Decimal("0.01"),
            "step_size": Decimal("0.01"),
            "min_qty": Decimal("0.01"),
            "min_notional": Decimal("5"),
            "timestamp": 9999999999.0,
        }
        return adapter

    @pytest.mark.asyncio
    async def test_scientific_notation_input(self, adapter):
        """Scientific notation should be handled."""
        result = await adapter._normalize_price("BNBUSDT", "8.780898E+2")
        assert result == "878.08"

    @pytest.mark.asyncio
    async def test_very_small_price(self, adapter):
        """Very small price should normalize correctly."""
        adapter._exchange_info_cache["SHIBUSDT"] = {
            "tick_size": Decimal("0.00000001"),
            "step_size": Decimal("1"),
            "timestamp": 9999999999.0,
        }
        result = await adapter._normalize_price("SHIBUSDT", "0.000012345678")
        assert result == "0.00001234"

    @pytest.mark.asyncio
    async def test_format_removes_trailing_zeros(self, adapter):
        """Normalized price should not have unnecessary trailing zeros."""
        result = await adapter._normalize_price("BNBUSDT", "900.00")
        # .normalize() removes trailing zeros
        assert result == "900"

    @pytest.mark.asyncio
    async def test_no_scientific_notation_in_output(self, adapter):
        """Output should never be in scientific notation."""
        adapter._exchange_info_cache["BTCUSDT"] = {
            "tick_size": Decimal("0.1"),
            "step_size": Decimal("0.001"),
            "timestamp": 9999999999.0,
        }
        result = await adapter._normalize_price("BTCUSDT", "91000")
        assert "E" not in result and "e" not in result
        assert result == "91000"
