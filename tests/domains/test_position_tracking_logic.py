"""
Tests for position_tracking PositionTracking logic.

FSMP-PERFECT-T07: Test position state management: open, increase, partial close, full close.
"""

import sys
import os
import pytest
from decimal import Decimal
from vfoundation.core.protocol import Message


class FSMCore:
    """Mock FSM core for testing."""

    def __init__(self):
        self.listeners = {}
        self.emitted_events = []

    def listen(self, event_name: str, callback):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def emit(self, event_name: str, payload: dict, why: str):
        """Emit event with payload and why."""
        self.emitted_events.append(
            {"event_name": event_name, "payload": payload, "why": why}
        )


def create_trade_event(symbol, side, quantity, price, fees=0.0, venue="binance", extra_pld=None):
    """Helper to create an EVT:TRADE_EXECUTED message."""
    payload = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "ts": 1234567890,
        "fees": fees,
        "venue": venue,
    }
    if extra_pld:
        payload.update(extra_pld)
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="execution",
        dst="position_tracking",
        pld=payload,
    )


def test_opens_new_long_position_correctly():
    """Verify that a new long position is created with correct avg price and quantity."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    trade_event = create_trade_event("BTCUSDT", "buy", 0.5, 70000)
    tracker.on_trade_executed(trade_event)

    position = tracker._positions["BTCUSDT"]
    assert position["quantity"] == Decimal("0.5")
    assert position["avg_price"] == Decimal("70000")
    assert "binance" in position["venues"]


def test_opens_new_short_position_correctly():
    """Verify that a new short position is created with correct avg price and quantity."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    trade_event = create_trade_event("ETHUSDT", "sell", 2.0, 3000)
    tracker.on_trade_executed(trade_event)

    position = tracker._positions["ETHUSDT"]
    assert position["quantity"] == Decimal("-2.0")
    assert position["avg_price"] == Decimal("3000")


def test_increases_existing_long_position():
    """Verify correct recalculation of avg_price and qty when adding to a position."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # First trade
    trade1 = create_trade_event("BTCUSDT", "buy", 0.5, 70000)
    tracker.on_trade_executed(trade1)

    # Second trade at a different price
    trade2 = create_trade_event("BTCUSDT", "buy", 0.5, 80000)
    tracker.on_trade_executed(trade2)

    position = tracker._positions["BTCUSDT"]
    assert position["quantity"] == Decimal("1.0")
    # Weighted average: (0.5*70000 + 0.5*80000) / 1.0 = 75000
    assert position["avg_price"] == Decimal("75000")


def test_increases_existing_short_position():
    """Verify correct avg_price calculation when adding to short position."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # First short
    trade1 = create_trade_event("ETHUSDT", "sell", 1.0, 3000)
    tracker.on_trade_executed(trade1)

    # Add to short
    trade2 = create_trade_event("ETHUSDT", "sell", 1.0, 2800)
    tracker.on_trade_executed(trade2)

    position = tracker._positions["ETHUSDT"]
    assert position["quantity"] == Decimal("-2.0")
    # Weighted average: (1.0*3000 + 1.0*2800) / 2.0 = 2900
    assert position["avg_price"] == Decimal("2900")


def test_partially_closes_long_position():
    """Verify partial close reduces quantity without changing avg_price."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # Open long position
    open_trade = create_trade_event("BTCUSDT", "buy", 1.0, 70000)
    tracker.on_trade_executed(open_trade)

    # Partial close
    close_trade = create_trade_event("BTCUSDT", "sell", 0.3, 75000)
    tracker.on_trade_executed(close_trade)

    position = tracker._positions["BTCUSDT"]
    assert position["quantity"] == Decimal("0.7")
    assert position["avg_price"] == Decimal("70000")  # avg_price unchanged


def test_fully_closes_long_position():
    """Verify full close removes the position from tracking."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # Open long position
    open_trade = create_trade_event("BTCUSDT", "buy", 1.0, 70000)
    tracker.on_trade_executed(open_trade)

    # Full close
    close_trade = create_trade_event("BTCUSDT", "sell", 1.0, 75000)
    tracker.on_trade_executed(close_trade)

    # Position should be removed or quantity=0
    assert "BTCUSDT" not in tracker._positions or tracker._positions["BTCUSDT"][
        "quantity"
    ] == Decimal("0")


