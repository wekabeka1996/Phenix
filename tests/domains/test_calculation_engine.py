"""
Tests for FeatureCalculationEngine (Phase B2 Pure Math Layer).

P2 Regression Tests:
- P2-2: depth_imbalance semantics (phi > 0.5 = bearish = ask dominance)
- P2-3: ts vs ts_ms handling in volatility_state
"""

import pytest
from decimal import Decimal

from apps.reference.domains.feature_engineering.calculation_engine import (
    FeatureCalculationEngine,
)


class _MinimalCfg:
    """Minimal config mock for FeatureCalculationEngine tests."""
    # Depth imbalance
    depth_half = Decimal("1000")
    neutral_value = Decimal("0.5")
    depth_imbalance_use_laplace_smoothing = False
    
    # Volatility
    volatility_sma_length = 10
    volatility_clamp_max = Decimal("0.1")
    volatility_window_ms = 60_000  # 1 minute window
    
    # Not used but required for engine init
    ms_per_sec = 1000


class TestDepthImbalanceSemantics:
    """P2-2 REGRESSION: depth_imbalance semantics.
    
    Contract:
    - phi > 0.5 = bearish (ask dominance, selling pressure)
    - phi < 0.5 = bullish (bid dominance, buying pressure)
    - phi = 0.5 = neutral
    """

    def test_ask_dominance_is_bearish(self):
        """When ask_qty > bid_qty, phi > 0.5 (bearish)."""
        cfg = _MinimalCfg()
        engine = FeatureCalculationEngine(cfg)
        
        # Ask dominance: sellers > buyers
        bid_qty = Decimal("100")
        ask_qty = Decimal("200")
        
        phi = engine.compute_depth_imbalance(bid_qty, ask_qty)
        
        assert phi > Decimal("0.5"), (
            f"phi={phi}, expected > 0.5 when ask > bid (bearish)"
        )

    def test_bid_dominance_is_bullish(self):
        """When bid_qty > ask_qty, phi < 0.5 (bullish)."""
        cfg = _MinimalCfg()
        engine = FeatureCalculationEngine(cfg)
        
        # Bid dominance: buyers > sellers
        bid_qty = Decimal("200")
        ask_qty = Decimal("100")
        
        phi = engine.compute_depth_imbalance(bid_qty, ask_qty)
        
        assert phi < Decimal("0.5"), (
            f"phi={phi}, expected < 0.5 when bid > ask (bullish)"
        )

    def test_equal_is_neutral(self):
        """When bid_qty == ask_qty, phi = 0.5 (neutral)."""
        cfg = _MinimalCfg()
        engine = FeatureCalculationEngine(cfg)
        
        bid_qty = Decimal("100")
        ask_qty = Decimal("100")
        
        phi = engine.compute_depth_imbalance(bid_qty, ask_qty)
        
        assert phi == Decimal("0.5"), (
            f"phi={phi}, expected exactly 0.5 when bid == ask (neutral)"
        )

    def test_zero_quantities_handled(self):
        """Zero quantities should not cause ZeroDivision."""
        cfg = _MinimalCfg()
        engine = FeatureCalculationEngine(cfg)
        
        # Both zero - epsilon prevents division by zero
        phi = engine.compute_depth_imbalance(Decimal("0"), Decimal("0"))
        
        assert phi == Decimal("0.5"), "Zero/zero should be neutral"
        
    def test_one_side_zero(self):
        """One side zero should push phi towards extreme (limited by Laplace smoothing)."""
        cfg = _MinimalCfg()
        engine = FeatureCalculationEngine(cfg)
        
        # Note: With depth_half=1000, Laplace smoothing prevents true extremes
        # For small quantities vs depth_half, phi won't reach 0 or 1
        # Use larger quantities to see more pronounced effect
        
        # All ask (10x depth_half), minimal bid = bearish
        phi_bearish = engine.compute_depth_imbalance(Decimal("0"), Decimal("10000"))
        assert phi_bearish > Decimal("0.5"), f"Expected >0.5 (bearish), got {phi_bearish}"
        
        # All bid (10x depth_half), minimal ask = bullish
        phi_bullish = engine.compute_depth_imbalance(Decimal("10000"), Decimal("0"))
        assert phi_bullish < Decimal("0.5"), f"Expected <0.5 (bullish), got {phi_bullish}"
        
        # Verify ordering: bearish > neutral > bullish
        phi_neutral = engine.compute_depth_imbalance(Decimal("100"), Decimal("100"))
        assert phi_bearish > phi_neutral > phi_bullish, \
            f"Expected bearish({phi_bearish}) > neutral({phi_neutral}) > bullish({phi_bullish})"


