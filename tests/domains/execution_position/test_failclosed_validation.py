from __future__ import annotations
import pytest
from vfoundation.core.protocol import Message
from decimal import Decimal

pytest_plugins = ("tests.domains.execution_position.conftest",)

def create_intent(rid, suffix, order_block):
    return Message(
        op="EVT", verb="TRADE_INTENT_PROPOSED",
        src="dm", dst="*",
        pld={
            "rid": f"RID-{suffix}",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order": order_block,
            "idempotent_key": f"KEY-{suffix}",
            "valid_for_ms": 10000,
        },
        why=f"test_{suffix}"
    )

def test_missing_order_type_rejected(fsm_harness):
    fsm, bus, _ = fsm_harness
    msg = create_intent("MISSING-TYPE", "MISSING-TYPE", {
        "qty": "0.1",
        # Missing order_type
    })
    
    fsm._on_trade_intent_proposed(msg)
    
    rejects = [e for e in bus.events if e[0] == "EVT:TRADE_INTENT_REJECTED"]
    assert len(rejects) == 1
    why = rejects[0][1][0].get("why", "")
    assert "NRR-INTENT-MISSING-ORDER_TYPE" in why

def test_limit_missing_price_rejected(fsm_harness):
    fsm, bus, _ = fsm_harness
    msg = create_intent("LIMIT-NO-PRICE", "LIMIT-NO-PRICE", {
        "qty": "0.1",
        "order_type": "LIMIT",
        "tif": "GTC"
        # Missing price
    })
    
    fsm._on_trade_intent_proposed(msg)
    
    rejects = [e for e in bus.events if e[0] == "EVT:TRADE_INTENT_REJECTED"]
    assert len(rejects) == 1
    assert "NRR-INTENT-MISSING-PRICE" in rejects[0][1][0]["why"]

def test_limit_missing_tif_rejected(fsm_harness):
    fsm, bus, _ = fsm_harness
    msg = create_intent("LIMIT-NO-TIF", "LIMIT-NO-TIF", {
        "qty": "0.1",
        "order_type": "LIMIT",
        "price": "10000"
        # Missing tif
    })
    
    fsm._on_trade_intent_proposed(msg)
    
    rejects = [e for e in bus.events if e[0] == "EVT:TRADE_INTENT_REJECTED"]
    assert len(rejects) == 1
    assert "NRR-INTENT-MISSING-TIF" in rejects[0][1][0]["why"]

def test_market_with_tif_rejected(fsm_harness):
    fsm, bus, _ = fsm_harness
    msg = create_intent("MARKET-WITH-TIF", "MARKET-WITH-TIF", {
        "qty": "0.1",
        "order_type": "MARKET",
        "tif": "GTC" # Forbidden for MARKET
    })
    
    fsm._on_trade_intent_proposed(msg)
    
    rejects = [e for e in bus.events if e[0] == "EVT:TRADE_INTENT_REJECTED"]
    assert len(rejects) == 1
    assert "NRR-INTENT-INVALID-TIF" in rejects[0][1][0]["why"]

def test_valid_market_success(fsm_harness):
    fsm, bus, _cfg = fsm_harness
    # Prepare dependencies
    fsm._latest_portfolio_state = {"equity_free_usdt": "10000", "positions": [], "positions_last_ts_ms": 9e12}
    fsm.exposure_guard.on_portfolio(fsm._latest_portfolio_state)

    msg = create_intent("VALID-MARKET", "VALID-MARKET", {
        "qty": "0.1",
        "order_type": "MARKET",
        # No TIF, No Price
    })
    
    fsm._on_trade_intent_proposed(msg)
    
    opens = [e for e in bus.events if e[0] == "DEC:OPEN"]
    assert len(opens) == 1

def test_valid_limit_success(fsm_harness):
    fsm, bus, _cfg = fsm_harness
    # Prepare dependencies
    fsm._latest_portfolio_state = {"equity_free_usdt": "10000", "positions": [], "positions_last_ts_ms": 9e12}
    fsm.exposure_guard.on_portfolio(fsm._latest_portfolio_state)

    msg = create_intent("VALID-LIMIT", "VALID-LIMIT", {
        "qty": "0.1",
        "order_type": "LIMIT",
        "price": "1000.0",
        "tif": "GTC",
        "price_ref": "1000.0" # needed for exposure guard check
    })
    
    fsm._on_trade_intent_proposed(msg)
    
    opens = [e for e in bus.events if e[0] == "DEC:OPEN"]
    assert len(opens) == 1
    payload = opens[0][1][0]
    assert payload["order_type"] == "LIMIT"
    assert payload["price"] == "1000.0"
    assert payload["tif"] == "GTC"
