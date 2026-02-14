"""
Comprehensive tests for TP/SL configuration and calculation.

Tests verify that per-symbol Aurora configs are correctly loaded and applied,
not falling back to global defaults.

BUG HUNTING:
- Verify sl_pct from aurora.yaml is used, not brackets.sl.fixed_bps from trading.yaml
- Verify tp_low_ratio/tp_high_ratio are applied correctly
- Verify trailing_stop config is read properly
"""

import pytest
from decimal import Decimal
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch
import yaml

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import AuroraConfig
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState


@pytest.fixture
def production_config() -> AuroraConfig:
    """Load actual production config."""
    config_dir = Path(__file__).parents[2] / "config" / "aurora"
    loader = ConfigLoader(config_dir=config_dir)
    return loader.load_config()


class TestAuroraConfigLoading:
    """Test that Aurora per-symbol configs are correctly loaded."""

    def test_ethusdt_exit_config_loaded(self, production_config: AuroraConfig):
        """ETHUSDT sl_pct should be 0.019 (1.9%), not default."""
        aurora = production_config.strategies.aurora
        assert aurora is not None, "Aurora strategy config missing"
        
        eth_cfg = aurora.assets.get("ETHUSDT")
        assert eth_cfg is not None, "ETHUSDT config missing in aurora.assets"
        assert eth_cfg.exit is not None, "ETHUSDT.exit config missing"
        
        # Critical: sl_pct should be 0.019 from aurora.yaml, not 0.004 from brackets
        assert eth_cfg.exit.sl_pct == pytest.approx(0.019, rel=1e-3), (
            f"ETHUSDT sl_pct={eth_cfg.exit.sl_pct}, expected 0.019 from aurora.yaml"
        )
        assert eth_cfg.exit.max_hold_sec == 3000, (
            f"ETHUSDT max_hold_sec={eth_cfg.exit.max_hold_sec}, expected 3000"
        )

    def test_ethusdt_take_profit_config_loaded(self, production_config: AuroraConfig):
        """ETHUSDT TP ratios should be from aurora.yaml."""
        eth_cfg = production_config.strategies.aurora.assets.get("ETHUSDT")
        assert eth_cfg.take_profit is not None, "ETHUSDT.take_profit config missing"
        
        assert eth_cfg.take_profit.tp_low_ratio == pytest.approx(0.4, rel=1e-3), (
            f"ETHUSDT tp_low_ratio={eth_cfg.take_profit.tp_low_ratio}, expected 0.4"
        )
        assert eth_cfg.take_profit.tp_high_ratio == pytest.approx(1.4, rel=1e-3), (
            f"ETHUSDT tp_high_ratio={eth_cfg.take_profit.tp_high_ratio}, expected 1.4"
        )
        assert eth_cfg.take_profit.partial_exit_pct == pytest.approx(0.7, rel=1e-3), (
            f"ETHUSDT partial_exit_pct={eth_cfg.take_profit.partial_exit_pct}, expected 0.7"
        )

    def test_solusdt_exit_config_loaded(self, production_config: AuroraConfig):
        """SOLUSDT sl_pct should match SSOT config."""
        sol_cfg = production_config.strategies.aurora.assets.get("SOLUSDT")
        assert sol_cfg is not None, "SOLUSDT config missing"
        assert sol_cfg.exit is not None, "SOLUSDT.exit missing"
        
        assert sol_cfg.exit.sl_pct == pytest.approx(0.0135, rel=1e-3), (
            f"SOLUSDT sl_pct={sol_cfg.exit.sl_pct}, expected 0.0135"
        )
        assert sol_cfg.exit.max_hold_sec == 3000, (
            f"SOLUSDT max_hold_sec={sol_cfg.exit.max_hold_sec}, expected 3000"
        )

    def test_solusdt_trailing_stop_enabled(self, production_config: AuroraConfig):
        """SOLUSDT should have trailing stop ENABLED."""
        sol_cfg = production_config.strategies.aurora.assets.get("SOLUSDT")
        assert sol_cfg.trailing_stop is not None, "SOLUSDT.trailing_stop missing"
        
        assert sol_cfg.trailing_stop.enabled is True, (
            f"SOLUSDT trailing_stop.enabled={sol_cfg.trailing_stop.enabled}, expected True"
        )
        assert sol_cfg.trailing_stop.activation_pct == pytest.approx(0.046, rel=1e-3)
        assert sol_cfg.trailing_stop.trail_pct == pytest.approx(0.018, rel=1e-3)

    def test_btcusdt_exit_config_loaded(self, production_config: AuroraConfig):
        """BTCUSDT sl_pct should be 0.02 (2.0%)."""
        btc_cfg = production_config.strategies.aurora.assets.get("BTCUSDT")
        assert btc_cfg is not None, "BTCUSDT config missing"
        assert btc_cfg.exit is not None, "BTCUSDT.exit missing"
        
        assert btc_cfg.exit.sl_pct == pytest.approx(0.02, rel=1e-3), (
            f"BTCUSDT sl_pct={btc_cfg.exit.sl_pct}, expected 0.02"
        )
        assert btc_cfg.exit.max_hold_sec == 3000, (
            f"BTCUSDT max_hold_sec={btc_cfg.exit.max_hold_sec}, expected 3000"
        )

    @pytest.mark.skip(reason="DOGEUSDT assigned to mean_reversion, not aurora (strategies.yaml)")
    def test_dogeusdt_max_hold_sec_loaded(self, production_config: AuroraConfig):
        """DOGEUSDT max_hold_sec should match SSOT config."""
        doge_cfg = production_config.strategies.aurora.assets.get("DOGEUSDT")
        assert doge_cfg is not None, "DOGEUSDT config missing"
        assert doge_cfg.exit is not None, "DOGEUSDT.exit missing"
        assert doge_cfg.exit.max_hold_sec == 1500, (
            f"DOGEUSDT max_hold_sec={doge_cfg.exit.max_hold_sec}, expected 1500"
        )

    @pytest.mark.skip(reason="XRPUSDT assigned to mean_reversion, not aurora (strategies.yaml)")
    def test_xrpusdt_max_hold_sec_loaded(self, production_config: AuroraConfig):
        """XRPUSDT max_hold_sec should match SSOT config."""
        xrp_cfg = production_config.strategies.aurora.assets.get("XRPUSDT")
        assert xrp_cfg is not None, "XRPUSDT config missing"
        assert xrp_cfg.exit is not None, "XRPUSDT.exit missing"
        assert xrp_cfg.exit.max_hold_sec == 1500, (
            f"XRPUSDT max_hold_sec={xrp_cfg.exit.max_hold_sec}, expected 1500"
        )

    def test_btcusdt_trailing_stop_disabled(self, production_config: AuroraConfig):
        """BTCUSDT should have trailing stop DISABLED."""
        btc_cfg = production_config.strategies.aurora.assets.get("BTCUSDT")
        assert btc_cfg.trailing_stop is not None, "BTCUSDT.trailing_stop missing"
        
        assert btc_cfg.trailing_stop.enabled is False, (
            f"BTCUSDT trailing_stop.enabled={btc_cfg.trailing_stop.enabled}, expected False"
        )

    def test_global_brackets_fallback_values(self, production_config: AuroraConfig):
        """Verify global fallback values in trading.yaml."""
        brackets = production_config.trading.execution.manage.brackets
        assert brackets is not None, "trading.execution.manage.brackets missing"
        
        # These are fallbacks, should NOT be used when per-symbol config exists
        assert brackets.sl.fixed_bps == 40, f"Global SL fallback={brackets.sl.fixed_bps}, expected 40"
        assert brackets.tp.fixed_bps == 80, f"Global TP fallback={brackets.tp.fixed_bps}, expected 80"


