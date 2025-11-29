"""
Unit tests for Open Flow FSM (FSMP-P1-T02).

Coverage: valid CMD:OPEN → DEC:OPEN, guard failures → ERR.
"""

from decimal import Decimal

from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_open import (
    OpenFlowFSM,
    OpenState as State,
)


def test_open_flow_valid_market_order():
    """Test valid MARKET order generates DEC:OPEN."""
    config = {
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "min_qty": "0.001",
                    "step_size": "0.001",
                    "tick_size": "0.01",
                    "min_notional": "5.0",
                }
            }
        }
    }
    fsm = OpenFlowFSM(cooldown_sec=0.1, config=config)

    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-001",
        why="open market",
        idempotent_key="test-key-001",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "1.0",
            "order_type": "MARKET",
            "tif": "GTC",
            "price_ref": "50000.0",  # Current market price for min_notional check
        },
    )

    result = fsm.handle(cmd)

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "OPEN"
    assert result.why == "OPEN_OK"
    assert result.pld["symbol"] == "BTCUSDT"
    assert result.pld["side"] == "BUY"
    assert Decimal(result.pld["qty"]) == Decimal("1.0")
    assert fsm.state == State.DONE
    assert fsm.get_metrics()["fsm_open_decisions_total"] == 1


def test_open_flow_qty_rounding():
    """Test that qty is rounded down to step_size."""
    config = {
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "min_qty": "0.001",
                    "step_size": "0.001",
                    "tick_size": "0.01",
                    "min_notional": "5.0",
                }
            }
        }
    }
    fsm = OpenFlowFSM(cooldown_sec=0.1, config=config)

    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-rounding",
        why="test qty rounding",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "1.234",  # Should be rounded down to 1.234 (already multiple of 0.001)
            "order_type": "MARKET",
            "tif": "GTC",
            "price_ref": "50000.0",
        },
    )

    result = fsm.handle(cmd)

    assert result is not None
    assert result.op == "DEC"
    assert (
        result.pld["qty"] == "1.234"
    )  # Should remain as is since it's already multiple


def test_open_flow_qty_below_min():
    """Test rejection when qty is below min_qty."""
    config = {
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "min_qty": "0.1",  # Higher min_qty
                    "step_size": "0.001",
                    "tick_size": "0.01",
                    "min_notional": "5.0",
                }
            }
        }
    }
    fsm = OpenFlowFSM(cooldown_sec=0.1, config=config)

    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-min-qty",
        why="test min qty",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.05",  # Below min_qty
            "order_type": "MARKET",
            "tif": "GTC",
            "price_ref": "50000.0",
        },
    )

    result = fsm.handle(cmd)

    assert result is not None
    assert result.op == "ERR"
    assert result.verb == "OPEN"
    assert "below minimum" in result.pld["reason"]


def test_open_flow_market_min_notional():
    """Test rejection when MARKET order notional is below minimum."""
    config = {
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "min_qty": "0.001",
                    "step_size": "0.001",
                    "tick_size": "0.01",
                    "min_notional": "100.0",  # High min_notional
                }
            }
        }
    }
    fsm = OpenFlowFSM(cooldown_sec=0.1, config=config)

    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-market-notional",
        why="test market notional",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "1.0",
            "order_type": "MARKET",
            "tif": "GTC",
            "price_ref": "50.0",  # Low price, notional = 1.0 * 50.0 = 50.0 < 100.0
        },
    )

    result = fsm.handle(cmd)

    assert result is not None
    assert result.op == "ERR"
    assert result.verb == "OPEN"
    assert "estimated notional" in result.pld["reason"]


def test_open_flow_valid_limit_order():
    """Test valid LIMIT order generates DEC:OPEN."""
    config = {
        "trading": {
            "instruments": {
                "ETHUSDT": {
                    "symbol": "ETHUSDT",
                    "min_qty": "0.01",
                    "step_size": "0.01",
                    "tick_size": "0.01",
                    "min_notional": "5.0",
                }
            }
        }
    }
    fsm = OpenFlowFSM(cooldown_sec=0.1, config=config)

    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-002",
        why="open limit",
        idempotent_key="test-key-002",
        pld={
            "symbol": "ETHUSDT",
            "side": "SELL",
            "qty": "2.5",
            "price": "1500.00",
            "order_type": "LIMIT",
            "tif": "GTC",
        },
    )

    result = fsm.handle(cmd)

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "OPEN"
    assert Decimal(result.pld["qty"]) == Decimal("2.5")
    assert Decimal(result.pld["price"]) == Decimal("1500.00")
    assert fsm.state == State.DONE


def test_open_flow_guard_fail_missing_symbol():
    """Test guard failure: missing symbol → ERR."""
    fsm = OpenFlowFSM()

    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-003",
        why="bad request",
        idempotent_key="test-key-003",
        pld={
            "side": "BUY",
            "qty": "1.0",
        },
    )

    result = fsm.handle(cmd)

    assert result is not None
    assert result.op == "ERR"
    assert "missing symbol" in result.pld["reason"]
    assert fsm.state == State.ERROR
    assert fsm.get_metrics()["fsm_guard_rejects_total"] == 1


