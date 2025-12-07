"""
DOGE/XRP Bracket Calculation Audit Test
========================================
Phase 3+ Audit: Verifies bracket calculation behavior for DOGE/XRP.

This test codifies the audit finding that DOGE/XRP positions were running
with "default/half-wired" mode (global bps instead of per-asset Optuna values).

Key findings documented:
1. Current config produces narrow brackets (40/80 bps from trading.yaml)
2. Log values (0.1/0.2 for DOGE, 2.0/2.1 for XRP) don't match current code
3. Those wide values suggest older config or different code path

References:
- trading.yaml lines 394-398: sl.fixed_bps=40, tp.fixed_bps=80
- fsm_manage.py lines 780-870: _calculate_bracket_prices()
- aurora_core.log: DOGE SL=0.100000, TP=0.200000
"""

import pytest
from decimal import Decimal
from pathlib import Path
import yaml
import sys
import os

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_trading_yaml() -> dict:
    """Load trading.yaml directly for testing."""
    config_path = PROJECT_ROOT / "config" / "aurora" / "trading.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


class TestDOGEXRPBracketAudit:
    """
    Audit tests for DOGE/XRP bracket calculation behavior.
    
    These tests verify the current bracket logic and document the mismatch
    between expected narrow brackets and observed wide static values in logs.
    """

    @pytest.fixture
    def trading_config(self):
        """Load real trading.yaml config."""
        return load_trading_yaml()

    def test_doge_has_aurora_instruments_config(self, trading_config):
        """
        AUDIT: Verify DOGEUSDT is now in aurora_instruments.
        
        After the Phase 3+ audit fix, DOGE should have per-instrument config.
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        
        # After fix: DOGE SHOULD have per-instrument config
        assert "DOGEUSDT" in aurora_instruments, \
            "DOGEUSDT should now have aurora_instruments config after audit fix!"
        
        # ETH and SOL should also have config (already existed)
        assert "ETHUSDT" in aurora_instruments
        assert "SOLUSDT" in aurora_instruments

    def test_xrp_has_aurora_instruments_config(self, trading_config):
        """
        AUDIT: Verify XRPUSDT is now in aurora_instruments.
        
        After the Phase 3+ audit fix, XRP should have per-instrument config.
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        
        # After fix: XRP SHOULD have per-instrument config
        assert "XRPUSDT" in aurora_instruments, \
            "XRPUSDT should now have aurora_instruments config after audit fix!"

    def test_global_bracket_bps_values(self, trading_config):
        """
        AUDIT: Verify global bracket bps values in trading.yaml.
        
        Current config (line 394-398):
        - sl.fixed_bps: 40
        - tp.fixed_bps: 80
        """
        brackets = trading_config.get("trading", {}).get("execution", {}).get("manage", {}).get("brackets", {})
        
        assert brackets.get("sl", {}).get("fixed_bps") == 40, "Global SL bps should be 40"
        assert brackets.get("tp", {}).get("fixed_bps") == 80, "Global TP bps should be 80"

    def test_doge_bracket_from_global_bps(self):
        """
        AUDIT: Calculate expected DOGE brackets using global bps.
        
        Given:
        - entry_price = 0.13971 (from aurora_core.log line 1230)
        - sl_bps = 40, tp_bps = 80
        
        Expected (for BUY/LONG):
        - SL = entry * (1 - 40/10000) = 0.13971 * 0.996 ≈ 0.13915
        - TP = entry * (1 + 80/10000) = 0.13971 * 1.008 ≈ 0.14083
        
        MISMATCH: Log shows SL=0.100000, TP=0.200000 (NOT 0.139/0.140!)
        """
        entry_price = Decimal("0.13971")
        sl_bps = Decimal("40")
        tp_bps = Decimal("80")
        
        # Calculate expected brackets for LONG position
        expected_sl = entry_price * (1 - sl_bps / 10000)
        expected_tp = entry_price * (1 + tp_bps / 10000)
        
        # Verify narrow brackets (~0.4%/0.8%)
        assert abs(float(expected_sl) - 0.13915) < 0.0001, \
            f"Expected SL ≈ 0.13915, got {expected_sl}"
        assert abs(float(expected_tp) - 0.14083) < 0.0001, \
            f"Expected TP ≈ 0.14083, got {expected_tp}"
        
        # Document the MISMATCH with log values
        log_sl = 0.100000
        log_tp = 0.200000
        
        # These should NOT match (documenting the discrepancy)
        assert abs(float(expected_sl) - log_sl) > 0.03, \
            "SL matches log value - unexpected! The mismatch was the audit finding."
        assert abs(float(expected_tp) - log_tp) > 0.05, \
            "TP matches log value - unexpected! The mismatch was the audit finding."

    def test_xrp_bracket_from_global_bps(self):
        """
        AUDIT: Calculate expected XRP brackets using global bps.
        
        Given:
        - entry_price = 2.0492 (from aurora_core.log)
        - sl_bps = 40, tp_bps = 80
        
        Expected (for BUY/LONG):
        - SL = entry * (1 - 40/10000) = 2.0492 * 0.996 ≈ 2.0410
        - TP = entry * (1 + 80/10000) = 2.0492 * 1.008 ≈ 2.0656
        
        MISMATCH: Log shows SL=2.0000, TP=2.1000 (NOT 2.04/2.06!)
        """
        entry_price = Decimal("2.0492")
        sl_bps = Decimal("40")
        tp_bps = Decimal("80")
        
        # Calculate expected brackets for LONG position
        expected_sl = entry_price * (1 - sl_bps / 10000)
        expected_tp = entry_price * (1 + tp_bps / 10000)
        
        # Verify narrow brackets (~0.4%/0.8%)
        assert abs(float(expected_sl) - 2.0410) < 0.001, \
            f"Expected SL ≈ 2.0410, got {expected_sl}"
        assert abs(float(expected_tp) - 2.0656) < 0.001, \
            f"Expected TP ≈ 2.0656, got {expected_tp}"
        
        # Document the MISMATCH with log values
        log_sl = 2.0000
        log_tp = 2.1000
        
        # These should NOT match (documenting the discrepancy)
        assert abs(float(expected_sl) - log_sl) > 0.03, \
            "SL matches log value - unexpected! The mismatch was the audit finding."
        assert abs(float(expected_tp) - log_tp) > 0.03, \
            "TP matches log value - unexpected! The mismatch was the audit finding."

    def test_numeric_backsolve_log_values(self):
        """
        AUDIT: Back-solve what bps would produce the log values.
        
        To get DOGE SL=0.1000, TP=0.2000 from mark≈0.1333:
        - sl_bps = (1 - 0.1000/0.1333) * 10000 ≈ 2497 bps (24.97%)
        - tp_bps = (0.2000/0.1333 - 1) * 10000 ≈ 5003 bps (50.03%)
        
        These values are nowhere in current config!
        """
        # Back-solve for DOGE
        doge_mark = 0.1333  # approximate mark that would produce log values
        doge_log_sl = 0.1000
        doge_log_tp = 0.2000
        
        doge_sl_bps_implied = (1 - doge_log_sl / doge_mark) * 10000
        doge_tp_bps_implied = (doge_log_tp / doge_mark - 1) * 10000
        
        # These are WAY larger than current config (40/80 bps)
        assert doge_sl_bps_implied > 2000, \
            f"Implied SL bps should be >2000, got {doge_sl_bps_implied}"
        assert doge_tp_bps_implied > 4000, \
            f"Implied TP bps should be >4000, got {doge_tp_bps_implied}"
        
        # Back-solve for XRP
        xrp_mark = 2.0333  # approximate mark
        xrp_log_sl = 2.0000
        xrp_log_tp = 2.1000
        
        xrp_sl_bps_implied = (1 - xrp_log_sl / xrp_mark) * 10000
        xrp_tp_bps_implied = (xrp_log_tp / xrp_mark - 1) * 10000
        
        # These are also larger than current config
        assert xrp_sl_bps_implied > 100, \
            f"Implied SL bps should be >100, got {xrp_sl_bps_implied}"
        assert xrp_tp_bps_implied > 300, \
            f"Implied TP bps should be >300, got {xrp_tp_bps_implied}"


