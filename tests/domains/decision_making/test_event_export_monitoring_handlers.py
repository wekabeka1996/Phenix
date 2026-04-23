import pytest
from unittest.mock import MagicMock
from vfoundation.core.protocol import Message
from apps.reference.domains.decision_making.event_handlers import DMEventHandlers
from apps.reference.config_contract import ConfigContractError


class DummyConfig:
    pass


class TestEventExportMonitoringHandlers:

    @pytest.fixture
    def mock_fsm(self):
        return MagicMock()

    @pytest.fixture
    def handlers(self, mock_fsm):
        clock_mock = MagicMock()
        dlog_mock = MagicMock()
        alpha_reg_mock = MagicMock()

        # We simulate that the alpha model calculculator works and returns some dummy scores
        class DummyScore:
            model_name = "test_alpha"

            def dict(self):
                return {"score": 0.5, "model": "test_alpha"}

        alpha_reg_mock.calculate_all_alpha.return_value = [DummyScore()]

        h = DMEventHandlers(
            fsm=mock_fsm,
            clock=clock_mock,
            config=DummyConfig(),
            symbol_states={},
            per_symbol_regimes={},
            shared_state={},
            dlog=dlog_mock,
            alpha_registry=alpha_reg_mock,
            handle_regime_flip_fn=lambda x, y: None,
            record_blocked_fn=lambda x: None,
            arming_require_regime_warmup=True,
            behavior_enabled=False,
            behavior_state={},
            logger=MagicMock()
        )
        return h

    def test_alpha_scores_aggregated_export(self, handlers, mock_fsm):
        """
        Prove that when on_features receives valid capabilities,
        it conditionally emits EVT:ALPHA_SCORES_AGGREGATED.
        """
        payload = {
            "symbol": "BTCUSDT",
            "features": {"price": 50000.0}
        }
        event = Message(
            name="EVT:FEATURES_CALCULATED",
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="feature_engineering",
            dst="decision_making",
            pld=payload
        )

        handlers.on_features(event)

        # Verify emit was called with ALPHA_SCORES_AGGREGATED
        found = False
        for call_args, call_kwargs in mock_fsm.emit.call_args_list:
            if call_args[0] == "EVT:ALPHA_SCORES_AGGREGATED":
                found = True
                assert call_kwargs["payload"]["symbol"] == "BTCUSDT"
                assert len(call_kwargs["payload"]["scores"]) == 1
        assert found, "EVT:ALPHA_SCORES_AGGREGATED was not emitted"

    def test_tick_features_are_rejected_by_bar_only_guard(self, handlers, mock_fsm):
        """
        Prove that tick-level features do not flow through the bar-only DM handler.
        """
        handlers.symbol_states["BTCUSDT"] = {}
        handlers._clock.now_ms.return_value = 1_700_000_000_000
        payload = {
            "symbol": "BTCUSDT",
            "tf_sec": 0,
            "features": {"price": 50000.0},
        }
        event = Message(
            name="EVT:TICK_FEATURES_CALCULATED",
            op="EVT",
            verb="TICK_FEATURES_CALCULATED",
            src="feature_engineering",
            dst="decision_making",
            pld=payload,
        )

        handlers.on_features(event)

        handlers.alpha_registry.calculate_all_alpha.assert_not_called()
        assert mock_fsm.emit.call_count == 0

    def test_decision_blocked_export(self, handlers, mock_fsm):
        """
        Prove that EVT:DECISION_BLOCKED is exported upon ConfigContractError.
        """
        # Force a ConfigContractError inside on_features by making the alpha_registry raise it
        handlers.alpha_registry.calculate_all_alpha.side_effect = ConfigContractError(
            symbol="BTCUSDT", why="test error", path="test.path"
        )

        payload = {
            "symbol": "BTCUSDT",
            "features": {"price": 40000.0}
        }
        event = Message(
            name="EVT:FEATURES_CALCULATED",
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="feature_engineering",
            dst="decision_making",
            pld=payload
        )

        handlers.on_features(event)

        found = False
        for call_args, call_kwargs in mock_fsm.emit.call_args_list:
            if len(call_args) > 0 and call_args[0] == "EVT:DECISION_BLOCKED":
                found = True
                payload_dict = call_args[1] if len(
                    call_args) > 1 else call_kwargs.get("payload", {})
                assert payload_dict["symbol"] == "BTCUSDT"
                assert "test error" in payload_dict["why"]
        assert found, "EVT:DECISION_BLOCKED was not emitted"