def test_open_flow_guard_fail_qty_out_of_bounds():
    """Test guard failure: qty < MIN_ORDER_QTY → ERR."""
    fsm = OpenFlowFSM()

    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-004",
        why="tiny qty",
        idempotent_key="test-key-004",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.0001",  # Below MIN_ORDER_QTY (0.001)
        },
    )

    result = fsm.handle(cmd)

    assert result is not None
    assert result.op == "ERR"
    assert "qty below minimum" in result.pld["reason"]
    assert fsm.get_metrics()["fsm_guard_rejects_total"] == 1


def test_open_flow_guard_fail_limit_without_price():
    """Test guard failure: LIMIT order without price → ERR."""
    fsm = OpenFlowFSM()

    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-005",
        why="limit no price",
        idempotent_key="test-key-005",
        pld={
            "symbol": "ETHUSDT",
            "side": "BUY",
            "qty": "1.0",
            "order_type": "LIMIT",
        },
    )

    result = fsm.handle(cmd)

    assert result is not None
    assert result.op == "ERR"
    assert "requires price" in result.pld["reason"]


def test_open_flow_guard_qty_step_rounding():
    """Test that qty is rounded down to step_size."""
    config = {
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "min_qty": "0.001",
                    "step_size": "0.001",
                    "tick_size": "0.01",
                    "min_notional": "5.0",
                }
            }
        }
    }
    fsm = OpenFlowFSM(cooldown_sec=0.1, config=config)

    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-step-rounding",
        why="qty rounding",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "1.0005",  # Should be rounded down to 1.000
            "order_type": "MARKET",
            "tif": "GTC",
            "price_ref": "50000.0",
        },
    )

    result = fsm.handle(cmd)

    assert result is not None
    assert result.op == "DEC"
    assert result.pld["qty"] == "1.000"  # Rounded down


def test_open_flow_guard_fail_min_notional():
    """Test guard failure: notional < MIN_NOTIONAL → ERR."""
    config = {
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "min_qty": "0.001",
                    "step_size": "0.001",
                    "tick_size": "0.01",
                    "min_notional": "10.0",
                }
            }
        }
    }
    fsm = OpenFlowFSM(config=config)

    cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-007",
        why="low notional",
        idempotent_key="test-key-007",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.001",
            "price": "5.00",  # notional = 0.005 < 10.0
            "order_type": "LIMIT",
        },
    )

    result = fsm.handle(cmd)

    assert result is not None
    assert result.op == "ERR"
    assert "notional" in result.pld["reason"]


def test_open_flow_guard_fail_cooldown():
    """Test guard failure: cooldown active → ERR."""
    config = {
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "min_qty": "0.001",
                    "step_size": "0.001",
                    "tick_size": "0.01",
                    "min_notional": "5.0",
                }
            }
        }
    }
    fsm = OpenFlowFSM(cooldown_sec=10.0, config=config)

    # First request succeeds
    cmd1 = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-008a",
        why="first",
        idempotent_key="test-key-008a",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "1.0",
        },
    )
    result1 = fsm.handle(cmd1)
    assert result1.op == "DEC"

    # Second request fails (cooldown) - don't reset, just try again
    cmd2 = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-rid-008b",
        why="second",
        idempotent_key="test-key-008b",
        pld={
            "symbol": "ETHUSDT",
            "side": "SELL",
            "qty": "2.0",
        },
    )
    result2 = fsm.handle(cmd2)
    assert result2.op == "ERR"
    assert "cooldown" in result2.pld["reason"]


def test_open_flow_non_open_message():
    """Test that non-CMD:OPEN messages return None."""
    fsm = OpenFlowFSM()

    msg = Message(
        op="EVT",
        verb="FILL",
        src="test",
        dst="execution_position",
        rid="test-rid-009",
        why="irrelevant",
    )

    result = fsm.handle(msg)
    assert result is None


def test_open_flow_metrics():
    """Test metrics tracking."""
    config = {
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "symbol": "BTCUSDT",
                    "min_qty": "0.001",
                    "step_size": "0.001",
                    "tick_size": "0.01",
                    "min_notional": "5.0",
                }
            }
        }
    }
    fsm = OpenFlowFSM(cooldown_sec=0.1, config=config)

    # 2 valid, 1 reject
    valid_cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="ep",
        rid="r1",
        why="ok",
        idempotent_key="k1",
        pld={"symbol": "BTC", "side": "BUY", "qty": "1.0"},
    )
    fsm.handle(valid_cmd)

    fsm.reset()
    fsm.handle(valid_cmd)  # Another valid

    invalid_cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="ep",
        rid="r2",
        why="bad",
        idempotent_key="k2",
        pld={"side": "BUY", "qty": "1.0"},
    )
    fsm.handle(invalid_cmd)

    metrics = fsm.get_metrics()
    assert metrics["fsm_open_decisions_total"] == 2
    assert metrics["fsm_guard_rejects_total"] == 1