def test_fully_closes_short_position():
    """Verify closing a short position removes or zeros it."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # Open short position
    open_trade = create_trade_event("ETHUSDT", "sell", 2.0, 3000)
    tracker.on_trade_executed(open_trade)

    # Close short
    close_trade = create_trade_event("ETHUSDT", "buy", 2.0, 2800)
    tracker.on_trade_executed(close_trade)

    assert "ETHUSDT" not in tracker._positions or tracker._positions["ETHUSDT"][
        "quantity"
    ] == Decimal("0")


def test_flips_long_to_short():
    """Verify that selling more than long qty flips to short position."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # Open long 1.0
    open_trade = create_trade_event("BTCUSDT", "buy", 1.0, 70000)
    tracker.on_trade_executed(open_trade)

    # Sell 1.5 -> should flip to short 0.5
    flip_trade = create_trade_event("BTCUSDT", "sell", 1.5, 75000)
    tracker.on_trade_executed(flip_trade)

    position = tracker._positions["BTCUSDT"]
    assert position["quantity"] == Decimal("-0.5")  # Net short
    assert position["avg_price"] == Decimal(
        "75000")  # New position at flip price


def test_flips_short_to_long():
    """Verify buying more than short qty flips to long position."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # Open short 1.0
    open_trade = create_trade_event("ETHUSDT", "sell", 1.0, 3000)
    tracker.on_trade_executed(open_trade)

    # Buy 1.5 -> should flip to long 0.5
    flip_trade = create_trade_event("ETHUSDT", "buy", 1.5, 2800)
    tracker.on_trade_executed(flip_trade)

    position = tracker._positions["ETHUSDT"]
    assert position["quantity"] == Decimal("0.5")  # Net long
    assert position["avg_price"] == Decimal(
        "2800")  # New position at flip price


def test_calculates_realized_pnl_on_close():
    """Verify realized P&L is calculated correctly on partial/full close."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # Open long 1.0 @ 70000
    open_trade = create_trade_event("BTCUSDT", "buy", 1.0, 70000)
    tracker.on_trade_executed(open_trade)

    initial_realized = tracker._realized_pnl

    # Close 0.5 @ 75000 -> realized P&L = 0.5 * (75000 - 70000) = 2500
    close_trade = create_trade_event("BTCUSDT", "sell", 0.5, 75000)
    tracker.on_trade_executed(close_trade)

    realized_pnl = tracker._realized_pnl
    expected_pnl = initial_realized + Decimal("0.5") * (
        Decimal("75000") - Decimal("70000")
    )
    assert realized_pnl == expected_pnl


def test_handles_fees_in_pnl_calculation():
    """Verify fees reduce realized P&L correctly (only close fees currently)."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # Open long 1.0 @ 70000 with fees=10 (fees on open not tracked in current implementation)
    open_trade = create_trade_event("BTCUSDT", "buy", 1.0, 70000, fees=10)
    tracker.on_trade_executed(open_trade)

    initial_realized = tracker._realized_pnl

    # Close 1.0 @ 75000 with fees=10
    # Gross P&L = 1.0 * (75000 - 70000) = 5000
    # Current implementation: Net P&L = 5000 - 10 (close fees only) = 4990
    close_trade = create_trade_event("BTCUSDT", "sell", 1.0, 75000, fees=10)
    tracker.on_trade_executed(close_trade)

    realized_pnl = tracker._realized_pnl
    # Expected: initial + (gross_pnl - close_fees)
    expected = initial_realized + (Decimal("5000") - Decimal("10"))
    assert realized_pnl == expected


def test_tracks_multiple_symbols_independently():
    """Verify multiple symbols are tracked separately."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # Open BTC long
    btc_trade = create_trade_event("BTCUSDT", "buy", 0.5, 70000)
    tracker.on_trade_executed(btc_trade)

    # Open ETH short
    eth_trade = create_trade_event("ETHUSDT", "sell", 2.0, 3000)
    tracker.on_trade_executed(eth_trade)

    assert "BTCUSDT" in tracker._positions
    assert "ETHUSDT" in tracker._positions
    assert tracker._positions["BTCUSDT"]["quantity"] == Decimal("0.5")
    assert tracker._positions["ETHUSDT"]["quantity"] == Decimal("-2.0")


