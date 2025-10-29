"""
Integration test for decision_making domain.

Tests that the domain correctly aggregates EVT:FEATURES_CALCULATED,
EVT:RISK_ASSESSMENT_COMPLETED, and EVT:PORTFOLIO_STATE_UPDATED events,
and emits a valid EVT:TRADE_INTENT_PROPOSED event.
"""
import sys
from pathlib import Path
from unittest import mock
import pytest
from vfoundation.core.protocol import Message

# Add paths for imports
apps_root = Path(__file__).parent.parent.parent / "apps"
vfoundation_root = Path(__file__).parent.parent.parent / "vfoundation"
if str(apps_root) not in sys.path:
    sys.path.insert(0, str(apps_root))
if str(vfoundation_root) not in sys.path:
    sys.path.insert(0, str(vfoundation_root))


@pytest.fixture
def mock_config():
    """Mock configuration for decision making tests."""
    return {
        "system": {
            "trade_intent_validity_ms": 30000,
            "kelly": {
                "fraction_cap": 0.85
            }
        },
        "trading": {
            "instruments": {
                "ETHUSDT": {
                    "lot_step": 0.001,
                    "tick_size": 0.01,
                    "min_qty": 0.001,
                    "step_size": "0.001"
                }
            },
            "decision": {
                "payoff_ratio_r": 2.0,
                "signal_weights": {
                    "obi": 0.3,
                    "tfi": 0.4,
                    "absorption": 0.3
                },
                "probability_bounds": {
                    "base": 0.5,
                    "max_prob": 0.8,
                    "min_prob": 0.1
                },
                "signal_threshold": 0.1,
                "p_calibration_version": "calibrated_v1",
                "position_sizing": {
                    "kelly_conservative_factor": 0.1,
                    "kelly_alpha": 0.5,
                    "min_position_size_usd": 10.0,
                    "max_position_size_usd": 1000.0,
                    "default_notional_cap_usd": 1000.0,
                    "liquidity_based_cap_usd": 10000.0
                },
                "calib_metrics_placeholder": "ECE=0.05, Brier=0.08"
            },
            "tca_prefs": {
                "max_slippage_bps": 50.0,
                "max_latency_ms": 5000,
                "maker_preference": "allow"
            },
            "risk_budgets": {
                "trade_cvar95_max_bps": 100.0,
                "session_cvar95_max_bps": 200.0
            },
            "risk_parameters": {
                "cvar_confidence": 0.95,
                "max_leverage": 5.0
            }
        }
    }


@pytest.fixture
def decision_making_domain(mock_config):
    """Create a DecisionMaking domain instance for testing."""
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    
    fsm = FSMCore()
    decision_component = DecisionMaking(fsm=fsm, config=mock_config)
    return decision_component


class FSMCore:
    """Simple FSM core interface for testing (minimal implementation)."""

    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}

    def listen(self, event_name: str, callback) -> None:
        """Register event listener."""
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def emit(self, event_name: str, payload: dict, why: str) -> None:
        """Emit event to listeners."""
        if event_name in self.listeners:
            for callback in self.listeners[event_name]:
                try:
                    callback(Message(
                        op="EVT",
                        verb=event_name.split(":")[1],  # Extract verb from EVT:VERB
                        src="test",
                        dst="any",
                        pld=payload,
                        why=why
                    ))
                except Exception as e:
                    print(f"Error in event listener: {e}")


def test_decision_making_aggregates_events_and_proposes_intent(decision_making_domain, caplog):
    """
    Test that decision_making domain aggregates three input events
    and emits EVT:TRADE_INTENT_PROPOSED with valid trade intent.
    """
    # Create mock listener for the domain's FSM
    mock_listener = mock.Mock()
    decision_making_domain.fsm.listen("EVT:TRADE_INTENT_PROPOSED", mock_listener)

    # Create input messages
    portfolio_msg = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="position_tracking",
        dst="decision_making",
        pld={
            "ts": 1693526400000,
            "equity": 10000.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "positions": []  # No existing positions to allow new trade
        }
    )

    risk_msg = Message(
        op="EVT",
        verb="RISK_ASSESSMENT_COMPLETED",
        src="risk_strategy",
        dst="decision_making",
        pld={
            "ts": 1693526400000,
            "symbol": "ETHUSDT",
            "risk_parameters": {
                "is_trading_allowed": True
            }
        }
    )

    features_msg = Message(
        op="EVT",
        verb="FEATURES_CALCULATED",
        src="analyzer",
        dst="decision_making",
        pld={
            "ts": 1693526400000,
            "symbol": "ETHUSDT",
            "features": {
                "obi": 0.02,
                "tfi": 0.15,
                "delta_price": 100.0,
                "absorption": 0.8,
                "price": 3000.0
            }
        }
    )

    # Emit all three input events to simulate complete information for decision making
    # Act
    decision_making_domain.on_portfolio(portfolio_msg)
    decision_making_domain.on_risk(risk_msg)
    decision_making_domain.on_features(features_msg)  # Features event triggers the decision

    # Assert
    mock_listener.assert_called_once()
    
    # Further assertions on the emitted event payload
    emitted_event = mock_listener.call_args[0][0]
    assert emitted_event.op == "EVT"
    assert emitted_event.verb == "TRADE_INTENT_PROPOSED"
    assert emitted_event.pld["instrument"] == "ETHUSDT"
    assert emitted_event.pld["side"] == "buy"
