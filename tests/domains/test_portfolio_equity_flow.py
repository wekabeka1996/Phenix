"""
Test for portfolio equity flow between domains.

Tests that equity values (equity_free_usdt, equity_cross_usdt) are correctly
computed in PositionTracking and used in DecisionMaking without zero-overwrite.
"""

import sys
from pathlib import Path

# Add paths for imports FIRST
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

print("DEBUG sys.path:", sys.path[:5])  # Debug


def test_position_tracking_emits_equity_fields():
    """
    Test that PositionTracking emits equity_free_usdt and equity_cross_usdt fields.
    """
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    # Mock FSM
    class MockFSM:
        def __init__(self):
            self.events = []

        def emit(self, event_name, payload, why):
            self.events.append((event_name, payload, why))

        def listen(self, *args):
            pass

    fsm = MockFSM()
    config = {
        "position_limits": {"max_positions": 10},
        "risk_limits": {"max_drawdown": 0.1},
    }
    position_tracker = PositionTracking(fsm=fsm, config=config)
    position_tracker.start()

    # Simulate balance update with USDT
    from vfoundation.core.protocol import Message

    balance_payload = {
        "assets": [
            {
                "asset": "USDT",
                "balance": "10000.0",
                "crossWalletBalance": "9500.0",
                "crossUnPnl": "500.0",
                "updateTime": 1693526400000,
            }
        ]
    }

    event = Message(
        op="EVT",
        verb="BALANCE_UPDATE_RECEIVED",
        src="test",
        dst="position_tracking",
        pld=balance_payload,
    )
    position_tracker.on_balance_update(event)

    # Verify portfolio update was emitted (should be 2 events: initial + balance update)
    assert len(fsm.events) == 2

    # Check the balance update event (second one)
    event_name, payload, why = fsm.events[1]
    assert event_name == "EVT:PORTFOLIO_STATE_UPDATED"
    assert "equity_free_usdt" in payload
    assert "equity_cross_usdt" in payload
    assert "equity_ts" in payload
    assert payload["equity_free_usdt"] == "10000.0"
    assert payload["equity_cross_usdt"] == "10000.0"  # 9500 + 500
    assert payload["equity_ts"] == 1693526400000


def test_decision_making_caches_equity():
    """
    Test that DecisionMaking's PortfolioProvider retains non-zero equity and doesn't overwrite with zero.
    """
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    # Mock FSM
    class MockFSM:
        def listen(self, *args):
            pass

    fsm = MockFSM()
    config = {
        "trading": {
            "instruments": {"BTCUSDT": {"step_size": "0.001"}},
            "decision": {"signal_weights": {"test": 1.0}, "signal_threshold": 0.1},
            "tca_prefs": {},
            "risk_budgets": {},
            "risk_parameters": {},
        }
    }
    decision_component = DecisionMaking(fsm=fsm, config=config)

    # First portfolio update with equity
    from vfoundation.core.protocol import Message

    portfolio_payload_1 = {
        "equity_free_usdt": "10000.0",
        "equity_total_usdt": "10500.0",
    }
    msg1 = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="test",
        dst="test",
        pld=portfolio_payload_1,
    )
    decision_component.on_portfolio(msg1)

    # Verify cached via portfolio_provider
    snapshot1 = decision_component.portfolio_provider.get_snapshot(
        prefer_nonzero=True)
    assert float(snapshot1.equity_free_usdt) == 10000.0
    assert float(snapshot1.equity_total_usdt) == 10500.0

    # Second update with zero (should not overwrite cached non-zero)
    portfolio_payload_2 = {
        "equity_free_usdt": "0.0", "equity_total_usdt": "0.0"}
    msg2 = Message(
        op="EVT",
        verb="PORTFOLIO_STATE_UPDATED",
        src="test",
        dst="test",
        pld=portfolio_payload_2,
    )
    decision_component.on_portfolio(msg2)

    # Verify cache preserved when prefer_nonzero=True
    snapshot2 = decision_component.portfolio_provider.get_snapshot(
        prefer_nonzero=True)
    assert float(snapshot2.equity_free_usdt) == 10000.0
    assert float(snapshot2.equity_total_usdt) == 10500.0


if __name__ == "__main__":
    test_position_tracking_emits_equity_fields()
    test_decision_making_caches_equity()
    print("✅ All tests passed!")
