"""
Integration test for risk_management domain.

Tests that the domain correctly subscribes to EVT:FEATURES_CALCULATED,
processes it, and emits a valid EVT:RISK_ASSESSMENT_COMPLETED event.
"""
from unittest import mock
import pytest
from vfoundation.core.protocol import Message


@pytest.fixture
def mock_config():
    """Mock configuration for risk management tests."""
    return {
        'risk_limits': {'max_drawdown': 0.1, 'max_leverage': 5.0},
        'position_limits': {'max_positions': 10}
    }


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


def test_risk_management_consumes_features_and_emits_assessment(mock_config):
    """
    Test that risk_management domain consumes EVT:FEATURES_CALCULATED
    and emits EVT:RISK_ASSESSMENT_COMPLETED with calculated risk parameters.
    """
    # Step 1: Initialization
    fsm = FSMCore()
    mock_listener = mock.Mock()
    fsm.listen("EVT:RISK_ASSESSMENT_COMPLETED", mock_listener)

    # Step 2: Start component (will fail until RiskManagement is implemented)
    # This import will raise ModuleNotFoundError until the component exists
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from apps.reference.domains.risk_management.risk_management import RiskManagement

    risk_component = RiskManagement(fsm=fsm, config=mock_config)
    risk_component.start()

    # Step 3: Simulate input event
    fake_features_payload = {
        "ts": 1693526400000,  # 2023-09-01 00:00:00 UTC in milliseconds
        "symbol": "BTCUSDT",
        "features": {
            "obi": 0.1,
            "tfi": -0.05,
            "delta_price": 10.5,
            "absorption": 0.8
        }
    }

    fsm.emit(
        "EVT:FEATURES_CALCULATED",
        payload=fake_features_payload,
        why="Simulated features for risk management test."
    )

    # Step 4: Verify result
    mock_listener.assert_called_once()

    # Get the event that was passed to the listener
    call_args = mock_listener.call_args
    fsm_event = call_args[0][0]  # First positional argument

    # Verify the payload structure matches risk_assessment_v1.json schema
    assert isinstance(fsm_event.pld, dict)
    assert "symbol" in fsm_event.pld
    assert isinstance(fsm_event.pld["symbol"], str)
    assert "ts" in fsm_event.pld
    assert isinstance(fsm_event.pld["ts"], int)
    assert "risk_parameters" in fsm_event.pld
    assert isinstance(fsm_event.pld["risk_parameters"], dict)

    # Verify required risk parameters are present
    risk_params = fsm_event.pld["risk_parameters"]
    required_params = ["is_trading_allowed"]
    for param in required_params:
        assert param in risk_params
        assert isinstance(risk_params[param], bool)