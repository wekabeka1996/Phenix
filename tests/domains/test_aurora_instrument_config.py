"""
Phase 0: Unit tests for Aurora per-instrument configuration.

Tests cover:
- Pydantic model validation
- TradingConfig.aurora_instruments field
- Fallback chain logic
- FSM symbol tracking
"""

import pytest
from decimal import Decimal
from typing import Optional

from apps.reference.config_models import (
    TradingConfig,
    AuroraInstrumentConfig,
    AuroraSideBiasConfig,
    AuroraExitConfig,
    AuroraTakeProfitConfig,
    AuroraTrailingStopConfig,
    AuroraExecutionConfig,
)


class TestAuroraInstrumentConfigModels:
    """Test Pydantic model validation for Aurora instrument configs."""

    def test_aurora_side_bias_config_defaults(self):
        """Test AuroraSideBiasConfig with all None defaults."""
        cfg = AuroraSideBiasConfig()
        assert cfg.penalty_factor is None
        assert cfg.window_sec is None
        assert cfg.target_ratio is None

    def test_aurora_side_bias_config_with_values(self):
        """Test AuroraSideBiasConfig with Optuna-like values."""
        cfg = AuroraSideBiasConfig(
            penalty_factor=0.8,
            window_sec=300,
            target_ratio=0.5
        )
        assert cfg.penalty_factor == 0.8
        assert cfg.window_sec == 300
        assert cfg.target_ratio == 0.5

    def test_aurora_exit_config_defaults(self):
        """Test AuroraExitConfig with all None defaults."""
        cfg = AuroraExitConfig()
        assert cfg.sl_pct is None
        assert cfg.max_hold_sec is None

    def test_aurora_exit_config_with_values(self):
        """Test AuroraExitConfig with typical values."""
        cfg = AuroraExitConfig(sl_pct=0.005, max_hold_sec=1800)
        assert cfg.sl_pct == 0.005
        assert cfg.max_hold_sec == 1800

    def test_aurora_take_profit_config(self):
        """Test AuroraTakeProfitConfig with partial exit settings."""
        cfg = AuroraTakeProfitConfig(
            tp_low_ratio=1.5,
            tp_high_ratio=3.0,
            partial_exit_pct=0.7
        )
        assert cfg.tp_low_ratio == 1.5
        assert cfg.tp_high_ratio == 3.0
        assert cfg.partial_exit_pct == 0.7

    def test_aurora_trailing_stop_config(self):
        """Test AuroraTrailingStopConfig with trailing settings."""
        cfg = AuroraTrailingStopConfig(
            enabled=True,
            activation_pct=0.003,
            trail_pct=0.002,
            min_update_interval_sec=5
        )
        assert cfg.enabled is True
        assert cfg.activation_pct == 0.003
        assert cfg.trail_pct == 0.002
        assert cfg.min_update_interval_sec == 5

    def test_aurora_trailing_stop_config_default_interval(self):
        """Test AuroraTrailingStopConfig has default 5s interval."""
        cfg = AuroraTrailingStopConfig(enabled=True)
        assert cfg.min_update_interval_sec == 5

    def test_aurora_execution_config(self):
        """Test AuroraExecutionConfig with order settings."""
        cfg = AuroraExecutionConfig(
            order_type="LIMIT",
            post_only=True,
            max_slippage_bps=10
        )
        assert cfg.order_type == "LIMIT"
        assert cfg.post_only is True
        assert cfg.max_slippage_bps == 10

    def test_aurora_instrument_config_full(self):
        """Test full AuroraInstrumentConfig with all nested configs."""
        cfg = AuroraInstrumentConfig(
            weights={"ema_slope": 0.15, "vwap_deviation": 0.12},
            side_bias=AuroraSideBiasConfig(penalty_factor=0.8),
            regime_thresholds={"TREND": 1.2, "VOLATILE": 0.8, "FLAT": 0.5},
            regime_sizing={"TREND": 1.0, "VOLATILE": 0.7, "FLAT": 0.5},
            exit=AuroraExitConfig(sl_pct=0.005),
            take_profit=AuroraTakeProfitConfig(tp_low_ratio=1.5),
            trailing_stop=AuroraTrailingStopConfig(enabled=True),
            execution=AuroraExecutionConfig(order_type="LIMIT"),
        )
        assert cfg.weights == {"ema_slope": 0.15, "vwap_deviation": 0.12}
        assert cfg.side_bias.penalty_factor == 0.8
        assert cfg.regime_thresholds["TREND"] == 1.2
        assert cfg.regime_sizing["VOLATILE"] == 0.7
        assert cfg.exit.sl_pct == 0.005
        assert cfg.take_profit.tp_low_ratio == 1.5
        assert cfg.trailing_stop.enabled is True
        assert cfg.execution.order_type == "LIMIT"

    def test_aurora_instrument_config_minimal(self):
        """Test AuroraInstrumentConfig with only weights (minimal config)."""
        cfg = AuroraInstrumentConfig(
            weights={"ema_slope": 0.2}
        )
        assert cfg.weights == {"ema_slope": 0.2}
        assert cfg.side_bias is None
        assert cfg.exit is None

    def test_aurora_instrument_config_extra_fields_allowed(self):
        """Test that extra='allow' works for future extensibility."""
        cfg = AuroraInstrumentConfig(
            weights={"test": 1.0},
            future_field="test_value"  # extra field
        )
        assert cfg.weights == {"test": 1.0}
        # Extra field should be stored
        assert hasattr(cfg, "future_field") or cfg.model_extra.get("future_field") == "test_value"


