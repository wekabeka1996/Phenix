import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from decimal import Decimal
from unittest.mock import MagicMock

from apps.reference.config_models import ShadowCriticalEventJournalConfig
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.fsm_close import CloseFlowFSM
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    ShadowCriticalEventJournal,
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
    cfg.trading.execution.watchdog.ack_ttl_ms = 5000
    cfg.trading.execution.watchdog.fill_ttl_ms = 5000
    cfg.trading.execution.anti_race_close_ms = 800
    cfg.trading.execution.cooldown_after_close_ms = 10_000
    cfg.domains.execution_position.fsm_open.idempotency_window_sec = 60

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


def test_shadow_journal_append_only_and_repeated_close_marker(tmp_path):
    path = tmp_path / "journal.jsonl"
    fsm = FSMCore()
    attach_shadow_journal(fsm, _shadow_cfg(path))

    payload = {"symbol": "BTCUSDT", "rid": "close-1"}
    fsm.emit("CMD:CLOSE", payload=payload, why="manual_close", rid="close-1")
    fsm.emit("CMD:CLOSE", payload=payload, why="manual_close", rid="close-1")

    records = _read_jsonl(path)
    assert len(records) == 2
    assert records[0]["schema_version"] == "1.0.0"
    assert records[1]["repeated_close"] is True
    assert records[1]["event_name"] == "CMD:CLOSE"


def test_shadow_journal_fail_open_and_duplicate_fill_marker(tmp_path):
    path = tmp_path / "journal.jsonl"
    fsm = FSMCore()
    journal = attach_shadow_journal(fsm, _shadow_cfg(path))
    assert journal is not None

    original_write = journal.sink.write
    state = {"failed": False}

    def flaky_write(record):
        if not state["failed"]:
            state["failed"] = True
            raise OSError("disk full")
        return original_write(record)

    payload = {
        "symbol": "BTCUSDT",
        "side": "buy",
        "orderId": "12345",
        "client_order_id": "ENTRY-BTCUSDT-1",
        "quantity": "0.01",
        "price": "50000",
        "ts": 1775261792250,
        "venue": "binance",
    }

    with patch.object(journal.sink, "write", side_effect=flaky_write):
        fsm.emit("EVT:TRADE_EXECUTED", payload=payload,
                 why="WS_ORDER_UPDATE_FILLED", rid="rid-1")
        fsm.emit("EVT:TRADE_EXECUTED", payload=payload,
                 why="polling_fill", rid="rid-1")

    records = _read_jsonl(path)
    assert len(records) == 1
    assert records[0]["suspected_duplicate"] is True
    assert records[0]["duplicate_heuristic"] is True
    assert records[0]["duplicate_kind"] == "cross_origin_duplicate_exposure"
    assert "shadow_journal_write_failed" in (
        records[0]["instrumentation_failure"] or "")


def test_shadow_journal_captures_regime_detected_heartbeat_truth(tmp_path):
    path = tmp_path / "journal.jsonl"
    fsm = FSMCore()
    attach_shadow_journal(fsm, _shadow_cfg(path))

    payload = {
        "symbol": "ETHUSDT",
        "ts": 1775105700000,
        "ts_ms": 1775105700000,
        "regime": "TREND_DOWN",
        "confidence": "0.85",
        "source_model": "sma_trend_v1",
        "changed": False,
        "raw_regime": "TREND_DOWN",
        "raw_confidence": "0.85",
        "stable_confidence": "0.85",
        "structural_regime_ref": "structural:ETHUSDT:1775105700000",
        "last_update_ts_ms": 1775105700256,
        "hysteresis_confirm_count": 3,
        "regime_layer": "structural",
        "regime_scope": "per_symbol",
        "regime_clock": "bar",
    }

    fsm.emit(
        "EVT:REGIME_DETECTED",
        payload=payload,
        why="regime=TREND_DOWN model=sma_trend_v1 symbol=ETHUSDT same",
        rid="rid-regime-heartbeat",
    )

    records = _read_jsonl(path)
    assert len(records) == 1
    assert records[0]["event_name"] == "EVT:REGIME_DETECTED"
    fragment = records[0]["payload_fragment"]
    assert fragment["regime"] == "TREND_DOWN"
    assert fragment["confidence"] == "0.85"
    assert fragment["changed"] is False
    assert fragment["raw_confidence"] == "0.85"
    assert fragment["structural_regime_ref"] == "structural:ETHUSDT:1775105700000"


