import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.truth_hardening import (
    attach_execution_truth_hardening,
)
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message


class _Bus:
    def __init__(self) -> None:
        self.listeners = {}

    def listen(self, topic, handler):
        self.listeners.setdefault(topic, []).append(handler)

    def emit(self, topic, payload=None, why="", data_ref=None, rid=None):
        return None


def _shadow_cfg(path: Path):
    return SimpleNamespace(
        observability=SimpleNamespace(
            shadow_journal=SimpleNamespace(
                enabled=True,
                path=str(path),
                schema_version="1.0.0",
                instrumentation_version="1.0.0",
                critical_events=list(DEFAULT_CRITICAL_EVENTS),
            )
        )
    )


def _read_jsonl(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _make_execpos_config(path: Path):
    cfg = MagicMock()
    cfg.execution = None
    cfg.trading = MagicMock()
    cfg.trading.execution = MagicMock()
    cfg.domains = MagicMock()
    cfg.domains.execution_position = MagicMock()
    cfg.binance_api = MagicMock()
    cfg.strategies = MagicMock()
    cfg.trading.execution.watchdog.ack_ttl_ms = 5000
    cfg.trading.execution.watchdog.fill_ttl_ms = 5000
    cfg.trading.execution.watchdog.check_interval_ms = 1000
    cfg.trading.execution.watchdog.rps_limit = 10
    cfg.trading.execution.anti_race_close_ms = 800
    cfg.trading.execution.cooldown_after_close_ms = 10_000
    cfg.trading.execution.fsm_periodic_cleanup_enabled = False
    cfg.domains.execution_position.fsm_open.idempotency_window_sec = 60
    guardian = cfg.domains.execution_position.guardian
    guardian.unified = True
    guardian.emit_tidy_event = True
    guardian.emit_tidy_monitoring_event = True
    guardian.poll_interval_ms = 500
    guardian.cleanup_ttl_ms = 6000
    guardian.symbol_cooldown_ms = 4000

    event_dedup = MagicMock()
    event_dedup.max_size = 100000
    event_dedup.ttl_ms = 86400000
    warm_state = MagicMock()
    warm_state.enabled = True
    warm_state.storage_path = str(path.with_name("warm_state.json"))
    warm_state.max_entries = 2000
    event_dedup.warm_state = warm_state
    cfg.domains.execution_position.event_dedup = event_dedup

    idempotent_cancel = MagicMock()
    idempotent_cancel.max_retries = 2
    cfg.domains.execution_position.idempotent_cancel = idempotent_cancel

    emergency = MagicMock()
    emergency.enabled = False
    emergency.wait_mode_bars = 2
    emergency.emergency_sl_bps = 100
    cfg.trading.execution.manage.emergency = emergency

    trailing = MagicMock()
    trailing.activation_pct = 0.003
    trailing.trail_pct = 0.006
    trailing.min_update_interval_sec = 5
    cfg.trailing = trailing

    cfg.trading.execution.manage.auto = True
    cfg.trading.execution.manage.brackets.enable = True
    cfg.trading.execution.manage.brackets.oco_emulation = True
    cfg.trading.execution.manage.brackets.sl.fixed_bps = 40
    cfg.trading.execution.manage.brackets.tp.fixed_bps = 80
    cfg.trading.execution.manage.brackets.offset_bps = 5

    btc_spec = MagicMock()
    btc_spec.tick_size = Decimal("0.01")
    btc_spec.step_size = Decimal("0.001")
    btc_spec.min_qty = Decimal("0.001")
    btc_spec.min_notional = Decimal("5.0")
    btc_spec.execution = MagicMock()
    btc_spec.execution.target_leverage = 20
    cfg.instruments = {"BTCUSDT": btc_spec}

    btc_asset_config = MagicMock()
    btc_asset_config.exit = MagicMock()
    btc_asset_config.exit.sl_pct = 0.02
    btc_asset_config.exit.max_hold_sec = 600
    btc_asset_config.take_profit = MagicMock()
    btc_asset_config.take_profit.tp_low_ratio = 0.5
    btc_asset_config.take_profit.tp_high_ratio = 1.0
    btc_asset_config.take_profit.partial_exit_pct = 0.5
    btc_asset_config.trailing_stop = MagicMock()
    btc_asset_config.trailing_stop.enabled = False
    cfg.strategies.aurora.assets = {"BTCUSDT": btc_asset_config}
    cfg.strategies.aurora.decision.bar_gating = None

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

    fb = cfg.domains.execution_position.fallback
    fb.policy = "fail_closed"
    fb.risk_reduction_pct = "0.5"
    fb.backoff_ms = [200, 500, 1000]

    cfg.trading.execution.exposure.leverage_defaults = {
        "__default__": 20, "BTCUSDT": 20}
    cfg.trading.execution.exposure.count_pending_orders = True
    cfg.trading.execution.exposure.exclude_reduce_only = True
    cfg.trading.risk = {
        "soft_limits": {
            "mode": "clip",
            "clip_min_notional_usdt": "10.0",
            "directional_ratio_max": "3.0",
            "side_exposure_usdt": "600.0",
            "margin_exposure_usdt": "1100.0",
        }
    }
    cfg.ops.storage.order_history_db = ":memory:"
    cfg.binance_api.testnet.api_key = ""
    cfg.binance_api.testnet.api_secret = ""
    cfg.binance_api.testnet.rest_url = ""
    cfg.binance_api.live.api_key = ""
    cfg.binance_api.live.api_secret = ""
    cfg.binance_api.live.rest_url = ""
    cfg.get_domain_mode.return_value = "testnet"
    cfg.trading.mode = "testnet"
    cfg.observability = _shadow_cfg(path).observability
    return cfg


def _trade_executed_payload(
    order_id: str,
    *,
    client_order_id: str | None = None,
    side: str = "buy",
    quantity: str = "0.01",
    price: str = "50000",
) -> dict:
    payload = {
        "symbol": "BTCUSDT",
        "side": side,
        "price": price,
        "quantity": quantity,
        "qty": quantity,
        "venue": "binance",
        "orderId": order_id,
    }
    if client_order_id is not None:
        payload["clientOrderId"] = client_order_id
        payload["client_order_id"] = client_order_id
    return payload


def test_shared_trade_executed_dedupe_suppresses_cross_origin_duplicate_before_callbacks(tmp_path):
    path = tmp_path / "journal.jsonl"
    config = ConfigLoader().load_config()
    config.observability.shadow_journal.enabled = True
    config.observability.shadow_journal.path = str(path)
    config.observability.shadow_journal.critical_events = list(
        DEFAULT_CRITICAL_EVENTS)
    config.domains.execution_position.event_dedup.warm_state.storage_path = str(
        tmp_path / "warm_state.json"
    )

    fsm = FSMCore()
    attach_shadow_journal(fsm, config)
    attach_execution_truth_hardening(fsm, config)

    seen = []
    fsm.listen("EVT:TRADE_EXECUTED",
               lambda msg: seen.append(msg.pld["orderId"]))

    payload = _trade_executed_payload(
        "12345",
        client_order_id="ENTRY-BTCUSDT-1",
    )

    fsm.emit("EVT:TRADE_EXECUTED", payload=payload,
             why="WS_ORDER_UPDATE_FILLED", rid="rid-1")
    fsm.emit("EVT:TRADE_EXECUTED", payload=payload,
             why="polling_fill", rid="rid-1")

    assert seen == ["12345"]

    records = _read_jsonl(path)
    assert len([r for r in records if r["event_name"]
               == "EVT:TRADE_EXECUTED"]) == 2
    suppressed = [r for r in records if r["event_name"]
                  == "HARDENING:TRADE_EXECUTED_SUPPRESSED"]
    assert len(suppressed) == 1
    assert any(r["suspected_duplicate"]
               is True for r in records if r["event_name"] == "EVT:TRADE_EXECUTED")


def test_shared_trade_executed_dedupe_allows_distinct_orders(tmp_path):
    path = tmp_path / "journal.jsonl"
    config = ConfigLoader().load_config()
    config.observability.shadow_journal.enabled = True
    config.observability.shadow_journal.path = str(path)
    config.observability.shadow_journal.critical_events = list(
        DEFAULT_CRITICAL_EVENTS)
    config.domains.execution_position.event_dedup.warm_state.storage_path = str(
        tmp_path / "warm_state.json"
    )

    fsm = FSMCore()
    attach_shadow_journal(fsm, config)
    attach_execution_truth_hardening(fsm, config)

    seen = []
    fsm.listen("EVT:TRADE_EXECUTED",
               lambda msg: seen.append(msg.pld["orderId"]))

    payload_a = _trade_executed_payload(
        "12345",
        client_order_id="ENTRY-BTCUSDT-1",
    )
    payload_b = _trade_executed_payload(
        "12346",
        client_order_id="ENTRY-BTCUSDT-2",
        quantity="0.02",
        price="50010",
    )

    fsm.emit("EVT:TRADE_EXECUTED", payload=payload_a,
             why="WS_ORDER_UPDATE_FILLED", rid="rid-1")
    fsm.emit("EVT:TRADE_EXECUTED", payload=payload_b,
             why="polling_fill", rid="rid-2")

    assert seen == ["12345", "12346"]
    records = _read_jsonl(path)
    assert not [r for r in records if r["event_name"]
                == "HARDENING:TRADE_EXECUTED_SUPPRESSED"]


def test_position_tracking_only_applies_duplicate_fill_once(tmp_path):
    path = tmp_path / "journal.jsonl"
    config = ConfigLoader().load_config()
    config.observability.shadow_journal.enabled = True
    config.observability.shadow_journal.path = str(path)
    config.observability.shadow_journal.critical_events = list(
        DEFAULT_CRITICAL_EVENTS)
    config.domains.execution_position.event_dedup.warm_state.storage_path = str(
        tmp_path / "warm_state.json"
    )

    fsm = FSMCore()
    tracker = PositionTracking(fsm, config)

    payload = {
        "symbol": "BTCUSDT",
        "orderId": "99887",
        "clientOrderId": "ENTRY-BTCUSDT-PT",
        "client_order_id": "ENTRY-BTCUSDT-PT",
        "side": "buy",
        "price": "50000",
        "quantity": "0.01",
        "qty": "0.01",
        "ts": 1710000000000,
        "fees": "0",
        "venue": "binance_futures",
    }

    with patch("apps.reference.domains.position_tracking.position_tracking.wal.append", return_value="wal-ok"):
        fsm.emit("EVT:TRADE_EXECUTED", payload=payload,
                 why="WS_ORDER_UPDATE_FILLED", rid="rid-pt-1")
        fsm.emit("EVT:TRADE_EXECUTED", payload=payload,
                 why="polling_fill", rid="rid-pt-1")

    assert tracker._positions["BTCUSDT"]["quantity"] == Decimal("0.01")
    records = _read_jsonl(path)
    assert len([r for r in records if r["event_name"] ==
               "HARDENING:TRADE_EXECUTED_SUPPRESSED"]) == 1


def test_execpos_cmd_close_guard_suppresses_repeated_close_and_allows_after_state_change(tmp_path):
    path = tmp_path / "journal.jsonl"
    config = _make_execpos_config(path)

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"):
        bus = _Bus()
        fsm = ExecPosFSM(config=config, fsm=bus, shadow_mode=True)
        fsm.adapter = None
        fsm._latest_portfolio_state = {
            "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.010"}]
        }

        msg = Message(
            op="CMD",
            verb="CLOSE",
            src="decision_making",
            dst="execution_position",
            rid="rid-close-1",
            pld={"symbol": "BTCUSDT", "reason": "manual_close"},
            why="manual_close",
        )

        first = fsm.handle(msg)
        second = fsm.handle(msg)

        fsm._latest_portfolio_state = {
            "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.005"}]
        }
        third = fsm.handle(msg)

    assert first is not None and first.op == "DEC" and first.verb == "CLOSE"
    assert second is None
    assert third is not None and third.op == "DEC" and third.verb == "CLOSE"

    records = _read_jsonl(path)
    suppressed = [r for r in records if r["event_name"]
                  == "HARDENING:CMD_CLOSE_SUPPRESSED"]
    assert len(suppressed) == 1
    assert "duplicate_cmd_close_same_effective_state" in suppressed[0]["notes"]
