import decimal
import pytest
from unittest.mock import MagicMock, patch
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.config_loader import AuroraConfig

class TestMarginFallback:
    """
    Test suite for Margin Fallback Logic in PositionTracking.
    Target: _calc_margin_used_usd
    """

    @pytest.fixture
    def mock_config(self):
        cfg = MagicMock(spec=AuroraConfig)
        # Mock leverage defaults for fallback logic (even if we test it's NOT used)
        cfg.trading = MagicMock()
        cfg.trading.execution = MagicMock()
        cfg.trading.execution.exposure = MagicMock()
        
        # Proper dict structure for leverage_defaults as expected by code
        cfg.trading.execution.exposure.leverage_defaults = {
            "__default__": "5", 
            "BTCUSDT": "10"
        }
        
        # Mock system config
        cfg.system = MagicMock()
        cfg.system.position_tracking = MagicMock()
        cfg.system.position_tracking.quantity_min_threshold = 0.0001
        
        # Mock domains config
        cfg.domains = MagicMock()
        cfg.domains.execution_position = MagicMock()
        
        # Position Tracking precision
        cfg.domains.position_tracking = MagicMock()
        cfg.domains.position_tracking.precision = MagicMock()
        cfg.domains.position_tracking.precision.quantity_min_threshold = 0.0001
        cfg.domains.position_tracking.precision.flat_position_threshold = 0.0001
        cfg.domains.position_tracking.precision.decimal_places = 2
        
        # Mock instruments (required for leverage resolution)
        cfg.instruments = {}
        
        return cfg

    @pytest.fixture
    def position_tracking(self, mock_config):
        fsm_mock = MagicMock()
        pt = PositionTracking(fsm=fsm_mock, config=mock_config)
        return pt

    def test_calc_margin_used_usd_valid_empty_overrides_ghosts(self, position_tracking, caplog):
        """
        [PART A] Reproduction Test:
        If internal memory has 'ghost' positions, but API returns explicit empty list [],
        margin should be 0.0 and NO 'FALLBACK MODE' log should appear.
        
        Currently (BUG): returns non-zero (ghost margin) and logs FALLBACK MODE.
        Target (FIX): return 0.0 and sync internal state (no fallback).
        """
        # 1. Setup Ghost Position in internal memory
        ghost_symbol = "BTCUSDT"
        position_tracking._positions = {
            ghost_symbol: {
                "quantity": decimal.Decimal("1.0"),
                "avg_price": decimal.Decimal("50000"),
                "venues": []
            }
        }
        
        # Verify setup (ghost exists)
        assert len(position_tracking._positions) == 1
        
        # 2. Call with explicit empty list (API says FLAT)
        with caplog.at_level("WARNING"):
            margin_used = position_tracking._calc_margin_used_usd([])
        
        # 3. Assertions
        
        # BUG REPRODUCTION EXPECTATION:
        # Current code does: if []: -> False -> Fallback -> Uses internal ghost -> margin > 0
        
        # FIX EXPECTATION:
        # Should return 0.0
        # Should NOT log "FALLBACK MODE"
        # Should clear internal positions (sync)
        
        has_fallback_log = any("FALLBACK MODE" in r.message for r in caplog.records)
        
        print(f"\nMargin: {margin_used}")
        print(f"Fallback Log Present: {has_fallback_log}")
        
        # Assertions designed to FAIL before fix
        assert margin_used == decimal.Decimal("0.00"), \
            f"Margin should be 0.00 for empty API list, got {margin_used} (Ghost positions used!)"
            
        assert not has_fallback_log, \
            "Should NOT trigger FALLBACK MODE for valid empty list"

        # Check explicit state clearing (Refined Plan requirement)
        # Note: _calc_margin_used_usd might not be responsible for clearing _positions directly 
        # (on_account_update does that usually), but the plan says we want to sync it here or ensure logic flow handles it.
        # Actually, let's verify if _calc_margin_used_usd IS where we want the side-effect?
        # Re-reading plan: "If positions == [], explicitly clear/sync self._positions"
        # Ideally, `on_account_update` updates positions *before* calling calc margin.
        # Let's check `position_tracking.py` line ~831 context.
        pass

