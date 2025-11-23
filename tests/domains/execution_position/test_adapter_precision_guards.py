"""
Unit tests for BinanceExecutionAdapter quantity/price normalization.

Tests EP-ADAPTER-PRECISION-GUARDS-S19: Symbol filter validation.
"""
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch

from apps.reference.domains.execution_position.binance_execution_adapter import (
    BinanceExecutionAdapter,
    BinanceValidationError,
)
from apps.reference.config_models import InstrumentProfile


@pytest.fixture
def mock_config():
    """Mock configuration object."""
    config = Mock()
    config.trading = Mock()
    config.trading.trading_env = "test"
    return config


@pytest.fixture
def solusdt_profile():
    """SOLUSDT instrument profile with integer quantity precision."""
    return InstrumentProfile(
        symbol="SOLUSDT",
        exchange="binance",
        base_asset="SOL",
        quote_asset="USDT",
        precision_quantity=0,  # Integer only
        precision_price=2,
        min_notional=10.0,
        min_qty=1.0,
        min_price=0.01,
        step_size=1.0,  # Must be multiples of 1
        tick_size=0.01,
        max_position_size=100.0,
        max_leverage=20.0,
    )


@pytest.fixture
def btcusdt_profile():
    """BTCUSDT instrument profile with decimal precision."""
    return InstrumentProfile(
        symbol="BTCUSDT",
        exchange="binance",
        base_asset="BTC",
        quote_asset="USDT",
        precision_quantity=3,
        precision_price=2,
        min_notional=10.0,
        min_qty=0.001,
        min_price=0.01,
        step_size=0.001,
        tick_size=0.01,
        max_position_size=10.0,
        max_leverage=20.0,
    )


@pytest.fixture
def adapter(mock_config, solusdt_profile, btcusdt_profile):
    """BinanceExecutionAdapter with mocked instrument profiles."""
    adapter = BinanceExecutionAdapter(
        fsm=None,
        config=mock_config,
        shadow_mode=True,
        rest_timeout_sec=20.0
    )
    # Pre-load instrument profiles
    adapter._instrument_profiles["SOLUSDT"] = solusdt_profile
    adapter._instrument_profiles["BTCUSDT"] = btcusdt_profile
    return adapter


class TestQuantizeQty:
    """Test _quantize_qty normalization."""

    def test_solusdt_qty_floored_to_integer(self, adapter):
        """SOLUSDT: qty 1.42 → 1 (floor to step_size=1)."""
        result = adapter._quantize_qty("SOLUSDT", 1.42)
        assert result == Decimal("1")

    def test_solusdt_qty_already_integer(self, adapter):
        """SOLUSDT: qty 5 → 5."""
        result = adapter._quantize_qty("SOLUSDT", 5)
        assert result == Decimal("5")

    def test_solusdt_qty_below_min_qty_raises(self, adapter):
        """SOLUSDT: qty 0.5 → BinanceValidationError (min_qty=1.0)."""
        with pytest.raises(BinanceValidationError, match="below min_qty"):
            adapter._quantize_qty("SOLUSDT", 0.5)

    def test_btcusdt_qty_decimal_precision(self, adapter):
        """BTCUSDT: qty 0.0015 → 0.001 (floor to step_size=0.001)."""
        result = adapter._quantize_qty("BTCUSDT", 0.0015)
        assert result == Decimal("0.001")

    def test_btcusdt_qty_exact_step(self, adapter):
        """BTCUSDT: qty 0.003 → 0.003 (exact step_size multiple)."""
        result = adapter._quantize_qty("BTCUSDT", 0.003)
        assert result == Decimal("0.003")

    def test_btcusdt_qty_below_min_qty_raises(self, adapter):
        """BTCUSDT: qty 0.0005 → BinanceValidationError (min_qty=0.001)."""
        with pytest.raises(BinanceValidationError, match="below min_qty"):
            adapter._quantize_qty("BTCUSDT", 0.0005)

    def test_invalid_qty_format_raises(self, adapter):
        """Invalid qty format → BinanceValidationError."""
        with pytest.raises(BinanceValidationError, match="Invalid quantity format"):
            adapter._quantize_qty("SOLUSDT", "invalid")


class TestQuantizePrice:
    """Test _quantize_price normalization."""

    def test_solusdt_price_floored_to_tick_size(self, adapter):
        """SOLUSDT: price 122.156 → 122.15 (floor to tick_size=0.01)."""
        result = adapter._quantize_price("SOLUSDT", 122.156)
        assert result == Decimal("122.15")

    def test_solusdt_price_exact_tick(self, adapter):
        """SOLUSDT: price 122.00 → 122.00 (exact tick_size multiple)."""
        result = adapter._quantize_price("SOLUSDT", 122.00)
        assert result == Decimal("122.00")

    def test_btcusdt_price_floored(self, adapter):
        """BTCUSDT: price 45678.999 → 45678.99 (floor to tick_size=0.01)."""
        result = adapter._quantize_price("BTCUSDT", 45678.999)
        assert result == Decimal("45678.99")

    def test_price_below_min_price_raises(self, adapter):
        """Price below min_price → BinanceValidationError."""
        with pytest.raises(BinanceValidationError, match="below min_price"):
            adapter._quantize_price("SOLUSDT", 0.005)

    def test_invalid_price_format_raises(self, adapter):
        """Invalid price format → BinanceValidationError."""
        with pytest.raises(BinanceValidationError, match="Invalid price format"):
            adapter._quantize_price("SOLUSDT", "not_a_number")


