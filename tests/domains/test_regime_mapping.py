"""
Tests for regime_mapping.py — Phase B3.

Tests cover:
- FlatRegime enum values
- FlatRegimeThresholds classification
- map_to_flat_regime() function
- is_flat_regime() helper
- MR parameter multipliers
- MRParameters dataclass
"""

import pytest
from decimal import Decimal

from apps.reference.domains.feature_engineering.regime_mapping import (
    FlatRegime,
    FlatRegimeThresholds,
    DEFAULT_THRESHOLDS,
    map_to_flat_regime,
    is_flat_regime,
    get_mr_sizing_multiplier,
    get_mr_stop_multiplier,
    get_mr_target_multiplier,
    MRParameters,
    get_mr_parameters,
)


class TestFlatRegime:
    """Test FlatRegime enum."""
    
    def test_enum_values(self):
        """Check all FLAT regime values exist."""
        assert FlatRegime.FLAT_LOW is not None
        assert FlatRegime.FLAT_NORMAL is not None
        assert FlatRegime.FLAT_HIGH is not None
    
    def test_enum_unique(self):
        """Each FLAT regime has unique value."""
        regimes = [FlatRegime.FLAT_LOW, FlatRegime.FLAT_NORMAL, FlatRegime.FLAT_HIGH]
        values = [r.value for r in regimes]
        assert len(values) == len(set(values))


class TestFlatRegimeThresholds:
    """Test FlatRegimeThresholds classification."""
    
    def test_default_thresholds(self):
        """Default thresholds match R&D values."""
        assert DEFAULT_THRESHOLDS.high_vol_pct == Decimal("0.003")  # 0.3%
        assert DEFAULT_THRESHOLDS.low_vol_pct == Decimal("0.001")   # 0.1%
    
    def test_classify_low_volatility(self):
        """ATR% below low_vol_pct → FLAT_LOW."""
        thresholds = FlatRegimeThresholds()
        
        # Well below threshold
        result = thresholds.classify(Decimal("0.0005"))  # 0.05%
        assert result == FlatRegime.FLAT_LOW
        
        # Just below threshold
        result = thresholds.classify(Decimal("0.00099"))
        assert result == FlatRegime.FLAT_LOW
    
    def test_classify_high_volatility(self):
        """ATR% above high_vol_pct → FLAT_HIGH."""
        thresholds = FlatRegimeThresholds()
        
        # Well above threshold
        result = thresholds.classify(Decimal("0.005"))  # 0.5%
        assert result == FlatRegime.FLAT_HIGH
        
        # Just above threshold
        result = thresholds.classify(Decimal("0.00301"))
        assert result == FlatRegime.FLAT_HIGH
    
    def test_classify_normal_volatility(self):
        """ATR% between thresholds → FLAT_NORMAL."""
        thresholds = FlatRegimeThresholds()
        
        # Middle of range
        result = thresholds.classify(Decimal("0.002"))  # 0.2%
        assert result == FlatRegime.FLAT_NORMAL
        
        # At low threshold (inclusive)
        result = thresholds.classify(Decimal("0.001"))
        assert result == FlatRegime.FLAT_NORMAL
        
        # At high threshold (exclusive)
        result = thresholds.classify(Decimal("0.003"))
        assert result == FlatRegime.FLAT_NORMAL
    
    def test_custom_thresholds(self):
        """Custom thresholds work correctly."""
        custom = FlatRegimeThresholds(
            high_vol_pct=Decimal("0.005"),
            low_vol_pct=Decimal("0.002")
        )
        
        # Now 0.003 is NORMAL (was HIGH with default)
        result = custom.classify(Decimal("0.003"))
        assert result == FlatRegime.FLAT_NORMAL
        
        # 0.0015 is LOW (was NORMAL with default)
        result = custom.classify(Decimal("0.0015"))
        assert result == FlatRegime.FLAT_LOW