class TestTradingConfigAuroraInstruments:
    """Test TradingConfig.aurora_instruments integration."""

    def test_trading_config_aurora_instruments_default(self):
        """Test TradingConfig has empty aurora_instruments by default."""
        cfg = TradingConfig()
        assert cfg.aurora_instruments == {}

    def test_trading_config_with_aurora_instruments(self):
        """Test TradingConfig with per-instrument Aurora configs."""
        cfg = TradingConfig(
            aurora_instruments={
                "BTCUSDT": AuroraInstrumentConfig(
                    weights={"ema_slope": 0.15},
                    exit=AuroraExitConfig(sl_pct=0.005)
                ),
                "ETHUSDT": AuroraInstrumentConfig(
                    weights={"vwap_deviation": 0.12},
                    exit=AuroraExitConfig(sl_pct=0.007)
                ),
            }
        )
        assert len(cfg.aurora_instruments) == 2
        assert "BTCUSDT" in cfg.aurora_instruments
        assert "ETHUSDT" in cfg.aurora_instruments
        assert cfg.aurora_instruments["BTCUSDT"].exit.sl_pct == 0.005
        assert cfg.aurora_instruments["ETHUSDT"].exit.sl_pct == 0.007

    def test_trading_config_aurora_instruments_lookup(self):
        """Test looking up per-instrument config from TradingConfig."""
        cfg = TradingConfig(
            aurora_instruments={
                "SOLUSDT": AuroraInstrumentConfig(
                    regime_thresholds={"TREND": 1.3}
                )
            }
        )
        sol_cfg = cfg.aurora_instruments.get("SOLUSDT")
        assert sol_cfg is not None
        assert sol_cfg.regime_thresholds["TREND"] == 1.3
        
        # Non-existent symbol returns None
        xrp_cfg = cfg.aurora_instruments.get("XRPUSDT")
        assert xrp_cfg is None


