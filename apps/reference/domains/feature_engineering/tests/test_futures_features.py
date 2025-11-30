"""
Tests for Futures Features (FTR-05).

Tests:
- Funding rate normalization
- Open Interest delta calculation
- Config gating (futures.enabled)
- V1 regression (existing tests unaffected)
"""

import pytest
from decimal import Decimal
from dataclasses import dataclass
from collections import deque
from typing import Dict, Any, Optional

from apps.reference.domains.feature_engineering.types import (
    HotState,
    ColdState,
    SymbolFeatureState,
    FeatureEngineeringConfig,
)
from apps.reference.domains.feature_engineering.calculation_engine import (
    FeatureCalculationEngine,
)


# =============================================================================
# MOCK CONFIG FOR TESTING
# =============================================================================

@dataclass
class MockFuturesConfig:
    enabled: bool = True
    
@dataclass
class MockFundingConfig:
    extreme_threshold: float = 0.001

@dataclass
class MockFuturesSection:
    enabled: bool = True
    funding: MockFundingConfig = None
    
    def __post_init__(self):
        if self.funding is None:
            self.funding = MockFundingConfig()


@dataclass
class MockDefaultsConfig:
    neutral_value: float = 0.5
    zero_value: float = 0.0
    correlation_default: float = 0.0
    ms_per_sec: int = 1000


@dataclass 
class MockFeatureEngineeringConfig:
    """Minimal mock config for testing calculation engine."""
    enable_new_metrics: bool = True
    futures: MockFuturesSection = None
    defaults: MockDefaultsConfig = None
    
    def __post_init__(self):
        if self.futures is None:
            self.futures = MockFuturesSection()
        if self.defaults is None:
            self.defaults = MockDefaultsConfig()


class TestableConfig:
    """Config wrapper for testing that mimics FeatureEngineeringConfig interface."""
    
    def __init__(self, futures_enabled: bool = True, extreme_threshold: float = 0.001):
        self._futures_enabled = futures_enabled
        self._extreme_threshold = Decimal(str(extreme_threshold))
        self._neutral_value = Decimal("0.5")
    
    @property
    def futures_enabled(self) -> bool:
        return self._futures_enabled
    
    @property
    def funding_extreme_threshold(self) -> Decimal:
        return self._extreme_threshold
    
    @property
    def neutral_value(self) -> Decimal:
        return self._neutral_value


# =============================================================================
# UNIT TESTS: CALCULATION ENGINE - FUNDING
# =============================================================================

class TestFundingNormalization:
    """Tests for funding rate normalization."""
    
    def setup_method(self):
        """Create fresh engine and state for each test."""
        self.cfg = TestableConfig(futures_enabled=True, extreme_threshold=0.001)
        self.engine = FeatureCalculationEngine(self.cfg)
        self.cold = ColdState()
    
    def test_funding_zero_returns_none(self):
        """No funding data yet -> return None."""
        result = self.engine.compute_funding_normalized(self.cold)
        assert result is None
    
    def test_funding_positive_normalized(self):
        """Positive funding (longs pay shorts) -> positive normalized."""
        self.engine.update_funding(self.cold, Decimal("0.0005"))  # 0.05%
        result = self.engine.compute_funding_normalized(self.cold)
        
        # 0.0005 / 0.001 = 0.5
        assert result == Decimal("0.5000")
    
    def test_funding_negative_normalized(self):
        """Negative funding (shorts pay longs) -> negative normalized."""
        self.engine.update_funding(self.cold, Decimal("-0.0003"))  # -0.03%
        result = self.engine.compute_funding_normalized(self.cold)
        
        # -0.0003 / 0.001 = -0.3
        assert result == Decimal("-0.3000")
    
    def test_funding_at_threshold_clamped_to_one(self):
        """Funding at threshold -> normalized = 1.0."""
        self.engine.update_funding(self.cold, Decimal("0.001"))  # exactly threshold
        result = self.engine.compute_funding_normalized(self.cold)
        assert result == Decimal("1.0000")
    
    def test_funding_above_threshold_clamped(self):
        """Funding above threshold -> clamped to 1.0."""
        self.engine.update_funding(self.cold, Decimal("0.005"))  # 0.5% (5x threshold)
        result = self.engine.compute_funding_normalized(self.cold)
        assert result == Decimal("1.0000")
    
    def test_funding_extreme_negative_clamped(self):
        """Extreme negative funding -> clamped to -1.0."""
        self.engine.update_funding(self.cold, Decimal("-0.003"))  # -0.3%
        result = self.engine.compute_funding_normalized(self.cold)
        assert result == Decimal("-1.0000")
    
    def test_funding_update_stores_next_ts(self):
        """update_funding stores next_funding_ts."""
        self.engine.update_funding(self.cold, Decimal("0.0001"), next_funding_ts=1234567890000)
        assert self.cold.next_funding_ts == 1234567890000