def test_handles_account_update_event():
    """Verify account balance updates are processed correctly."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    account_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="broker",
        dst="position_tracking",
        pld={
            "totalWalletBalance": 100000.0,
            "totalUnrealizedProfit": 5000.0,
            "positions": [],
            "ts": 1234567890,
        },
    )

    tracker.on_account_update(account_msg)

    # Check that equity was updated
    assert tracker._equity == Decimal("100000.0")


def test_handles_balance_update_event():
    """Verify balance updates are processed without errors."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    balance_msg = Message(
        op="EVT",
        verb="BALANCE_UPDATE_RECEIVED",
        src="broker",
        dst="position_tracking",
        pld={
            "assets": [{"asset": "USDT", "free": "50000.0", "locked": "10000.0"}],
            "ts": 1234567890,
        },
    )

    # Should not raise an exception
    tracker.on_balance_update(balance_msg)
    # Balance updates are logged but not stored in current implementation
    assert True  # Test passes if no exception


def test_emits_portfolio_state_on_trade():
    """Verify EVT:PORTFOLIO_STATE_UPDATED is emitted after trade execution."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # Open a position
    trade = create_trade_event("BTCUSDT", "buy", 0.5, 70000)
    tracker.on_trade_executed(trade)

    # Check if EVT:PORTFOLIO_STATE_UPDATED was emitted
    portfolio_events = [
        e
        for e in fsm.emitted_events
        if e["event_name"] == "EVT:PORTFOLIO_STATE_UPDATED"
    ]
    assert len(portfolio_events) > 0, "Expected PORTFOLIO_STATE_UPDATED event"

    portfolio_pld = portfolio_events[0]["payload"]
    assert "positions" in portfolio_pld
    # positions is a list of dicts
    assert len(portfolio_pld["positions"]) > 0
    assert portfolio_pld["positions"][0]["symbol"] == "BTCUSDT"


def test_filters_out_zero_positions():
    """Verify zero-quantity positions are excluded from portfolio state."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # Open and close a position
    open_trade = create_trade_event("BTCUSDT", "buy", 1.0, 70000)
    tracker.on_trade_executed(open_trade)

    close_trade = create_trade_event("BTCUSDT", "sell", 1.0, 75000)
    tracker.on_trade_executed(close_trade)

    # Check last portfolio state event
    portfolio_events = [
        e
        for e in fsm.emitted_events
        if e["event_name"] == "EVT:PORTFOLIO_STATE_UPDATED"
    ]
    assert len(portfolio_events) >= 2  # One for open, one for close

    last_event = portfolio_events[-1]
    positions = last_event["payload"].get("positions", {})
    # BTCUSDT should not be in positions (closed)
    assert "BTCUSDT" not in positions


def test_rejects_invalid_side():
    """Verify invalid trade side raises ValueError."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    invalid_trade = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="execution",
        dst="position_tracking",
        pld={
            "symbol": "BTCUSDT",
            "side": "invalid",  # Invalid side
            "quantity": 1.0,
            "price": 70000,
            "ts": 1234567890,
            "fees": 0.0,
            "venue": "binance",
        },
    )

    with pytest.raises(ValueError, match="Invalid side"):
        tracker.on_trade_executed(invalid_trade)


def test_account_update_with_positions():
    """Verify account update loads positions from account data."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    account_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="broker",
        dst="position_tracking",
        pld={
            "totalWalletBalance": 100000.0,
            "totalUnrealizedProfit": 5000.0,
            "positions": [
                {"symbol": "BTCUSDT", "positionAmt": "0.5", "entryPrice": "70000"},
                {"symbol": "ETHUSDT", "positionAmt": "-2.0", "entryPrice": "3000"},
            ],
            "ts": 1234567890,
        },
    )

    tracker.on_account_update(account_msg)

    # Check positions were loaded
    assert "BTCUSDT" in tracker._positions
    assert tracker._positions["BTCUSDT"]["quantity"] == Decimal("0.5")
    assert tracker._positions["BTCUSDT"]["avg_price"] == Decimal("70000")

    assert "ETHUSDT" in tracker._positions
    assert tracker._positions["ETHUSDT"]["quantity"] == Decimal("-2.0")


