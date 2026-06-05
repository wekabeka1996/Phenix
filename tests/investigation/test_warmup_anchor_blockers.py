"""
Investigation Tests: Warmup and Anchor Blockers

Purpose: Diagnose why no orders are placed in live trading.

Two suspected issues:
1. FeatureEngineering warmup.full_ready never becomes True because macro_resid
   is not ready (depends on anchor BTC price history).
2. anchor_update_from_ticks: false in domains.yaml prevents anchor_prices from
   being populated via ticks (only EVT:ANCHOR_UPDATED works).

These tests verify the exact conditions required for macro_resid readiness
and how anchor data flows into FeatureEngineering.
"""

import unittest
import decimal
from collections import deque
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Optional, Dict, Any


# =============================================================================
# SECTION 1: MACRO_RESID WARMUP REQUIREMENTS
# =============================================================================

class TestMacroResidWarmupRequirements(unittest.TestCase):
    """
    Test the exact conditions required for macro_resid to become ready.
    
    Hypothesis: macro_resid requires:
    1. beta_window samples in macro_resid_asset_returns AND macro_resid_anchor_returns
    2. mad_window samples in macro_resid_buffer
    3. var(anchor_returns) > var_floor
    
    If anchor_prices (BTCUSDT) is empty or has < 2 elements, NO returns are
    calculated → macro_resid NEVER becomes ready → full_ready = False → NO TRADING.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from apps.reference.domains.feature_engineering.types import HotState
        
        self.cfg = MagicMock()
        self.cfg.macro_resid_enabled = True
        self.cfg.macro_resid_beta_window = 20
        self.cfg.macro_resid_mad_window = 10
        self.cfg.macro_resid_winsor_percentile = 0.0
        self.cfg.macro_resid_var_floor = 1e-10
        self.cfg.macro_resid_scale_floor = 1e-6
        self.cfg.macro_resid_clip = 3.0
        self.cfg.macro_resid_neutral = 0.0
        
        self.engine = FeatureCalculationEngine(self.cfg)
        self.state = HotState()
    
    def test_fresh_state_not_ready_with_reason(self):
        """Fresh HotState should not be ready, with explicit reason."""
        value, is_ready, reason = self.engine.compute_macro_resid(self.state)
        
        self.assertFalse(is_ready, "Fresh state should NOT be ready")
        self.assertIsNotNone(reason, "Reason must be provided")
        self.assertIn("insufficient_samples", reason)
        self.assertEqual(float(value), 0.0, "Should return neutral value")
    
    def test_partial_warmup_not_ready(self):
        """Partial warmup (beta filled, MAD not) should not be ready."""
        # Fill beta_window samples
        for i in range(self.cfg.macro_resid_beta_window):
            self.engine.update_macro_resid(self.state, 0.001 * i, 0.001 * i)
        
        # But don't call compute enough times to fill MAD buffer
        value, is_ready, reason = self.engine.compute_macro_resid(self.state)
        
        # Should not be ready - MAD buffer not full
        self.assertFalse(is_ready, f"Should NOT be ready, reason: {reason}")
        self.assertIn("mad_warmup", reason or "")
    
    def test_full_warmup_becomes_ready(self):
        """Full warmup (beta + MAD filled) should become ready."""
        total_needed = self.cfg.macro_resid_beta_window + self.cfg.macro_resid_mad_window
        
        for i in range(total_needed):
            # Varying returns to avoid var_floor issue
            anchor_ret = 0.001 * ((i % 10) - 5)
            asset_ret = anchor_ret * 1.1  # Slightly different
            self.engine.update_macro_resid(self.state, asset_ret, anchor_ret)
            self.engine.compute_macro_resid(self.state)  # Populates MAD buffer
        
        value, is_ready, reason = self.engine.compute_macro_resid(self.state)
        
        self.assertTrue(is_ready, f"Should be ready after full warmup, reason: {reason}")
        self.assertIsNone(reason)
    
    def test_zero_variance_anchor_failopen_ready(self):
        """If all anchor returns are identical, var < floor → fail-open with beta=0.
        
        This is the CRITICAL fix: low anchor variance should NOT block warmup.
        Instead, we degrade to beta=0 (no anchor info), which computes macro_resid
        based purely on asset returns. This prevents permanent warmup deadlock.
        """
        # All identical anchor returns = zero variance
        for i in range(50):
            self.engine.update_macro_resid(self.state, 0.001 * i, 0.005)  # Fixed anchor
            self.engine.compute_macro_resid(self.state)
        
        value, is_ready, reason = self.engine.compute_macro_resid(self.state)
        
        # FAIL-OPEN: must become ready even with zero anchor variance
        self.assertTrue(is_ready, f"Zero variance should NOT block readiness (fail-open), got reason: {reason}")
        self.assertIsNone(reason, f"Should have no blocking reason, got: {reason}")
        # Value should be non-zero since asset returns vary
        self.assertNotEqual(float(value), 0.0, "Value should be non-zero (based on asset returns only)")
    
    def test_readiness_state_persists(self):
        """Verify readiness state is persisted in HotState."""
        # Before warmup
        self.assertFalse(self.state.macro_resid_ready)
        self.assertIsNone(self.state.macro_resid_not_ready_reason)
        
        # Partial warmup - compute to set reason
        self.engine.compute_macro_resid(self.state)
        self.assertFalse(self.state.macro_resid_ready)
        self.assertIsNotNone(self.state.macro_resid_not_ready_reason)
        
        # Full warmup
        for i in range(100):
            anchor_ret = 0.001 * ((i % 10) - 5)
            asset_ret = anchor_ret * 1.1
            self.engine.update_macro_resid(self.state, asset_ret, anchor_ret)
            self.engine.compute_macro_resid(self.state)
        
        self.assertTrue(self.state.macro_resid_ready)
        self.assertIsNone(self.state.macro_resid_not_ready_reason)


class TestMacroResidDependsOnAnchorHistory(unittest.TestCase):
    """
    Test that macro_resid computation in FeatureEngineering depends on anchor_prices.
    
    This is the CRITICAL path:
    - FeatureEngineering._calculate_and_emit_features()
    - Checks self.anchor_prices.get("BTCUSDT", None)
    - If None or len < 2, anchor_return cannot be computed
    - Therefore macro_resid buffers are NEVER updated
    - Therefore macro_resid NEVER becomes ready
    
    This test verifies this dependency.
    """
    
    def test_anchor_prices_empty_prevents_macro_resid_update(self):
        """When anchor_prices is empty, macro_resid buffers are never updated."""
        # Simulate the condition in feature_engineering.py lines 567-577
        anchor_prices: Dict[str, deque] = {"BTCUSDT": deque(maxlen=12)}
        
        btc_price_hist = anchor_prices.get("BTCUSDT", None)
        
        # Condition from code: if btc_price_hist and len(btc_price_hist) >= 2
        can_compute_returns = bool(btc_price_hist and len(btc_price_hist) >= 2)
        
        self.assertFalse(can_compute_returns, 
            "Empty anchor_prices should prevent return computation")
    
    def test_single_anchor_price_prevents_macro_resid_update(self):
        """When anchor_prices has only 1 element, returns cannot be computed."""
        anchor_prices: Dict[str, deque] = {"BTCUSDT": deque(maxlen=12)}
        anchor_prices["BTCUSDT"].append(decimal.Decimal("100000"))
        
        btc_price_hist = anchor_prices.get("BTCUSDT", None)
        can_compute_returns = bool(btc_price_hist and len(btc_price_hist) >= 2)
        
        self.assertFalse(can_compute_returns,
            "Single price in anchor_prices should prevent return computation")
    
    def test_two_anchor_prices_enables_macro_resid_update(self):
        """When anchor_prices has >= 2 elements, returns can be computed."""
        anchor_prices: Dict[str, deque] = {"BTCUSDT": deque(maxlen=12)}
        anchor_prices["BTCUSDT"].append(decimal.Decimal("99000"))
        anchor_prices["BTCUSDT"].append(decimal.Decimal("100000"))
        
        btc_price_hist = anchor_prices.get("BTCUSDT", None)
        can_compute_returns = bool(btc_price_hist and len(btc_price_hist) >= 2)
        
        self.assertTrue(can_compute_returns,
            "Two prices in anchor_prices should enable return computation")
    
    def test_anchor_return_calculation(self):
        """Verify anchor return calculation matches code."""
        anchor_prices: Dict[str, deque] = {"BTCUSDT": deque(maxlen=12)}
        anchor_prices["BTCUSDT"].append(decimal.Decimal("95000"))
        anchor_prices["BTCUSDT"].append(decimal.Decimal("100000"))
        
        btc_price_hist = anchor_prices["BTCUSDT"]
        btc_prev = btc_price_hist[-2] if len(btc_price_hist) >= 2 else btc_price_hist[-1]
        btc_curr = btc_price_hist[-1]
        anchor_return = float((btc_curr - btc_prev) / btc_prev) if btc_prev > 0 else 0.0
        
        expected = (100000 - 95000) / 95000
        self.assertAlmostEqual(anchor_return, expected, places=6)


# =============================================================================
# SECTION 2: ANCHOR UPDATE MECHANISMS
# =============================================================================

class TestAnchorUpdateMechanisms(unittest.TestCase):
    """
    Test the two mechanisms for updating anchor_prices:
    1. EVT:ANCHOR_UPDATED event (always works)
    2. Tick-based update (only if anchor_update_from_ticks: true)
    
    With anchor_update_from_ticks: false (default), ONLY EVT:ANCHOR_UPDATED works.
    If MarketData doesn't emit EVT:ANCHOR_UPDATED, anchor_prices stays empty.
    """
    
    def test_anchor_update_from_ticks_false_blocks_tick_updates(self):
        """When anchor_update_from_ticks=false, ticks don't update anchor_prices."""
        # Simulate config
        cfg = MagicMock()
        cfg.macro_sync_anchor_update_from_ticks = False
        cfg.macro_sync_anchors = ["BTCUSDT", "ETHUSDT"]
        
        # Simulate tick for anchor symbol
        symbol = "BTCUSDT"
        price = decimal.Decimal("100000")
        
        # Condition from code line 430:
        # if self.cfg.macro_sync_anchor_update_from_ticks and symbol in self.cfg.macro_sync_anchors:
        should_update = cfg.macro_sync_anchor_update_from_ticks and symbol in cfg.macro_sync_anchors
        
        self.assertFalse(should_update,
            "With anchor_update_from_ticks=false, ticks should NOT update anchor_prices")
    
    def test_anchor_update_from_ticks_true_allows_tick_updates(self):
        """When anchor_update_from_ticks=true, ticks update anchor_prices."""
        cfg = MagicMock()
        cfg.macro_sync_anchor_update_from_ticks = True
        cfg.macro_sync_anchors = ["BTCUSDT", "ETHUSDT"]
        
        symbol = "BTCUSDT"
        
        should_update = cfg.macro_sync_anchor_update_from_ticks and symbol in cfg.macro_sync_anchors
        
        self.assertTrue(should_update,
            "With anchor_update_from_ticks=true, ticks SHOULD update anchor_prices")
    
    def test_non_anchor_symbol_never_updates_anchor_prices(self):
        """Non-anchor symbols never update anchor_prices, regardless of config."""
        cfg = MagicMock()
        cfg.macro_sync_anchor_update_from_ticks = True
        cfg.macro_sync_anchors = ["BTCUSDT", "ETHUSDT"]
        
        symbol = "DOGEUSDT"  # Not an anchor
        
        should_update = cfg.macro_sync_anchor_update_from_ticks and symbol in cfg.macro_sync_anchors
        
        self.assertFalse(should_update,
            "Non-anchor symbols should never update anchor_prices")


