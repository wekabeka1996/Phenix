"""
Integration test for Features -> DecisionMaking flow.
"""

from pathlib import Path

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message


class TestFeaturesToDecisionFlow:
    """Test that DecisionMaking processes features and stays fail-closed."""

    def test_decision_making_receives_features_and_stays_silent(self):
        """Current decision flow does not emit without the full context chain."""
        fsm = FSMCore()
        config = ConfigLoader(Path("config/aurora")).load_config()
        decision_making = DecisionMaking(fsm, config)

        emitted_events = []

        def mock_emit(event_name, payload=None, why=None, **kwargs):
            emitted_events.append({
                "event": event_name,
                "payload": payload,
                "why": why,
            })

        fsm.emit = mock_emit

        features_msg = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="feature_engineering",
            dst="decision_making",
            pld={
                "symbol": "ETHUSDT",
                "ts": 1000000,
                "features": {
                    "obi": "0.5",
                    "tfi": "0.3",
                    "delta_price": "0.01",
                    "absorption": "0.0",
                    "price": "3000.0",
                },
            },
        )

        risk_msg = Message(
            op="EVT",
            verb="RISK_ASSESSMENT_COMPLETED",
            src="risk_management",
            dst="decision_making",
            pld={
                "symbol": "ETHUSDT",
                "ts": 1000000,
                "risk_parameters": {
                    "is_trading_allowed": True,
                    "risk_score": 0.2,
                },
            },
        )

        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="decision_making",
            pld={
                "equity": "10000.0",
                "positions": [],
                "ts": 1000000,
            },
        )

        decision_making.on_features(features_msg)
        decision_making.on_risk(risk_msg)
        decision_making.on_portfolio(portfolio_msg)

        trade_events = [
            e for e in emitted_events if e["event"] == "EVT:TRADE_INTENT_PROPOSED"
        ]
        assert trade_events == []
        assert emitted_events == []

    def test_decision_making_with_weak_signal_no_trade(self):
        """Weak signals still do not produce trade intents."""
        fsm = FSMCore()
        config = ConfigLoader(Path("config/aurora")).load_config()
        decision_making = DecisionMaking(fsm, config)

        emitted_events = []
        fsm.emit = lambda event_name, payload=None, why=None, **kwargs: emitted_events.append(
            {"event": event_name, "payload": payload, "why": why}
        )

        features_msg = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="feature_engineering",
            dst="decision_making",
            pld={
                "symbol": "ETHUSDT",
                "ts": 1000000,
                "features": {
                    "obi": "0.1",
                    "tfi": "0.05",
                    "delta_price": "0.001",
                    "absorption": "0.0",
                    "price": "3000.0",
                },
            },
        )

        risk_msg = Message(
            op="EVT",
            verb="RISK_ASSESSMENT_COMPLETED",
            src="risk_management",
            dst="decision_making",
            pld={
                "symbol": "ETHUSDT",
                "ts": 1000000,
                "risk_parameters": {
                    "is_trading_allowed": True,
                    "risk_score": 0.2,
                },
            },
        )

        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="decision_making",
            pld={
                "equity": "10000.0",
                "positions": [],
                "ts": 1000000,
            },
        )

        decision_making.on_features(features_msg)
        decision_making.on_risk(risk_msg)
        decision_making.on_portfolio(portfolio_msg)

        trade_events = [
            e for e in emitted_events if e["event"] == "EVT:TRADE_INTENT_PROPOSED"
        ]
        assert trade_events == []
