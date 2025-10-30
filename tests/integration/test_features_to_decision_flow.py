"""
Integration test for Features → DecisionMaking flow.
Tests that DecisionMaking receives features and makes trading decisions.
"""
import unittest
from unittest.mock import patch
from vfoundation.core.fsm_core import FSMCore
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from vfoundation.core.protocol import Message


class TestFeaturesToDecisionFlow(unittest.TestCase):
    """Test that DecisionMaking processes features and makes decisions."""

    def test_decision_making_receives_features_and_makes_decision(self):
        """Test that DecisionMaking receives features, calculates signal score, and makes decision."""
        # Arrange
        fsm = FSMCore()
        config = {
            "decision": {
                "signal_weights": {
                    "obi": 0.6,
                    "tfi": 0.35,
                    "delta_price": 0.05
                },
                "signal_threshold": 0.05
            },
            "tca_prefs": {},
            "risk_budgets": {},
            "instruments": {
                "ETHUSDT": {
                    "step_size": "0.001" # Example step_size
                }
            }
        }

        # Create DecisionMaking domain
        decision_making = DecisionMaking(fsm, config)

        # Mock the emit method to capture events
        emitted_events = []

        def mock_emit(event_name, payload=None, why=None, **kwargs):
            emitted_events.append({
                'event': event_name,
                'payload': payload,
                'why': why
            })

        fsm.emit = mock_emit

        # Act: Simulate features event
        features_msg = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="feature_engineering",
            dst="decision_making",
            pld={
                "symbol": "ETHUSDT",
                "ts": 1000000,
                "features": {
                    "obi": "0.5",  # Strong positive OBI
                    "tfi": "0.3",  # Positive TFI
                    "delta_price": "0.01",  # Small positive delta
                    "absorption": "0.0",
                    "price": "3000.0"
                }
            }
        )

        # Simulate risk event (required for decision)
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
                    "risk_score": 0.2
                }
            }
        )

        # Simulate portfolio event (required for decision)
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="decision_making",
            pld={
                "equity": "10000.0",
                "positions": [],
                "ts": 1000000
            }
        )

        # Emit events in sequence
        decision_making.on_features(features_msg)
        decision_making.on_risk(risk_msg)
        decision_making.on_portfolio(portfolio_msg)

        # Assert: Check that TRADE_INTENT_PROPOSED event was emitted
        trade_events = [e for e in emitted_events if e['event'] == 'EVT:TRADE_INTENT_PROPOSED']
        assert len(trade_events) == 1, f"Expected 1 TRADE_INTENT_PROPOSED event, got {len(trade_events)}"

        event = trade_events[0]
        payload = event['payload']

        # Validate payload structure
        assert payload['symbol'] == 'ETHUSDT'

        print(f"✅ Test passed: DecisionMaking made BUY decision")

    def test_decision_making_with_weak_signal_no_trade(self):
        """Test that DecisionMaking doesn't trade when signal is below threshold."""
        # Arrange
        fsm = FSMCore()
        config = {
            "decision": {
                "signal_weights": {
                    "obi": 0.6,
                    "tfi": 0.35,
                    "delta_price": 0.05
                },
                "signal_threshold": 0.5  # High threshold
            },
            "tca_prefs": {},
            "risk_budgets": {},
            "instruments": {
                "ETHUSDT": {
                    "step_size": "0.001" # Example step_size
                }
            }
        }

        decision_making = DecisionMaking(fsm, config)

        emitted_events = []
        fsm.emit = lambda event_name, payload=None, why=None, **kwargs: \
            emitted_events.append({'event': event_name, 'payload': payload, 'why': why})

        # Act: Simulate weak features
        features_msg = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="feature_engineering",
            dst="decision_making",
            pld={
                "symbol": "ETHUSDT",
                "ts": 1000000,
                "features": {
                    "obi": "0.1",  # Weak OBI
                    "tfi": "0.05",  # Weak TFI
                    "delta_price": "0.001",  # Very small delta
                    "absorption": "0.0",
                    "price": "3000.0"
                }
            }
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
                    "risk_score": 0.2
                }
            }
        )

        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="decision_making",
            pld={
                "equity": "10000.0",
                "positions": [],
                "ts": 1000000
            }
        )

        # Emit events
        decision_making.on_features(features_msg)
        decision_making.on_risk(risk_msg)
        decision_making.on_portfolio(portfolio_msg)

        # Assert: No trade should be made
        trade_events = [e for e in emitted_events if e['event'] == 'EVT:TRADE_INTENT_PROPOSED']
        assert len(trade_events) == 0, f"Expected no trade events, got {len(trade_events)}"

        print("✅ Test passed: DecisionMaking correctly deferred weak signal")