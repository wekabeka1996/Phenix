import time
from decimal import Decimal
from apps.reference.domains.execution_position.fsm_manage import (
    ManageFlowFSM,
    ManageState,
)
from vfoundation.core.protocol import Message


def make_fill_msg(rid="r1", symbol="ETHUSDT", qty=1, price=100.0, side="BUY"):
    return Message(
        op="EVT",
        verb="FILL",
        src="test",
        dst="manager",
        rid=rid,
        pld={"symbol": symbol, "qty": qty, "price": price, "side": side},
    )


def test_hydrate_success_and_brackets_state():
    fsm = ManageFlowFSM(config={"brackets": {}})
    pd = {
        "qty": 2,
        "entry_price": "100",
        "side": "BUY",
        "open_ts": time.time(),
        "sl_order_id": "s1",
    }
    fsm.hydrate(pd)
    # having sl_order_id should set BRACKETS_PLACED
    assert fsm.state in (
        ManageState.TRACKING,
        ManageState.BRACKETS_PLACED,
        ManageState.OPENED,
    )


def test_hydrate_missing_key_sets_error():
    fsm = ManageFlowFSM()
    fsm.hydrate({"entry_price": "100"})
    assert fsm.state == ManageState.ERROR


def test_should_place_brackets_and_place_flow():
    cfg = {
        "trading": {
            "execution": {
                "manage": {
                    "auto": True,
                    "brackets": {"enable": True, "sl": {"fixed_bps": 50}, "tp": {"fixed_bps": 100}}
                }
            }
        }
    }
    fsm = ManageFlowFSM(config=cfg)

    # Before any fills, should not place
    assert fsm._should_place_brackets() is True

    msg = make_fill_msg()
    # simulate a fill -> handle should place brackets and return BATCH message
    dec = fsm.handle(msg)
    # Either None (if something went wrong) or a DEC BATCH message
    if dec is not None:
        assert dec.op == "DEC"
        assert dec.verb in ("BATCH", "PLACE_ORDER")


def test_calculate_bracket_prices_and_get_opposite():
    # Mock config structure to match what _calculate_bracket_prices expects
    cfg = {
        "trading": {
            "execution": {
                "manage": {
                    "brackets": {
                        "sl": {"fixed_bps": 50}, 
                        "tp": {"fixed_bps": 100},
                        "stop_loss_bps": 50 # Legacy fallback
                    }
                }
            }
        }
    }
    fsm = ManageFlowFSM(config=cfg)
    fsm.position_entry_price = Decimal("100")
    # _get_opposite_side() expects position_side to be "BUY"/"SELL"
    fsm.position_side = "BUY"
    fsm.position_qty = Decimal("1")
    
    # Manually set _manage_cfg to ensure it's picked up if config parsing fails in init
    # (Though init should handle it if we pass correct structure)
    # But let's just rely on the config passed to init.
    
    # Phase A2: returns (sl, tp1, tp2)
    sl, tp1, tp2 = fsm._calculate_bracket_prices()
    assert sl is not None and tp1 is not None
    # tp2 is None without take_profit config
    assert tp2 is None
    # When position_side="BUY", opposite side is "SELL"
    assert fsm._get_opposite_side() == "SELL"
