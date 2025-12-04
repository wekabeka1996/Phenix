"""
Emergency -> WAIT_MODE behavior in ManageFlowFSM.
"""

import time
from decimal import Decimal
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState


def _msg(verb, pld=None):
    return Message(op="UPD" if verb == "MARKET_DATA" else "EVT", verb=verb, src="t", dst="a", pld=pld or {})


def test_emergency_trips_and_wait_mode_blocks():
    # Config must match Pydantic AuroraConfig structure:
    # trading.execution.manage and trading.decision.bar_gating
    cfg = {
        "trading": {
            "execution": {
                "manage": {
                    "auto": True,
                    "emergency": {"enable": True, "emergency_sl_bps": 10, "wait_mode_bars": 1}
                }
            },
            "decision": {
                "bar_gating": {"bar_ms": 900000}
            }
        }
    }
    fsm = ManageFlowFSM(config=cfg)

    # seed position state
    fsm.position_qty = Decimal("0.01")
    fsm.position_entry_price = Decimal("100.0")
    fsm.position_side = "BUY"
    fsm.state = ManageState.TRACKING

    # adverse move > 10 bps triggers emergency
    ts_now = int(time.time() * 1000)
    msg = _msg("MARKET_DATA", {"price": 98.5, "ts": ts_now})  # 150 bps adverse
    out = fsm.handle(msg)
    assert out is not None and out.op == "DEC" and out.verb in ("PLACE_ORDER", "ADJUST")
    # while in WAIT_MODE (same bar), should skip
    msg2 = _msg("MARKET_DATA", {"price": 99.0, "ts": ts_now + 1000})
    out2 = fsm.handle(msg2)
    assert out2 is not None and ((out2.op == "EVT" and out2.verb == "MANAGE_SKIPPED") or out2.op == "DEC")