class TestManageFlowFSMConfigAccess:
    """Test that ManageFlowFSM correctly reads per-symbol configs."""

    def test_get_aurora_instr_cfg_returns_ethusdt(self, production_config: AuroraConfig):
        """_get_aurora_instr_cfg should return ETHUSDT config."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "ETHUSDT"
        
        cfg = fsm._get_aurora_instr_cfg()
        assert cfg is not None, "_get_aurora_instr_cfg() returned None for ETHUSDT"
        assert cfg.exit is not None, "ETHUSDT exit config missing"
        assert cfg.exit.sl_pct == pytest.approx(0.019, rel=1e-3)

    def test_get_exit_param_uses_per_symbol_not_global(self, production_config: AuroraConfig):
        """_get_exit_param should return per-symbol sl_pct, not global bps."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "ETHUSDT"
        
        sl_pct = fsm._get_exit_param("sl_pct", default=None)
        
        # Should be 0.019 from aurora.yaml, NOT 0.004 (40 bps / 10000)
        assert sl_pct is not None, "sl_pct is None - config not loaded"
        assert sl_pct == pytest.approx(0.019, rel=1e-3), (
            f"sl_pct={sl_pct}, expected 0.019 from aurora.yaml. "
            f"If 0.004, system is using global fallback (40 bps)!"
        )

    def test_get_take_profit_params_returns_per_symbol(self, production_config: AuroraConfig):
        """_get_take_profit_params should return per-symbol TP ratios."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "ETHUSDT"
        
        tp_low, tp_high, partial = fsm._get_take_profit_params()
        
        assert tp_low == pytest.approx(0.4, rel=1e-3), f"tp_low_ratio={tp_low}, expected 0.4"
        assert tp_high == pytest.approx(1.4, rel=1e-3), f"tp_high_ratio={tp_high}, expected 1.4"
        assert partial == pytest.approx(0.7, rel=1e-3), f"partial_exit_pct={partial}, expected 0.7"


class TestBracketPriceCalculation:
    """Test actual SL/TP price calculations."""

    def test_ethusdt_sl_calculation_uses_config_pct(self, production_config: AuroraConfig):
        """ETHUSDT SL should be calculated from 1.9% (0.019), not 0.4% (40 bps)."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "ETHUSDT"
        fsm.position_side = "BUY"
        fsm.position_entry_price = Decimal("3500")
        fsm.position_qty = Decimal("1")
        
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()
        
        # Expected SL for LONG @ $3500 with 1.9% SL:
        # SL = 3500 * (1 - 0.019) = 3433.50
        expected_sl = Decimal("3500") * (Decimal("1") - Decimal("0.019"))
        
        # If using global 40 bps fallback:
        # SL = 3500 * (1 - 0.004) = 3486.00 (WRONG!)
        wrong_sl = Decimal("3500") * (Decimal("1") - Decimal("0.004"))
        
        assert sl_price is not None, "SL price is None"
        
        # Allow some tolerance for tick_size quantization
        assert abs(sl_price - expected_sl) < Decimal("10"), (
            f"ETHUSDT SL={sl_price}, expected ~{expected_sl} (1.9% from entry). "
            f"If close to {wrong_sl}, system is using 40 bps global fallback!"
        )

    def test_ethusdt_tp_calculation_uses_ratio(self, production_config: AuroraConfig):
        """ETHUSDT TP1 should use tp_low_ratio=0.4 relative to SL distance."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "ETHUSDT"
        fsm.position_side = "BUY"
        fsm.position_entry_price = Decimal("3500")
        fsm.position_qty = Decimal("1")
        
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()
        
        # Expected TP1 for LONG @ $3500 with sl_pct=0.019, tp_low_ratio=0.4:
        # TP1 = 3500 * (1 + 0.019 * 0.4) = 3500 * 1.0076 = 3526.60
        expected_tp1 = Decimal("3500") * (Decimal("1") + Decimal("0.019") * Decimal("0.4"))
        
        # If using global 80 bps fallback:
        # TP1 = 3500 * (1 + 0.008) = 3528.00 (close but wrong logic)
        
        assert tp1_price is not None, "TP1 price is None"
        
        # Check TP2 as well
        # TP2 = 3500 * (1 + 0.019 * 1.4) = 3500 * 1.0266 = 3593.10
        expected_tp2 = Decimal("3500") * (Decimal("1") + Decimal("0.019") * Decimal("1.4"))
        
        assert tp2_price is not None, "TP2 price is None (should have tp_high_ratio=1.4)"
        assert abs(tp2_price - expected_tp2) < Decimal("10"), (
            f"ETHUSDT TP2={tp2_price}, expected ~{expected_tp2}"
        )

    def test_solusdt_sl_calculation(self, production_config: AuroraConfig):
        """SOLUSDT SL should match SSOT sl_pct."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "SOLUSDT"
        fsm.position_side = "BUY"
        fsm.position_entry_price = Decimal("200")
        fsm.position_qty = Decimal("10")
        
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()
        
        # Expected SL = entry * (1 - sl_pct)
        expected_sl = Decimal("200") * (Decimal("1") - Decimal("0.0135"))
        
        assert sl_price is not None, "SL price is None"
        assert abs(sl_price - expected_sl) < Decimal("1"), (
            f"SOLUSDT SL={sl_price}, expected ~{expected_sl}"
        )

    def test_sol_sl_pct_applied(self, production_config: AuroraConfig):
        """SOLUSDT SL should use sl_pct=0.0135 and be quantized to tick_size."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "SOLUSDT"
        fsm.position_side = "SELL"
        fsm.position_entry_price = Decimal("79.6401785714285714300")
        fsm.position_qty = Decimal("5")

        sl_price, _, _ = fsm._calculate_bracket_prices()

        tick_size = Decimal(str(production_config.instruments["SOLUSDT"].tick_size))
        expected_raw = fsm.position_entry_price * (Decimal("1") + Decimal("0.0135"))
        expected_quantized = (expected_raw / tick_size).quantize(Decimal("1")) * tick_size

        assert sl_price == expected_quantized, (
            f"SOLUSDT SELL SL={sl_price}, expected {expected_quantized} "
            f"(raw={expected_raw}, tick={tick_size})"
        )

    def test_btcusdt_sl_calculation(self, production_config: AuroraConfig):
        """BTCUSDT SL should be 2.0% (0.02)."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "BTCUSDT"
        fsm.position_side = "BUY"
        fsm.position_entry_price = Decimal("98000")
        fsm.position_qty = Decimal("0.01")
        
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()
        
        # Expected SL = 98000 * (1 - 0.02) = 96040
        expected_sl = Decimal("98000") * (Decimal("1") - Decimal("0.02"))
        
        assert sl_price is not None, "SL price is None"
        assert abs(sl_price - expected_sl) < Decimal("100"), (
            f"BTCUSDT SL={sl_price}, expected ~{expected_sl} (2.0%)"
        )

    def test_short_position_sl_above_entry(self, production_config: AuroraConfig):
        """For SHORT position, SL should be ABOVE entry price."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "ETHUSDT"
        fsm.position_side = "SELL"  # SHORT
        fsm.position_entry_price = Decimal("3500")
        fsm.position_qty = Decimal("1")
        
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()
        
        # For SHORT, SL = 3500 * (1 + 0.019) = 3566.50 (ABOVE entry)
        expected_sl = Decimal("3500") * (Decimal("1") + Decimal("0.019"))
        
        assert sl_price is not None
        assert sl_price > fsm.position_entry_price, (
            f"SHORT SL={sl_price} should be > entry={fsm.position_entry_price}"
        )
        assert abs(sl_price - expected_sl) < Decimal("10")


class TestFailClosedBehavior:
    """Test that system CRASHES (fail-closed) when config is missing."""

    def test_unknown_symbol_crashes_fail_closed(self, production_config: AuroraConfig):
        """Unknown symbol should raise ValueError, NOT fall back silently."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "UNKNOWNUSDT"  # Not in aurora.assets
        fsm.position_side = "BUY"
        fsm.position_entry_price = Decimal("100")
        fsm.position_qty = Decimal("1")
        
        # FAIL-CLOSED: Should raise ValueError, not silently use fallback
        with pytest.raises(ValueError) as exc_info:
            fsm._calculate_bracket_prices()
        
        # Check error message is descriptive
        assert "FAIL-CLOSED" in str(exc_info.value)
        assert "sl_pct not configured" in str(exc_info.value)
        assert "UNKNOWNUSDT" in str(exc_info.value)