class TestMapToFlatRegime:
    """Test map_to_flat_regime() function."""
    
    # --- Trending markets → None ---
    
    def test_trend_up_returns_none(self):
        """TREND_UP not suitable for MR."""
        result = map_to_flat_regime("TREND_UP")
        assert result is None
    
    def test_trend_down_returns_none(self):
        """TREND_DOWN not suitable for MR."""
        result = map_to_flat_regime("TREND_DOWN")
        assert result is None
    
    def test_high_volatility_returns_none(self):
        """HIGH_VOLATILITY not suitable for MR."""
        result = map_to_flat_regime("HIGH_VOLATILITY")
        assert result is None
    
    # --- LOW_VOLATILITY → FLAT_LOW ---
    
    def test_low_volatility_maps_to_flat_low(self):
        """LOW_VOLATILITY → FLAT_LOW."""
        result = map_to_flat_regime("LOW_VOLATILITY")
        assert result == FlatRegime.FLAT_LOW
    
    # --- MEAN_REVERSION + ATR% ---
    
    def test_mean_reversion_without_atr(self):
        """P0 FIX: MEAN_REVERSION without ATR → None (fail-closed)."""
        result = map_to_flat_regime("MEAN_REVERSION")
        assert result is None  # P0: Without ATR, can't classify → fail-closed
    
    def test_mean_reversion_with_low_atr(self):
        """MEAN_REVERSION + low ATR → FLAT_LOW."""
        result = map_to_flat_regime("MEAN_REVERSION", Decimal("0.0005"))
        assert result == FlatRegime.FLAT_LOW
    
    def test_mean_reversion_with_normal_atr(self):
        """MEAN_REVERSION + normal ATR → FLAT_NORMAL."""
        result = map_to_flat_regime("MEAN_REVERSION", Decimal("0.002"))
        assert result == FlatRegime.FLAT_NORMAL
    
    def test_mean_reversion_with_high_atr(self):
        """MEAN_REVERSION + high ATR → FLAT_HIGH."""
        result = map_to_flat_regime("MEAN_REVERSION", Decimal("0.005"))
        assert result == FlatRegime.FLAT_HIGH
    
    # --- P0 FIX: UNCERTAIN → None (fail-closed) ---
    
    def test_uncertain_without_atr(self):
        """P0 FIX: UNCERTAIN → None (fail-closed, no trading before regime established)."""
        result = map_to_flat_regime("UNCERTAIN")
        assert result is None  # P0: MR must NOT trade when regime is uncertain
    
    def test_uncertain_with_atr(self):
        """P0 FIX: UNCERTAIN with ATR still returns None (fail-closed)."""
        result = map_to_flat_regime("UNCERTAIN", Decimal("0.0005"))
        assert result is None  # P0: ATR doesn't help if regime is uncertain
    
    # --- Edge cases ---
    
    def test_case_insensitive(self):
        """Regime matching is case-insensitive."""
        # With ATR, MEAN_REVERSION maps correctly
        assert map_to_flat_regime("mean_reversion", Decimal("0.002")) == FlatRegime.FLAT_NORMAL
        assert map_to_flat_regime("Mean_Reversion", Decimal("0.002")) == FlatRegime.FLAT_NORMAL
        assert map_to_flat_regime("MEAN_REVERSION", Decimal("0.002")) == FlatRegime.FLAT_NORMAL
    
    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace is trimmed."""
        assert map_to_flat_regime("  MEAN_REVERSION  ", Decimal("0.002")) == FlatRegime.FLAT_NORMAL
    
    def test_unknown_regime_returns_none(self):
        """Unknown regime → None."""
        assert map_to_flat_regime("UNKNOWN_REGIME") is None
        assert map_to_flat_regime("BREAKOUT") is None
    
    def test_empty_string_returns_none(self):
        """Empty string → None."""
        assert map_to_flat_regime("") is None
        assert map_to_flat_regime("   ") is None
    
    def test_none_regime_returns_none(self):
        """None regime → None."""
        assert map_to_flat_regime(None) is None


class TestIsFlatRegime:
    """Test is_flat_regime() helper."""
    
    def test_flat_regimes(self):
        """Regimes mappable to FLAT return True (only when properly configured)."""
        # LOW_VOLATILITY always maps
        assert is_flat_regime("LOW_VOLATILITY") is True
        # MEAN_REVERSION requires ATR, so without it returns False
        assert is_flat_regime("MEAN_REVERSION") is False  # P0: No ATR → fail-closed
        # UNCERTAIN always returns None now (fail-closed)
        assert is_flat_regime("UNCERTAIN") is False  # P0: fail-closed
    
    def test_non_flat_regimes(self):
        """Non-flat regimes return False."""
        assert is_flat_regime("TREND_UP") is False
        assert is_flat_regime("TREND_DOWN") is False
        assert is_flat_regime("HIGH_VOLATILITY") is False


class TestMRMultipliers:
    """Test MR parameter multiplier functions."""
    
    def test_sizing_multipliers(self):
        """Sizing multipliers are correct."""
        assert get_mr_sizing_multiplier(FlatRegime.FLAT_LOW) == Decimal("0.8")
        assert get_mr_sizing_multiplier(FlatRegime.FLAT_NORMAL) == Decimal("1.0")
        assert get_mr_sizing_multiplier(FlatRegime.FLAT_HIGH) == Decimal("0.7")
    
    def test_stop_multipliers(self):
        """Stop multipliers are correct."""
        assert get_mr_stop_multiplier(FlatRegime.FLAT_LOW) == Decimal("0.6")
        assert get_mr_stop_multiplier(FlatRegime.FLAT_NORMAL) == Decimal("1.0")
        assert get_mr_stop_multiplier(FlatRegime.FLAT_HIGH) == Decimal("1.5")
    
    def test_target_multipliers(self):
        """Target multipliers are correct."""
        assert get_mr_target_multiplier(FlatRegime.FLAT_LOW) == Decimal("0.8")
        assert get_mr_target_multiplier(FlatRegime.FLAT_NORMAL) == Decimal("1.0")
        assert get_mr_target_multiplier(FlatRegime.FLAT_HIGH) == Decimal("1.2")


class TestMRParameters:
    """Test MRParameters dataclass."""
    
    def test_from_flat_low(self):
        """MRParameters from FLAT_LOW."""
        params = MRParameters.from_flat_regime(FlatRegime.FLAT_LOW)
        
        assert params.flat_regime == FlatRegime.FLAT_LOW
        assert params.sizing_mult == Decimal("0.8")
        assert params.stop_mult == Decimal("0.6")
        assert params.target_mult == Decimal("0.8")
    
    def test_from_flat_normal(self):
        """MRParameters from FLAT_NORMAL."""
        params = MRParameters.from_flat_regime(FlatRegime.FLAT_NORMAL)
        
        assert params.flat_regime == FlatRegime.FLAT_NORMAL
        assert params.sizing_mult == Decimal("1.0")
        assert params.stop_mult == Decimal("1.0")
        assert params.target_mult == Decimal("1.0")
    
    def test_from_flat_high(self):
        """MRParameters from FLAT_HIGH."""
        params = MRParameters.from_flat_regime(FlatRegime.FLAT_HIGH)
        
        assert params.flat_regime == FlatRegime.FLAT_HIGH
        assert params.sizing_mult == Decimal("0.7")
        assert params.stop_mult == Decimal("1.5")
        assert params.target_mult == Decimal("1.2")
    
    def test_from_flat_regime_with_config_sizing(self):
        """MRParameters uses config_sizing when provided."""
        config_sizing = {
            "FLAT_NORMAL": {
                "sizing_mult": 1.5,
                "stop_mult": 0.8,
                "target_mult": 1.1
            }
        }
        
        params = MRParameters.from_flat_regime(FlatRegime.FLAT_NORMAL, config_sizing)
        
        assert params.flat_regime == FlatRegime.FLAT_NORMAL
        assert params.sizing_mult == Decimal("1.5")
        assert params.stop_mult == Decimal("0.8")
        assert params.target_mult == Decimal("1.1")
    
    def test_from_flat_regime_partial_config_override(self):
        """MRParameters uses partial config_sizing with defaults for missing."""
        config_sizing = {
            "FLAT_LOW": {
                "sizing_mult": 0.9,
                # stop_mult and target_mult not specified
            }
        }
        
        params = MRParameters.from_flat_regime(FlatRegime.FLAT_LOW, config_sizing)
        
        assert params.sizing_mult == Decimal("0.9")  # From config
        assert params.stop_mult == Decimal("0.6")    # Default
        assert params.target_mult == Decimal("0.8")  # Default


class TestMRMultipliersWithConfig:
    """Test MR multiplier functions with config_sizing override."""
    
    def test_sizing_multiplier_from_config(self):
        """get_mr_sizing_multiplier uses config when provided."""
        config = {"FLAT_HIGH": {"sizing_mult": 0.5}}
        
        result = get_mr_sizing_multiplier(FlatRegime.FLAT_HIGH, config)
        assert result == Decimal("0.5")
    
    def test_sizing_multiplier_fallback(self):
        """get_mr_sizing_multiplier falls back to default."""
        config = {"FLAT_LOW": {"sizing_mult": 0.9}}  # No FLAT_HIGH
        
        result = get_mr_sizing_multiplier(FlatRegime.FLAT_HIGH, config)
        assert result == Decimal("0.7")  # Default
    
    def test_stop_multiplier_from_config(self):
        """get_mr_stop_multiplier uses config when provided."""
        config = {"FLAT_NORMAL": {"stop_mult": 1.2}}
        
        result = get_mr_stop_multiplier(FlatRegime.FLAT_NORMAL, config)
        assert result == Decimal("1.2")
    
    def test_target_multiplier_from_config(self):
        """get_mr_target_multiplier uses config when provided."""
        config = {"FLAT_LOW": {"target_mult": 0.9}}
        
        result = get_mr_target_multiplier(FlatRegime.FLAT_LOW, config)
        assert result == Decimal("0.9")


class TestGetMRParameters:
    """Test get_mr_parameters() convenience function."""
    
    def test_returns_none_for_trending(self):
        """Returns None for trending regimes."""
        assert get_mr_parameters("TREND_UP") is None
        assert get_mr_parameters("TREND_DOWN") is None
    
    def test_returns_params_for_mean_reversion(self):
        """Returns MRParameters for MEAN_REVERSION."""
        params = get_mr_parameters("MEAN_REVERSION", Decimal("0.002"))
        
        assert params is not None
        assert params.flat_regime == FlatRegime.FLAT_NORMAL
    
    def test_uses_atr_for_classification(self):
        """ATR is used for FLAT classification."""
        # Low ATR → FLAT_LOW
        params = get_mr_parameters("MEAN_REVERSION", Decimal("0.0005"))
        assert params.flat_regime == FlatRegime.FLAT_LOW
        
        # High ATR → FLAT_HIGH
        params = get_mr_parameters("MEAN_REVERSION", Decimal("0.005"))
        assert params.flat_regime == FlatRegime.FLAT_HIGH
    
    def test_custom_thresholds(self):
        """Custom thresholds are used."""
        custom = FlatRegimeThresholds(
            high_vol_pct=Decimal("0.01"),
            low_vol_pct=Decimal("0.005")
        )
        
        # 0.003 is LOW with custom thresholds
        params = get_mr_parameters("MEAN_REVERSION", Decimal("0.003"), custom)
        assert params.flat_regime == FlatRegime.FLAT_LOW
    
    def test_with_config_sizing(self):
        """get_mr_parameters passes config_sizing to MRParameters."""
        config_sizing = {
            "FLAT_NORMAL": {"sizing_mult": 2.0}
        }
        
        params = get_mr_parameters(
            "MEAN_REVERSION",
            Decimal("0.002"),
            config_sizing=config_sizing
        )


# ============================================================================
# P0 REGRESSION TESTS: Fail-closed behavior for UNCERTAIN regime
# ============================================================================

class TestP0FailClosedRegression:
    """
    P0 REGRESSION: UNCERTAIN and MEAN_REVERSION without ATR must NOT allow trading.
    
    Before fix: UNCERTAIN → FLAT_NORMAL (allowed MR trading before regime established)
    After fix: UNCERTAIN → None (fail-closed, no trading)
    
    This prevents trading when:
    1. regime_detector has not yet established the regime (warmup phase)
    2. ATR data is not available (can't properly size stops/targets)
    """

    def test_uncertain_is_fail_closed(self):
        """P0: UNCERTAIN must return None to block MR trading."""
        result = map_to_flat_regime("UNCERTAIN")
        assert result is None, (
            "UNCERTAIN must return None (fail-closed). "
            "MR must NOT trade when regime is not established."
        )

    def test_uncertain_with_any_atr_still_fail_closed(self):
        """P0: UNCERTAIN with ATR still returns None (regime uncertainty trumps ATR)."""
        # Low ATR
        assert map_to_flat_regime("UNCERTAIN", Decimal("0.0005")) is None
        # Normal ATR
        assert map_to_flat_regime("UNCERTAIN", Decimal("0.002")) is None
        # High ATR
        assert map_to_flat_regime("UNCERTAIN", Decimal("0.005")) is None

    def test_mean_reversion_requires_atr(self):
        """P0: MEAN_REVERSION without ATR must return None (can't classify properly)."""
        result = map_to_flat_regime("MEAN_REVERSION")
        assert result is None, (
            "MEAN_REVERSION without ATR must return None. "
            "Without ATR, can't determine FLAT_LOW/NORMAL/HIGH for stop sizing."
        )

    def test_mean_reversion_with_atr_works(self):
        """MEAN_REVERSION with ATR should work normally."""
        # With ATR, classification works
        assert map_to_flat_regime("MEAN_REVERSION", Decimal("0.0005")) == FlatRegime.FLAT_LOW
        assert map_to_flat_regime("MEAN_REVERSION", Decimal("0.002")) == FlatRegime.FLAT_NORMAL
        assert map_to_flat_regime("MEAN_REVERSION", Decimal("0.005")) == FlatRegime.FLAT_HIGH

    def test_low_volatility_always_maps(self):
        """LOW_VOLATILITY should always map to FLAT_LOW (no ATR needed)."""
        # LOW_VOLATILITY is explicit regime, doesn't need ATR
        assert map_to_flat_regime("LOW_VOLATILITY") == FlatRegime.FLAT_LOW

    def test_get_mr_parameters_returns_none_for_uncertain(self):
        """get_mr_parameters returns None for UNCERTAIN regime."""
        params = get_mr_parameters("UNCERTAIN", Decimal("0.002"))
        assert params is None, "get_mr_parameters must return None for UNCERTAIN"

    def test_get_mr_parameters_returns_none_for_mr_without_atr(self):
        """get_mr_parameters returns None for MEAN_REVERSION without ATR."""
        params = get_mr_parameters("MEAN_REVERSION", None)
        assert params is None, "get_mr_parameters must return None when ATR is None"
