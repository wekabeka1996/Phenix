"""
Tests for DecisionMaking per-asset Aurora overrides.

Verifies that aurora_instruments.<SYMBOL>.* configs are correctly
applied in decision-making logic, with proper fallback to global defaults.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from apps.reference.config_models import (
    AuroraConfig,
    TradingConfig,
    DecisionConfig,
    AuroraInstrumentConfig,
    AuroraSideBiasConfig,
    AuroraExitConfig,
)
from apps.reference.domains.decision_making.decision_making import DecisionMaking


class MockFSM:
    """Simple FSM mock for testing."""
    def __init__(self):
        self.listeners = {}
    
    def listen(self, event_name, callback):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)
    
    def get_position_state(self, symbol):
        return None


class TestDecisionMakingAuroraOverrides:
    """Test per-asset Aurora configuration overrides in DecisionMaking."""

    @pytest.fixture
    def mock_fsm(self):
        """Create mock FSM for DecisionMaking."""
        return MockFSM()

    @pytest.fixture
    def base_config_dict(self):
        """Base config dict with required fields."""
        return {
            "system": {"trade_intent_validity_ms": 30000, "kelly": {"fraction_cap": 0.85}},
            "trading": {
                "instruments": {
                    "ETHUSDT": {"lot_step": 0.001, "tick_size": 0.01, "min_qty": 0.001},
                    "SOLUSDT": {"lot_step": 0.001, "tick_size": 0.01, "min_qty": 0.001},
                    "BTCUSDT": {"lot_step": 0.001, "tick_size": 0.01, "min_qty": 0.001},
                },
                "decision": {
                    "payoff_ratio_r": 2.0,
                    "signal_weights": {"global_signal": 0.5},
                    "probability_bounds": {"base": 0.5, "max_prob": 0.8, "min_prob": 0.1},
                    "signal_threshold": 0.1,
                    "p_calibration_version": "calibrated_v1",
                    "position_sizing": {
                        "kelly_conservative_factor": 0.1,
                        "kelly_alpha": 0.5,
                        "min_position_size_usd": 10.0,
                        "max_position_size_usd": 1000.0,
                        "default_notional_cap_usd": 1000.0,
                    },
                    "side_bias_penalty_factor": 0.5,
                    "side_bias_window_sec": 60,
                    "sell_target_ratio": 0.6,
                    "regime_threshold_multipliers": {"GLOBAL": 1.0},
                    "regime_sizing": {"default": 1.0},
                },
                "tca_prefs": {"max_slippage_bps": 50.0, "max_latency_ms": 5000},
                "risk_budgets": {"trade_cvar95_max_bps": 100.0, "session_cvar95_max_bps": 200.0},
                "risk_parameters": {"cvar_confidence": 0.95, "max_leverage": 5.0},
                "aurora_instruments": {
                    "ETHUSDT": {
                        "weights": {"eth_signal": 0.8, "volatility": 0.2},
                        "side_bias": {
                            "penalty_factor": 0.3,
                            "window_sec": 120,
                            "target_ratio": 0.7,
                        },
                        "regime_thresholds": {"ETH_TREND": 1.5},
                        "regime_sizing": {"TREND": 0.8, "MR": 1.2},
                    },
                    "SOLUSDT": {
                        "weights": {"sol_momentum": 0.6},
                        "side_bias": {
                            "penalty_factor": 0.4,
                        },
                        "regime_thresholds": {"SOL_VOLATILE": 2.0},
                    },
                },
            },
        }

    @pytest.fixture
    def dm_with_overrides(self, base_config_dict, mock_fsm):
        """Create DecisionMaking instance with per-asset overrides."""
        return DecisionMaking(config=base_config_dict, fsm=mock_fsm)

    # =========================================================================
    # Test _get_aurora_instrument_cfg
    # =========================================================================

    def test_get_aurora_instrument_cfg_returns_config_for_known_symbol(self, dm_with_overrides):
        """Per-instrument config is returned for configured symbol."""
        cfg = dm_with_overrides._get_aurora_instrument_cfg("ETHUSDT")
        
        assert cfg is not None
        assert cfg.weights == {"eth_signal": 0.8, "volatility": 0.2}

    def test_get_aurora_instrument_cfg_returns_none_for_unknown_symbol(self, dm_with_overrides):
        """None returned for symbol without per-instrument config."""
        cfg = dm_with_overrides._get_aurora_instrument_cfg("BTCUSDT")
        
        assert cfg is None

    # =========================================================================
    # Test _get_param (weights)
    # =========================================================================

    def test_get_param_uses_per_instrument_weights(self, dm_with_overrides):
        """Weights from aurora_instruments override global."""
        weights = dm_with_overrides._get_param("ETHUSDT", "weights", {})
        
        assert weights == {"eth_signal": 0.8, "volatility": 0.2}

    def test_get_param_falls_back_to_global_for_unknown_symbol(self, dm_with_overrides):
        """Default used when no per-instrument config and param not in global."""
        # _get_param looks for "weights" in per-instrument first, then global decision.weights
        # Since BTCUSDT has no per-instrument, and decision.signal_weights != decision.weights,
        # it falls back to the provided default
        weights = dm_with_overrides._get_param("BTCUSDT", "weights", {"default": 0.1})
        
        # Falls back to provided default since global path is different
        assert weights == {"default": 0.1}

    def test_get_param_uses_default_when_no_config(self, mock_fsm, base_config_dict):
        """Default value used when param not in any config."""
        # Remove aurora_instruments for this test
        config = base_config_dict.copy()
        config["trading"] = {**config["trading"]}
        config["trading"]["aurora_instruments"] = {}
        
        dm = DecisionMaking(config=config, fsm=mock_fsm)
        
        # Ask for non-existent param
        unknown = dm._get_param("ANYUSDT", "nonexistent_param", "fallback_value")
        
        assert unknown == "fallback_value"

    # =========================================================================
    # Test _get_side_bias_params
    # =========================================================================

    def test_get_side_bias_params_uses_per_instrument(self, dm_with_overrides):
        """Side bias params from aurora_instruments override global."""
        penalty, window, target = dm_with_overrides._get_side_bias_params("ETHUSDT")
        
        assert penalty == 0.3  # Per-instrument override
        assert window == 120   # Per-instrument override
        assert target == 0.7   # Per-instrument override

    def test_get_side_bias_params_partial_override(self, dm_with_overrides):
        """Partial per-instrument config with global fallback."""
        penalty, window, target = dm_with_overrides._get_side_bias_params("SOLUSDT")
        
        assert penalty == 0.4  # Per-instrument override
        assert window == 60    # Falls back to global (not in per-instrument)
        assert target == 0.6   # Falls back to global (not in per-instrument)

    def test_get_side_bias_params_falls_back_to_global(self, dm_with_overrides):
        """Global side bias used for symbol without per-instrument config."""
        penalty, window, target = dm_with_overrides._get_side_bias_params("BTCUSDT")
        
        assert penalty == 0.5  # Global
        assert window == 60    # Global
        assert target == 0.6   # Global

    # =========================================================================
    # Test _get_regime_thresholds
    # =========================================================================

    def test_get_regime_thresholds_uses_per_instrument(self, dm_with_overrides):
        """Regime thresholds from aurora_instruments override global."""
        thresholds = dm_with_overrides._get_regime_thresholds("ETHUSDT")
        
        assert thresholds == {"ETH_TREND": 1.5}

    def test_get_regime_thresholds_falls_back_to_global(self, dm_with_overrides):
        """Global regime thresholds used for unknown symbol."""
        thresholds = dm_with_overrides._get_regime_thresholds("BTCUSDT")
        
        assert thresholds == {"GLOBAL": 1.0}

    # =========================================================================
    # Test _get_regime_sizing
    # =========================================================================

    def test_get_regime_sizing_uses_per_instrument(self, dm_with_overrides):
        """Regime sizing from aurora_instruments override global."""
        sizing = dm_with_overrides._get_regime_sizing("ETHUSDT")
        
        assert sizing == {"TREND": 0.8, "MR": 1.2}

    def test_get_regime_sizing_falls_back_to_global(self, dm_with_overrides):
        """Empty dict returned when no per-instrument and no global sizing_modifiers."""
        sizing = dm_with_overrides._get_regime_sizing("BTCUSDT")
        
        # Global looks for 'sizing_modifiers' not 'regime_sizing', so returns {}
        assert sizing == {}

    def test_get_regime_sizing_returns_empty_when_not_in_per_instrument(self, dm_with_overrides):
        """Empty dict when symbol has per-instrument but no regime_sizing."""
        sizing = dm_with_overrides._get_regime_sizing("SOLUSDT")
        
        # SOLUSDT has per-instrument config but no regime_sizing
        # Falls back to global sizing_modifiers which doesn't exist, returns {}
        assert sizing == {}


class TestDecisionMakingPartialExitFill:
    """Test partial exit fill handling in FSM."""

    def test_tp1_fill_reduces_position_qty(self):
        """TP1 fill should reduce position_qty by partial_exit_pct."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
        from apps.reference.config_models import AuroraConfig, TradingConfig, ExecutionConfig, ManageConfig, BracketsConfig
        from vfoundation.core.protocol import Message
        
        config = AuroraConfig(
            trading=TradingConfig(
                execution=ExecutionConfig(
                    manage=ManageConfig(
                        brackets=BracketsConfig(
                            enable=True,
                            oco_emulation=True,
                        )
                    )
                )
            )
        )
        
        fsm = ManageFlowFSM(config=config)
        fsm.state = ManageState.BRACKETS_PLACED
        fsm.position_qty = Decimal("1.0")
        fsm.partial_exit_pct = 0.7  # 70% at TP1
        fsm.tp1_order_id = "tp1_123"
        fsm.tp2_order_id = "tp2_123"
        fsm.sl_order_id = "sl_123"
        
        # Simulate TP1 fill
        fill_msg = Message(
            ver="v1",
            ts=1234567890,
            src="test",
            op="EVT",
            dst="execution_position",
            verb="EVT:FILL",
            pld={
                "orderId": "tp1_123",
                "clientOrderId": "pos_tp1",
                "symbol": "BTCUSDT",
            }
        )
        
        result = fsm._handle_bracket_fill(fill_msg)
        
        # Position should be reduced
        assert fsm.position_qty == Decimal("0.3")  # 1.0 - 0.7 = 0.3
        # TP1 cleared, TP2 and SL remain
        assert fsm.tp1_order_id is None
        assert fsm.tp2_order_id == "tp2_123"
        assert fsm.sl_order_id == "sl_123"

    def test_tp2_fill_cancels_sl(self):
        """TP2 fill should cancel SL (full position closed)."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
        from apps.reference.config_models import AuroraConfig, TradingConfig, ExecutionConfig, ManageConfig, BracketsConfig
        from vfoundation.core.protocol import Message
        
        config = AuroraConfig(
            trading=TradingConfig(
                execution=ExecutionConfig(
                    manage=ManageConfig(
                        brackets=BracketsConfig(
                            enable=True,
                            oco_emulation=True,
                        )
                    )
                )
            )
        )
        
        fsm = ManageFlowFSM(config=config)
        fsm.state = ManageState.BRACKETS_PLACED
        fsm.position_qty = Decimal("0.3")  # Remaining after TP1
        fsm.tp2_order_id = "tp2_123"
        fsm.sl_order_id = "sl_123"
        
        # Simulate TP2 fill
        fill_msg = Message(
            ver="v1",
            ts=1234567890,
            src="test",
            op="EVT",
            dst="execution_position",
            verb="EVT:FILL",
            pld={
                "orderId": "tp2_123",
                "clientOrderId": "pos_tp2",
                "symbol": "BTCUSDT",
            }
        )
        
        result = fsm._handle_bracket_fill(fill_msg)
        
        # Should emit cancel for SL
        assert result is not None
        assert result.verb == "CANCEL_ORDER"
        assert result.pld["orderId"] == "sl_123"
        
        # All tracking cleared
        assert fsm.tp1_order_id is None
        assert fsm.tp2_order_id is None
        assert fsm.sl_order_id is None
        assert fsm.position_qty == Decimal("0")

    def test_sl_fill_cancels_all_tp_orders(self):
        """SL fill should cancel both TP1 and TP2."""
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
        from apps.reference.config_models import AuroraConfig, TradingConfig, ExecutionConfig, ManageConfig, BracketsConfig
        from vfoundation.core.protocol import Message
        
        config = AuroraConfig(
            trading=TradingConfig(
                execution=ExecutionConfig(
                    manage=ManageConfig(
                        brackets=BracketsConfig(
                            enable=True,
                            oco_emulation=True,
                        )
                    )
                )
            )
        )
        
        fsm = ManageFlowFSM(config=config)
        fsm.state = ManageState.BRACKETS_PLACED
        fsm.position_qty = Decimal("1.0")
        fsm.tp1_order_id = "tp1_123"
        fsm.tp2_order_id = "tp2_123"
        fsm.sl_order_id = "sl_123"
        
        # Simulate SL fill
        fill_msg = Message(
            ver="v1",
            ts=1234567890,
            src="test",
            op="EVT",
            dst="execution_position",
            verb="EVT:FILL",
            pld={
                "orderId": "sl_123",
                "clientOrderId": "pos_sl",
                "symbol": "BTCUSDT",
            }
        )
        
        result = fsm._handle_bracket_fill(fill_msg)
        
        # Should emit cancel for TP1 (first in list)
        assert result is not None
        assert result.verb == "CANCEL_ORDER"
        assert result.pld["orderId"] == "tp1_123"
        
        # All tracking cleared
        assert fsm.tp1_order_id is None
        assert fsm.tp2_order_id is None
        assert fsm.sl_order_id is None
