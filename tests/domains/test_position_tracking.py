"""
Integration test for position_tracking domain.

Tests that the domain correctly subscribes to EVT:TRADE_EXECUTED,
processes it, and emits a valid EVT:PORTFOLIO_STATE_UPDATED event.
"""

from unittest import mock
import pytest
from vfoundation.core.protocol import Message


@pytest.fixture
def mock_config():
    """Mock configuration for position tracking tests."""
    return {
        "position_limits": {"max_positions": 10},
        "risk_limits": {"max_drawdown": 0.1},
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
                    callback(
                        Message(
                            op="EVT",
                            verb=event_name.split(":")[1],  # Extract verb from EVT:VERB
                            src="test",
                            dst="any",
                            pld=payload,
                            why=why,
                        )
                    )
                except Exception as e:
                    print(f"Error in event listener: {e}")


def test_position_tracking_consumes_trade_and_updates_portfolio(mock_config):
    """
    Test that position_tracking domain consumes EVT:TRADE_EXECUTED
    and emits EVT:PORTFOLIO_STATE_UPDATED with updated portfolio state.
    """
    # Step 1: Initialization
    fsm = FSMCore()
    mock_listener = mock.Mock()
    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", mock_listener)

    # Step 2: Start component (will fail until PositionTracking is implemented)
    # This import will raise ModuleNotFoundError until the component exists
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)
    position_tracker.start()

    # Step 3: Simulate input event
    fake_trade_payload = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "price": 50000.0,
        "quantity": 0.1,
        "ts": 1693526400000,  # 2023-09-01 00:00:00 UTC in milliseconds
        "fees": 0.0,
        "venue": "binance",
    }

    fsm.emit(
        "EVT:TRADE_EXECUTED",
        payload=fake_trade_payload,
        why="Simulated trade for position tracking test.",
    )

    # Step 4: Verify result
    mock_listener.assert_called_once()

    # Get the event that was passed to the listener
    call_args = mock_listener.call_args
    fsm_event = call_args[0][0]  # First positional argument

    # Verify the payload structure matches portfolio_state_v1.json schema
    assert isinstance(fsm_event.pld, dict)
    assert "ts" in fsm_event.pld
    assert isinstance(fsm_event.pld["ts"], int)
    assert "equity" in fsm_event.pld
    # FIXED: After precision refactoring, financial fields are strings
    assert isinstance(fsm_event.pld["equity"], str), "equity should be string"
    assert "realized_pnl" in fsm_event.pld
    assert isinstance(fsm_event.pld["realized_pnl"], str), (
        "realized_pnl should be string"
    )
    assert "unrealized_pnl" in fsm_event.pld
    assert isinstance(fsm_event.pld["unrealized_pnl"], str), (
        "unrealized_pnl should be string"
    )
    assert "positions" in fsm_event.pld
    assert isinstance(fsm_event.pld["positions"], list)

    # Verify positions array contains our BTC position
    positions = fsm_event.pld["positions"]
    assert len(positions) >= 1

    # Find BTC position
    btc_position = None
    for pos in positions:
        if pos.get("symbol") == "BTCUSDT":
            btc_position = pos
            break

    assert btc_position is not None, "BTC position should be present"
    assert btc_position["symbol"] == "BTCUSDT"
    # FIXED: After precision refactoring, position fields are strings
    assert btc_position["net_position"] == "0.1", "net_position should be string '0.1'"
    assert btc_position["avg_entry_price"] == "50000.0", (
        "avg_entry_price should be string"
    )
    assert isinstance(btc_position["venues"], list)
    assert "binance" in btc_position["venues"]