# =============================================================================
# UNIT TESTS: CALCULATION ENGINE - OPEN INTEREST
# =============================================================================

class TestOpenInterestDelta:
    """Tests for Open Interest delta percentage calculation."""
    
    def setup_method(self):
        """Create fresh engine and state for each test."""
        self.cfg = TestableConfig(futures_enabled=True)
        self.engine = FeatureCalculationEngine(self.cfg)
        self.cold = ColdState()
    
    def test_oi_no_prev_returns_none(self):
        """No previous OI -> return None (first update)."""
        self.engine.update_open_interest(self.cold, Decimal("50000"))
        result = self.engine.compute_oi_delta_pct(self.cold)
        assert result is None
    
    def test_oi_delta_positive(self):
        """OI increased -> positive delta."""
        # First update: establishes baseline
        self.engine.update_open_interest(self.cold, Decimal("50000"))
        # Second update: 10% increase
        self.engine.update_open_interest(self.cold, Decimal("55000"))
        
        result = self.engine.compute_oi_delta_pct(self.cold)
        
        # (55000 - 50000) / 50000 * 100 = 10%
        assert result == Decimal("10.00")
    
    def test_oi_delta_negative(self):
        """OI decreased -> negative delta."""
        self.engine.update_open_interest(self.cold, Decimal("50000"))
        self.engine.update_open_interest(self.cold, Decimal("45000"))
        
        result = self.engine.compute_oi_delta_pct(self.cold)
        
        # (45000 - 50000) / 50000 * 100 = -10%
        assert result == Decimal("-10.00")
    
    def test_oi_delta_small_change(self):
        """Small OI change -> accurate delta."""
        self.engine.update_open_interest(self.cold, Decimal("100000"))
        self.engine.update_open_interest(self.cold, Decimal("100500"))
        
        result = self.engine.compute_oi_delta_pct(self.cold)
        
        # (100500 - 100000) / 100000 * 100 = 0.5%
        assert result == Decimal("0.50")
    
    def test_oi_stores_timestamp(self):
        """update_open_interest stores timestamp."""
        self.engine.update_open_interest(self.cold, Decimal("50000"), ts=1234567890000)
        assert self.cold.last_oi_update_ts == 1234567890000
    
    def test_oi_history_chain(self):
        """Multiple updates maintain correct history."""
        self.engine.update_open_interest(self.cold, Decimal("100"))
        self.engine.update_open_interest(self.cold, Decimal("110"))
        self.engine.update_open_interest(self.cold, Decimal("99"))
        
        # Current state
        assert self.cold.open_interest == Decimal("99")
        assert self.cold.prev_open_interest == Decimal("110")
        
        # Delta = (99 - 110) / 110 * 100 = -10%
        result = self.engine.compute_oi_delta_pct(self.cold)
        assert result == Decimal("-10.00")


# =============================================================================
# INTEGRATION TEST: COLD STATE UPDATES
# =============================================================================