class TestEvtAnchorUpdatedHandler(unittest.TestCase):
    """
    Test EVT:ANCHOR_UPDATED event handling in FeatureEngineering.
    
    This is the PRIMARY mechanism for anchor price updates when
    anchor_update_from_ticks: false.
    """
    
    def test_anchor_updated_event_structure(self):
        """Verify expected event payload structure."""
        # Expected format from _on_anchor_updated_event:
        event_pld = {
            "anchor": "BTCUSDT",
            "price": "100000.50",
            "ts_ms": 1704067200000,
        }
        
        anchor = event_pld.get("anchor")
        price = event_pld.get("price")
        ts_ms = event_pld.get("ts_ms")
        
        self.assertEqual(anchor, "BTCUSDT")
        self.assertEqual(price, "100000.50")
        self.assertEqual(ts_ms, 1704067200000)
    
    def test_update_anchor_price_populates_deque(self):
        """Simulate update_anchor_price logic."""
        anchor_prices: Dict[str, deque] = {
            "BTCUSDT": deque(maxlen=12),
            "ETHUSDT": deque(maxlen=12),
        }
        
        def update_anchor_price(anchor: str, price: str, ts_ms: int) -> None:
            if anchor in anchor_prices:
                anchor_prices[anchor].append(decimal.Decimal(price))
        
        # Simulate updates
        update_anchor_price("BTCUSDT", "95000", 1704067200000)
        update_anchor_price("BTCUSDT", "96000", 1704067205000)
        update_anchor_price("BTCUSDT", "97000", 1704067210000)
        
        self.assertEqual(len(anchor_prices["BTCUSDT"]), 3)
        self.assertEqual(anchor_prices["BTCUSDT"][-1], decimal.Decimal("97000"))
    
    def test_ts_ms_required_raises_on_missing(self):
        """ts_ms is mandatory - missing should raise error."""
        from apps.reference.config_contract import ConfigContractError
        
        def update_anchor_price_strict(anchor: str, price: str, ts_ms: Optional[int]) -> None:
            if ts_ms is None or int(ts_ms) <= 0:
                raise ConfigContractError(
                    path="market_data.anchor.ts_ms",
                    symbol=str(anchor),
                    why="Missing exchange-derived ts_ms",
                )
        
        with self.assertRaises(ConfigContractError):
            update_anchor_price_strict("BTCUSDT", "100000", None)
        
        with self.assertRaises(ConfigContractError):
            update_anchor_price_strict("BTCUSDT", "100000", 0)