def test_position_tracking_multiple_trades(mock_config):
    """
    Test position tracking with multiple trades (accumulation and partial close).
    """
    # Step 1: Initialize FSM core
    fsm = FSMCore()

    # Step 2: Set up mock listeners
    portfolio_listener = mock.Mock()
    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)

    # Step 3: Initialize component
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)
    position_tracker.start()

    # Step 4: First trade - buy 0.1 BTC
    trade1_payload = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "price": 50000.0,
        "quantity": 0.1,
        "ts": 1693526400000,
        "fees": 0.0,
        "venue": "binance",
    }

    fsm.emit("EVT:TRADE_EXECUTED", payload=trade1_payload, why="First trade: buy BTC.")

    # Step 5: Second trade - buy more BTC (accumulation)
    trade2_payload = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "price": 51000.0,
        "quantity": 0.05,
        "ts": 1693526460000,
        "fees": 0.0,
        "venue": "binance",
    }

    fsm.emit(
        "EVT:TRADE_EXECUTED",
        payload=trade2_payload,
        why="Second trade: accumulate BTC.",
    )

    # Step 6: Third trade - sell part (partial close)
    trade3_payload = {
        "symbol": "BTCUSDT",
        "side": "sell",
        "price": 52000.0,
        "quantity": 0.08,
        "ts": 1693526520000,
        "fees": 5.0,
        "venue": "binance",
    }

    fsm.emit(
        "EVT:TRADE_EXECUTED",
        payload=trade3_payload,
        why="Third trade: partial sell BTC.",
    )

    # Step 7: Verify final state
    # Should have 3 calls to listener
    assert portfolio_listener.call_count == 3

    # Get the final call
    final_call = portfolio_listener.call_args
    final_event = final_call[0][0]

    final_payload = final_event.pld
    positions = final_payload["positions"]

    # Should have one BTC position
    assert len(positions) == 1
    btc_pos = positions[0]
    assert btc_pos["symbol"] == "BTCUSDT"
    # FIXED: After precision refactoring, position fields are strings
    assert abs(float(btc_pos["net_position"]) - 0.07) < 1e-9  # 0.1 + 0.05 - 0.08 = 0.07

    # Average price should be weighted: (0.1*50000 + 0.05*51000) / 0.15 = 50333.33
    # After partial sell, remaining position keeps original average
    expected_avg = (0.1 * 50000 + 0.05 * 51000) / 0.15
    assert abs(float(btc_pos["avg_entry_price"]) - expected_avg) < 1e-9

    # Should have realized P&L from the partial sell
    # Sold 0.08 at 52000, average entry was ~50333, so profit per unit ~1677
    # Total realized P&L: 0.08 * 1677 - 5 = ~133.76 - 5 = ~128.76
    # FIXED: After precision refactoring, realized_pnl is string
    assert float(final_payload["realized_pnl"]) > 0

    print(f"✅ Multiple trades test passed! Final position: {btc_pos}")


def test_position_tracking_complete_position_close(mock_config):
    """
    Test position tracking with complete position close (realized P&L).
    """
    # Step 1: Initialize FSM core
    fsm = FSMCore()

    # Step 2: Set up mock listeners
    portfolio_listener = mock.Mock()
    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)

    # Step 3: Initialize component
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)
    position_tracker.start()

    # Step 4: Buy BTC
    buy_payload = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "price": 50000.0,
        "quantity": 0.1,
        "ts": 1693526400000,
        "fees": 0.0,
        "venue": "binance",
    }

    fsm.emit("EVT:TRADE_EXECUTED", payload=buy_payload, why="Buy BTC.")

    # Step 5: Sell all BTC at higher price
    sell_payload = {
        "symbol": "BTCUSDT",
        "side": "sell",
        "price": 55000.0,
        "quantity": 0.1,
        "ts": 1693526460000,
        "fees": 10.0,
        "venue": "binance",
    }

    fsm.emit("EVT:TRADE_EXECUTED", payload=sell_payload, why="Sell all BTC.")

    # Step 6: Verify final state
    assert portfolio_listener.call_count == 2

    # Get the final call
    final_call = portfolio_listener.call_args
    final_event = final_call[0][0]

    final_payload = final_event.pld

    # Position should be closed (empty positions array)
    positions = final_payload["positions"]
    assert len(positions) == 0

    # Should have realized P&L: 0.1 * (55000 - 50000) - 10 = 5000 - 10 = 4990
    expected_pnl = 0.1 * (55000 - 50000) - 10
    # FIXED: After precision refactoring, realized_pnl is string
    assert abs(float(final_payload["realized_pnl"]) - expected_pnl) < 1e-9

    print(
        f"✅ Complete close test passed! Realized P&L: {final_payload['realized_pnl']}"
    )


