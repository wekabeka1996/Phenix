import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from vfoundation.core.fsm_core import FSMCore, InvalidMessagePayloadError
from vfoundation.core.schema_registry import init_global_registry


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


def _canonical_guard_payload() -> dict:
    return {
        "ts_ms": 1775450000000,
        "symbol": "BTCUSDT",
        "rid": "rid-guard-contract",
        "lifecycle_id": "lifecycle-1",
        "tracked_rid": "tracked-rid-1",
        "block_reason": "local_manage_state_conflict",
        "reason": "local_manage_state_conflict",
        "current_local_state": "TRACKING",
        "local_manage_state": "TRACKING",
        "portfolio_truth_state": "LONG",
        "portfolio_state": "LONG",
        "divergence_detected": False,
        "has_active_lifecycle": True,
        "closing_position": False,
        "position_qty": "0.10",
        "entry_order_id": "entry-1",
        "entry_client_order_id": "ENTRY-1",
        "sl_order_id": "sl-1",
        "tp_order_id": "tp-1",
        "tp1_order_id": "tp1-1",
        "tp2_order_id": "tp2-1",
        "why": "execution:local_manage_state_conflict",
    }


@pytest.fixture(autouse=True)
def _init_schema_registry():
    init_global_registry(
        project_root=".",
        yaml_path="apps/reference/dictionaries/verb_registry_v1.yaml",
    )


def test_execution_guard_blocked_canonical_payload_validates_and_reaches_shadow(tmp_path):
    shadow_path = tmp_path / "shadow.jsonl"
    fsm = FSMCore()
    attach_shadow_journal(fsm, _shadow_cfg(shadow_path))

    payload = _canonical_guard_payload()

    fsm.emit(
        "EVT:EXECUTION_GUARD_BLOCKED",
        payload=payload,
        why=payload["why"],
        rid=payload["rid"],
    )

    records = _read_jsonl(shadow_path)
    assert len(records) == 1
    assert records[0]["event_name"] == "EVT:EXECUTION_GUARD_BLOCKED"
    fragment = records[0]["payload_fragment"]
    assert fragment["has_active_lifecycle"] is True
    assert fragment["entry_order_id"] == "entry-1"
    assert fragment["tp2_order_id"] == "tp2-1"


def test_execution_guard_blocked_schema_remains_bounded():
    fsm = FSMCore()
    payload = _canonical_guard_payload()
    payload["unexpected_dump_field"] = {"raw": "noise"}

    with pytest.raises(InvalidMessagePayloadError, match="unexpected_dump_field"):
        fsm.emit(
            "EVT:EXECUTION_GUARD_BLOCKED",
            payload=payload,
            why=payload["why"],
            rid=payload["rid"],
        )