# =============================================================================
# SECTION 3: FULL_READY COMPUTATION WITH MACRO_RESID
# =============================================================================

class TestFullReadyWithMacroResid(unittest.TestCase):
    """
    Test compute_warmup_full_ready with macro_resid in the picture.
    
    Key behavior:
    - macro_resid is in declared_keys
    - When macro_resid_enabled=true, macro_resid:True is REQUIRED in ready_map
    - If macro_resid is False in ready_map → full_ready = False → NO TRADING
    """
    
    def create_config_mock(self, macro_resid_enabled: bool = True):
        """Create a mock config for FeatureEngineeringConfig."""
        from apps.reference.domains.feature_engineering.types import FeatureEngineeringConfig
        
        mock_cfg = MagicMock()
        mock_cfg.readiness_registry = MagicMock()
        mock_cfg.readiness_registry.declared_keys = [
            "obi", "tfi", "delta_price", "depth_imbalance", "liquidity_kappa",
            "absorption", "ema_bias", "volume_spike", "volatility_state",
            "macro_sync", "macro_resid", "spread_bps", "large_trade_imbalance",
            "volume_zscore",
        ]
        mock_cfg.absorption = MagicMock()
        mock_cfg.absorption.mode = "disabled"  # Standard: absorption disabled
        mock_cfg.macro_resid = MagicMock()
        mock_cfg.macro_resid.enabled = macro_resid_enabled
        mock_cfg.macro_sync = MagicMock()
        mock_cfg.macro_sync.enabled = True
        
        wrapped = FeatureEngineeringConfig.__new__(FeatureEngineeringConfig)
        wrapped._cfg = mock_cfg
        return wrapped
    
    def test_macro_resid_not_ready_blocks_full_ready(self):
        """If macro_resid=False in ready_map and enabled, full_ready=False."""
        cfg = self.create_config_mock(macro_resid_enabled=True)
        
        # All ready except macro_resid
        ready_map = {k: True for k in cfg.readiness_registry_declared_keys}
        ready_map["macro_resid"] = False  # NOT READY
        ready_map["absorption"] = False   # Disabled, doesn't count
        
        result = cfg.compute_warmup_full_ready(ready_map)
        
        self.assertFalse(result,
            "macro_resid=False should block full_ready when enabled")
    
    def test_macro_resid_ready_allows_full_ready(self):
        """If all required features are ready including macro_resid, full_ready=True."""
        cfg = self.create_config_mock(macro_resid_enabled=True)
        
        ready_map = {k: True for k in cfg.readiness_registry_declared_keys}
        ready_map["absorption"] = False  # Disabled, doesn't count
        
        result = cfg.compute_warmup_full_ready(ready_map)
        
        self.assertTrue(result,
            "All features ready should allow full_ready")
    
    def test_macro_resid_disabled_skips_check(self):
        """If macro_resid_enabled=False, macro_resid is not required for full_ready."""
        cfg = self.create_config_mock(macro_resid_enabled=False)
        
        ready_map = {k: True for k in cfg.readiness_registry_declared_keys}
        ready_map["macro_resid"] = False  # Not ready, but also not required
        ready_map["absorption"] = False   # Disabled
        
        result = cfg.compute_warmup_full_ready(ready_map)
        
        self.assertTrue(result,
            "macro_resid disabled should not block full_ready")
    
    def test_missing_key_blocks_full_ready(self):
        """Missing key in ready_map blocks full_ready (fail-closed)."""
        cfg = self.create_config_mock(macro_resid_enabled=True)
        
        # Missing macro_resid key entirely
        ready_map = {k: True for k in cfg.readiness_registry_declared_keys if k != "macro_resid"}
        ready_map["absorption"] = False
        
        result = cfg.compute_warmup_full_ready(ready_map)
        
        self.assertFalse(result,
            "Missing key should block full_ready (fail-closed)")