def test_position_tracking_short_position(mock_config):
    """
    Test position tracking with short positions (negative quantity).
    """
    # Step 1: Initialize FSM core
    fsm = FSMCore()

    # Step 2: Set up mock listeners
    portfolio_listener = mock.Mock()
    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)

    # Step 3: Initialize component
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)
    position_tracker.start()

    # Step 4: Short sell BTC
    short_payload = {
        "symbol": "BTCUSDT",
        "side": "sell",
        "price": 50000.0,
        "quantity": 0.1,
        "ts": 1693526400000,
        "fees": 0.0,
        "venue": "binance",
    }

    fsm.emit("EVT:TRADE_EXECUTED", payload=short_payload, why="Short sell BTC.")

    # Step 5: Verify position
    portfolio_listener.assert_called_once()
    call_args = portfolio_listener.call_args
    event = call_args[0][0]

    positions = event.pld["positions"]
    assert len(positions) == 1
    pos = positions[0]
    assert pos["symbol"] == "BTCUSDT"
    # FIXED: After precision refactoring, position fields are strings
    assert pos["net_position"] == "-0.1", (
        "net_position should be string '-0.1' for short"
    )
    assert pos["avg_entry_price"] == "50000.0", "avg_entry_price should be string"

    print(f"✅ Short position test passed! Position: {pos}")


def test_position_tracking_multiple_venues(mock_config):
    """
    Test position tracking with multiple venues for the same symbol.
    """
    # Step 1: Initialize FSM core
    fsm = FSMCore()

    # Step 2: Set up mock listeners
    portfolio_listener = mock.Mock()
    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)

    # Step 3: Initialize component
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)
    position_tracker.start()

    # Step 4: Trade on binance
    trade1_payload = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "price": 50000.0,
        "quantity": 0.1,
        "ts": 1693526400000,
        "fees": 0.0,
        "venue": "binance",
    }

    fsm.emit("EVT:TRADE_EXECUTED", payload=trade1_payload, why="Buy BTC on binance.")

    # Step 5: Trade on kraken
    trade2_payload = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "price": 50100.0,
        "quantity": 0.05,
        "ts": 1693526460000,
        "fees": 0.0,
        "venue": "kraken",
    }

    fsm.emit("EVT:TRADE_EXECUTED", payload=trade2_payload, why="Buy BTC on kraken.")

    # Step 6: Verify final state
    assert portfolio_listener.call_count == 2

    # Get the final call
    final_call = portfolio_listener.call_args
    final_event = final_call[0][0]

    final_payload = final_event.pld
    positions = final_payload["positions"]

    # Should have one BTC position
    assert len(positions) == 1
    btc_pos = positions[0]
    assert btc_pos["symbol"] == "BTCUSDT"
    # FIXED: After precision refactoring, position fields are strings
    assert abs(float(btc_pos["net_position"]) - 0.15) < 1e-9  # 0.1 + 0.05 = 0.15

    # Average price should be weighted: (0.1*50000 + 0.05*50100) / 0.15 = 50033.33
    expected_avg = (0.1 * 50000 + 0.05 * 50100) / 0.15
    assert abs(float(btc_pos["avg_entry_price"]) - expected_avg) < 1e-9

    # Should track both venues
    assert set(btc_pos["venues"]) == {"binance", "kraken"}

    print(f"✅ Multiple venues test passed! Position: {btc_pos}")


