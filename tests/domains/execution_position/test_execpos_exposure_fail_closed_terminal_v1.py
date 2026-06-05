import os
from decimal import Decimal

import pytest

from vfoundation.core.protocol import Message
from vfoundation.dr import wal


@pytest.fixture(autouse=True)
def _isolate_wal_dir(tmp_path):
    from vfoundation.dr import wal as wal_module

    old_dir = getattr(wal_module, "WAL_DIR", None)
    wal_dir = tmp_path / "wal"
    wal.set_wal_dir(wal_dir)
    wal.reset()
    try:
        yield
    finally:
        if old_dir is not None:
            wal.set_wal_dir(old_dir)
        wal.reset()


@pytest.fixture(autouse=True)
def _isolate_order_log(tmp_path, monkeypatch):
    # Prevent tests from polluting repo logs/order_log_v1.jsonl
    from apps.reference.telemetry.order_logger import order_logger

    old_log_file = order_logger.log_file
    log_file = tmp_path / "order_log_v1.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    order_logger.log_file = log_file

    # Avoid schema validation unless suite explicitly wants it.
    monkeypatch.setenv("ENV", "")
    try:
        yield
    finally:
        order_logger.log_file = old_log_file


def _portfolio_ok(equity: str = "10000"):
    import time

    return {
        "positions_last_ts_ms": int(time.time() * 1000),
        "equity_free_usdt": equity,
        "open_positions_margin_usd": "0",
        "positions": [],
    }


def test_fail_closed_blocks_and_returns_err_and_writes_wal(fsm_harness):
    fsm, _bus, _cfg = fsm_harness

    # No equity -> EQUITY_UNKNOWN
    fsm._latest_portfolio_state = {}

    rid = "rid_fail_closed_1"
    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid=rid,
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.01",
            "price_ref": "20000",
            "order_type": "MARKET",
            "idempotent_key": "k1",
        },
        why="test",
    )

    res = fsm.handle(msg)
    assert res is not None
    assert res.op == "ERR"
    assert res.verb == "OPEN"
    assert res.pld.get("reason") == "EQUITY_UNKNOWN"
    assert res.pld.get("symbol") == "BTCUSDT"
    assert res.pld.get("side") == "BUY"

    # Must not reserve on blocked attempt
    assert len(fsm.exposure_guard.state.reservations) == 0
    assert len(fsm.exposure_guard.state.pending_exposure) == 0

    events = wal.read_all()
    assert any(e.get("op") == "ERR" and e.get("verb") == "OPEN" and e.get("rid") == rid for e in events)


def test_passed_exposure_check_reserves_with_symbol_and_side(fsm_harness):
    fsm, _bus, _cfg = fsm_harness
    fsm._latest_portfolio_state = _portfolio_ok("10000")

    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid="rid_ok_1",
        pld={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "qty": "0.01",
            "price_ref": "20000",
            "order_type": "MARKET",
            "idempotent_key": "k_ok",
        },
        why="test",
    )

    exposure_err = fsm._check_exposure_fail_closed(msg)
    assert exposure_err is None

    assert "k_ok" in fsm.exposure_guard.state.pending_exposure
    item = fsm.exposure_guard.state.pending_exposure["k_ok"]
    assert item.get("symbol") == "BTCUSDT"
    assert item.get("side") == "SELL"
    assert item.get("notional") == Decimal("200")


def test_exposure_check_exception_is_fail_closed_and_writes_wal(fsm_harness, monkeypatch):
    fsm, _bus, _cfg = fsm_harness
    fsm._latest_portfolio_state = _portfolio_ok("10000")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(fsm.exposure_guard, "can_open", boom)

    rid = "rid_exc_1"
    msg = Message(
        op="CMD",
        verb="OPEN",
        src="decision_making",
        dst="execution_position",
        rid=rid,
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.01",
            "price_ref": "20000",
            "order_type": "MARKET",
            "idempotent_key": "k_exc",
        },
        why="test",
    )

    res = fsm._check_exposure_fail_closed(msg)
    assert res is not None
    assert res.op == "ERR"
    assert res.verb == "OPEN"
    assert res.pld.get("reason") == "EXPOSURE_CHECK_ERROR"

    events = wal.read_all()
    assert any(e.get("op") == "ERR" and e.get("verb") == "OPEN" and e.get("rid") == rid for e in events)


def test_order_log_has_no_empty_symbol_records():
    import json
    from apps.reference.telemetry.order_logger import order_logger

    log_file = order_logger.log_file
    # File may not exist if no order_logger.write occurred in this test process
    if not log_file.exists():
        return

    for line in log_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("source_fsm") == "ExposureGuard":
            assert o.get("symbol") not in (None, "")