def test_shadow_journal_captures_regime_detected_transition_truth(tmp_path):
    path = tmp_path / "journal.jsonl"
    fsm = FSMCore()
    attach_shadow_journal(fsm, _shadow_cfg(path))

    payload = {
        "symbol": "ETHUSDT",
        "ts": 1775106000000,
        "ts_ms": 1775106000000,
        "regime": "LOW_VOLATILITY",
        "confidence": "0.28",
        "source_model": "volatility_v2",
        "changed": True,
        "raw_regime": "LOW_VOLATILITY",
        "raw_confidence": "0.2869",
        "stable_confidence": "0.28",
        "structural_regime_ref": "structural:ETHUSDT:1775106000000",
        "last_update_ts_ms": 1775106000123,
        "hysteresis_confirm_count": 3,
        "regime_layer": "structural",
        "regime_scope": "per_symbol",
        "regime_clock": "bar",
    }

    fsm.emit(
        "EVT:REGIME_DETECTED",
        payload=payload,
        why="regime=LOW_VOLATILITY model=volatility_v2 symbol=ETHUSDT",
        rid="rid-regime-transition",
    )

    records = _read_jsonl(path)
    assert len(records) == 1
    fragment = records[0]["payload_fragment"]
    assert fragment["changed"] is True
    assert fragment["regime"] == "LOW_VOLATILITY"
    assert fragment["raw_regime"] == "LOW_VOLATILITY"
    assert fragment["last_update_ts_ms"] == 1775106000123


def test_shadow_journal_typed_default_matches_runtime_default_allowlist():
    assert list(ShadowCriticalEventJournalConfig().critical_events) == list(
        DEFAULT_CRITICAL_EVENTS
    )


def test_loaded_runtime_config_retains_regime_detected_in_shadow_journal():
    config = ConfigLoader().load_config()

    assert "EVT:REGIME_DETECTED" in config.observability.shadow_journal.critical_events


def test_loaded_runtime_shadow_journal_links_business_rid_to_retained_detector_artifact(tmp_path):
    path = tmp_path / "journal.jsonl"
    config = ConfigLoader().load_config()
    config.observability.shadow_journal.enabled = True
    config.observability.shadow_journal.path = str(path)

    fsm = FSMCore()
    attach_shadow_journal(fsm, config)

    detector_ts_ms = 1775400000000
    detector_ref = f"structural:ETHUSDT:{detector_ts_ms}"
    detector_payload = {
        "symbol": "ETHUSDT",
        "ts": detector_ts_ms,
        "ts_ms": detector_ts_ms,
        "regime": "LOW_VOLATILITY",
        "confidence": "0.57",
        "source_model": "volatility_v2",
        "changed": False,
        "raw_regime": "LOW_VOLATILITY",
        "raw_confidence": "0.57",
        "stable_confidence": "0.57",
        "structural_regime_ref": detector_ref,
        "last_update_ts_ms": detector_ts_ms + 123,
        "hysteresis_confirm_count": 3,
        "regime_layer": "structural",
        "regime_scope": "per_symbol",
        "regime_clock": "bar",
        "regime_owner": "regime_detector",
    }
    business_rid = "rid-runtime-business-link-1"

    fsm.emit(
        "EVT:REGIME_DETECTED",
        payload=detector_payload,
        why="regime=LOW_VOLATILITY model=volatility_v2 symbol=ETHUSDT same",
        rid="rid-detector-heartbeat-1",
    )
    fsm.emit(
        "EVT:TRADE_INTENT_PROPOSED",
        payload={
            "rid": business_rid,
            "symbol": "ETHUSDT",
            "side": "BUY",
            "qty": "0.01",
            "price": "2400.0",
            "strategy_id": "aurora",
            "regime": "LOW_VOLATILITY",
            "regime_confidence": 0.57,
            "regime_provenance": {
                "source_kind": "detector_cache",
                "detector_event": {
                    "event_name": "EVT:REGIME_DETECTED",
                    "rid": "rid-detector-heartbeat-1",
                    "ts_ms": detector_ts_ms,
                    "last_update_ts_ms": detector_ts_ms + 123,
                    "structural_regime_ref": detector_ref,
                    "changed": False,
                    "regime": "LOW_VOLATILITY",
                    "confidence": "0.57",
                    "raw_regime": "LOW_VOLATILITY",
                    "raw_confidence": "0.57",
                },
                "cache_snapshot": {
                    "cache_write_ts_ms": detector_ts_ms + 200,
                    "regime": "LOW_VOLATILITY",
                    "confidence": 0.57,
                },
            },
        },
        why="controlled_runtime_like_business_case",
        rid=business_rid,
    )

    records = _read_jsonl(path)
    detector_records = [
        record
        for record in records
        if record["event_name"] == "EVT:REGIME_DETECTED"
        and record["symbol"] == "ETHUSDT"
    ]
    intent_records = [
        record
        for record in records
        if record["event_name"] == "EVT:TRADE_INTENT_PROPOSED"
        and record["rid"] == business_rid
    ]

    assert len(detector_records) == 1
    assert len(intent_records) == 1

    detector_fragment = detector_records[0]["payload_fragment"]
    intent_fragment = intent_records[0]["payload_fragment"]
    detector_ref_from_intent = intent_fragment["regime_provenance"]["detector_event"]

    assert detector_fragment["ts_ms"] == detector_ts_ms
    assert detector_fragment["regime"] == "LOW_VOLATILITY"
    assert detector_fragment["confidence"] == "0.57"
    assert detector_fragment["structural_regime_ref"] == detector_ref
    assert detector_ref_from_intent["event_name"] == "EVT:REGIME_DETECTED"
    assert detector_ref_from_intent["rid"] == "rid-detector-heartbeat-1"
    assert detector_ref_from_intent["ts_ms"] == detector_fragment["ts_ms"]
    assert detector_ref_from_intent["regime"] == detector_fragment["regime"]
    assert detector_ref_from_intent["confidence"] == detector_fragment["confidence"]
    assert detector_ref_from_intent["structural_regime_ref"] == detector_fragment["structural_regime_ref"]


