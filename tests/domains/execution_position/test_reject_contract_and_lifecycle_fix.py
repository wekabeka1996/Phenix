"""
Tests for execution-boundary TRADE_INTENT_REJECTED contract closure.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from vfoundation.core.fsm_core import FSMCore

SCHEMA_PATH = Path("schemas/trade_intent_rejected_v1.json")
ALLOWED_KEYS: frozenset[str] = frozenset(
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["properties"].keys()
)
REQUIRED_KEYS: frozenset[str] = frozenset(
    json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["required"]
)


def _validate_reject_payload(payload: dict) -> None:
    missing = REQUIRED_KEYS - payload.keys()
    assert not missing, f"Schema violation: missing required fields: {missing}"

    extra = payload.keys() - ALLOWED_KEYS
    assert not extra, (
        f"Schema violation: unexpected extra fields present: {extra}. "
        f"Allowed: {ALLOWED_KEYS}"
    )

    assert isinstance(payload["ts_ms"], int)
    assert isinstance(payload["symbol"], str)
    assert isinstance(payload["reason_code"], str)
    assert payload["stage"] in ("RISK", "STRATEGY", "DECISION", "EXECUTION")
    assert isinstance(payload["why"], str)


class _FakeBus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, Any]] = []

    def emit(self, topic: str, payload=None, why=None, data_ref=None, **kw) -> None:
        self.emitted.append((topic, payload or {}))

    def listen(self, *args, **kw) -> None:
        return None


def _make_fsm_stub(bus: _FakeBus, lifecycle=None, *, write_wal: bool = False) -> Any:
    fsm = MagicMock()
    fsm.bus = bus
    fsm._trade_lifecycle = lifecycle
    fsm._emit_trade_intent_reject_wal = write_wal
    return fsm


def _make_err_msg(why: str, payload: dict | None = None) -> Any:
    msg = MagicMock()
    msg.op = "ERR"
    msg.verb = "OPEN"
    msg.why = why
    msg.pld = dict(payload or {})
    msg.rid = "ERR-RID-1"
    msg.data_ref = None
    return msg


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
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def test_intent_router_produces_schema_valid_reject_payload() -> None:
    from apps.reference.domains.execution_position.flows.open.intent_router import IntentRouter
    from vfoundation.core.protocol import Message

    bus = _FakeBus()
    fsm = _make_fsm_stub(bus)
    fsm.handle = MagicMock(return_value=_make_err_msg("OPEN_GUARD_FAIL"))
    fsm.open_flow = MagicMock()
    fsm.manage_flows = {}

    router = IntentRouter(fsm=fsm)
    intent_msg = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        pld={
            "rid": "RID-SCHEMA-TEST-1",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order": {
                "qty": "0.01",
                "order_type": "LIMIT",
                "price": "50000",
                "tif": "GTC",
            },
            "valid_for_ms": 30_000,
            "idempotent_key": "KEY-1",
        },
        why="test_schema_valid",
    )

    with patch.object(router, "_mark_intent_routed"):
        router.on_trade_intent_proposed(intent_msg)

    emitted = [p for (t, p) in bus.emitted if t == "EVT:TRADE_INTENT_REJECTED"]
    assert emitted, "No EVT:TRADE_INTENT_REJECTED was emitted"

    payload = emitted[0]
    _validate_reject_payload(payload)
    assert "reason" not in payload


def test_intent_router_maps_local_lifecycle_conflict_to_specific_reason_code() -> None:
    from apps.reference.domains.execution_position.flows.open.intent_router import IntentRouter
    from vfoundation.core.protocol import Message

    bus = _FakeBus()
    fsm = _make_fsm_stub(bus)
    fsm.handle = MagicMock(
        return_value=_make_err_msg(
            "OPEN_GUARD_FAIL",
            {
                "reason": "local_manage_state_conflict",
                "local_manage_state": "BRACKETS_PENDING",
                "portfolio_state": "FLAT",
                "divergence_detected": True,
                "tracked_rid": "tracked-rid-1",
                "lifecycle_id": "lifecycle-1",
                "entry_order_id": "entry-1",
                "sl_order_id": "sl-1",
                "tp_order_id": "tp-1",
            },
        )
    )
    fsm.open_flow = MagicMock()
    fsm.manage_flows = {}

    router = IntentRouter(fsm=fsm)
    intent_msg = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="execution_position",
        pld={
            "rid": "RID-LOCAL-CONFLICT-1",
            "instrument": "BTCUSDT",
            "side": "BUY",
            "order": {
                "qty": "0.01",
                "order_type": "LIMIT",
                "price": "50000",
                "tif": "GTC",
            },
            "valid_for_ms": 30_000,
            "idempotent_key": "KEY-1",
        },
        why="test_schema_valid",
    )

    with patch.object(router, "_mark_intent_routed"):
        router.on_trade_intent_proposed(intent_msg)

    emitted = [p for (t, p) in bus.emitted if t == "EVT:TRADE_INTENT_REJECTED"]
    assert emitted, "No EVT:TRADE_INTENT_REJECTED was emitted"

    payload = emitted[0]
    _validate_reject_payload(payload)
    assert payload["reason_code"] == "NRR-EXECUTION-LOCAL-LIFECYCLE-CONFLICT"
    assert payload["why"] == "OPEN_GUARD_FAIL"
    assert payload["details"]["reason"] == "local_manage_state_conflict"
    assert payload["details"]["local_manage_state"] == "BRACKETS_PENDING"
    assert payload["details"]["portfolio_state"] == "FLAT"
    assert payload["details"]["divergence_detected"] is True


def test_lifecycle_reject_terminates_intent_not_orphan_ttl(tmp_path) -> None:
    from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger

    log_file = tmp_path / "trade_lifecycle.jsonl"
    logger = TradeLifecycleLogger(
        log_file=str(log_file),
        orphan_ttl_sec=3600,
    )

    rid = "RID-LIFECYCLE-REJECT-TEST-1"
    logger.on_intent(rid=rid, symbol="BTCUSDT", side="BUY", strategy_id="aurora")
    assert rid in logger._trades
    assert logger._trades[rid].status == "INTENT"

    logger.on_reject(rid=rid, reject_reason="OPEN_GUARD_FAIL")

    assert rid not in logger._trades
    records = _read_jsonl(log_file)
    assert len(records) == 1
    assert records[0]["rid"] == rid
    assert records[0]["status"] == "REJECTED"
    assert records[0]["close_reason"] == "OPEN_GUARD_FAIL"
    assert logger.sweep_expired() == 0


def test_reject_schema_rejects_forbidden_extra_fields() -> None:
    bad_payload = {
        "ts_ms": int(time.time() * 1000),
        "symbol": "BTCUSDT",
        "reason_code": "NRR-EXECUTION-REJECTED",
        "reason": "OPEN_GUARD_FAIL",
        "stage": "EXECUTION",
        "why": "OPEN_GUARD_FAIL",
    }

    with pytest.raises(AssertionError, match="unexpected extra fields"):
        _validate_reject_payload(bad_payload)


def test_reject_schema_accepts_valid_shape() -> None:
    good_payload = {
        "ts_ms": int(time.time() * 1000),
        "symbol": "BTCUSDT",
        "reason_code": "NRR-EXECUTION-REJECTED",
        "stage": "EXECUTION",
        "why": "OPEN_GUARD_FAIL",
    }
    _validate_reject_payload(good_payload)


def test_fsmcore_normalizes_legacy_trade_intent_rejected_before_schema_validation(tmp_path) -> None:
    from vfoundation.core.schema_registry import init_global_registry

    init_global_registry(project_root=".")
    journal_path = tmp_path / "shadow_trade_intent_rejected.jsonl"
    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(journal_path))

    seen: list[dict] = []
    bus.listen("EVT:TRADE_INTENT_REJECTED", lambda msg: seen.append(dict(msg.pld or {})))

    legacy_payload = {
        "ts_ms": int(time.time() * 1000),
        "instrument": "BTCUSDT",
        "reason_code": "NRR-EXECUTION-REJECTED",
        "reason": "OPEN_GUARD_FAIL",
        "stage": "EXECUTION",
        "why": "OPEN_GUARD_FAIL",
        "rid": "RID-LEGACY-NORMALIZE-1",
    }

    bus.emit("EVT:TRADE_INTENT_REJECTED", legacy_payload, "legacy_payload")

    assert len(seen) == 1
    payload = seen[0]
    _validate_reject_payload(payload)
    assert payload["symbol"] == "BTCUSDT"
    assert "reason" not in payload

    records = _read_jsonl(journal_path)
    shadow_events = [r for r in records if r["event_name"] == "EVT:TRADE_INTENT_REJECTED"]
    assert len(shadow_events) == 1
    fragment = shadow_events[0]["payload_fragment"]
    assert fragment["reason_code"] == "NRR-EXECUTION-REJECTED"
    assert fragment["stage"] == "EXECUTION"
    assert fragment["why"] == "OPEN_GUARD_FAIL"
    assert "reason" not in fragment


def test_canonical_trade_intent_reject_helper_writes_observability_and_closes_lifecycle(tmp_path) -> None:
    from apps.reference.domains.execution_position.contract_layer.trade_intent_reject_contracts import (
        emit_canonical_trade_intent_rejected_event,
    )
    from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import (
        build_trade_intent_rejected_message,
    )
    from apps.reference.telemetry.trade_lifecycle_logger import TradeLifecycleLogger
    from vfoundation.core.schema_registry import init_global_registry

    init_global_registry(project_root=".")
    journal_path = tmp_path / "shadow_trade_intent_reject_helper.jsonl"
    lifecycle_path = tmp_path / "trade_lifecycle.jsonl"
    bus = FSMCore()
    attach_shadow_journal(bus, _shadow_cfg(journal_path))

    logger = TradeLifecycleLogger(log_file=str(lifecycle_path), orphan_ttl_sec=3600)
    rid = "RID-EXEC-REJECT-HELPER-1"
    logger.on_intent(rid=rid, symbol="BTCUSDT", side="BUY", strategy_id="aurora")

    observed: list[dict] = []
    bus.listen("EVT:TRADE_INTENT_REJECTED", lambda msg: observed.append(dict(msg.pld or {})))

    wal_records: list[dict] = []
    legacy_payload = {
        "ts_ms": int(time.time() * 1000),
        "instrument": "BTCUSDT",
        "reason_code": "NRR-EXECUTION-REJECTED",
        "reason": "OPEN_GUARD_FAIL",
        "stage": "EXECUTION",
        "why": "OPEN_GUARD_FAIL",
        "rid": rid,
        "details": {"origin": "test"},
    }

    with patch(
        "apps.reference.domains.execution_position.contract_layer.trade_intent_reject_contracts.wal.append",
        side_effect=wal_records.append,
    ):
        normalized = emit_canonical_trade_intent_rejected_event(
            fsm=bus,
            payload=legacy_payload,
            rid=rid,
            src="execution_position",
            why="execution_rejected",
            lifecycle=logger,
            write_wal=True,
            fallback_symbol="BTCUSDT",
            fallback_reason_code="NRR-EXECUTION-REJECTED",
            fallback_stage="EXECUTION",
            fallback_why="OPEN_GUARD_FAIL",
        )

    _validate_reject_payload(normalized)
    assert "reason" not in normalized
    assert len(observed) == 1
    assert "reason" not in observed[0]

    assert len(wal_records) == 1
    wal_payload = wal_records[0]["pld"]
    expected_record = build_trade_intent_rejected_message(
        normalized,
        src="execution_position",
        rid=rid,
    ).model_dump()
    _validate_reject_payload(wal_payload)
    assert wal_payload["rid"] == rid
    assert "reason" not in wal_payload
    assert wal_records[0]["op"] == expected_record["op"]
    assert wal_records[0]["verb"] == expected_record["verb"]
    assert wal_records[0]["src"] == expected_record["src"]
    assert wal_records[0]["dst"] == expected_record["dst"]
    assert wal_records[0]["ts"] == expected_record["ts"]
    assert wal_records[0]["why"] == expected_record["why"]

    shadow_records = _read_jsonl(journal_path)
    shadow_events = [r for r in shadow_records if r["event_name"] == "EVT:TRADE_INTENT_REJECTED"]
    assert len(shadow_events) == 1
    shadow_fragment = shadow_events[0]["payload_fragment"]
    assert shadow_fragment["reason_code"] == "NRR-EXECUTION-REJECTED"
    assert shadow_fragment["why"] == "OPEN_GUARD_FAIL"

    lifecycle_records = _read_jsonl(lifecycle_path)
    assert len(lifecycle_records) == 1
    assert lifecycle_records[0]["rid"] == rid
    assert lifecycle_records[0]["status"] == "REJECTED"
    assert lifecycle_records[0]["close_reason"] == "OPEN_GUARD_FAIL"