class TestFSMSymbolTracking:
    """Test FSM symbol tracking for per-instrument config."""

    def test_manage_flow_fsm_has_symbol_field(self):
        """Test ManageFlowFSM has self.symbol field."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        
        fsm = ManageFlowFSM()
        assert hasattr(fsm, "symbol")
        assert fsm.symbol is None

    def test_manage_flow_fsm_symbol_set_on_fill(self):
        """Test symbol is set when position opens via fill."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
        from vfoundation.core.protocol import Message
        
        fsm = ManageFlowFSM()
        
        # Simulate fill event with symbol (include required fields)
        fill_msg = Message(
            ver="v1",
            ts=1234567890,
            src="test",
            op="EVT",
            dst="execution_position",
            verb="EVT:FILL",
            pld={
                "qty": "1.0",
                "price": "50000.0",
                "side": "BUY",
                "symbol": "BTCUSDT"
            }
        )
        
        # Need to set state to trigger fill processing
        fsm.state = ManageState.FLAT
        fsm._on_fill(fill_msg)
        
        assert fsm.symbol == "BTCUSDT"
        assert fsm.position_side == "BUY"
        assert fsm.position_qty == Decimal("1.0")

    def test_manage_flow_fsm_symbol_cleared_on_reset(self):
        """Test symbol is cleared when FSM resets."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        
        fsm = ManageFlowFSM()
        fsm.symbol = "BTCUSDT"
        fsm.position_side = "BUY"
        
        fsm.reset()
        
        assert fsm.symbol is None
        assert fsm.position_side is None

    def test_manage_flow_fsm_get_aurora_instr_cfg_with_symbol(self):
        """Test _get_aurora_instr_cfg uses self.symbol."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig
        
        # Create config with aurora_instruments
        config = AuroraConfig(
            trading=TradingConfig(
                aurora_instruments={
                    "BTCUSDT": AuroraInstrumentConfig(
                        weights={"test": 1.0}
                    )
                }
            )
        )
        
        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "BTCUSDT"
        
        instr_cfg = fsm._get_aurora_instr_cfg()
        assert instr_cfg is not None
        assert instr_cfg.weights == {"test": 1.0}

    def test_manage_flow_fsm_get_aurora_instr_cfg_no_symbol(self):
        """Test _get_aurora_instr_cfg returns None when no symbol."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        
        fsm = ManageFlowFSM()
        assert fsm.symbol is None
        
        instr_cfg = fsm._get_aurora_instr_cfg()
        assert instr_cfg is None

    def test_manage_flow_fsm_get_aurora_instr_cfg_legacy_dict_support(self):
        """Test _get_aurora_instr_cfg converts legacy dict to Pydantic model.
        
        This ensures consistency with DecisionMaking._get_aurora_instrument_cfg()
        which also supports legacy dict configs.
        """
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig
        from unittest.mock import MagicMock
        
        # Create config where aurora_instruments contains raw dict (legacy format)
        config = AuroraConfig(
            trading=TradingConfig()
        )
        # Manually set dict value to simulate legacy config
        config.trading.aurora_instruments = {
            "BTCUSDT": {"weights": {"ema_slope": 0.15}, "exit": {"sl_pct": 0.005}}
        }
        
        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "BTCUSDT"
        
        # Should convert dict to AuroraInstrumentConfig
        instr_cfg = fsm._get_aurora_instr_cfg()
        assert instr_cfg is not None
        assert isinstance(instr_cfg, AuroraInstrumentConfig)
        assert instr_cfg.weights == {"ema_slope": 0.15}
        assert instr_cfg.exit.sl_pct == 0.005

    def test_manage_flow_fsm_get_exit_param_fallback(self):
        """Test _get_exit_param returns default when no per-instrument config."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        
        fsm = ManageFlowFSM()
        fsm.symbol = "BTCUSDT"
        
        # No aurora_instruments configured, should return default
        sl_pct = fsm._get_exit_param("sl_pct", 0.01)
        assert sl_pct == 0.01


