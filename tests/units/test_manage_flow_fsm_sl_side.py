"""
Validate that ManageFlowFSM places SL with the OPPOSITE side to close positions.
"""

import pytest
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM


def test_sl_side_is_opposite_for_long():
    # Config enables auto-manage and brackets
    cfg = {
        "trading": {
            "execution": {
                "manage": {
                    "auto": True,
                    "brackets": {
                        "enable": True,
                        "sl": {"fixed_bps": 50},
                        "tp": {"fixed_bps": 100},
                    },
                }
            }
        }
    }
    fsm = ManageFlowFSM(config=cfg)

    # Simulate FILL that opens a long position
    fill_msg = Message(
        op="EVT",
        verb="FILL",
        src="test",
        dst="execution_position",
        rid="RID-1",
        pld={"symbol": "SOLUSDT", "qty": "1.0",
             "price": "100.0", "side": "BUY"},
    )

    dec = fsm.handle(fill_msg)
    assert dec is not None, "ManageFlowFSM should emit DEC:BATCH for brackets"
    assert dec.op == "DEC" and dec.verb == "BATCH", "Expected DEC:BATCH for bracket orders"
    
    # Extract SL message from batch
    messages = dec.pld.get("messages", [])
    sl_msg = next((m for m in messages if m.get("why") == "SL bracket"), None)
    assert sl_msg is not None, "Batch should contain SL bracket"
    assert sl_msg.get("pld", {}).get("order_type") == "STOP_MARKET", "SL must be STOP_MARKET"
    assert sl_msg.get("pld", {}).get("reduceOnly") is True, "SL must be reduceOnly"
    assert sl_msg.get("pld", {}).get("side") == "SELL", "SL side must be opposite to BUY position"


def test_sl_side_is_opposite_for_short():
    cfg = {
        "trading": {
            "execution": {
                "manage": {
                    "auto": True,
                    "brackets": {
                        "enable": True,
                        "sl": {"fixed_bps": 50},
                        "tp": {"fixed_bps": 100},
                    },
                }
            }
        }
    }
    fsm = ManageFlowFSM(config=cfg)

    fill_msg = Message(
        op="EVT",
        verb="FILL",
        src="test",
        dst="execution_position",
        rid="RID-2",
        pld={"symbol": "ETHUSDT", "qty": "2.0",
             "price": "3000.0", "side": "SELL"},
    )

    dec = fsm.handle(fill_msg)
    assert dec is not None and dec.op == "DEC" and dec.verb == "BATCH"
    
    # Extract SL message from batch
    messages = dec.pld.get("messages", [])
    sl_msg = next((m for m in messages if m.get("why") == "SL bracket"), None)
    assert sl_msg is not None, "Batch should contain SL bracket"
    assert sl_msg.get("pld", {}).get("order_type") == "STOP_MARKET"
    assert sl_msg.get("pld", {}).get("reduceOnly") is True
    assert sl_msg.get("pld", {}).get("side") == "BUY", "SL side must be opposite to SELL position"