class TestValidateMinNotional:
    """Test _validate_min_notional."""

    def test_solusdt_valid_notional(self, adapter):
        """SOLUSDT: qty=1 * price=120 = 120 USDT >= min_notional=10."""
        # Should not raise
        adapter._validate_min_notional("SOLUSDT", Decimal("1"), Decimal("120"))

    def test_solusdt_invalid_notional_raises(self, adapter):
        """SOLUSDT: qty=1 * price=5 = 5 USDT < min_notional=10."""
        with pytest.raises(BinanceValidationError, match="below min_notional"):
            adapter._validate_min_notional(
                "SOLUSDT", Decimal("1"), Decimal("5"))

    def test_btcusdt_valid_notional(self, adapter):
        """BTCUSDT: qty=0.001 * price=45000 = 45 USDT >= min_notional=10."""
        adapter._validate_min_notional(
            "BTCUSDT", Decimal("0.001"), Decimal("45000"))

    def test_btcusdt_invalid_notional_raises(self, adapter):
        """BTCUSDT: qty=0.001 * price=5000 = 5 USDT < min_notional=10."""
        with pytest.raises(BinanceValidationError, match="below min_notional"):
            adapter._validate_min_notional(
                "BTCUSDT", Decimal("0.001"), Decimal("5000"))


class TestGetInstrumentProfile:
    """Test _get_instrument_profile with lazy loading."""

    def test_profile_cached_after_first_call(self, mock_config):
        """Instrument profile is cached after first call."""
        adapter = BinanceExecutionAdapter(
            fsm=None,
            config=mock_config,
            shadow_mode=True
        )

        with patch("apps.reference.domains.execution_position.binance_execution_adapter.resolve_instrument_profile") as mock_resolve:
            mock_resolve.return_value = InstrumentProfile(
                symbol="ETHUSDT",
                exchange="binance",
                base_asset="ETH",
                quote_asset="USDT",
                precision_quantity=3,
                precision_price=2,
                min_notional=10.0,
                min_qty=0.001,
                min_price=0.01,
                step_size=0.001,
                tick_size=0.01,
                max_position_size=50.0,
                max_leverage=20.0,
            )

            # First call - should call resolve_instrument_profile
            profile1 = adapter._get_instrument_profile("ETHUSDT")
            assert profile1.symbol == "ETHUSDT"
            assert mock_resolve.call_count == 1

            # Second call - should use cache
            profile2 = adapter._get_instrument_profile("ETHUSDT")
            assert profile2 is profile1
            assert mock_resolve.call_count == 1  # Not called again

    def test_unknown_symbol_raises(self, mock_config):
        """Unknown symbol → BinanceValidationError."""
        adapter = BinanceExecutionAdapter(
            fsm=None,
            config=mock_config,
            shadow_mode=True
        )

        with patch("apps.reference.domains.execution_position.binance_execution_adapter.resolve_instrument_profile") as mock_resolve:
            mock_resolve.side_effect = Exception("Symbol not configured")

            with pytest.raises(BinanceValidationError, match="not configured or invalid"):
                adapter._get_instrument_profile("UNKNOWN")


class TestRestTimeout:
    """Test REST timeout configuration (EP-ADAPTER-TIMEOUT-CONFIG-S20)."""

    def test_default_timeout_20_seconds(self, mock_config):
        """Default REST timeout is 20.0 seconds."""
        adapter = BinanceExecutionAdapter(
            fsm=None,
            config=mock_config,
            shadow_mode=True
        )
        assert adapter._rest_timeout == 20.0

    def test_custom_timeout_from_init(self, mock_config):
        """Custom REST timeout from __init__ parameter."""
        adapter = BinanceExecutionAdapter(
            fsm=None,
            config=mock_config,
            shadow_mode=True,
            rest_timeout_sec=30.0
        )
        assert adapter._rest_timeout == 30.0

    def test_timeout_converted_to_float(self, mock_config):
        """REST timeout is converted to float."""
        adapter = BinanceExecutionAdapter(
            fsm=None,
            config=mock_config,
            shadow_mode=True,
            rest_timeout_sec=15
        )
        assert adapter._rest_timeout == 15.0
        assert isinstance(adapter._rest_timeout, float)