class TestVolatilityTsHandling:
    """P2-3 REGRESSION: ts vs ts_ms handling in volatility_state.
    
    Contract:
    - ts_ms should be in milliseconds (> 1_000_000_000_000 for 2001+)
    - If ts appears to be in seconds, auto-convert to ms
    - If ts is invalid (0, negative, None), volatility not ready
    """

    def test_ts_ms_valid_milliseconds(self):
        """Valid ts_ms in milliseconds should work."""
        from collections import deque
        from apps.reference.domains.feature_engineering.types import HotState
        
        cfg = _MinimalCfg()
        engine = FeatureCalculationEngine(cfg)
        
        state = HotState(
            range_hist=deque(maxlen=cfg.volatility_sma_length),
        )
        
        ts_ms = 1700000000000  # Nov 2023 in ms
        current_tick = {"ts": ts_ms, "price": Decimal("100")}
        
        # Should not raise exception
        engine.update_volatility_state(state, Decimal("100"), current_tick)
        
        # Should initialize range window
        assert state.range_window_start_ts is not None

    def test_ts_seconds_auto_converted(self):
        """ts in seconds should be auto-converted to ms (if implemented)."""
        from collections import deque
        from apps.reference.domains.feature_engineering.types import HotState
        
        cfg = _MinimalCfg()
        engine = FeatureCalculationEngine(cfg)
        
        state = HotState(
            range_hist=deque(maxlen=cfg.volatility_sma_length),
        )
        
        ts_sec = 1700000000  # Nov 2023 in seconds
        current_tick = {"ts": ts_sec, "price": Decimal("100")}
        
        # Should handle gracefully (auto-convert and accept)
        engine.update_volatility_state(state, Decimal("100"), current_tick)
        
        # After P2-3 fix: seconds auto-converted to ms
        # Window start should be in ms range
        assert state.range_window_start_ts is not None
        assert state.range_window_start_ts >= 1_000_000_000_000, \
            f"Expected ms timestamp, got {state.range_window_start_ts}"

    def test_ts_zero_not_ready(self):
        """ts=0 should set not ready flag."""
        from collections import deque
        from apps.reference.domains.feature_engineering.types import HotState
        
        cfg = _MinimalCfg()
        engine = FeatureCalculationEngine(cfg)
        
        state = HotState(
            range_hist=deque(maxlen=cfg.volatility_sma_length),
        )
        
        current_tick = {"ts": 0, "price": Decimal("100")}
        
        # Should not raise exception
        engine.update_volatility_state(state, Decimal("100"), current_tick)
        
        # After P2-3 fix: bad ts should set not ready
        assert state.volatility_state_ready is False
        assert state.volatility_state_not_ready_reason == "bad_ts"

    def test_ts_missing_key_handled(self):
        """Missing ts key should be handled gracefully."""
        from collections import deque
        from apps.reference.domains.feature_engineering.types import HotState
        
        cfg = _MinimalCfg()
        engine = FeatureCalculationEngine(cfg)
        
        state = HotState(
            range_hist=deque(maxlen=cfg.volatility_sma_length),
        )
        
        current_tick = {"price": Decimal("100")}  # No ts
        
        # Should not raise KeyError, uses .get() with default 0
        engine.update_volatility_state(state, Decimal("100"), current_tick)
        
        # Should set not ready (ts defaults to 0)
        assert state.volatility_state_ready is False