def test_position_tracking_invalid_side(mock_config):
    """
    Test position tracking with invalid trade side (should be ignored).
    """
    # Step 1: Initialize FSM core
    fsm = FSMCore()

    # Step 2: Set up mock listeners
    portfolio_listener = mock.Mock()
    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)

    # Step 3: Initialize component
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)
    position_tracker.start()

    # Step 4: Invalid trade side
    invalid_payload = {
        "symbol": "BTCUSDT",
        "side": "invalid",
        "price": 50000.0,
        "quantity": 0.1,
        "ts": 1693526400000,
        "fees": 0.0,
        "venue": "binance",
    }

    # Should handle error gracefully (no exception raised, error logged)
    fsm.emit("EVT:TRADE_EXECUTED", payload=invalid_payload, why="Invalid side test.")

    # No portfolio update should have been emitted due to error
    portfolio_listener.assert_not_called()

    print("✅ Invalid side test passed! No portfolio update emitted.")


def test_position_tracking_position_flip(mock_config):
    """
    Test position tracking with position flip (long to short or vice versa).
    """
    # Step 1: Initialize FSM core
    fsm = FSMCore()

    # Step 2: Set up mock listeners
    portfolio_listener = mock.Mock()
    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)

    # Step 3: Initialize component
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)
    position_tracker.start()

    # Step 4: First trade - buy 0.1 BTC
    buy_payload = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "price": 50000.0,
        "quantity": 0.1,
        "ts": 1693526400000,
        "fees": 0.0,
        "venue": "binance",
    }

    fsm.emit("EVT:TRADE_EXECUTED", payload=buy_payload, why="Buy BTC.")

    # Step 5: Second trade - sell 0.15 BTC (flip to short position)
    sell_payload = {
        "symbol": "BTCUSDT",
        "side": "sell",
        "price": 48000.0,
        "quantity": 0.15,
        "ts": 1693526460000,
        "fees": 5.0,
        "venue": "binance",
    }

    fsm.emit(
        "EVT:TRADE_EXECUTED",
        payload=sell_payload,
        why="Sell more than position (flip).",
    )

    # Step 6: Verify final state
    assert portfolio_listener.call_count == 2

    # Get the final call
    final_call = portfolio_listener.call_args
    final_event = final_call[0][0]

    final_payload = final_event.pld
    positions = final_payload["positions"]

    # Should have one BTC position (now short)
    assert len(positions) == 1
    btc_pos = positions[0]
    assert btc_pos["symbol"] == "BTCUSDT"
    # FIXED: After precision refactoring, position fields are strings
    assert (
        abs(float(btc_pos["net_position"]) - (-0.05)) < 1e-9
    )  # -0.1 + 0.15 = -0.05 (short)

    # After flip, average price should be the flip price (48000)
    # FIXED: After precision refactoring, avg_entry_price is string
    assert abs(float(btc_pos["avg_entry_price"]) - 48000.0) < 1e-9

    # Should have realized P&L from the closed portion
    # Closed 0.1 at 48000, original entry 50000, so loss per unit 2000
    # Total realized P&L: 0.1 * (48000 - 50000) - 5 = -2000 - 5 = -2005
    # FIXED: After precision refactoring, realized_pnl is string
    assert float(final_payload["realized_pnl"]) < 0

    print(f"✅ Position flip test passed! Final position: {btc_pos}")