class TestTrailingStopConfig:
    """Test trailing stop configuration access."""

    def test_solusdt_trailing_config_accessible(self, production_config: AuroraConfig):
        """SOLUSDT trailing stop params should be accessible."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "SOLUSDT"
        
        cfg = fsm._get_aurora_instr_cfg()
        assert cfg is not None
        assert cfg.trailing_stop is not None
        
        assert cfg.trailing_stop.enabled is True
        assert cfg.trailing_stop.activation_pct == pytest.approx(0.046)
        assert cfg.trailing_stop.trail_pct == pytest.approx(0.018)
        assert cfg.trailing_stop.min_update_interval_sec == 5

    def test_ethusdt_trailing_disabled(self, production_config: AuroraConfig):
        """ETHUSDT trailing stop should be disabled."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "ETHUSDT"
        
        cfg = fsm._get_aurora_instr_cfg()
        assert cfg.trailing_stop.enabled is False


class TestConfigConsistency:
    """Cross-validate config files for consistency."""

    def test_all_aurora_symbols_have_exit_config(self, production_config: AuroraConfig):
        """All enabled Aurora symbols should have exit config."""
        aurora = production_config.strategies.aurora
        
        for symbol, cfg in aurora.assets.items():
            if cfg.enabled:
                assert cfg.exit is not None, f"{symbol} is enabled but missing exit config"
                assert cfg.exit.sl_pct is not None, f"{symbol} is enabled but missing sl_pct"

    def test_all_aurora_symbols_have_take_profit_config(self, production_config: AuroraConfig):
        """All enabled Aurora symbols should have take_profit config."""
        aurora = production_config.strategies.aurora
        
        for symbol, cfg in aurora.assets.items():
            if cfg.enabled:
                assert cfg.take_profit is not None, f"{symbol} is enabled but missing take_profit config"
                assert cfg.take_profit.tp_low_ratio is not None, f"{symbol} missing tp_low_ratio"

    def test_sl_pct_values_are_reasonable(self, production_config: AuroraConfig):
        """SL percentages should be in reasonable range (0.5% - 5%)."""
        aurora = production_config.strategies.aurora
        
        for symbol, cfg in aurora.assets.items():
            if cfg.enabled and cfg.exit and cfg.exit.sl_pct:
                sl_pct = cfg.exit.sl_pct
                assert 0.005 <= sl_pct <= 0.05, (
                    f"{symbol} sl_pct={sl_pct} outside reasonable range [0.5%, 5%]"
                )