# =============================================================================
# SECTION 4: END-TO-END ANCHOR → MACRO_RESID → FULL_READY FLOW
# =============================================================================

class TestEndToEndAnchorToFullReady(unittest.TestCase):
    """
    End-to-end test: Anchor updates → macro_resid warmup → full_ready.
    
    This simulates the complete flow to verify the hypothesis that:
    - Without anchor updates, macro_resid never becomes ready
    - Without macro_resid ready, full_ready = False
    - Without full_ready, no trading occurs
    """
    
    def test_no_anchor_updates_means_no_macro_resid_ready(self):
        """Simulate: MarketData never sends EVT:ANCHOR_UPDATED."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from apps.reference.domains.feature_engineering.types import HotState
        
        cfg = MagicMock()
        cfg.macro_resid_enabled = True
        cfg.macro_resid_beta_window = 20
        cfg.macro_resid_mad_window = 10
        cfg.macro_resid_winsor_percentile = 0.0
        cfg.macro_resid_var_floor = 1e-10
        cfg.macro_resid_scale_floor = 1e-6
        cfg.macro_resid_clip = 3.0
        cfg.macro_resid_neutral = 0.0
        
        engine = FeatureCalculationEngine(cfg)
        state = HotState()
        
        # Simulate 1000 ticks WITHOUT any anchor updates
        # anchor_prices["BTCUSDT"] is empty → returns never computed
        anchor_prices: Dict[str, deque] = {"BTCUSDT": deque(maxlen=12)}
        
        for i in range(1000):
            # Can't compute anchor_return - anchor_prices empty
            btc_price_hist = anchor_prices.get("BTCUSDT", None)
            if not (btc_price_hist and len(btc_price_hist) >= 2):
                # This is what happens in real code - update_macro_resid is NOT called
                pass
        
        # Check macro_resid state - should still not be ready
        value, is_ready, reason = engine.compute_macro_resid(state)
        
        self.assertFalse(is_ready,
            "macro_resid should NOT be ready without anchor updates")
        self.assertIn("insufficient_samples", reason or "")
    
    def test_with_anchor_updates_macro_resid_becomes_ready(self):
        """Simulate: MarketData sends EVT:ANCHOR_UPDATED regularly."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from apps.reference.domains.feature_engineering.types import HotState
        
        cfg = MagicMock()
        cfg.macro_resid_enabled = True
        cfg.macro_resid_beta_window = 20
        cfg.macro_resid_mad_window = 10
        cfg.macro_resid_winsor_percentile = 0.0
        cfg.macro_resid_var_floor = 1e-10
        cfg.macro_resid_scale_floor = 1e-6
        cfg.macro_resid_clip = 3.0
        cfg.macro_resid_neutral = 0.0
        
        engine = FeatureCalculationEngine(cfg)
        state = HotState()
        
        # Simulate with anchor updates - use more realistic price movements
        anchor_prices: Dict[str, deque] = {"BTCUSDT": deque(maxlen=100)}
        
        # First, populate anchor_prices with varying movements (simulates real BTC volatility)
        import random
        random.seed(42)
        btc_price = 95000.0
        for i in range(50):
            # Random walk with realistic volatility (0.1% per tick)
            btc_price *= (1 + random.uniform(-0.002, 0.002))
            anchor_prices["BTCUSDT"].append(decimal.Decimal(str(btc_price)))
        
        # Now process 50 ticks (simulate _calculate_and_emit_features)
        asset_price = 3000.0
        for i in range(50):
            # Asset prices with their own volatility
            prev_asset = asset_price
            asset_price *= (1 + random.uniform(-0.003, 0.003))
            prev_price = decimal.Decimal(str(prev_asset))
            price = decimal.Decimal(str(asset_price))
            
            btc_price_hist = anchor_prices["BTCUSDT"]
            if btc_price_hist and len(btc_price_hist) >= 2:
                # Calculate returns (matching code logic)
                asset_return = float((price - prev_price) / prev_price) if prev_price > 0 else 0.0
                btc_prev = btc_price_hist[-2]
                btc_curr = btc_price_hist[-1]
                anchor_return = float((btc_curr - btc_prev) / btc_prev) if btc_prev > 0 else 0.0
                
                # Update buffers
                engine.update_macro_resid(state, asset_return, anchor_return)
            
            # Compute to populate MAD buffer
            engine.compute_macro_resid(state)
            
            # Add new anchor price for next iteration (with movement)
            btc_price *= (1 + random.uniform(-0.002, 0.002))
            anchor_prices["BTCUSDT"].append(decimal.Decimal(str(btc_price)))
        
        # Final check
        value, is_ready, reason = engine.compute_macro_resid(state)
        
        self.assertTrue(is_ready,
            f"macro_resid should be ready with anchor updates, reason: {reason}")
    
    def test_full_ready_chain_requires_anchor_flow(self):
        """Verify the complete chain: no anchors → no macro_resid → no full_ready."""
        from apps.reference.domains.feature_engineering.types import FeatureEngineeringConfig
        
        # Create config mock
        mock_cfg = MagicMock()
        mock_cfg.readiness_registry = MagicMock()
        mock_cfg.readiness_registry.declared_keys = [
            "obi", "tfi", "delta_price", "depth_imbalance", "liquidity_kappa",
            "absorption", "ema_bias", "volume_spike", "volatility_state",
            "macro_sync", "macro_resid", "spread_bps", "large_trade_imbalance",
            "volume_zscore",
        ]
        mock_cfg.absorption = MagicMock()
        mock_cfg.absorption.mode = "disabled"
        mock_cfg.macro_resid = MagicMock()
        mock_cfg.macro_resid.enabled = True
        mock_cfg.macro_sync = MagicMock()
        mock_cfg.macro_sync.enabled = True
        
        wrapped = FeatureEngineeringConfig.__new__(FeatureEngineeringConfig)
        wrapped._cfg = mock_cfg
        
        # Simulate ready_map as it would be with no anchor updates
        # All basic features ready, but macro_resid NOT ready
        ready_map = {
            "obi": True,
            "tfi": True,
            "delta_price": True,
            "depth_imbalance": True,
            "liquidity_kappa": True,
            "absorption": False,  # Disabled
            "ema_bias": True,
            "volume_spike": True,
            "volatility_state": True,
            "macro_sync": True,
            "macro_resid": False,  # NOT READY - this is the blocker
            "spread_bps": True,
            "large_trade_imbalance": True,
            "volume_zscore": True,
        }
        
        result = wrapped.compute_warmup_full_ready(ready_map)
        
        self.assertFalse(result,
            "full_ready should be False when macro_resid is not ready")