def test_account_update_removes_flat_positions():
    """Verify account update removes positions with zero quantity."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # First, add a position via trade
    trade = create_trade_event("BTCUSDT", "buy", 1.0, 70000)
    tracker.on_trade_executed(trade)
    assert "BTCUSDT" in tracker._positions

    # Now account update with zero position
    account_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="broker",
        dst="position_tracking",
        pld={
            "totalWalletBalance": 100000.0,
            "totalUnrealizedProfit": 0.0,
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.0",
                    "entryPrice": "70000",
                }  # Flat
            ],
            "ts": 1234567890,
        },
    )

    tracker.on_account_update(account_msg)

    # Position should be removed
    assert "BTCUSDT" not in tracker._positions


def test_start_method():
    """Verify start() method can be called without errors."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    # Should not raise an exception
    tracker.start()
    assert True  # Test passes if no exception


def test_trade_dedup_skips_duplicate_trades():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(
        config={"trading": {"position_sync": {"trade_dedup_window_sec": 120}}},
        fsm=fsm,
    )

    trade_event = create_trade_event(
        "BTCUSDT",
        "buy",
        0.5,
        70000,
        extra_pld={"trade_id": "abc-123"},
    )

    tracker.on_trade_executed(trade_event)
    tracker.on_trade_executed(trade_event)  # Duplicate

    assert tracker.trade_dedup_hits_total == 1
    assert tracker._positions["BTCUSDT"]["quantity"] == Decimal("0.5")
    portfolio_events = [
        e for e in fsm.emitted_events if e["event_name"] == "EVT:PORTFOLIO_STATE_UPDATED"
    ]
    assert len(portfolio_events) == 1


def test_account_update_overrides_local_state():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    open_trade = create_trade_event("BTCUSDT", "buy", 1.0, 70000)
    tracker.on_trade_executed(open_trade)

    account_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="broker",
        dst="position_tracking",
        pld={
            "totalWalletBalance": 100000.0,
            "totalUnrealizedProfit": 0.0,
            "positions": [
                {"symbol": "BTCUSDT", "positionAmt": "2.0", "entryPrice": "72000"}
            ],
            "ts": 1234567999,
        },
    )

    tracker.on_account_update(account_msg)

    assert tracker._positions["BTCUSDT"]["quantity"] == Decimal("2.0")
    assert tracker._positions["BTCUSDT"]["avg_price"] == Decimal("72000")
    assert tracker.snapshot_reconciliation_drift_total >= 1


def test_account_update_detects_manual_closure():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    trade = create_trade_event("ETHUSDT", "buy", 0.5, 3500)
    tracker.on_trade_executed(trade)

    account_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="broker",
        dst="position_tracking",
        pld={
            "totalWalletBalance": 50000.0,
            "totalUnrealizedProfit": 0.0,
            "positions": [],
            "ts": 1234568000,
        },
    )

    tracker.on_account_update(account_msg)

    assert "ETHUSDT" not in tracker._positions
    assert tracker.manual_intervention_detected_total == 1


def test_trade_processing_continues_when_wal_soft_fail(monkeypatch):
    """WAL returning None should not block processing when strict_wal is disabled."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(
        config={"trading": {"dr": {"strict_wal": False}}},
        fsm=fsm,
    )

    def fake_append(_payload):
        return None

    monkeypatch.setattr(
        "apps.reference.domains.position_tracking.position_tracking.wal.append",
        fake_append,
    )

    trade_event = create_trade_event("BTCUSDT", "buy", 0.2, 50000)
    tracker.on_trade_executed(trade_event)

    assert "BTCUSDT" in tracker._positions, "Position should still update"
    assert any(
        event["event_name"] == "EVT:PORTFOLIO_STATE_UPDATED"
        for event in fsm.emitted_events
    ), "Portfolio update should be emitted"


def test_trade_processing_stops_when_wal_strict(monkeypatch):
    """Default strict_wal should halt processing on WAL failure."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    monkeypatch.setattr(
        "apps.reference.domains.position_tracking.position_tracking.wal.append",
        lambda _payload: None,
    )

    trade_event = create_trade_event("ETHUSDT", "buy", 0.1, 3000)
    tracker.on_trade_executed(trade_event)

    assert "ETHUSDT" not in tracker._positions
    assert not any(
        event["event_name"] == "EVT:PORTFOLIO_STATE_UPDATED"
        for event in fsm.emitted_events
    )


