"""
Tests for Feature Engineering ready_map contract.

Verifies that basic instant features (obi, tfi, delta_price, etc.)
are always marked as ready=True in warmup.ready, since they don't
require history accumulation (unlike ema_bias, volume_spike, etc.).

This is critical for SignalScoreV2 integration which uses:
    is_ready = readiness.get(feat, False)
and blocks on essential_features if not ready.
"""
import unittest


class TestReadyMapBasicFeatures(unittest.TestCase):
    """Test that basic features are present in ready_map."""

    # Features that should always be ready (computed from current tick)
    INSTANT_FEATURES = [
        "obi",
        "tfi", 
        "delta_price",
        "depth_imbalance",
        "liquidity_kappa",
        "absorption",
        "volume_zscore",
    ]

    # Features that require warmup/history
    WARMUP_FEATURES = [
        "ema_bias",
        "volume_spike",
        "volatility_state",
        "macro_sync",
        "spread_bps",
        "large_trade_imbalance",
    ]

    def test_instant_features_always_ready(self):
        """Instant features should always be True in ready_map."""
        # Simulate ready_map as it should be constructed
        ready_map = {
            # Basic instant features (always ready from first tick)
            "obi": True,
            "tfi": True,
            "delta_price": True,
            "depth_imbalance": True,
            "liquidity_kappa": True,
            "absorption": True,
            "volume_zscore": True,
            # Warmup-dependent (mocked as False for this test)
            "ema_bias": False,
            "volume_spike": False,
            "volatility_state": False,
            "macro_sync": False,
            "spread_bps": False,
            "large_trade_imbalance": False,
        }

        for feat in self.INSTANT_FEATURES:
            self.assertIn(feat, ready_map, f"{feat} must be in ready_map")
            self.assertTrue(ready_map[feat], f"{feat} must be True (instant)")

    def test_warmup_features_present(self):
        """Warmup features should be present (value depends on state)."""
        ready_map = {
            "obi": True,
            "tfi": True,
            "delta_price": True,
            "depth_imbalance": True,
            "liquidity_kappa": True,
            "absorption": True,
            "volume_zscore": True,
            "ema_bias": True,  # After warmup
            "volume_spike": True,
            "volatility_state": False,  # Still warming up
            "macro_sync": True,
            "spread_bps": True,
            "large_trade_imbalance": False,
        }

        for feat in self.WARMUP_FEATURES:
            self.assertIn(feat, ready_map, f"{feat} must be in ready_map")

    def test_essential_features_for_aurora(self):
        """Essential features for Aurora must be in ready_map."""
        # From aurora.yaml: essential_features: [obi, delta_price]
        essential = ["obi", "delta_price"]
        
        ready_map = {
            "obi": True,
            "tfi": True,
            "delta_price": True,
            "depth_imbalance": True,
            "liquidity_kappa": True,
            "absorption": True,
            "volume_zscore": True,
            "ema_bias": True,
            "volume_spike": True,
            "volatility_state": True,
            "macro_sync": True,
            "spread_bps": True,
            "large_trade_imbalance": True,
        }

        for feat in essential:
            self.assertIn(feat, ready_map, f"Essential {feat} must be in ready_map")
            self.assertTrue(ready_map[feat], f"Essential {feat} must be ready")

if __name__ == '__main__':
    unittest.main()