# =============================================================================
# SECTION 5: CONFIG VERIFICATION TESTS
# =============================================================================

class TestProductionConfigValues(unittest.TestCase):
    """
    Verify the actual production config values that may cause issues.
    """
    
    def test_anchor_update_from_ticks_config_value(self):
        """Check actual config value for anchor_update_from_ticks."""
        import yaml
        from pathlib import Path
        
        config_path = Path("/home/wekabeka/Музыка/Phenix/config/aurora/domains.yaml")
        
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            
            macro_sync = config.get("feature_engineering", {}).get("macro_sync", {})
            anchor_update_from_ticks = macro_sync.get("anchor_update_from_ticks", "NOT_FOUND")
            
            # Document current value
            print(f"\n[CONFIG] anchor_update_from_ticks = {anchor_update_from_ticks}")
            
            if anchor_update_from_ticks is False:
                print("[WARNING] anchor_update_from_ticks=false means anchor_prices are ONLY")
                print("          updated via EVT:ANCHOR_UPDATED events.")
                print("          If MarketData doesn't emit these events, macro_resid will NEVER be ready!")
    
    def test_macro_resid_enabled_config_value(self):
        """Check if macro_resid is enabled in production config."""
        import yaml
        from pathlib import Path
        
        config_path = Path("/home/wekabeka/Музыка/Phenix/config/aurora/domains.yaml")
        
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            
            macro_resid = config.get("feature_engineering", {}).get("macro_resid", {})
            enabled = macro_resid.get("enabled", "NOT_FOUND")
            beta_window = macro_resid.get("beta_window", "NOT_FOUND")
            mad_window = macro_resid.get("mad_window", "NOT_FOUND")
            
            print(f"\n[CONFIG] macro_resid.enabled = {enabled}")
            print(f"[CONFIG] macro_resid.beta_window = {beta_window}")
            print(f"[CONFIG] macro_resid.mad_window = {mad_window}")
            
            if enabled is True:
                total_samples = (beta_window or 60) + (mad_window or 30)
                print(f"[INFO] macro_resid requires {total_samples} samples to become ready")
    
    def test_readiness_registry_includes_macro_resid(self):
        """Verify macro_resid is in declared_keys (required for full_ready)."""
        import yaml
        from pathlib import Path
        
        config_path = Path("/home/wekabeka/Музыка/Phenix/config/aurora/domains.yaml")
        
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            
            readiness_registry = config.get("feature_engineering", {}).get("readiness_registry", {})
            declared_keys = readiness_registry.get("declared_keys", [])
            
            print(f"\n[CONFIG] readiness_registry.declared_keys = {declared_keys}")
            
            if "macro_resid" in declared_keys:
                print("[INFO] macro_resid is in declared_keys - it MUST be ready for full_ready=True")
            else:
                print("[WARNING] macro_resid NOT in declared_keys - may not block trading")


