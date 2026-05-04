from __future__ import annotations

import time
from collections import defaultdict
from decimal import Decimal
from typing import Any, Callable

import pytest
from vfoundation.core.protocol import Message

pytest_plugins = ("tests.domains.execution_position.conftest",)

def test_e2e_trade_intent_proposed_leads_to_execpos_dec_open(monkeypatch, fsm_harness):
    """Smoke E2E: Intent -> ExecPosFSM -> CMD:OPEN (internal) -> DEC:OPEN."""

    execpos_fsm, bus, _cfg = fsm_harness

    # ExecPosFSM passes its own internal portfolio_state into ExposureGuard.can_open().
    # Seed that internal state to avoid fail-closed EQUITY_UNKNOWN.
    portfolio_state = {
        "positions_last_ts_ms": 9999999999999,
        "equity_free_usdt": "10000",
        "open_positions_margin_usd": "0",
        "positions": [],
    }
    execpos_fsm._latest_portfolio_state = dict(portfolio_state)
    execpos_fsm.exposure_guard.on_portfolio(dict(portfolio_state))

    # Make sure leverage defaults exist for reserve/can_open path.
    _cfg.trading.execution.exposure.leverage_defaults = {"__default__": 20, "BTCUSDT": 20}

    # Construct the event message
    intent_msg = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="*",
        pld={
            "rid": "RID-E2E-INTENT-1",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order": {
                "order_type": "MARKET",  # ORDER-POLICY-01: explicit order_type required
                "qty": str(Decimal("0.01")),
                "price": str(Decimal("1000")),
                "price_ref": str(Decimal("1000")),
                "reduce_only": False,
            },
            "idempotent_key": "K-E2E-INTENT-1",
            "valid_for_ms": 10000,
        },
        why="e2e_intent",
    )
    
    # Manually trigger handler because FakeBus doesn't implement dispatch
    execpos_fsm._on_trade_intent_proposed(intent_msg)

    # Check for DEC:OPEN emission on the bus
    # bus.events is list of (topic, args, kwargs)
    dec_open_events = [e for e in bus.events if e[0] == "DEC:OPEN"]
    
    # Debug: print events if failed
    if not dec_open_events:
        print(f"Bus Events: {bus.events}")

    assert dec_open_events, "Expected DEC:OPEN event on bus"
    
    # Optional: Check details of the event
    # args[0] is payload
    topic, args, kwargs = dec_open_events[0]
    payload = args[0]
    assert payload["symbol"] == "BTCUSDT"
    assert payload["side"] == "BUY"


def test_e2e_reduce_only_leads_to_dec_close(monkeypatch, fsm_harness):
    """Smoke E2E: Reduce-Only Intent -> ExecPosFSM -> CMD:CLOSE (internal) -> DEC:CLOSE."""
    
    execpos_fsm, bus, _cfg = fsm_harness
    
    # Needed for CloseFlow?
    # CloseFlow checks if position exists. In shadow mode, it might be permissive or strict.
    # CloseFlowFSM.handle checks msg.verb == "CLOSE".
    # And emits DEC:CLOSE.
    
    # Construct the event message
    intent_msg = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="*",
        pld={
            "rid": "RID-E2E-CLOSE-1",
            "instrument": "BTCUSDT",
            "side": "SELL",
            "reduce_only": True,
            "order": {
                "qty": str(Decimal("0.01")),
                "reduce_only": True,
            },
            "idempotent_key": "K-E2E-CLOSE-1",
        },
        why="e2e_close",
    )

    # Manually trigger handler
    execpos_fsm._on_trade_intent_proposed(intent_msg)

    # Check for DEC:CLOSE emission
    dec_close_events = [e for e in bus.events if e[0] == "DEC:CLOSE"]
    
    if not dec_close_events:
        print(f"Bus Events: {bus.events}")
        
    assert dec_close_events, "Expected DEC:CLOSE event on bus"
    
    topic, args, kwargs = dec_close_events[0]
    payload = args[0]
    assert payload["symbol"] == "BTCUSDT"
    assert payload["reduce_only"] is True
