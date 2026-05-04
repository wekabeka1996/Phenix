"""
Tests for AuroraBuiltinPlugin.

SCORCHED-EARTH-2026-01-27: Legacy path tests removed.
Migration to AuroraHandler complete. _NoopHandler deleted.

Verifies:
1. Real handler wrapper returned when aurora config present
2. ValueError raised when aurora config missing (fail-closed)
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.config_models import OperationalMode
from apps.reference.domains.strategies.plugins.aurora_builtin import (
    AuroraBuiltinPlugin,
    _AuroraHandlerWrapper,
)


class TestAuroraBuiltinPlugin:
    """Tests for AuroraBuiltinPlugin behavior."""

    # SCORCHED-EARTH-2026-01-27: test_returns_noop_when_legacy_enabled DELETED
    # Legacy path removed. No more _NoopHandler.

    def test_returns_real_handler_when_config_present(self):
        """Plugin should return real handler when aurora config is present."""
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
                        operational_mode=OperationalMode.PARANOID,
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        side_bias_target_ratio=0.72,
                        side_bias_penalty_factor=0.25,
                        side_bias_min_intents=18,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                    ),
                    assets={},
                )
            )
        )
        fsm = MagicMock()
        plugin = AuroraBuiltinPlugin()
        
        handler = plugin.create_handler(fsm=fsm, config=config)
        
        assert isinstance(handler, _AuroraHandlerWrapper)

    def test_raises_when_aurora_config_missing(self):
        """Plugin should raise ValueError when aurora config is missing (fail-closed)."""
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=None,
            )
        )
        fsm = MagicMock()
        plugin = AuroraBuiltinPlugin()
        
        # SCORCHED-EARTH-2026-01-27: Changed from returning _NoopHandler to raising ValueError
        with pytest.raises(ValueError, match="Aurora strategy configuration missing"):
            plugin.create_handler(fsm=fsm, config=config)

    def test_handler_wrapper_registers_listeners(self):
        """Handler wrapper should register event listeners on FSM."""
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
                        operational_mode=OperationalMode.PARANOID,
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        side_bias_target_ratio=0.72,
                        side_bias_penalty_factor=0.25,
                        side_bias_min_intents=18,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                    ),
                    assets={},
                )
            )
        )
        fsm = MagicMock()
        plugin = AuroraBuiltinPlugin()
        
        handler = plugin.create_handler(fsm=fsm, config=config)
        handler.register()
        
        # Current runtime also wires portfolio/exposure/order/rejection events
        # for objective/exposure-aware pre-trade evaluation.
        # - CMD:PROCESS_STRATEGY is primary trigger
        # - EVT:TRADE_EXECUTED for P0-3-FIX position state sync
        assert fsm.listen.call_count == 9
        listen_calls = [call[0][0] for call in fsm.listen.call_args_list]
        assert "EVT:REGIME_DETECTED" in listen_calls
        assert "CMD:PROCESS_STRATEGY" in listen_calls  # T2B-03: Primary trigger
        assert "EVT:FEATURES_CALCULATED" in listen_calls  # Data-only (warmup caching)
        assert "EVT:TRADE_EXECUTED" in listen_calls  # P0-3-FIX: Position state sync
        assert "EVT:SYSTEM_STRESS_STATE_UPDATED" in listen_calls
        assert "EVT:PORTFOLIO_STATE_UPDATED" in listen_calls
        assert "EVT:EXPOSURE_SUMMARY_UPDATED" in listen_calls
        assert "EVT:ORDER_STATE_CHANGED" in listen_calls
        assert "EVT:TRADE_INTENT_REJECTED" in listen_calls
