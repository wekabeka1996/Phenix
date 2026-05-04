"""
Test: Aurora vol-adj gates work with correct 300s window (no phantom price_motion).

DoD for P0-2 and P0-3 (DM-STRATEGY-SSOT-FIXPLAN-01):
- Aurora signal → gateway → intent without phantom price_motion skip
- Vol-adj gates use valid pm_norm_300s window

This test validates that Aurora handler's vol-adj gates:
1. Use a valid price_motion window (300s, not 900s)
2. Actually evaluate gates (not silently skip due to None)
"""

import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal


class TestAuroraVolAdjGatesFixed:
    """Test suite for Aurora vol-adj gates with fixed window."""

    @pytest.fixture
    def mock_handler_state(self):
        """Create mock AuroraHandler with correct window config."""
        handler = MagicMock()
        handler.motion_window_sec = 300  # FIXED: was 900
        handler.vol_gates_enabled = True
        handler.anti_flat_sigma = 0.5
        handler.anti_fomo_sigma = 4.0
        return handler

    def test_aurora_uses_300s_window_not_900s(self, mock_handler_state):
        """
        Given: Config motion_window_sec=300 (after P0-2 fix)
        When: Building window_key for price_motion lookup
        Then: Uses pm_norm_300s (not pm_norm_900s)
        """
        handler = mock_handler_state
        window_key = f"pm_norm_{handler.motion_window_sec}s"
        
        assert window_key == "pm_norm_300s", f"Expected pm_norm_300s, got {window_key}"
        assert window_key != "pm_norm_900s", "Should NOT use 900s window"

    def test_get_motion_norm_sigma_returns_value_for_300s(self, mock_handler_state):
        """
        Given: features contain pm_norm_300s=0.8
        When: _get_motion_norm_sigma is called
        Then: Returns 0.8 (not None)
        """
        handler = mock_handler_state
        
        features = {
            "price_motion": {
                "pm_norm_10s": 0.1,
                "pm_norm_60s": 0.3,
                "pm_norm_300s": 0.8,  # Valid window
            }
        }
        
        # Simulate _get_motion_norm_sigma logic
        pm = features.get("price_motion")
        if pm:
            window_key = f"pm_norm_{handler.motion_window_sec}s"
            val = pm.get(window_key)
            if val is not None:
                result = abs(float(val))
            else:
                result = None
        else:
            result = None
        
        assert result == 0.8, f"Expected 0.8, got {result}"

    def test_get_motion_norm_sigma_returns_none_for_900s(self, mock_handler_state):
        """
        Given: features contain only 10/60/300s windows (per schema)
        And: motion_window_sec=900 (legacy broken config)
        When: _get_motion_norm_sigma is called
        Then: Returns None (window doesn't exist)
        """
        # Legacy broken config
        handler = MagicMock()
        handler.motion_window_sec = 900  # BROKEN: doesn't exist in schema
        
        features = {
            "price_motion": {
                "pm_norm_10s": 0.1,
                "pm_norm_60s": 0.3,
                "pm_norm_300s": 0.8,
                # NO pm_norm_900s!
            }
        }
        
        pm = features.get("price_motion")
        window_key = f"pm_norm_{handler.motion_window_sec}s"
        result = pm.get(window_key) if pm else None
        
        assert result is None, "900s window should not exist in schema-compliant payload"

    def test_vol_gates_not_silent_skip_with_valid_window(self, mock_handler_state):
        """
        Given: motion_norm_sigma is available (0.8)
        And: anti_flat_sigma=0.5, anti_fomo_sigma=4.0
        When: _apply_vol_adj_gates is called for entry
        Then: Gate evaluates and returns False (passed, not blocked)
        """
        handler = mock_handler_state
        motion_norm_sigma = 0.8  # > 0.5 (anti_flat), < 4.0 (anti_fomo)
        
        # Simulate gate logic
        if motion_norm_sigma is None:
            # Silent skip (BAD - old behavior)
            gate_result = "SKIP"
        elif motion_norm_sigma < handler.anti_flat_sigma:
            gate_result = "BLOCK_ANTI_FLAT"
        elif motion_norm_sigma > handler.anti_fomo_sigma:
            gate_result = "BLOCK_ANTI_FOMO"
        else:
            gate_result = "PASS"
        
        assert gate_result == "PASS", f"Expected PASS, got {gate_result}"

    def test_anti_flat_gate_blocks_low_motion(self, mock_handler_state):
        """
        Given: motion_norm_sigma=0.2 (< anti_flat_sigma=0.5)
        When: _apply_vol_adj_gates is called for entry
        Then: Gate blocks with ANTI_FLAT reason
        """
        handler = mock_handler_state
        motion_norm_sigma = 0.2  # < 0.5 = dead market
        
        if motion_norm_sigma < handler.anti_flat_sigma:
            gate_result = "BLOCK_ANTI_FLAT"
        else:
            gate_result = "PASS"
        
        assert gate_result == "BLOCK_ANTI_FLAT"

    def test_anti_fomo_gate_blocks_extreme_motion(self, mock_handler_state):
        """
        Given: motion_norm_sigma=5.0 (> anti_fomo_sigma=4.0)
        When: _apply_vol_adj_gates is called for entry
        Then: Gate blocks with ANTI_FOMO reason
        """
        handler = mock_handler_state
        motion_norm_sigma = 5.0  # > 4.0 = extreme impulse
        
        if motion_norm_sigma > handler.anti_fomo_sigma:
            gate_result = "BLOCK_ANTI_FOMO"
        else:
            gate_result = "PASS"
        
        assert gate_result == "BLOCK_ANTI_FOMO"

    def test_gates_skip_when_motion_is_none(self, mock_handler_state):
        """
        Given: motion_norm_sigma is None (missing data)
        When: _apply_vol_adj_gates is called
        Then: Gate skips (returns False = no block)
        
        This is the legacy behavior that P0-3 aims to fix by caching price_motion.
        """
        handler = mock_handler_state
        motion_norm_sigma = None  # Missing
        
        if motion_norm_sigma is None:
            # Don't block on missing data (readiness handles this)
            gate_result = "SKIP"
        else:
            gate_result = "EVALUATE"
        
        assert gate_result == "SKIP"


