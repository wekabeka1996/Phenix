import pytest
import time
from decimal import Decimal
from vfoundation.core.protocol import Message


def test_ack_portfolio_fill_order(fsm_harness):
    """Sequence: ACK -> PORTFOLIO_UPDATE -> FILL"""
    fsm, bus, cfg = fsm_harness

    # Simulate ACK
    ack_pld = {"orderId": "ord_1", "symbol": "BTCUSDT", "rid": "r1"}
    ack_msg = Message(op="EVT", verb="ORDER_ACK",
                      src="adapter", dst="exec", pld=ack_pld)
    fsm._on_order_ack(ack_msg)
    assert "ack_ord_1_BTCUSDT" in fsm._processed_events

    # Simulate Portfolio Update
    port_pld = {"total_equity": "10000", "available_margin": "5000"}
    port_msg = Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED",
                       src="adapter", dst="exec", pld=port_pld)
    fsm._on_portfolio_state_updated(port_msg)
    assert fsm._latest_portfolio_state["total_equity"] == "10000"

    # Simulate FILL
    fill_pld = {"orderId": "ord_1", "symbol": "BTCUSDT",
                "quantity": "0.1", "rid": "r1"}
    fill_msg = Message(op="EVT", verb="ORDER_FILL",
                       src="adapter", dst="exec", pld=fill_pld)
    fsm._on_order_fill(fill_msg)
    # DEF-E18: key now includes cumQty+updateTime suffix when no tradeId present
    assert any(k.startswith("fill_ord_1_BTCUSDT")
               for k in fsm._processed_events)


def test_fill_before_ack_out_of_order(fsm_harness):
    """Sequence: FILL -> ACK (out-of-order)"""
    fsm, bus, cfg = fsm_harness

    # FILL arrived before ACK
    fill_pld = {"orderId": "ord_2", "symbol": "BTCUSDT",
                "quantity": "0.1", "rid": "r2"}
    fill_msg = Message(op="EVT", verb="ORDER_FILL",
                       src="adapter", dst="exec", pld=fill_pld)
    fsm._on_order_fill(fill_msg)
    # DEF-E18: key now includes cumQty+updateTime suffix when no tradeId present
    assert any(k.startswith("fill_ord_2_BTCUSDT")
               for k in fsm._processed_events)

    # ACK arrived later
    ack_pld = {"orderId": "ord_2", "symbol": "BTCUSDT", "rid": "r2"}
    ack_msg = Message(op="EVT", verb="ORDER_ACK",
                      src="adapter", dst="exec", pld=ack_pld)
    fsm._on_order_ack(ack_msg)
    assert "ack_ord_2_BTCUSDT" in fsm._processed_events
    # Both should be processed without error


def test_portfolio_lagging_after_open(fsm_harness):
    """Simulate Portfolio lag: OPEN sent, but portfolio not updated yet"""
    fsm, bus, cfg = fsm_harness

    # Initial portfolio
    port_pld = {"total_equity": "1000", "available_margin": "500"}
    fsm._on_portfolio_state_updated(
        Message(op="EVT", verb="P", src="adapter", dst="exec", pld=port_pld))

    # Trigger OPEN (mocked exposure guard check)
    # We want to see if ExposureGuard correctly uses postfill_reservations or if it's lagging.
    # In ExecPosFSM._on_order_fill, it adds to postfill_reservations.

    fill_pld = {"orderId": "ord_lag", "symbol": "BTCUSDT",
                "quantity": "0.5", "rid": "rlag"}
    fill_msg = Message(op="EVT", verb="ORDER_FILL",
                       src="adapter", dst="exec", pld=fill_pld)
    fsm._on_order_fill(fill_msg)

    # Check if exposure guard now has the reservation
    assert any(
        "ord_lag" in k for k in fsm.exposure_guard.state.postfill_reservations.keys())


def test_duplicate_fill_idempotency(fsm_harness):
    """Duplicate FILL event (same event id / orderId)"""
    fsm, bus, cfg = fsm_harness

    fill_pld = {"orderId": "ord_dup", "symbol": "BTCUSDT",
                "quantity": "0.1", "rid": "rdup"}
    fill_msg = Message(op="EVT", verb="ORDER_FILL",
                       src="adapter", dst="exec", pld=fill_pld)

    # First processing
    fsm._on_order_fill(fill_msg)
    count1 = len(fsm.exposure_guard.state.postfill_reservations)

    # Duplicate processing
    fsm._on_order_fill(fill_msg)
    count2 = len(fsm.exposure_guard.state.postfill_reservations)

    # Should NOT increase reservations or process logic again
    assert count1 == count2
    # DEF-E18: key now includes cumQty+updateTime suffix when no tradeId present
    assert any(k.startswith("fill_ord_dup_BTCUSDT")
               for k in fsm._processed_events)
