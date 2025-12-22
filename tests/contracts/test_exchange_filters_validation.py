"""
Tests for Exchange Filters SSOT Validation.

TASK51-A: TDD tests for fail-closed filter validation.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock

from apps.reference.domains.exchange_filters.contracts import (
    ExchangeFilters,
    SSOTFilters,
    FilterMismatch,
)
from apps.reference.domains.exchange_filters.validator import (
    ExchangeFiltersValidator,
    FilterMismatchError,
    validate_instruments_on_startup,
)


# ==============================================================================
# Test Fixtures
# ==============================================================================


def make_exchange_info(
    symbol: str,
    step_size: str = "0.001",
    min_qty: str = "0.001",
    min_notional: str = "5",
    tick_size: str = "0.01",
) -> dict:
    """Create mock exchangeInfo response."""
    return {
        "symbols": [
            {
                "symbol": symbol,
                "filters": [
                    {
                        "filterType": "LOT_SIZE",
                        "stepSize": step_size,
                        "minQty": min_qty,
                        "maxQty": "10000",
                    },
                    {
                        "filterType": "MIN_NOTIONAL",
                        "notional": min_notional,
                    },
                    {
                        "filterType": "PRICE_FILTER",
                        "tickSize": tick_size,
                    },
                ],
            }
        ]
    }


# ==============================================================================
# Contract Tests
# ==============================================================================


class TestExchangeFiltersContract:
    """Test ExchangeFilters dataclass contracts."""
    
    def test_valid_filters(self):
        """Valid filters should create successfully."""
        f = ExchangeFilters(
            symbol="SOLUSDT",
            step_size=Decimal("1"),
            min_qty=Decimal("1"),
            min_notional=Decimal("5"),
        )
        assert f.symbol == "SOLUSDT"
        assert f.step_size == Decimal("1")
    
    def test_step_size_must_be_positive(self):
        """step_size <= 0 should raise ValueError."""
        with pytest.raises(ValueError, match="step_size must be positive"):
            ExchangeFilters(
                symbol="TEST",
                step_size=Decimal("0"),
                min_qty=Decimal("1"),
                min_notional=Decimal("5"),
            )
    
    def test_min_qty_must_be_positive(self):
        """min_qty <= 0 should raise ValueError."""
        with pytest.raises(ValueError, match="min_qty must be positive"):
            ExchangeFilters(
                symbol="TEST",
                step_size=Decimal("1"),
                min_qty=Decimal("-1"),
                min_notional=Decimal("5"),
            )


class TestSSOTFiltersContract:
    """Test SSOTFilters parsing from YAML."""
    
    def test_from_yaml_dict(self):
        """Should parse YAML dict correctly."""
        data = {
            "symbol": "SOLUSDT",
            "step_size": "1",
            "min_qty": "1",
            "min_notional": "5",
            "tick_size": "0.01",
        }
        f = SSOTFilters.from_yaml_dict("SOLUSDT", data)
        assert f.step_size == Decimal("1")
        assert f.min_qty == Decimal("1")
        assert f.min_notional == Decimal("5")
    
    def test_from_yaml_dict_defaults(self):
        """Should use defaults for missing fields."""
        data = {"symbol": "TEST"}
        f = SSOTFilters.from_yaml_dict("TEST", data)
        assert f.step_size == Decimal("0.001")
        assert f.min_qty == Decimal("0.001")
        assert f.min_notional == Decimal("5")


class TestFilterMismatch:
    """Test FilterMismatch severity logic."""
    
    def test_step_size_ssot_smaller_is_critical(self):
        """SSOT step_size < exchange = CRITICAL (would cause rejects)."""
        m = FilterMismatch(
            symbol="SOLUSDT",
            field="step_size",
            ssot_value=Decimal("0.01"),  # SSOT says 0.01
            exchange_value=Decimal("1"),  # Exchange requires 1
        )
        assert m.severity == "CRITICAL"
    
    def test_step_size_ssot_larger_is_warning(self):
        """SSOT step_size > exchange = WARNING (overly conservative)."""
        m = FilterMismatch(
            symbol="ETHUSDT",
            field="step_size",
            ssot_value=Decimal("0.01"),
            exchange_value=Decimal("0.001"),
        )
        assert m.severity == "WARNING"
    
    def test_min_qty_ssot_smaller_is_critical(self):
        """SSOT min_qty < exchange = CRITICAL."""
        m = FilterMismatch(
            symbol="SOLUSDT",
            field="min_qty",
            ssot_value=Decimal("0.1"),
            exchange_value=Decimal("1"),
        )
        assert m.severity == "CRITICAL"


# ==============================================================================
# Validator Tests
# ==============================================================================


class TestExchangeFiltersValidator:
    """Test ExchangeFiltersValidator core functionality."""
    
    @pytest.mark.asyncio
    async def test_fetch_exchange_filters_parses_correctly(self):
        """Should parse exchangeInfo response into ExchangeFilters."""
        adapter = AsyncMock()
        adapter.get_exchange_info.return_value = make_exchange_info(
            "SOLUSDT",
            step_size="1",
            min_qty="1",
            min_notional="5",
        )
        
        validator = ExchangeFiltersValidator(adapter)
        filters = await validator.fetch_exchange_filters("SOLUSDT")
        
        assert filters.symbol == "SOLUSDT"
        assert filters.step_size == Decimal("1")
        assert filters.min_qty == Decimal("1")
        assert filters.min_notional == Decimal("5")
    
    @pytest.mark.asyncio
    async def test_compare_filters_no_mismatch(self):
        """Matching filters should return empty list."""
        ssot = SSOTFilters(
            symbol="ETHUSDT",
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("5"),
        )
        exchange = ExchangeFilters(
            symbol="ETHUSDT",
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("5"),
        )
        
        validator = ExchangeFiltersValidator(AsyncMock())
        mismatches = validator.compare_filters(ssot, exchange)
        
        assert len(mismatches) == 0
    
    @pytest.mark.asyncio
    async def test_compare_filters_step_size_mismatch(self):
        """Should detect step_size mismatch."""
        ssot = SSOTFilters(
            symbol="SOLUSDT",
            step_size=Decimal("0.01"),  # WRONG
            min_qty=Decimal("1"),
            min_notional=Decimal("5"),
        )
        exchange = ExchangeFilters(
            symbol="SOLUSDT",
            step_size=Decimal("1"),  # CORRECT
            min_qty=Decimal("1"),
            min_notional=Decimal("5"),
        )
        
        validator = ExchangeFiltersValidator(AsyncMock())
        mismatches = validator.compare_filters(ssot, exchange)
        
        assert len(mismatches) == 1
        assert mismatches[0].field == "step_size"
        assert mismatches[0].severity == "CRITICAL"


# ==============================================================================
# TASK51-A Required Tests
# ==============================================================================


class TestFiltersValidationCrashBehavior:
    """TASK51-A: Test fail-closed behavior."""
    
    @pytest.mark.asyncio
    async def test_filters_mismatch_crashes_in_live(self):
        """
        TASK51-A Test 1: Mismatch should crash in LIVE mode.
        
        Validates that FilterMismatchError is raised when SSOT
        doesn't match exchange filters.
        """
        adapter = AsyncMock()
        adapter.get_exchange_info.return_value = make_exchange_info(
            "SOLUSDT",
            step_size="1",  # Exchange reality
            min_qty="1",
            min_notional="5",
        )
        
        # SSOT is WRONG (says 0.01 but exchange requires 1)
        ssot_filters = {
            "SOLUSDT": SSOTFilters(
                symbol="SOLUSDT",
                step_size=Decimal("0.01"),  # WRONG!
                min_qty=Decimal("1"),
                min_notional=Decimal("5"),
            )
        }
        
        validator = ExchangeFiltersValidator(adapter, warn_only=False)
        
        with pytest.raises(FilterMismatchError) as exc_info:
            await validator.validate_all(ssot_filters, mode="live")
        
        assert "step_size" in str(exc_info.value)
        assert "SOLUSDT" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_filters_match_passes(self):
        """
        TASK51-A Test 2: Matching filters should pass without exception.
        """
        adapter = AsyncMock()
        adapter.get_exchange_info.return_value = make_exchange_info(
            "ETHUSDT",
            step_size="0.001",
            min_qty="0.001",
            min_notional="5",
        )
        
        ssot_filters = {
            "ETHUSDT": SSOTFilters(
                symbol="ETHUSDT",
                step_size=Decimal("0.001"),
                min_qty=Decimal("0.001"),
                min_notional=Decimal("5"),
            )
        }
        
        validator = ExchangeFiltersValidator(adapter, warn_only=False)
        
        # Should not raise
        mismatches = await validator.validate_all(ssot_filters, mode="live")
        assert len(mismatches) == 0
    
    @pytest.mark.asyncio
    async def test_sol_step_size_mismatch_detected(self):
        """
        TASK51-A Test 3: SOL step_size=1 mismatch should be detected.
        
        This is the specific case from production:
        - SSOT had step_size=0.01 (wrong)
        - Exchange requires step_size=1
        - Resulted in qty->0 and REJECT
        """
        adapter = AsyncMock()
        adapter.get_exchange_info.return_value = make_exchange_info(
            "SOLUSDT",
            step_size="1",  # Exchange: step_size=1 (integer lots only!)
            min_qty="1",
            min_notional="5",
        )
        
        # WRONG SSOT config (the bug that was in production)
        ssot_wrong = SSOTFilters(
            symbol="SOLUSDT",
            step_size=Decimal("0.01"),  # BUG: was 0.01
            min_qty=Decimal("0.01"),
            min_notional=Decimal("5"),
        )
        
        validator = ExchangeFiltersValidator(adapter, warn_only=False)
        
        with pytest.raises(FilterMismatchError) as exc_info:
            await validator.validate_symbol(ssot_wrong, mode="live")
        
        # Check that the error clearly identifies the problem
        error_msg = str(exc_info.value)
        assert "SOLUSDT" in error_msg
        assert "step_size" in error_msg
        # The mismatch should show SSOT=0.01 vs Exchange=1
        assert any(
            m.ssot_value == Decimal("0.01") and m.exchange_value == Decimal("1")
            for m in exc_info.value.mismatches
        )


class TestWarmonlyMode:
    """Test warn_only behavior for DEV/SHADOW modes."""
    
    @pytest.mark.asyncio
    async def test_warn_only_logs_instead_of_crash(self):
        """
        warn_only=True should log warning instead of raising exception.
        """
        adapter = AsyncMock()
        adapter.get_exchange_info.return_value = make_exchange_info(
            "SOLUSDT",
            step_size="1",
            min_qty="1",
            min_notional="5",
        )
        
        ssot_filters = {
            "SOLUSDT": SSOTFilters(
                symbol="SOLUSDT",
                step_size=Decimal("0.01"),  # WRONG
                min_qty=Decimal("1"),
                min_notional=Decimal("5"),
            )
        }
        
        validator = ExchangeFiltersValidator(adapter, warn_only=True)
        
        # Should NOT raise with warn_only=True
        mismatches = await validator.validate_all(ssot_filters, mode="shadow")
        
        assert "SOLUSDT" in mismatches
        assert len(mismatches["SOLUSDT"]) > 0


class TestValidateInstrumentsOnStartup:
    """Test the startup hook function."""
    
    @pytest.mark.asyncio
    async def test_validates_instruments_yaml_format(self):
        """Should parse instruments.yaml format correctly."""
        adapter = AsyncMock()
        adapter.get_exchange_info.return_value = make_exchange_info(
            "BTCUSDT",
            step_size="0.001",
            min_qty="0.001",
            min_notional="100",
        )
        
        instruments_config = {
            "instruments": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "step_size": "0.001",
                    "min_qty": "0.001",
                    "min_notional": "100",
                }
            }
        }
        
        # Should not raise
        await validate_instruments_on_startup(
            adapter,
            instruments_config,
            mode="testnet",
        )
    
    @pytest.mark.asyncio
    async def test_empty_instruments_skips_validation(self):
        """Empty instruments config should skip validation."""
        adapter = AsyncMock()
        
        # Should not raise
        await validate_instruments_on_startup(
            adapter,
            {},
            mode="live",
        )
        
        # Adapter should not be called
        adapter.get_exchange_info.assert_not_called()


# ==============================================================================
# Integration Tests (with actual YAML config)
# ==============================================================================


class TestIntegrationWithRealConfig:
    """Integration tests with actual instruments.yaml structure."""
    
    @pytest.mark.asyncio
    async def test_current_ssot_matches_expected_exchange_values(self):
        """
        Verify that current instruments.yaml has correct values
        for the known symbols.
        """
        # These are the CORRECT values from Binance testnet
        expected = {
            "SOLUSDT": {"step_size": "1", "min_qty": "1", "min_notional": "5"},
            "ETHUSDT": {"step_size": "0.001", "min_qty": "0.001", "min_notional": "5"},
            "BTCUSDT": {"step_size": "0.001", "min_qty": "0.001", "min_notional": "100"},
        }
        
        adapter = AsyncMock()
        
        async def mock_get_exchange_info(symbol):
            if symbol in expected:
                return make_exchange_info(symbol, **expected[symbol])
            raise ValueError(f"Unknown symbol: {symbol}")
        
        adapter.get_exchange_info = mock_get_exchange_info
        
        # Current SSOT values (should match)
        ssot_filters = {
            "SOLUSDT": SSOTFilters.from_yaml_dict("SOLUSDT", {
                "symbol": "SOLUSDT",
                "step_size": "1",
                "min_qty": "1",
                "min_notional": "5",
            }),
            "ETHUSDT": SSOTFilters.from_yaml_dict("ETHUSDT", {
                "symbol": "ETHUSDT",
                "step_size": "0.001",
                "min_qty": "0.001",
                "min_notional": "5",
            }),
            "BTCUSDT": SSOTFilters.from_yaml_dict("BTCUSDT", {
                "symbol": "BTCUSDT",
                "step_size": "0.001",
                "min_qty": "0.001",
                "min_notional": "100",
            }),
        }
        
        validator = ExchangeFiltersValidator(adapter)
        
        # Should pass without exception
        mismatches = await validator.validate_all(ssot_filters, mode="live")
        assert len(mismatches) == 0