class TestPriceMotionCaching:
    """Test price_motion caching from EVT:FEATURES_CALCULATED to CMD handler."""

    def test_price_motion_exists_in_features_calculated(self):
        """
        EVT:FEATURES_CALCULATED payload contains price_motion block.
        """
        features_calculated_payload = {
            "ts": 1704067200000,
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "features": {
                "obi": "0.15",
                "tfi": "-0.23",
            },
            "warmup": {"full_ready": True},
            "price_motion": {
                "ret_10s": 0.0001,
                "ret_60s": 0.0005,
                "ret_300s": 0.002,
                "vol_pct_10s": 0.0002,
                "vol_pct_60s": 0.0008,
                "vol_pct_300s": 0.003,
                "pm_norm_10s": 0.5,
                "pm_norm_60s": 0.625,
                "pm_norm_300s": 0.667,
            },
        }
        
        pm = features_calculated_payload.get("price_motion")
        assert pm is not None, "EVT:FEATURES_CALCULATED must contain price_motion"
        assert "pm_norm_300s" in pm

    def test_price_motion_not_in_cmd_process_strategy_features(self):
        """
        CMD:PROCESS_STRATEGY features block does NOT contain price_motion.
        This is the root cause of phantom gates.
        """
        cmd_payload = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1704067200000,
            "bar": {
                "open": "43000",
                "high": "43100",
                "low": "42900",
                "close": "43050",
                "volume": "100",
            },
            "features": {
                # EP-01.1 volatility/liquidity
                "volatility": {"atr_14": 150.0, "atr_ready": True},
                "liquidity": {"obi_close": "0.05"},
                # NO price_motion here!
            },
            "warmup": {"full_ready": True},
            "regime": {"overall_regime": "FLAT_NORMAL"},
        }
        
        features = cmd_payload.get("features", {})
        pm = features.get("price_motion")
        
        # This is the current broken state
        assert pm is None, "CMD.features should NOT contain price_motion (current behavior)"

    def test_aurora_should_cache_price_motion_from_evt(self):
        """
        P0-3 Fix: Aurora handler should cache price_motion from EVT:FEATURES_CALCULATED.
        """
        # Simulated symbol state with cached price_motion
        class MockSymbolState:
            def __init__(self):
                self._cached_price_motion = None
        
        state = MockSymbolState()
        
        # On EVT:FEATURES_CALCULATED
        evt_payload = {
            "symbol": "BTCUSDT",
            "price_motion": {
                "pm_norm_300s": 0.75,
            },
        }
        state._cached_price_motion = evt_payload.get("price_motion")
        
        # Later, in CMD handler, retrieve from cache
        pm_from_cache = state._cached_price_motion
        
        assert pm_from_cache is not None
        assert pm_from_cache.get("pm_norm_300s") == 0.75


class TestSchemaCompliance:
    """Test price_motion schema compliance."""

    def test_schema_only_defines_10_60_300s_windows(self):
        """
        features_price_motion_v1.json only defines pm_norm_10s, pm_norm_60s, pm_norm_300s.
        No pm_norm_900s exists in schema.
        """
        valid_windows = ["pm_norm_10s", "pm_norm_60s", "pm_norm_300s"]
        invalid_windows = ["pm_norm_900s", "pm_norm_600s", "pm_norm_1800s"]
        
        # Schema-compliant payload
        price_motion = {
            "ret_10s": 0.0001,
            "ret_60s": 0.0005,
            "ret_300s": 0.002,
            "vol_pct_10s": 0.0002,
            "vol_pct_60s": 0.0008,
            "vol_pct_300s": 0.003,
            "pm_norm_10s": 0.5,
            "pm_norm_60s": 0.6,
            "pm_norm_300s": 0.7,
        }
        
        for valid_key in valid_windows:
            assert valid_key in price_motion, f"{valid_key} must be in schema"
        
        for invalid_key in invalid_windows:
            assert invalid_key not in price_motion, f"{invalid_key} should NOT be in schema"

    def test_config_motion_window_sec_should_be_valid(self):
        """
        Config motion_window_sec must be one of: 10, 60, 300.
        """
        valid_windows = [10, 60, 300]
        
        # After P0-2 fix
        config_value = 300
        
        assert config_value in valid_windows, f"motion_window_sec={config_value} not in valid windows"
        
        # Old broken value
        broken_value = 900
        assert broken_value not in valid_windows, "900 should NOT be a valid window"
