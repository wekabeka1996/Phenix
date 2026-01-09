"""
Tests for AuroraBuiltinPlugin kill-switch logic.

Verifies:
1. NoopHandler returned when legacy_tick_path_enabled=True
2. Real handler wrapper returned when legacy_tick_path_enabled=False
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.domains.strategies.plugins.aurora_builtin import (
    AuroraBuiltinPlugin,
    _NoopHandler,
    _AuroraHandlerWrapper,
)


class TestAuroraBuiltinKillSwitch:
    """Tests for kill-switch behavior."""

    def test_returns_noop_when_legacy_enabled(self):
        """Plugin should return NoopHandler when legacy_tick_path_enabled=True."""
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    legacy_tick_path_enabled=True,
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
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
        
        assert isinstance(handler, _NoopHandler)

    def test_returns_real_handler_when_legacy_disabled(self):
        """Plugin should return real handler when legacy_tick_path_enabled=False."""
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    legacy_tick_path_enabled=False,
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
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

    def test_returns_noop_when_aurora_config_missing(self):
        """Plugin should return NoopHandler when aurora config is missing."""
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=None,
            )
        )
        fsm = MagicMock()
        plugin = AuroraBuiltinPlugin()
        
        handler = plugin.create_handler(fsm=fsm, config=config)
        
        assert isinstance(handler, _NoopHandler)

    def test_handler_wrapper_registers_listeners(self):
        """Handler wrapper should register event listeners on FSM."""
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    legacy_tick_path_enabled=False,
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
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
        
        # Should have registered two listeners
        assert fsm.listen.call_count == 2
        listen_calls = [call[0][0] for call in fsm.listen.call_args_list]
        assert "EVT:REGIME_DETECTED" in listen_calls
        assert "EVT:FEATURES_CALCULATED" in listen_calls
