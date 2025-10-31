"""
Tests for PositionTracking state synchronization logic.
"""
import sys
import os
from decimal import Decimal
import pytest
from vfoundation.core.protocol import Message

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from apps.reference.domains.position_tracking.position_tracking import PositionTracking

class FSMCore:
    """Mock FSM core for testing."""
    def __init__(self):
        self.emitted_events = []
    
    def listen(self, event_name: str, callback):
        pass
    
    def emit(self, event_name: str, payload: dict, why: str):
        self.emitted_events.append({
            "event_name": event_name,
            "payload": payload,
            "why": why
        })

@pytest.fixture
def tracker():
    """Creates a PositionTracking instance for testing."""
    fsm = FSMCore()
    return PositionTracking(config={}, fsm=fsm)

def create_trade_event(symbol, side, quantity, price):
    """Helper to create a trade event."""
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="test",
        dst="test",
        pld={
            "symbol": symbol,
            "side": side,
            "quantity": str(quantity),
            "price": str(price),
            "ts": 1234567890,
            "fees": "0",
            "venue": "test"
        }
    )

def create_account_update(positions, wallet_balance="10000"):
    """Helper to create an account update event."""
    return Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="test",
        dst="test",
        pld={
            "positions": positions,
            "wallet_balance": wallet_balance
        }
    )

def test_sync_removes_closed_positions(tracker):
    """Verify that sync logic removes positions not present in the account update."""
    # 1. Open a position to create internal state
    trade = create_trade_event("BTCUSDT", "buy", 1.0, 60000)
    tracker.on_trade_executed(trade)
    assert "BTCUSDT" in tracker.get_positions()

    # 2. Simulate an account update where the position is now closed (not in the list)
    account_update = create_account_update(positions=[])
    tracker.on_account_update(account_update)

    # 3. Assert that the position was removed
    assert "BTCUSDT" not in tracker.get_positions()

def test_sync_updates_existing_positions(tracker):
    """Verify that sync logic updates quantities and prices of existing positions."""
    # 1. Open a position
    trade = create_trade_event("BTCUSDT", "buy", 1.0, 60000)
    tracker.on_trade_executed(trade)

    # 2. Account update shows a change in the position
    updated_positions = [
        {"symbol": "BTCUSDT", "positionAmt": "0.5", "entryPrice": "61000"}
    ]
    account_update = create_account_update(positions=updated_positions)
    tracker.on_account_update(account_update)

    # 3. Assert position is updated
    position = tracker.get_positions()["BTCUSDT"]
    assert position["net_position"] == Decimal("0.5")
    assert position["avg_entry_price"] == Decimal("61000")

def test_sync_adds_new_positions(tracker):
    """Verify that sync logic adds new positions that appear in the account update."""
    # 1. Initial state is empty
    assert not tracker.get_positions()

    # 2. Account update shows a new position
    new_positions = [
        {"symbol": "ETHUSDT", "positionAmt": "10", "entryPrice": "3000"}
    ]
    account_update = create_account_update(positions=new_positions)
    tracker.on_account_update(account_update)

    # 3. Assert new position is added
    assert "ETHUSDT" in tracker.get_positions()
    position = tracker.get_positions()["ETHUSDT"]
    assert position["net_position"] == Decimal("10")

def test_full_reconciliation_scenario(tracker):
    """
    Test a full reconciliation:
    - One position is closed (BTCUSDT)
    - One position is updated (ETHUSDT)
    - One new position is added (SOLUSDT)
    """
    # 1. Create initial state with two positions
    tracker.on_trade_executed(create_trade_event("BTCUSDT", "buy", 1, 60000))
    tracker.on_trade_executed(create_trade_event("ETHUSDT", "sell", -5, 3000))
    assert "BTCUSDT" in tracker.get_positions()
    assert "ETHUSDT" in tracker.get_positions()

    # 2. Account update with reconciled state
    reconciled_positions = [
        {"symbol": "ETHUSDT", "positionAmt": "-2", "entryPrice": "3100"}, # Updated
        {"symbol": "SOLUSDT", "positionAmt": "100", "entryPrice": "150"}  # New
        # BTCUSDT is missing, implying it was closed
    ]
    account_update = create_account_update(positions=reconciled_positions)
    tracker.on_account_update(account_update)

    # 3. Assert the state is correct
    final_positions = tracker.get_positions()
    assert "BTCUSDT" not in final_positions
    assert "ETHUSDT" in final_positions
    assert "SOLUSDT" in final_positions
    assert final_positions["ETHUSDT"]["net_position"] == Decimal("-2")
    assert final_positions["SOLUSDT"]["avg_entry_price"] == Decimal("150")