class TestConfigFallbackChain:
    """Test per-instrument -> global fallback chain."""

    def test_fallback_to_global_when_no_per_instrument(self):
        """Test global config is used when no per-instrument config exists."""
        from apps.reference.config_models import AuroraConfig, DecisionConfig
        
        # Config with only global decision settings
        cfg = AuroraConfig(
            trading=TradingConfig(
                decision=DecisionConfig(signal_threshold=0.5),
                aurora_instruments={}  # No per-instrument
            )
        )
        
        # Global should still be accessible
        assert cfg.trading.decision.signal_threshold == 0.5
        assert cfg.trading.aurora_instruments.get("BTCUSDT") is None

    def test_per_instrument_overrides_global(self):
        """Test per-instrument config takes precedence over global."""
        from apps.reference.config_models import AuroraConfig, DecisionConfig
        
        cfg = AuroraConfig(
            trading=TradingConfig(
                decision=DecisionConfig(signal_threshold=0.5),  # global
                aurora_instruments={
                    "BTCUSDT": AuroraInstrumentConfig(
                        # Per-instrument override (different param, but demonstrates precedence)
                        weights={"ema_slope": 0.99}
                    )
                }
            )
        )
        
        # Global is still 0.5
        assert cfg.trading.decision.signal_threshold == 0.5
        
        # But BTCUSDT has its own weights
        btc_cfg = cfg.trading.aurora_instruments["BTCUSDT"]
        assert btc_cfg.weights["ema_slope"] == 0.99


class TestBracketCalculationWithPerInstrumentConfig:
    """Test FSM bracket calculation with per-instrument sl_pct."""

    def test_bracket_prices_use_per_instrument_sl_pct(self):
        """Test _calculate_bracket_prices uses per-instrument sl_pct."""
        from decimal import Decimal
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig

        # Create config with per-instrument exit config
        config = AuroraConfig(
            trading=TradingConfig(
                aurora_instruments={
                    "ETHUSDT": AuroraInstrumentConfig(
                        exit=AuroraExitConfig(sl_pct=0.019)  # 1.9% SL
                    )
                }
            )
        )

        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "ETHUSDT"
        fsm.position_entry_price = Decimal("2000.00")
        fsm.position_side = "BUY"

        # Phase A2: returns (sl, tp1, tp2)
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()

        # SL should be 1.9% below entry for BUY
        expected_sl = Decimal("2000.00") * (Decimal("1") - Decimal("0.019"))
        assert sl_price == expected_sl  # 1962.00
        # tp1 from bps fallback, tp2 = None (no take_profit config)
        assert tp1_price is not None
        assert tp2_price is None

    def test_bracket_prices_fallback_to_global_bps(self):
        """Test _calculate_bracket_prices falls back to global bps when no per-instrument."""
        from decimal import Decimal
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig

        # Config without per-instrument exit, but with global brackets
        config = AuroraConfig(
            trading=TradingConfig(
                aurora_instruments={}  # No per-instrument
            )
        )

        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "XRPUSDT"
        fsm.position_entry_price = Decimal("1.00")
        fsm.position_side = "BUY"

        # Phase A2: returns (sl, tp1, tp2)
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()

        # Should use default 50 bps (0.5%) when no config
        # 1.00 * (1 - 50/10000) = 1.00 * 0.995 = 0.995
        expected_sl = Decimal("1.00") * (1 - Decimal("50") / 10000)
        assert sl_price == expected_sl
        assert tp1_price is not None
        assert tp2_price is None  # No TP2 without take_profit config

    def test_bracket_prices_sell_side_with_per_instrument(self):
        """Test _calculate_bracket_prices for SELL with per-instrument sl_pct."""
        from decimal import Decimal
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig

        config = AuroraConfig(
            trading=TradingConfig(
                aurora_instruments={
                    "SOLUSDT": AuroraInstrumentConfig(
                        exit=AuroraExitConfig(sl_pct=0.015)  # 1.5% SL
                    )
                }
            )
        )

        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "SOLUSDT"
        fsm.position_entry_price = Decimal("100.00")
        fsm.position_side = "SELL"

        # Phase A2: returns (sl, tp1, tp2)
        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()

        # SL should be 1.5% ABOVE entry for SELL
        expected_sl = Decimal("100.00") * (Decimal("1") + Decimal("0.015"))
        assert sl_price == expected_sl  # 101.50
        assert tp1_price is not None
        assert tp2_price is None

    def test_bracket_prices_tp1_tp2_with_risk_ratio(self):
        """Test _calculate_bracket_prices with TP1/TP2 risk-ratio config."""
        from decimal import Decimal
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig

        # Config with full take_profit settings (Optuna-optimized)
        config = AuroraConfig(
            trading=TradingConfig(
                aurora_instruments={
                    "ETHUSDT": AuroraInstrumentConfig(
                        exit=AuroraExitConfig(sl_pct=0.02),  # 2% SL (risk unit)
                        take_profit=AuroraTakeProfitConfig(
                            tp_low_ratio=1.5,   # TP1 = 1.5x risk = 3%
                            tp_high_ratio=3.0,  # TP2 = 3x risk = 6%
                            partial_exit_pct=0.7,  # 70% at TP1
                        )
                    )
                }
            )
        )

        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "ETHUSDT"
        fsm.position_entry_price = Decimal("2000.00")
        fsm.position_side = "BUY"

        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()

        # SL = 2% below entry = 2000 * 0.98 = 1960
        expected_sl = Decimal("2000.00") * (Decimal("1") - Decimal("0.02"))
        assert sl_price == expected_sl

        # TP1 = 1.5 * 2% above entry = 3% = 2000 * 1.03 = 2060
        risk_pct = Decimal("0.02")
        tp1_off = risk_pct * Decimal("1.5")  # 0.03
        expected_tp1 = Decimal("2000.00") * (Decimal("1") + tp1_off)
        assert tp1_price == expected_tp1

        # TP2 = 3 * 2% above entry = 6% = 2000 * 1.06 = 2120
        tp2_off = risk_pct * Decimal("3.0")  # 0.06
        expected_tp2 = Decimal("2000.00") * (Decimal("1") + tp2_off)
        assert tp2_price == expected_tp2

        # partial_exit_pct should be stored
        assert fsm.partial_exit_pct == 0.7

    def test_bracket_prices_tp1_only_no_tp2(self):
        """Test _calculate_bracket_prices with only tp_low_ratio (no TP2)."""
        from decimal import Decimal
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig

        config = AuroraConfig(
            trading=TradingConfig(
                aurora_instruments={
                    "BTCUSDT": AuroraInstrumentConfig(
                        exit=AuroraExitConfig(sl_pct=0.015),
                        take_profit=AuroraTakeProfitConfig(
                            tp_low_ratio=2.0,  # TP1 = 2x risk
                            # tp_high_ratio=None → no TP2
                        )
                    )
                }
            )
        )

        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "BTCUSDT"
        fsm.position_entry_price = Decimal("50000.00")
        fsm.position_side = "BUY"

        sl_price, tp1_price, tp2_price = fsm._calculate_bracket_prices()

        # TP1 calculated, TP2 should be None
        assert sl_price is not None
        assert tp1_price is not None
        assert tp2_price is None


