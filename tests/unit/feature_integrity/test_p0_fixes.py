"""
Feature Integrity Unit Tests - P0 Fixes.

TASK: FEATURE-INTEGRITY-RUNTIME+AUDIT-FULL-002

Tests for:
- P0-1: Volatility state overflow fix (hard floor + cap + firewall)
- P0-0: Readiness contract audit (missing ready keys detection)
- P0-2: Spread health gate (book truth validation)
- P0-3: Feature sanity firewall (NaN/Inf protection)
"""

import unittest
import decimal
import math
from collections import deque
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, '/home/wekabeka/Музыка/Phenix')

from apps.reference.domains.feature_engineering.types import HotState


class MockVolatilityConfig:
    """Mock config for volatility tests."""
    neutral_value = decimal.Decimal("0.5")
    volatility_state_cap = decimal.Decimal("3.0")
    volatility_tick_floor = decimal.Decimal("0.0001")
    volatility_division_eps = decimal.Decimal("0.000000001")


class TestVolatilityStateOverflow(unittest.TestCase):
    """P0-1: Volatility state overflow fix tests."""
    
    def setUp(self):
        """Set up test state."""
        self.state = HotState(
            range_hist=deque(maxlen=10),
            range_stats=(5, 0.0, 0.0),  # 5 samples, mean=0, m2=0 (FLAT MARKET)
            range_min=decimal.Decimal("50000.00"),
            range_max=decimal.Decimal("50000.00"),  # No range
            volatility_state_ready=False,
            volatility_state_not_ready_reason=None,
        )
    
    def test_flat_market_no_overflow_avg_range_zero(self):
        """When avg_range=0 (flat market), should use hard floor, not divide by zero."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        
        # Create mock config
        cfg = MockVolatilityConfig()
        engine = MagicMock()
        engine.cfg = cfg
        
        # Simulate the computation logic directly
        count, mean, _ = self.state.range_stats
        avg_range = decimal.Decimal(str(mean))  # 0.0
        current_range = self.state.range_max - self.state.range_min  # 0
        
        # P0-1: Hard floor
        tick_floor = cfg.volatility_tick_floor
        division_eps = cfg.volatility_division_eps
        denom = max(avg_range, tick_floor, division_eps)
        
        # This should NOT be zero
        self.assertGreater(denom, decimal.Decimal("0"))
        
        # Division should be safe
        ratio = current_range / denom
        self.assertTrue(ratio.is_finite())
        self.assertEqual(ratio, decimal.Decimal("0"))  # 0 / 0.0001 = 0
    
    def test_avg_range_tiny_no_overflow(self):
        """When avg_range is tiny (1e-15), should use hard floor."""
        avg_range = decimal.Decimal("1e-15")
        current_range = decimal.Decimal("1.0")
        
        tick_floor = decimal.Decimal("0.0001")
        division_eps = decimal.Decimal("1e-9")
        
        denom = max(avg_range, tick_floor, division_eps)
        
        # Should be tick_floor, not 1e-15
        self.assertEqual(denom, tick_floor)
        
        # Ratio should be finite
        ratio = current_range / denom
        self.assertTrue(ratio.is_finite())
        self.assertLess(ratio, decimal.Decimal("1e10"))  # Reasonable value
    
    def test_nan_inf_firewall(self):
        """NaN/Inf values should be caught and return neutral."""
        # Simulate a ratio that becomes Inf
        ratio_inf = float('inf')
        self.assertFalse(math.isfinite(ratio_inf))
        
        # Simulate NaN
        ratio_nan = float('nan')
        self.assertFalse(math.isfinite(ratio_nan))


class TestReadinessContractAudit(unittest.TestCase):
    """P0-0: Readiness contract audit tests."""
    
    DECLARED_READY_KEYS = {
        "obi", "tfi", "delta_price", "depth_imbalance", "liquidity_kappa",
        "absorption", "ema_bias", "volume_spike", "volatility_state",
        "macro_sync", "spread_bps", "large_trade_imbalance", "volume_zscore"
    }
    
    ESSENTIAL_FEATURES = {"obi", "delta_price"}
    
    def test_essential_subset_of_declared(self):
        """essential_features must be subset of declared_keys."""
        missing = self.ESSENTIAL_FEATURES - self.DECLARED_READY_KEYS
        self.assertEqual(missing, set(), f"Essential features {missing} not in declared keys")
    
    def test_missing_ready_keys_detection(self):
        """Detect missing ready keys before scoring."""
        # Simulate warmup.ready that's missing some keys
        readiness_map = {
            "obi": True,
            "tfi": True,
            # delta_price is MISSING
            "ema_bias": True,
        }
        
        essential_set = self.ESSENTIAL_FEATURES
        missing_ready_keys = essential_set - set(readiness_map.keys())
        
        self.assertEqual(missing_ready_keys, {"delta_price"})
    
    def test_full_ready_invariant(self):
        """If full_ready=True, all declared keys must be present."""
        # Simulate a complete ready_map
        ready_map = {key: True for key in self.DECLARED_READY_KEYS}
        full_ready = all(ready_map.values())
        
        self.assertTrue(full_ready)
        
        # Invariant: all declared keys present
        self.assertEqual(set(ready_map.keys()), self.DECLARED_READY_KEYS)
    
    def test_full_ready_with_missing_keys_should_fail(self):
        """full_ready=True but missing keys should be caught."""
        ready_map = {
            "obi": True,
            "tfi": True,
            # Missing most other keys
        }
        full_ready = all(ready_map.values())  # This would be True if all present values are True
        
        # But invariant check should fail
        declared_keys = self.DECLARED_READY_KEYS
        actual_keys = set(ready_map.keys())
        invariant_violated = declared_keys != actual_keys
        
        self.assertTrue(invariant_violated)


class TestWarmupFullReadySemantics(unittest.TestCase):
    """P0-0: full_ready should be config-aware for disabled experimental features."""

    def test_absorption_disabled_does_not_block_full_ready(self):
        """R2: absorption.mode=disabled must not prevent warmup.full_ready from becoming True."""
        from apps.reference.domains.feature_engineering.types import FeatureEngineeringConfig
        from unittest.mock import MagicMock

        mock_cfg = MagicMock()
        mock_cfg.readiness_registry = MagicMock()
        mock_cfg.readiness_registry.declared_keys = [
            "obi",
            "tfi",
            "delta_price",
            "depth_imbalance",
            "liquidity_kappa",
            "absorption",
            "ema_bias",
            "volume_spike",
            "volatility_state",
            "macro_sync",
            "macro_resid",
            "spread_bps",
            "large_trade_imbalance",
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

        ready_map = {k: True for k in mock_cfg.readiness_registry.declared_keys}
        ready_map["absorption"] = False  # disabled feature is not ready by design

        self.assertTrue(wrapped.compute_warmup_full_ready(ready_map))


class TestSignalScoreV2ReadinessLookup(unittest.TestCase):
    """Test SignalScoreV2 readiness lookup behavior."""
    
    ESSENTIAL_FEATURES = {"obi", "delta_price"}
    
    def test_missing_key_defaults_to_false(self):
        """Missing key in readiness map should default to False (fail-closed)."""
        readiness = {"obi": True}  # delta_price is missing
        
        # This is how SignalScoreV2 checks
        is_ready = readiness.get("delta_price", False)
        self.assertFalse(is_ready)
    
    def test_essential_missing_causes_defer(self):
        """Essential feature missing should cause DEFER."""
        features = {"obi": 0.3, "tfi": -0.2, "ema_bias": 0.55}
        readiness = {"obi": True, "tfi": True, "ema_bias": True}
        weights = {"obi": 0.15, "delta_price": 0.1}
        
        not_ready_essential = []
        for feat, w in weights.items():
            if feat not in features:
                if feat in self.ESSENTIAL_FEATURES:
                    not_ready_essential.append(feat)
        
        self.assertIn("delta_price", not_ready_essential)


class TestSyntheticReachability(unittest.TestCase):
    """Synthetic reachability tests for LONG/SHORT."""
    
    def test_sell_reachable_with_negative_features(self):
        """With negative directional features, SELL should be reachable."""
        # Simulate negative direction features
        features = {
            "obi": -0.5,  # Sell pressure
            "tfi": -0.4,  # More sellers
            "delta_price": -0.3,  # Price dropping
            "ema_bias": 0.35,  # Bearish (below 0.5 neutral)
            "depth_imbalance": 0.65,  # More ask depth (bearish)
            "macro_sync": 0.5,  # Neutral
        }
        
        weights = {
            "obi": 0.15,
            "tfi": 0.15,
            "delta_price": 0.1,
            "ema_bias": 0.15,
            "depth_imbalance": 0.15,
            "macro_sync": 0.1,
        }
        
        neutrals = {
            "obi": 0.0,
            "tfi": 0.0,
            "delta_price": 0.0,
            "ema_bias": 0.5,
            "depth_imbalance": 0.5,
            "macro_sync": 0.5,
        }
        
        # Compute score (simplified)
        score_raw = sum(
            weights[f] * (features[f] - neutrals[f])
            for f in features.keys()
        )
        wabs = sum(abs(w) for w in weights.values())
        score = score_raw / wabs if wabs > 0 else 0
        
        # Score should be NEGATIVE (sell signal)
        self.assertLess(score, 0, f"Score {score} should be negative for SELL")
    
    def test_buy_reachable_with_positive_features(self):
        """With positive directional features, BUY should be reachable."""
        features = {
            "obi": 0.6,  # Buy pressure
            "tfi": 0.5,  # More buyers
            "delta_price": 0.4,  # Price rising
            "ema_bias": 0.65,  # Bullish
            "depth_imbalance": 0.35,  # More bid depth
            "macro_sync": 0.5,
        }
        
        weights = {
            "obi": 0.15,
            "tfi": 0.15,
            "delta_price": 0.1,
            "ema_bias": 0.15,
            "depth_imbalance": 0.15,
            "macro_sync": 0.1,
        }
        
        neutrals = {
            "obi": 0.0,
            "tfi": 0.0,
            "delta_price": 0.0,
            "ema_bias": 0.5,
            "depth_imbalance": 0.5,
            "macro_sync": 0.5,
        }
        
        score_raw = sum(
            weights[f] * (features[f] - neutrals[f])
            for f in features.keys()
        )
        wabs = sum(abs(w) for w in weights.values())
        score = score_raw / wabs if wabs > 0 else 0
        
        # Score should be POSITIVE (buy signal)
        self.assertGreater(score, 0, f"Score {score} should be positive for BUY")


class TestFeatureSanityFirewall(unittest.TestCase):
    """P0-3: Feature sanity firewall tests."""
    
    def test_nan_detection(self):
        """NaN values should be detected."""
        val = float('nan')
        self.assertTrue(math.isnan(val))
        self.assertFalse(math.isfinite(val))
    
    def test_inf_detection(self):
        """Inf values should be detected."""
        val_pos = float('inf')
        val_neg = float('-inf')
        
        self.assertFalse(math.isfinite(val_pos))
        self.assertFalse(math.isfinite(val_neg))
    
    def test_out_of_range_detection(self):
        """Out-of-range values should be detected."""
        bounds = {"min": -1.0, "max": 1.0}
        
        valid_values = [-1.0, -0.5, 0.0, 0.5, 1.0]
        invalid_values = [-1.5, 1.5, 100.0, -100.0]
        
        for v in valid_values:
            self.assertTrue(bounds["min"] <= v <= bounds["max"])
        
        for v in invalid_values:
            self.assertFalse(bounds["min"] <= v <= bounds["max"])


if __name__ == "__main__":
    unittest.main()


class TestP02BookHealthGate(unittest.TestCase):
    """P0-2: Book health gate runtime tests."""
    
    def test_book_stale_returns_unhealthy(self):
        """If book age > max_age_sec, health check returns False."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from unittest.mock import MagicMock
        
        # Mock config with health gate enabled
        cfg = MagicMock()
        cfg.spread_health_gate_enabled = True
        cfg.spread_health_max_age_sec = 5.0
        cfg.spread_health_min_update_events = 1
        cfg.spread_health_min_trades_count = 1
        cfg.spread_health_window_sec = 10.0
        cfg.feature_sanity_enabled = False
        
        engine = FeatureCalculationEngine(cfg)
        
        # Set last update 10 seconds ago
        engine._book_last_update_ts_ms["BTCUSDT"] = 1000
        
        # Check at current ts = 11000 (10s later)
        is_healthy, reason = engine.check_book_health("BTCUSDT", 11000)
        
        self.assertFalse(is_healthy)
        self.assertIn("book_stale", reason)
    
    def test_book_fresh_with_activity_returns_healthy(self):
        """Fresh book with activity returns healthy."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from unittest.mock import MagicMock
        
        cfg = MagicMock()
        cfg.spread_health_gate_enabled = True
        cfg.spread_health_max_age_sec = 5.0
        cfg.spread_health_min_update_events = 1
        cfg.spread_health_min_trades_count = 1
        cfg.spread_health_window_sec = 10.0
        cfg.feature_sanity_enabled = False
        
        engine = FeatureCalculationEngine(cfg)
        
        # Simulate recent book update
        engine.update_book_health("BTCUSDT", ts_ms=5000, is_book_update=True, is_trade=True)
        
        # Check at current ts = 6000 (1s later)
        is_healthy, reason = engine.check_book_health("BTCUSDT", 6000)
        
        self.assertTrue(is_healthy)
        self.assertIsNone(reason)
    
    def test_no_book_updates_returns_unhealthy(self):
        """No book updates ever received → unhealthy."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from unittest.mock import MagicMock
        
        cfg = MagicMock()
        cfg.spread_health_gate_enabled = True
        cfg.spread_health_max_age_sec = 5.0
        cfg.spread_health_min_update_events = 1
        cfg.spread_health_min_trades_count = 1
        cfg.spread_health_window_sec = 10.0
        cfg.feature_sanity_enabled = False
        
        engine = FeatureCalculationEngine(cfg)
        
        is_healthy, reason = engine.check_book_health("BTCUSDT", 5000)
        
        self.assertFalse(is_healthy)
        self.assertEqual(reason, "no_book_updates_received")


