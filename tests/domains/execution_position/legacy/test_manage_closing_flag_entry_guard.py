import time

import pytest
import time
import types
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.legacy.fsm_manage import ManageFlowFSM, ManageState

pytestmark = pytest.mark.execpos_legacy



BASIC_CFG = {
    "brackets": {
        "enable": True,
        "sl": {"fixed_bps": 50},
        "tp": {"fixed_bps": 100},
    }
}


def make_entry_fill(ts_ms: int) -> Message:
    return Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="test",
        dst="manage",
        rid="rid-entry",
        pld={
            "symbol": "BTCUSDT",
            "qty": "1.0",
            "price": "50000",
            "side": "BUY",
            "order_type": "MARKET",
            "type": "MARKET",
            "ts": ts_ms,
        },
    )


def _stub_place_brackets(self, *_, **__):
    self.state = ManageState.TRACKING
    return None


def test_is_definitely_new_entry_requires_timestamp():
    fsm = ManageFlowFSM(config=BASIC_CFG)
    fsm._closing_position = True
    fsm._closing_position_ts = time.time()
    msg = make_entry_fill(ts_ms=int(time.time() * 1000))
    # Remove ts to simulate missing data
    msg.pld.pop("ts")

    release_flag, meta = fsm._is_definitely_new_entry(msg)

    assert release_flag is False
    assert meta["reason"] == "fill_ts_missing"


def test_stale_entry_fill_keeps_closing_flag():
    fsm = ManageFlowFSM(config=BASIC_CFG)
    fsm._auto_manage_enabled = True
    fsm._place_brackets = types.MethodType(_stub_place_brackets, fsm)
    fsm.state = ManageState.FLAT
    fsm._closing_position = True
    fsm._closing_position_ts = time.time()

    stale_ts_ms = int((fsm._closing_position_ts - 0.5) * 1000)
    msg = make_entry_fill(ts_ms=stale_ts_ms)

    release_flag, meta = fsm._is_definitely_new_entry(msg)
    assert release_flag is False
    assert meta["reason"] == "fill_before_closing_flag"

    fsm.handle(msg)

    assert fsm._closing_position is True


def test_new_entry_fill_clears_closing_flag():
    fsm = ManageFlowFSM(config=BASIC_CFG)
    fsm._auto_manage_enabled = True
    observed = {"during_place": None}

    def local_stub(self, *_, **__):
        observed["during_place"] = self._closing_position
        return _stub_place_brackets(self)

    fsm._place_brackets = types.MethodType(local_stub, fsm)
    fsm.state = ManageState.FLAT
    fsm._closing_position = True
    fsm._closing_position_ts = time.time()

    fresh_ts_ms = int((fsm._closing_position_ts + 0.5) * 1000)
    msg = make_entry_fill(ts_ms=fresh_ts_ms)

    original_helper = fsm._is_definitely_new_entry
    captured = {"calls": 0, "result": None}

    def tracking_helper(self, message):
        captured["calls"] += 1
        captured["result"] = original_helper(message)
        return captured["result"]

    fsm._is_definitely_new_entry = types.MethodType(tracking_helper, fsm)

    release_flag, meta = fsm._is_definitely_new_entry(msg)
    assert release_flag is True
    assert meta["reason"] == "fill_after_closing_flag"

    fsm.handle(msg)

    assert captured["calls"] > 0
    assert captured["result"][0] is True
    assert observed["during_place"] is False
    assert fsm._closing_position is False

