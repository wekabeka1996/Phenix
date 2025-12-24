import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from vfoundation.core.protocol import Message
from vfoundation.dr import wal


@pytest.fixture(autouse=True)
def _isolate_wal_dir(tmp_path):
    wal_dir = tmp_path / "wal"
    wal.set_wal_dir(wal_dir)
    wal.reset()
    yield


def _make_cfg() -> MagicMock:
    cfg = MagicMock()

    # Watchdog / open-flow config accessed during ExecPosFSM init
    cfg.trading.execution.watchdog.ack_ttl_ms = 5000
    cfg.trading.execution.watchdog.fill_ttl_ms = 5000
    cfg.domains.execution_position.fsm_open.idempotency_window_sec = 60

    # ExposureGuard config
    eg = cfg.domains.execution_position.exposure_guard
    eg.max_equity_utilization_pct = "95.0"
    eg.max_portfolio_fraction = "1.0"
    eg.max_long_utilization_pct = "100.0"
    eg.max_short_utilization_pct = "100.0"
    eg.max_directional_ratio = "5.0"
    eg.max_concentration_pct = "20.0"
    eg.pending_ttl_sec = 5
    eg.post_fill_ttl_sec = 5
    eg.stale_ttl_sec = 10

    # Leverage defaults required by ExposureGuard.resolve_symbol_leverage()
    cfg.trading.execution.exposure.leverage_defaults = {"__default__": 20, "BTCUSDT": 20}

    # Soft limits required by ExposureGuard._load_soft_limit_config() contract
    cfg.trading.risk = {
        "soft_limits": {
            "mode": "clip",
            "clip_min_notional_usdt": "10.0",
            "directional_ratio_max": "3.0",
            "side_exposure_usdt": "600.0",
            "margin_exposure_usdt": "1100.0",
        }
    }

    # Instruments
    btc_spec = MagicMock()
    btc_spec.tick_size = Decimal("0.01")
    btc_spec.step_size = Decimal("0.001")
    btc_spec.min_qty = Decimal("0.001")
    btc_spec.min_notional = Decimal("5.0")
    cfg.instruments.get.side_effect = lambda k, default=None: {"BTCUSDT": btc_spec}.get(k, default)

    # Storage mock for OrderLedger/guardian
    storage_mock = MagicMock()
    storage_mock.order_history_db = ":memory:"
    cfg.ops.storage = storage_mock

    # Prevent real adapter init (shadow mode)
    cfg.binance_api.testnet.api_key = ""
    cfg.binance_api.testnet.api_secret = ""
    cfg.binance_api.testnet.rest_url = ""
    cfg.binance_api.live.api_key = ""
    cfg.binance_api.live.api_secret = ""
    cfg.binance_api.live.rest_url = ""

    # Some configs are accessed via cfg.trading.get in older tests; provide safe default
    cfg.trading.get = lambda key, default=None: default

    return cfg


def test_fail_closed_err_open_is_written_to_wal_sync():
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

    cfg = _make_cfg()

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"):
        fsm = ExecPosFSM(config=cfg, fsm=MagicMock(), shadow_mode=True)

    # Force equity missing -> EQUITY_UNKNOWN
    fsm._latest_portfolio_state = {}

    rid = "rid_int_1"
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
            "idempotent_key": "k_int_1",
        },
        why="test",
    )

    res = fsm.handle(msg)
    assert res is not None
    assert res.op == "ERR" and res.verb == "OPEN"
    assert res.pld.get("reason") == "EQUITY_UNKNOWN"

    # Must not reserve on blocked attempt
    assert len(fsm.exposure_guard.state.reservations) == 0
    assert len(fsm.exposure_guard.state.pending_exposure) == 0

    # Must persist to WAL synchronously
    ev = wal.read_all()
    assert any(e.get("op") == "ERR" and e.get("verb") == "OPEN" and e.get("rid") == rid for e in ev)