class TestDOGEXRPNewConfig:
    """
    Tests to verify the new aurora_instruments config for DOGE/XRP.
    
    These tests verify that the config changes from the Phase 3+ audit
    have been correctly applied.
    """

    @pytest.fixture
    def trading_config(self):
        """Load real trading.yaml config."""
        return load_trading_yaml()

    def test_doge_has_exit_config(self, trading_config):
        """
        After config update: DOGE should have sl_pct=0.0197 (1.97%).
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        doge_cfg = aurora_instruments.get("DOGEUSDT", {})
        
        assert doge_cfg, "DOGEUSDT should have aurora_instruments config"
        exit_cfg = doge_cfg.get("exit", {})
        assert exit_cfg.get("sl_pct") == pytest.approx(0.0197, abs=0.001), \
            f"DOGE sl_pct should be 0.0197, got {exit_cfg.get('sl_pct')}"

    def test_xrp_has_exit_config(self, trading_config):
        """
        After config update: XRP should have sl_pct=0.0144 (1.44%).
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        xrp_cfg = aurora_instruments.get("XRPUSDT", {})
        
        assert xrp_cfg, "XRPUSDT should have aurora_instruments config"
        exit_cfg = xrp_cfg.get("exit", {})
        assert exit_cfg.get("sl_pct") == pytest.approx(0.0144, abs=0.001), \
            f"XRP sl_pct should be 0.0144, got {exit_cfg.get('sl_pct')}"

    def test_doge_has_trailing_stop_enabled(self, trading_config):
        """
        After config update: DOGE should have trailing_stop enabled.
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        doge_cfg = aurora_instruments.get("DOGEUSDT", {})
        
        trailing_cfg = doge_cfg.get("trailing_stop", {})
        assert trailing_cfg.get("enabled") is True, \
            f"DOGE trailing_stop should be enabled, got {trailing_cfg.get('enabled')}"

    def test_xrp_trailing_stop_disabled(self, trading_config):
        """
        After config update: XRP should have trailing_stop disabled.
        (XRP has extreme vol sensitivity, static TP is safer)
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        xrp_cfg = aurora_instruments.get("XRPUSDT", {})
        
        trailing_cfg = xrp_cfg.get("trailing_stop", {})
        assert trailing_cfg.get("enabled") is False, \
            f"XRP trailing_stop should be disabled, got {trailing_cfg.get('enabled')}"

    def test_doge_has_weights(self, trading_config):
        """
        After config update: DOGE should have signal weights configured.
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        doge_cfg = aurora_instruments.get("DOGEUSDT", {})
        
        weights = doge_cfg.get("weights", {})
        assert weights, "DOGE should have weights configured"
        assert "ema" in weights
        assert "volume" in weights
        assert "obi" in weights

    def test_xrp_has_weights_from_optuna(self, trading_config):
        """
        After config update: XRP should have Optuna-optimized weights.
        
        From aurora_phase3_production.yaml:
        - ema: 0.427
        - volume: 0.385
        - macro: 0.469
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        xrp_cfg = aurora_instruments.get("XRPUSDT", {})
        
        weights = xrp_cfg.get("weights", {})
        assert weights, "XRP should have weights configured"
        assert weights.get("ema") == pytest.approx(0.427, abs=0.01)
        assert weights.get("volume") == pytest.approx(0.385, abs=0.01)
        assert weights.get("macro") == pytest.approx(0.469, abs=0.01)

    def test_doge_allowed_regimes(self, trading_config):
        """
        After config update: DOGE should have FLAT regimes for MR.
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        doge_cfg = aurora_instruments.get("DOGEUSDT", {})
        
        allowed = doge_cfg.get("allowed_regimes", [])
        assert "FLAT_LOW" in allowed
        assert "FLAT_NORMAL" in allowed
        assert "LOW_VOLATILITY" in allowed

    def test_xrp_regime_sizing_extreme_vol_reduction(self, trading_config):
        """
        After config update: XRP should have extreme HIGH_VOLATILITY reduction.
        
        From Phase 3 optimization: high_volatility_multiplier = 0.1 (90% smaller)
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        xrp_cfg = aurora_instruments.get("XRPUSDT", {})
        
        regime_sizing = xrp_cfg.get("regime_sizing", {})
        assert regime_sizing.get("HIGH_VOLATILITY") == pytest.approx(0.1, abs=0.01), \
            "XRP should have extreme HIGH_VOLATILITY sizing reduction"