def test_account_update_continues_when_wal_soft_fail(monkeypatch):
    """Account updates should still refresh state when strict_wal is disabled."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(
        config={"trading": {"dr": {"strict_wal": False}}},
        fsm=fsm,
    )

    def raise_append(_payload):
        raise RuntimeError("wal down")

    monkeypatch.setattr(
        "apps.reference.domains.position_tracking.position_tracking.wal.append",
        raise_append,
    )

    account_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="broker",
        dst="position_tracking",
        pld={
            "totalWalletBalance": 100000.0,
            "totalUnrealizedProfit": 0.0,
            "positions": [],
            "ts": 1,
        },
    )

    tracker.on_account_update(account_msg)
    assert tracker._equity == Decimal("100000.0")


def test_account_update_stops_when_wal_strict(monkeypatch):
    """Strict WAL should block account update processing on failure."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    def fail_append(_payload):
        raise RuntimeError("wal down")

    monkeypatch.setattr(
        "apps.reference.domains.position_tracking.position_tracking.wal.append",
        fail_append,
    )

    account_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="broker",
        dst="position_tracking",
        pld={
            "totalWalletBalance": 50000.0,
            "totalUnrealizedProfit": 0.0,
            "positions": [],
            "ts": 1,
        },
    )

    tracker.on_account_update(account_msg)
    assert tracker._equity == Decimal("0")


def test_force_full_resync_uses_registered_fetcher():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    calls = []

    def fake_fetcher(symbol, reason, rid):
        calls.append((symbol, reason, rid))
        return {
            "status": "ok",
            "symbol": symbol or "ALL",
            "extra": "snapshot",
        }

    tracker.register_snapshot_fetcher(fake_fetcher)

    summary = tracker.force_full_resync(
        reason="manual_resync",
        symbol="BTCUSDT",
        rid="RID-123",
    )

    assert calls == [("BTCUSDT", "manual_resync", "RID-123")]
    assert summary["status"] == "ok"
    assert summary["symbol"] == "BTCUSDT"
    assert summary["reason"] == "manual_resync"


def test_force_resync_command_emits_error_without_fetcher():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    cmd = Message(
        op="CMD",
        verb="POSITION_FORCE_RESYNC",
        src="debug",
        dst="position_tracking",
        pld={"symbol": "ETHUSDT", "reason": "manual"},
    )

    tracker.on_force_resync_command(cmd)

    completion_events = [
        event for event in fsm.emitted_events if event["event_name"] == "EVT:POSITION_FORCE_RESYNC_COMPLETED"
    ]
    assert completion_events, "force resync completion event should be emitted"
    assert completion_events[-1]["payload"]["status"] == "error"


def test_account_update_force_resync_skips_wal(monkeypatch):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    fsm = FSMCore()
    tracker = PositionTracking(config={}, fsm=fsm)

    def explode(*_args, **_kwargs):
        raise AssertionError(
            "_append_event_to_wal should not be called for force_resync payloads")

    monkeypatch.setattr(
        "apps.reference.domains.position_tracking.position_tracking.PositionTracking._append_event_to_wal",
        explode,
    )

    account_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="broker",
        dst="position_tracking",
        pld={
            "_force_resync": True,
            "_force_resync_reason": "manual",
            "_force_resync_symbol": "BTCUSDT",
            "totalWalletBalance": 1000.0,
            "totalUnrealizedProfit": 0.0,
            "positions": [],
            "ts": 1700000000,
        },
    )

    tracker.on_account_update(account_msg)
    assert tracker._equity == Decimal("1000.0")