class TestColdStateIntegration:
    """Integration tests for ColdState updates."""
    
    def test_cold_state_initial_values(self):
        """ColdState initializes with correct defaults."""
        cold = ColdState()
        
        assert cold.funding_rate == Decimal("0")
        assert cold.open_interest == Decimal("0")
        assert cold.next_funding_ts == 0
        assert cold.prev_open_interest is None
        assert cold.last_oi_update_ts == 0
    
    def test_symbol_feature_state_cold_access(self):
        """SymbolFeatureState.cold is accessible and mutable."""
        hot = HotState()
        cold = ColdState()
        state = SymbolFeatureState(hot=hot, cold=cold)
        
        # Update via cold reference
        state.cold.funding_rate = Decimal("0.0001")
        assert state.cold.funding_rate == Decimal("0.0001")


# =============================================================================
# CONTRACT TESTS: V2 FEATURES
# =============================================================================

class TestV2FuturesContracts:
    """Tests for V2 Futures feature contracts."""
    
    def test_v2_metadata_contains_futures(self):
        """V2_FEATURE_METADATA includes futures features."""
        from apps.reference.domains.feature_engineering.contracts import V2_FEATURE_METADATA
        
        assert "funding_rate_normalized" in V2_FEATURE_METADATA
        assert "oi_delta_pct" in V2_FEATURE_METADATA
        assert "funding_rate" in V2_FEATURE_METADATA
    
    def test_v2_metadata_futures_group(self):
        """Futures features have group='futures'."""
        from apps.reference.domains.feature_engineering.contracts import V2_FEATURE_METADATA
        
        assert V2_FEATURE_METADATA["funding_rate_normalized"]["group"] == "futures"
        assert V2_FEATURE_METADATA["oi_delta_pct"]["group"] == "futures"
    
    def test_funding_normalized_range(self):
        """funding_rate_normalized has correct range."""
        from apps.reference.domains.feature_engineering.contracts import V2_FEATURE_METADATA
        
        meta = V2_FEATURE_METADATA["funding_rate_normalized"]
        assert meta["range"] == (-1, 1)
        assert meta["neutral"] == Decimal("0")


# =============================================================================
# CONFIG GATING TESTS
# =============================================================================

class TestFuturesConfigGating:
    """Tests for futures.enabled config gating."""
    
    def test_config_futures_disabled_by_default(self):
        """futures_enabled returns False when config has no futures section."""
        # Create minimal mock that doesn't have futures
        class MinimalConfig:
            def __init__(self):
                self._cfg = type('obj', (object,), {'futures': None})()
        
        cfg = FeatureEngineeringConfig.__new__(FeatureEngineeringConfig)
        cfg._cfg = type('obj', (object,), {'futures': None})()
        
        assert cfg.futures_enabled == False
    
    def test_testable_config_enabled(self):
        """TestableConfig with futures_enabled=True works."""
        cfg = TestableConfig(futures_enabled=True)
        assert cfg.futures_enabled == True
    
    def test_testable_config_disabled(self):
        """TestableConfig with futures_enabled=False works."""
        cfg = TestableConfig(futures_enabled=False)
        assert cfg.futures_enabled == False


# =============================================================================
# EDGE CASES
# =============================================================================

class TestFuturesEdgeCases:
    """Edge case tests for robustness."""
    
    def setup_method(self):
        self.cfg = TestableConfig(futures_enabled=True)
        self.engine = FeatureCalculationEngine(self.cfg)
        self.cold = ColdState()
    
    def test_funding_very_small_value(self):
        """Very small funding rate normalizes correctly."""
        self.engine.update_funding(self.cold, Decimal("0.00001"))  # 0.001%
        result = self.engine.compute_funding_normalized(self.cold)
        
        # 0.00001 / 0.001 = 0.01
        assert result == Decimal("0.0100")
    
    def test_oi_prev_zero_returns_none(self):
        """OI delta with prev=0 returns None (avoid division by zero)."""
        self.cold.prev_open_interest = Decimal("0")
        self.cold.open_interest = Decimal("50000")
        
        result = self.engine.compute_oi_delta_pct(self.cold)
        assert result is None
    
    def test_oi_large_values(self):
        """OI delta handles large values correctly."""
        self.engine.update_open_interest(self.cold, Decimal("1000000000"))  # 1B
        self.engine.update_open_interest(self.cold, Decimal("1050000000"))  # 1.05B
        
        result = self.engine.compute_oi_delta_pct(self.cold)
        assert result == Decimal("5.00")