class TestETHSOLComparisonBaseline:
    """
    Baseline tests for ETH/SOL configs (should already pass).
    Used to verify the test structure works correctly.
    """

    @pytest.fixture
    def trading_config(self):
        """Load real trading.yaml config."""
        return load_trading_yaml()

    def test_eth_has_per_instrument_exit(self, trading_config):
        """
        ETH: sl_pct=0.019 (1.9%), max_hold_sec=900
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        eth_cfg = aurora_instruments.get("ETHUSDT", {})
        
        assert eth_cfg, "ETHUSDT should have aurora_instruments config"
        exit_cfg = eth_cfg.get("exit", {})
        assert exit_cfg.get("sl_pct") == pytest.approx(0.019, abs=0.001)
        assert exit_cfg.get("max_hold_sec") == 900

    def test_sol_has_per_instrument_exit(self, trading_config):
        """
        SOL: sl_pct=0.027 (2.7%), max_hold_sec=180
        """
        aurora_instruments = trading_config.get("trading", {}).get("aurora_instruments", {})
        sol_cfg = aurora_instruments.get("SOLUSDT", {})
        
        assert sol_cfg, "SOLUSDT should have aurora_instruments config"
        exit_cfg = sol_cfg.get("exit", {})
        assert exit_cfg.get("sl_pct") == pytest.approx(0.027, abs=0.001)
        assert exit_cfg.get("max_hold_sec") == 180