def test_position_tracking_short_to_long_flip(mock_config):
    """
    Test position tracking with short to long position flip.
    """
    # Step 1: Initialize FSM core
    fsm = FSMCore()

    # Step 2: Set up mock listeners
    portfolio_listener = mock.Mock()
    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)

    # Step 3: Initialize component
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)
    position_tracker.start()

    # Step 4: First trade - short sell 0.1 BTC
    short_payload = {
        "symbol": "BTCUSDT",
        "side": "sell",
        "price": 50000.0,
        "quantity": 0.1,
        "ts": 1693526400000,
        "fees": 0.0,
        "venue": "binance",
    }

    fsm.emit("EVT:TRADE_EXECUTED", payload=short_payload, why="Short sell BTC.")

    # Step 5: Second trade - buy 0.15 BTC (flip to long position)
    buy_payload = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "price": 52000.0,
        "quantity": 0.15,
        "ts": 1693526460000,
        "fees": 5.0,
        "venue": "binance",
    }

    fsm.emit(
        "EVT:TRADE_EXECUTED",
        payload=buy_payload,
        why="Buy more than short position (flip).",
    )

    # Step 6: Verify final state
    assert portfolio_listener.call_count == 2

    # Get the final call
    final_call = portfolio_listener.call_args
    final_event = final_call[0][0]

    final_payload = final_event.pld
    positions = final_payload["positions"]

    # Should have one BTC position (now long)
    assert len(positions) == 1
    btc_pos = positions[0]
    assert btc_pos["symbol"] == "BTCUSDT"
    # FIXED: After precision refactoring, position fields are strings
    assert (
        abs(float(btc_pos["net_position"]) - 0.05) < 1e-9
    )  # -0.1 + 0.15 = 0.05 (long)

    # After flip, average price should be the flip price (52000)
    assert abs(float(btc_pos["avg_entry_price"]) - 52000.0) < 1e-9

    # Should have realized P&L from the closed portion
    # Closed 0.1 short at 52000, original entry 50000, so loss per unit 2000
    # Total realized P&L: -0.1 * (52000 - 50000) - 5 = -2000 - 5 = -2005
    # FIXED: After precision refactoring, realized_pnl is string
    assert float(final_payload["realized_pnl"]) < 0

    print(f"✅ Short to long flip test passed! Final position: {btc_pos}")


def test_position_tracking_partial_close(mock_config):
    """
    Test position tracking with partial position close.
    """
    # Step 1: Initialize FSM core
    fsm = FSMCore()

    # Step 2: Set up mock listeners
    portfolio_listener = mock.Mock()
    fsm.listen("EVT:PORTFOLIO_STATE_UPDATED", portfolio_listener)

    # Step 3: Initialize component
    import sys
    import os

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from apps.reference.domains.position_tracking.position_tracking import (
        PositionTracking,
    )

    position_tracker = PositionTracking(fsm=fsm, config=mock_config)
    position_tracker.start()

    # Step 4: First trade - buy 0.2 BTC
    buy_payload = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "price": 50000.0,
        "quantity": 0.2,
        "ts": 1693526400000,
        "fees": 0.0,
        "venue": "binance",
    }

    fsm.emit("EVT:TRADE_EXECUTED", payload=buy_payload, why="Buy BTC.")

    # Step 5: Second trade - sell 0.1 BTC (partial close)
    sell_payload = {
        "symbol": "BTCUSDT",
        "side": "sell",
        "price": 55000.0,
        "quantity": 0.1,
        "ts": 1693526460000,
        "fees": 5.0,
        "venue": "binance",
    }

    fsm.emit("EVT:TRADE_EXECUTED", payload=sell_payload, why="Partial sell BTC.")

    # Step 6: Verify final state
    assert portfolio_listener.call_count == 2

    # Get the final call
    final_call = portfolio_listener.call_args
    final_event = final_call[0][0]

    final_payload = final_event.pld
    positions = final_payload["positions"]

    # Should have one BTC position
    assert len(positions) == 1
    btc_pos = positions[0]
    assert btc_pos["symbol"] == "BTCUSDT"
    # FIXED: After precision refactoring, position fields are strings
    assert abs(float(btc_pos["net_position"]) - 0.1) < 1e-9  # 0.2 - 0.1 = 0.1

    # Average price should remain the same (partial close keeps original average)
    assert abs(float(btc_pos["avg_entry_price"]) - 50000.0) < 1e-9

    # Should have realized P&L from the partial close
    # Sold 0.1 at 55000, original entry 50000, so profit per unit 5000
    # Total realized P&L: 0.1 * (55000 - 50000) - 5 = 500 - 5 = 495
    # FIXED: After precision refactoring, realized_pnl is string
    assert abs(float(final_payload["realized_pnl"]) - 495.0) < 1e-9

    print(f"✅ Partial close test passed! Final position: {btc_pos}")