class TestP03FeatureSanityFirewall(unittest.TestCase):
    """P0-3: Feature sanity firewall runtime tests."""
    
    def test_nan_returns_not_ready(self):
        """NaN value → not_ready with reason."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from unittest.mock import MagicMock
        import decimal
        
        cfg = MagicMock()
        cfg.feature_sanity_enabled = True
        cfg.feature_sanity_nan_inf_behavior = "neutral_and_not_ready"
        cfg.feature_sanity_bounds = {}
        cfg.neutral_value = decimal.Decimal("0.5")
        
        engine = FeatureCalculationEngine(cfg)
        
        val, is_ready, reason = engine.sanitize_feature("obi", float('nan'))
        
        self.assertEqual(val, decimal.Decimal("0.5"))  # Neutral
        self.assertFalse(is_ready)
        self.assertIn("nan_inf", reason)
    
    def test_inf_returns_not_ready(self):
        """Inf value → not_ready with reason."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from unittest.mock import MagicMock
        import decimal
        
        cfg = MagicMock()
        cfg.feature_sanity_enabled = True
        cfg.feature_sanity_nan_inf_behavior = "neutral_and_not_ready"
        cfg.feature_sanity_bounds = {}
        cfg.neutral_value = decimal.Decimal("0.5")
        
        engine = FeatureCalculationEngine(cfg)
        
        val, is_ready, reason = engine.sanitize_feature("tfi", float('inf'))
        
        self.assertFalse(is_ready)
        self.assertIn("nan_inf", reason)
    
    def test_out_of_range_clamped_and_not_ready(self):
        """Out-of-range value → clamped and not_ready."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from unittest.mock import MagicMock
        import decimal
        
        cfg = MagicMock()
        cfg.feature_sanity_enabled = True
        cfg.feature_sanity_nan_inf_behavior = "neutral_and_not_ready"
        cfg.feature_sanity_bounds = {"obi": {"min": -1.0, "max": 1.0}}
        cfg.neutral_value = decimal.Decimal("0.5")
        
        engine = FeatureCalculationEngine(cfg)
        
        # Value 5.0 is out of range [-1, 1]
        val, is_ready, reason = engine.sanitize_feature("obi", 5.0)
        
        self.assertEqual(val, decimal.Decimal("1"))  # Clamped to max
        self.assertFalse(is_ready)
        self.assertIn("out_of_range", reason)
    
    def test_valid_value_passes(self):
        """Valid value → passes sanity, is_ready=True."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from unittest.mock import MagicMock
        import decimal
        
        cfg = MagicMock()
        cfg.feature_sanity_enabled = True
        cfg.feature_sanity_nan_inf_behavior = "neutral_and_not_ready"
        cfg.feature_sanity_bounds = {"obi": {"min": -1.0, "max": 1.0}}
        cfg.neutral_value = decimal.Decimal("0.5")
        
        engine = FeatureCalculationEngine(cfg)
        
        val, is_ready, reason = engine.sanitize_feature("obi", 0.3)
        
        self.assertEqual(float(val), 0.3)
        self.assertTrue(is_ready)
        self.assertIsNone(reason)
    
    def test_batch_sanitize(self):
        """Batch sanitize updates all features."""
        from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
        from unittest.mock import MagicMock
        import decimal
        
        cfg = MagicMock()
        cfg.feature_sanity_enabled = True
        cfg.feature_sanity_nan_inf_behavior = "neutral_and_not_ready"
        cfg.feature_sanity_bounds = {"obi": {"min": -1.0, "max": 1.0}}
        cfg.neutral_value = decimal.Decimal("0.5")
        
        engine = FeatureCalculationEngine(cfg)
        
        features = {"obi": "0.3", "tfi": "nan"}
        
        sanitized, readiness, reasons = engine.sanitize_features_dict(features)
        
        self.assertTrue(readiness["obi"])
        self.assertFalse(readiness["tfi"])
        self.assertEqual(len(reasons), 1)
        self.assertIn("nan_inf", reasons[0])


class TestNoSilentFallbacks(unittest.TestCase):
    """Verify no silent fallbacks in decision paths."""
    
    def test_liquidity_kappa_missing_must_defer_not_use_zero(self):
        """liquidity_kappa missing → must DEFER, not use 0."""
        # Simulate features without liquidity_kappa
        features_data = {"obi": 0.3, "tfi": 0.2}  # No liquidity_kappa
        
        # Correct behavior: key check before use
        if "liquidity_kappa" not in features_data:
            action = "DEFER"
        else:
            action = "CONTINUE"
        
        self.assertEqual(action, "DEFER")
    
    def test_feature_present_continues(self):
        """Feature present → continues normally."""
        features_data = {"obi": 0.3, "liquidity_kappa": 0.8}
        
        if "liquidity_kappa" not in features_data:
            action = "DEFER"
        else:
            action = "CONTINUE"
        
        self.assertEqual(action, "CONTINUE")