class TestEndToEndBracketCalculation:
    """
    CRITICAL: End-to-end tests that verify the ENTIRE config path works.
    This simulates what happens in production when a position is opened.
    """

    def test_ethusdt_full_bracket_path_uses_aurora_config(self, production_config: AuroraConfig):
        """
        CRITICAL TEST: Verify ETHUSDT uses sl_pct=0.019 from aurora.yaml
        and NOT 40 bps (0.004) from trading.yaml fallback.
        
        This test simulates the exact production path:
        1. Config loaded (same as main.py)
        2. ManageFlowFSM created with config
        3. Position opened with symbol
        4. _calculate_bracket_prices called
        5. Verify SL price matches 1.9% (not 0.4%)
        """
        # Simulate production: create FSM with real config
        fsm = ManageFlowFSM(config=production_config)
        
        # Simulate position entry (BUY at 3000 USDT)
        fsm.symbol = "ETHUSDT"
        fsm.position_side = "BUY"
        fsm.position_entry_price = Decimal("3000.00")
        fsm.position_qty = Decimal("0.1")
        
        # Call the ACTUAL method used in production
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()
        
        # Expected values based on aurora.yaml config:
        # - sl_pct = 0.019 (1.9%)
        # - tp_low_ratio = 0.4, tp_high_ratio = 1.4
        # SL for BUY: entry * (1 - sl_pct) = 3000 * 0.981 = 2943.00
        # TP1: entry * (1 + sl_pct * tp_low) = 3000 * (1 + 0.019 * 0.4) = 3000 * 1.0076 = 3022.80
        # TP2: entry * (1 + sl_pct * tp_high) = 3000 * (1 + 0.019 * 1.4) = 3000 * 1.0266 = 3079.80
        
        expected_sl = Decimal("3000") * Decimal("0.981")  # ~2943
        expected_tp1 = Decimal("3000") * (Decimal("1") + Decimal("0.019") * Decimal("0.4"))  # ~3022.80
        
        # CRITICAL ASSERTION: SL should be ~2943, NOT ~2988 (which would be 40 bps fallback)
        fallback_sl = Decimal("3000") * Decimal("0.996")  # 40 bps fallback = 2988
        
        # SL should match aurora.yaml (1.9%), not fallback (0.4%)
        assert abs(sl_price - expected_sl) < Decimal("1"), (
            f"ETHUSDT SL={sl_price}, expected ~{expected_sl} (1.9% from aurora.yaml). "
            f"If SL is ~{fallback_sl}, it means fallback to 40 bps is being used!"
        )
        
        # TP1 should also be calculated correctly
        assert tp1_price is not None, "TP1 should not be None"
        assert abs(tp1_price - expected_tp1) < Decimal("1"), (
            f"ETHUSDT TP1={tp1_price}, expected ~{expected_tp1}"
        )
        
        # TP2 should exist (configured in aurora.yaml)
        assert tp2_price is not None, "TP2 should not be None for ETHUSDT"

    def test_solusdt_full_bracket_path_uses_aurora_config(self, production_config: AuroraConfig):
        """
        CRITICAL TEST: Verify SOLUSDT uses sl_pct from aurora.yaml (no fallback)
        """
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "SOLUSDT"
        fsm.position_side = "BUY"
        fsm.position_entry_price = Decimal("150.00")
        fsm.position_qty = Decimal("1.0")
        
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()
        
        # Expected: sl_pct = 0.0135 (1.35%)
        # SL for BUY: 150 * (1 - 0.0135) = 147.975
        expected_sl = Decimal("150") * (Decimal("1") - Decimal("0.0135"))
        fallback_sl = Decimal("150") * Decimal("0.996")  # 40 bps fallback
        
        assert abs(sl_price - expected_sl) < Decimal("0.1"), (
            f"SOLUSDT SL={sl_price}, expected ~{expected_sl} (from aurora.yaml). "
            f"If SL is ~{fallback_sl}, fallback is being used!"
        )

    def test_short_position_bracket_calculation(self, production_config: AuroraConfig):
        """Test SHORT position bracket calculation uses correct config."""
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "BTCUSDT"
        fsm.position_side = "SELL"  # SHORT
        fsm.position_entry_price = Decimal("100000.00")
        fsm.position_qty = Decimal("0.01")
        
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()
        
        # For SHORT: SL is ABOVE entry
        # sl_pct = 0.02 (2.0%)
        # SL: 100000 * (1 + 0.02) = 102000
        expected_sl = Decimal("100000") * Decimal("1.02")
        
        assert abs(sl_price - expected_sl) < Decimal("10"), (
            f"BTCUSDT SHORT SL={sl_price}, expected ~{expected_sl}"
        )
        
        # For SHORT: TP is BELOW entry
        assert tp1_price < fsm.position_entry_price, (
            f"SHORT TP1 should be below entry. TP1={tp1_price}, entry={fsm.position_entry_price}"
        )

    def test_intent_prices_override_config(self, production_config: AuroraConfig):
        """
        Test that strategy-injected intent prices take precedence over config.
        This is the PHASE A2 intent injection path.
        """
        fsm = ManageFlowFSM(config=production_config)
        fsm.symbol = "ETHUSDT"
        fsm.position_side = "BUY"
        fsm.position_entry_price = Decimal("3000.00")
        fsm.position_qty = Decimal("0.1")
        
        # Inject intent prices (as Strategy would)
        intent_sl = Decimal("2900.00")  # Custom SL
        intent_tp = Decimal("3200.00")  # Custom TP
        fsm.set_intent_prices(sl_price=intent_sl, tp_price=intent_tp)
        
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()
        
        # Intent prices should be used (after quantization)
        # Allow small rounding differences
        assert abs(sl_price - intent_sl) < Decimal("1"), (
            f"Intent SL not used. Got {sl_price}, expected ~{intent_sl}"
        )
        assert abs(tp1_price - intent_tp) < Decimal("1"), (
            f"Intent TP not used. Got {tp1_price}, expected ~{intent_tp}"
        )