def test_close_flow_transition_captures_before_after_state(tmp_path):
    path = tmp_path / "journal.jsonl"
    journal = ShadowCriticalEventJournal(path=str(path))
    flow = CloseFlowFSM()
    flow.set_shadow_journal(journal)

    result = flow.handle(
        Message(
            op="CMD",
            verb="CLOSE",
            src="decision_making",
            dst="execution_position",
            rid="close-rid",
            pld={"symbol": "BTCUSDT"},
        )
    )

    assert result is not None
    assert result.op == "DEC"
    records = _read_jsonl(path)
    assert len(records) == 2
    close_record = next(
        record for record in records if record["event_name"] == "DEC:CLOSE")
    input_record = next(
        record for record in records if record["event_name"] == "CMD:CLOSE")
    assert close_record["truth_owner"] == "CloseFlowFSM"
    assert close_record["local_state_before"]["state"] == "FLAT"
    assert close_record["local_state_after"]["state"] == "DONE"
    assert close_record["local_state_after"]["last_close_reason"] == "MANUAL_CLOSE"
    # Input record no longer carries state snapshots (semantic fix);
    # only the output record is authoritative for the transition window.
    assert input_record["local_state_before"] is None
    assert input_record["local_state_after"] is None
    assert "record_role=input" in input_record["notes"]


def test_execpos_hydrate_writes_restore_record(tmp_path):
    path = tmp_path / "journal.jsonl"
    fsm_config = _make_execpos_config(path)

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"):
        bus = _Bus()
        fsm = ExecPosFSM(config=fsm_config, fsm=bus)
        fsm.hydrate({"symbol": "BTCUSDT", "qty": "0.01",
                    "entry_price": "50000", "side": "BUY"})

    records = _read_jsonl(path)
    restore_records = [r for r in records if r["event_name"]
                       == "RESTORE:EXECUTION_POSITION_HYDRATE"]
    assert len(restore_records) == 1
    assert restore_records[0]["restore_marker"] is True
    assert restore_records[0]["truth_owner"] == "ExecPosFSM"
    assert restore_records[0]["local_state_before"] is not None
    assert restore_records[0]["local_state_after"] is not None


def test_position_tracking_load_snapshot_writes_restore_record(tmp_path):
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

    state = {
        "positions": {
            "BTCUSDT": {
                "qty": "0.01",
                "avg_price": "50000",
                "venues": ["binance"],
            }
        },
        "portfolio": {
            "equity": "1000",
            "balance": "995",
        },
    }
    state_hash = hashlib.sha256(json.dumps(
        state, sort_keys=True).encode("utf-8")).hexdigest()
    snapshot = {
        "timestamp_utc": "2026-03-20T10:00:00Z",
        "state_hash": f"sha256:{state_hash}",
        "state": state,
    }

    assert tracker.load_snapshot(snapshot) is True

    records = _read_jsonl(path)
    restore_records = [r for r in records if r["event_name"]
                       == "RESTORE:POSITION_TRACKING_SNAPSHOT_LOAD"]
    assert len(restore_records) == 1
    assert restore_records[0]["restore_marker"] is True
    assert restore_records[0]["truth_owner"] == "PositionTracking"