# =============================================================================
# SECTION 6: DIAGNOSTIC HELPERS
# =============================================================================

class TestDiagnosticHelpers(unittest.TestCase):
    """
    Helper tests that output diagnostic information for debugging.
    """
    
    def test_diagnose_macro_resid_state_progression(self):
        """Show how macro_resid state progresses through warmup."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from apps.reference.domains.feature_engineering.types import HotState
        
        cfg = MagicMock()
        cfg.macro_resid_enabled = True
        cfg.macro_resid_beta_window = 20
        cfg.macro_resid_mad_window = 10
        cfg.macro_resid_winsor_percentile = 0.0
        cfg.macro_resid_var_floor = 1e-10
        cfg.macro_resid_scale_floor = 1e-6
        cfg.macro_resid_clip = 3.0
        cfg.macro_resid_neutral = 0.0
        
        engine = FeatureCalculationEngine(cfg)
        state = HotState()
        
        print("\n[DIAGNOSTIC] Macro Resid Warmup Progression:")
        print(f"  beta_window = {cfg.macro_resid_beta_window}")
        print(f"  mad_window = {cfg.macro_resid_mad_window}")
        print(f"  total needed ≈ {cfg.macro_resid_beta_window + cfg.macro_resid_mad_window}")
        print("-" * 60)
        
        ready_at = None
        for i in range(50):
            anchor_ret = 0.001 * ((i % 10) - 5)
            asset_ret = anchor_ret * 1.1
            engine.update_macro_resid(state, asset_ret, anchor_ret)
            value, is_ready, reason = engine.compute_macro_resid(state)
            
            if i < 5 or i % 10 == 0 or (is_ready and ready_at is None):
                print(f"  tick {i:3d}: is_ready={is_ready}, reason={reason}")
            
            if is_ready and ready_at is None:
                ready_at = i
        
        print("-" * 60)
        if ready_at is not None:
            print(f"[RESULT] macro_resid became ready at tick {ready_at}")
        else:
            print("[RESULT] macro_resid did NOT become ready in 50 ticks")
    
    def test_diagnose_anchor_price_buffer_requirements(self):
        """Show anchor_price buffer requirements for returns calculation."""
        print("\n[DIAGNOSTIC] Anchor Price Buffer Requirements:")
        print("-" * 60)
        print("  For anchor_return calculation:")
        print("    - Need len(anchor_prices[BTCUSDT]) >= 2")
        print("    - btc_prev = anchor_prices[-2]")
        print("    - btc_curr = anchor_prices[-1]")
        print("    - anchor_return = (btc_curr - btc_prev) / btc_prev")
        print()
        print("  Sources of anchor updates:")
        print("    1. EVT:ANCHOR_UPDATED event (always works)")
        print("    2. Ticks (only if anchor_update_from_ticks=true)")
        print()
        print("  If anchor_update_from_ticks=false AND no EVT:ANCHOR_UPDATED:")
        print("    → anchor_prices stays empty")
        print("    → anchor_return cannot be computed")
        print("    → macro_resid buffers never updated")
        print("    → macro_resid NEVER becomes ready")
        print("    → full_ready = False")
        print("    → NO TRADING")
        print("-" * 60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