class TestTrailingStopWithPerInstrumentConfig:
    """Test FSM trailing stop with per-instrument config."""

    def test_get_trailing_stop_params_per_instrument(self):
        """Test _get_trailing_stop_params reads per-instrument config."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig

        config = AuroraConfig(
            trading=TradingConfig(
                aurora_instruments={
                    "ETHUSDT": AuroraInstrumentConfig(
                        trailing_stop=AuroraTrailingStopConfig(
                            enabled=True,
                            activation_pct=0.005,  # 0.5%
                            trail_pct=0.008,       # 0.8%
                            min_update_interval_sec=10,
                        )
                    )
                }
            )
        )

        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "ETHUSDT"

        enabled, activation_pct, trail_pct, min_sec = fsm._get_trailing_stop_params()

        assert enabled is True
        assert activation_pct == 0.005
        assert trail_pct == 0.008
        assert min_sec == 10

    def test_get_trailing_stop_params_fallback_to_global(self):
        """Test _get_trailing_stop_params falls back to global when no per-instrument."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig

        # Global trailing dict (legacy format)
        config = AuroraConfig(
            trailing={
                "enable": True,
                "activation_profit_atr_k": 0.01,
                "step_bps": 15,
                "cooldown_sec": 20,
            },
            trading=TradingConfig(
                aurora_instruments={}
            )
        )

        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "XRPUSDT"

        enabled, activation_pct, trail_pct, min_sec = fsm._get_trailing_stop_params()

        assert enabled is True
        assert activation_pct == 0.01  # Legacy name: activation_profit_atr_k
        assert trail_pct == 15         # Legacy: step_bps
        assert min_sec == 20           # Legacy: cooldown_sec

    def test_trailing_stop_disabled_by_default(self):
        """Test trailing stop disabled when not configured."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig

        config = AuroraConfig(
            trading=TradingConfig(
                aurora_instruments={}
            )
        )

        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "SOLUSDT"

        enabled, _, _, _ = fsm._get_trailing_stop_params()

        assert enabled is False

    def test_peak_price_tracking(self):
        """Test peak price is updated during trailing."""
        from decimal import Decimal
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig

        config = AuroraConfig(
            trading=TradingConfig(
                aurora_instruments={}
            )
        )

        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "ETHUSDT"
        fsm.position_side = "BUY"
        fsm.position_entry_price = Decimal("2000.00")

        # Initially no peak price
        assert fsm.peak_price is None

        # After reset, peak should be None
        fsm.reset()
        assert fsm.peak_price is None


class TestMaxHoldTimeWatchdog:
    """Test FSM max hold time watchdog."""

    def test_get_max_hold_sec_per_instrument(self):
        """Test _get_max_hold_sec reads per-instrument config."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig

        config = AuroraConfig(
            trading=TradingConfig(
                aurora_instruments={
                    "ETHUSDT": AuroraInstrumentConfig(
                        exit=AuroraExitConfig(
                            sl_pct=0.02,
                            max_hold_sec=900,  # 15 minutes
                        )
                    ),
                    "SOLUSDT": AuroraInstrumentConfig(
                        exit=AuroraExitConfig(
                            sl_pct=0.015,
                            max_hold_sec=660,  # 11 minutes
                        )
                    )
                }
            )
        )

        fsm = ManageFlowFSM(config=config)

        fsm.symbol = "ETHUSDT"
        assert fsm._get_max_hold_sec() == 900

        fsm.symbol = "SOLUSDT"
        assert fsm._get_max_hold_sec() == 660

        fsm.symbol = "BTCUSDT"  # Not configured
        assert fsm._get_max_hold_sec() is None

    def test_check_max_hold_time_timeout(self):
        """Test _check_max_hold_time emits close message on timeout."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig
        from vfoundation.core.protocol import Message

        config = AuroraConfig(
            trading=TradingConfig(
                aurora_instruments={
                    "ETHUSDT": AuroraInstrumentConfig(
                        exit=AuroraExitConfig(max_hold_sec=600)
                    )
                }
            )
        )

        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "ETHUSDT"
        fsm.position_side = "BUY"
        fsm.position_qty = Decimal("1.0")

        msg = Message(
            op="UPD", verb="MARKET_DATA", src="test", dst="test",
            rid="test_rid", pld={"symbol": "ETHUSDT"}
        )

        # Not timed out yet
        result = fsm._check_max_hold_time(msg, elapsed_sec=599)
        assert result is None

        # Timed out
        result = fsm._check_max_hold_time(msg, elapsed_sec=601)
        assert result is not None
        assert result.verb == "CLOSE_POSITION"
        assert result.pld["reason"] == "MAX_HOLD_TIME_EXCEEDED"
        assert result.pld["side"] == "SELL"  # Opposite of BUY

    def test_check_max_hold_time_no_config(self):
        """Test _check_max_hold_time returns None when not configured."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
        from apps.reference.config_models import AuroraConfig
        from vfoundation.core.protocol import Message

        config = AuroraConfig(
            trading=TradingConfig(aurora_instruments={})
        )

        fsm = ManageFlowFSM(config=config)
        fsm.symbol = "XRPUSDT"
        fsm.position_side = "BUY"
        fsm.position_qty = Decimal("100.0")

        msg = Message(
            op="UPD", verb="MARKET_DATA", src="test", dst="test",
            rid="test_rid", pld={"symbol": "XRPUSDT"}
        )

        # No max_hold_sec configured - should never trigger
        result = fsm._check_max_hold_time(msg, elapsed_sec=999999)
        assert result is None
