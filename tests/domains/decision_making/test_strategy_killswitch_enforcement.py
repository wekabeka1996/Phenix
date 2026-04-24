import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from apps.reference.domains.strategies.plugins.aurora_builtin import AuroraBuiltinPlugin, _DisabledAuroraHandlerWrapper, _AuroraHandlerWrapper
from apps.reference.config_contract import ConfigContractError
from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler


class TestStrategyKillswitchEnforcement:
    def _make_config(self, enabled: bool, assignments: dict[str, list[str]] = None):
        """Helper to mock AuroraConfig and StrategiesRegistry configs."""
        config = MagicMock()
        
        # Strategies block
        config.strategies = MagicMock()
        config.strategies.aurora = SimpleNamespace(
            enabled=enabled,
            timeframe_sec=300,
            decision=SimpleNamespace(
                operational_mode="testnet",
                signal_threshold="0.1",
                side_bias_window_sec="60",
                side_bias_target_ratio="0.5",
                side_bias_penalty_factor="0.5",
                side_bias_min_intents="1",
                regime_threshold_multipliers={"DEFAULT": 1.0},
                signals=SimpleNamespace(normalize_signals_mode="signed_v2"),
                exit=SimpleNamespace(time_exit_enabled=False, signal_exit_enabled=False),
            ),
        )

        # Registry assignments
        if assignments is not None:
            config.strategies_registry = SimpleNamespace(
                assignments=assignments
            )
        else:
            config.strategies_registry = None

        return config

    def test_aurora_disabled_prevents_plugin_activation(self):
        """1. test_aurora_disabled_prevents_plugin_activation: 
        Proves creating the handler returns the offline wrapper when disabled (with no conflicting assignments).
        """
        config = self._make_config(enabled=False, assignments={"BTCUSDT": ["other_strat"]})
        plugin = AuroraBuiltinPlugin()
        fsm_mock = MagicMock()
        
        wrapper = plugin.create_handler(fsm=fsm_mock, config=config)
        
        # Verify it returns the disconnected facade
        assert isinstance(wrapper, _DisabledAuroraHandlerWrapper)
        
        # Verify attempt to register does literally nothing (fsm not attached)
        wrapper.register()
        fsm_mock.listen.assert_not_called()

    def test_aurora_disabled_with_assignments_fails_closed(self):
        """2. test_aurora_disabled_with_assignments_fails_closed:
        Proves strict failure if operator sets enabled=False but leaves assignments mapped to aurora.
        """
        config = self._make_config(enabled=False, assignments={"BTCUSDT": ["aurora", "mean_reversion"]})
        plugin = AuroraBuiltinPlugin()
        fsm_mock = MagicMock()
        
        with pytest.raises(ConfigContractError) as exc:
            plugin.create_handler(fsm=fsm_mock, config=config)
            
        assert "globally disabled (enabled=False)" in str(exc.value)
        assert "still assigned to symbols" in str(exc.value)

    def test_aurora_disabled_prevents_handler_symbol_enablement(self):
        """3. test_aurora_disabled_prevents_handler_symbol_enablement:
        Proves that even if the raw AuroraHandler is instantiated manually, it rejects processing.
        """
        config = self._make_config(enabled=False)
        fsm_mock = MagicMock()
        
        # Instantiate raw handler (bypassing the wrapper plugin completely)
        def emit_fn(evt, pld): pass
        handler = AuroraHandler(config=config, emit_fn=emit_fn)
        
        # Prove tracking internal state correctly parses enabled flag
        assert handler._is_enabled is False
        
        # Prove on_process_strategy fails closed and refuses to execute
        process_cmd = {"symbol": "BTCUSDT", "tf_sec": 300, "bar_close_ts": 123, "rid": "rid"}
        with patch("apps.reference.domains.strategies.runtimes.aurora.handler.write_trade_intent_rejected") as mock_write:
            handler.on_process_strategy(process_cmd)
        
        # Verify rejection went out cleanly
        mock_write.assert_called_once()
        assert mock_write.call_args.kwargs["reason_code"] == "STRATEGY_DISABLED"

    def test_aurora_enabled_normal_path_still_works(self):
        """4. test_aurora_enabled_normal_path_still_works:
        Proves enabled=True instantiates normally and connects event listeners.
        """
        config = self._make_config(enabled=True, assignments={"BTCUSDT": ["aurora"]})
        plugin = AuroraBuiltinPlugin()
        fsm_mock = MagicMock()
        
        wrapper = plugin.create_handler(fsm=fsm_mock, config=config)
        
        # Verify normal wrapper returned
        assert isinstance(wrapper, _AuroraHandlerWrapper)
        assert isinstance(wrapper.handler, AuroraHandler)
        assert wrapper.handler._is_enabled is True
        
        # Verify listeners are established
        wrapper.register()
        fsm_mock.listen.assert_any_call("CMD:PROCESS_STRATEGY", wrapper._on_process_strategy)

    def test_no_decorative_flag_behavior_remains(self):
        """5. test_no_decorative_flag_behavior_remains:
        Ensures the enabled field acts as a functional switch dictating processing and memory layout boundaries.
        """
        # Part A - completely offline when config is correct
        config_off = self._make_config(enabled=False, assignments={})
        plugin_off = AuroraBuiltinPlugin()
        wrapper_off = plugin_off.create_handler(fsm=MagicMock(), config=config_off)
        assert isinstance(wrapper_off, _DisabledAuroraHandlerWrapper)
        
        # Part B - explodes when contradictory
        config_err = self._make_config(enabled=False, assignments={"SOLUSDT": ["aurora"]})
        with pytest.raises(ConfigContractError):
            plugin_off.create_handler(fsm=MagicMock(), config=config_err)
