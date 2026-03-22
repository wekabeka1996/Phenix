import json
from pathlib import Path

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.truth_hardening import (
    attach_execution_truth_hardening,
)
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    attach_shadow_journal,
)
from vfoundation.core.fsm_core import FSMCore


def _read_jsonl(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _make_config(journal_path: Path, warm_state_path: Path):
    config = ConfigLoader().load_config()
    config.observability.shadow_journal.enabled = True
    config.observability.shadow_journal.path = str(journal_path)
    config.observability.shadow_journal.critical_events = list(DEFAULT_CRITICAL_EVENTS)
    config.domains.execution_position.event_dedup.warm_state.enabled = True
    config.domains.execution_position.event_dedup.warm_state.storage_path = str(warm_state_path)
    config.domains.execution_position.event_dedup.warm_state.max_entries = 2000
    return config


def test_restart_seeded_warm_state_suppresses_exact_terminal_fill_after_restart(tmp_path):
    journal_path = tmp_path / "journal.jsonl"
    warm_state_path = tmp_path / "warm_state.json"
    config = _make_config(journal_path, warm_state_path)

    payload = {
        "symbol": "BTCUSDT",
        "orderId": "7777",
        "clientOrderId": "ENTRY-BTCUSDT-WS-1",
        "client_order_id": "ENTRY-BTCUSDT-WS-1",
    }

    fsm_a = FSMCore()
    attach_shadow_journal(fsm_a, config)
    attach_execution_truth_hardening(fsm_a, config)
    seen_a = []
    fsm_a.listen("EVT:TRADE_EXECUTED", lambda msg: seen_a.append(msg.pld["orderId"]))
    fsm_a.emit("EVT:TRADE_EXECUTED", payload=payload, why="WS_ORDER_UPDATE_FILLED", rid="rid-warm-1")

    fsm_b = FSMCore()
    attach_shadow_journal(fsm_b, config)
    attach_execution_truth_hardening(fsm_b, config)
    seen_b = []
    fsm_b.listen("EVT:TRADE_EXECUTED", lambda msg: seen_b.append(msg.pld["orderId"]))
    fsm_b.emit("EVT:TRADE_EXECUTED", payload=payload, why="WS_ORDER_UPDATE_FILLED", rid="rid-warm-1")

    assert seen_a == ["7777"]
    assert seen_b == []
    assert warm_state_path.exists()

    with open(warm_state_path, "r", encoding="utf-8") as fh:
        state = json.load(fh)
    assert len(state["entries"]) == 1
    assert state["entries"][0]["order_id"] == "7777"

    records = _read_jsonl(journal_path)
    assert len([r for r in records if r["event_name"] == "RESTORE:EXECUTION_TRUTH_WARM_STATE_EMPTY"]) == 1
    assert len([r for r in records if r["event_name"] == "RESTORE:EXECUTION_TRUTH_WARM_STATE_LOADED"]) == 1
    assert len([r for r in records if r["event_name"] == "HARDENING:TRADE_EXECUTED_WARM_STATE_MISS"]) == 1
    assert len([r for r in records if r["event_name"] == "HARDENING:TRADE_EXECUTED_WARM_STATE_HIT"]) == 1
    assert len([r for r in records if r["event_name"] == "HARDENING:TRADE_EXECUTED_SUPPRESSED"]) == 1


def test_restart_seeded_warm_state_allows_distinct_exact_terminal_fill_after_restart(tmp_path):
    journal_path = tmp_path / "journal.jsonl"
    warm_state_path = tmp_path / "warm_state.json"
    config = _make_config(journal_path, warm_state_path)

    payload_a = {
        "symbol": "BTCUSDT",
        "orderId": "7777",
        "clientOrderId": "ENTRY-BTCUSDT-WS-A",
        "client_order_id": "ENTRY-BTCUSDT-WS-A",
    }
    payload_b = {
        "symbol": "BTCUSDT",
        "orderId": "7788",
        "clientOrderId": "ENTRY-BTCUSDT-WS-B",
        "client_order_id": "ENTRY-BTCUSDT-WS-B",
    }

    fsm_a = FSMCore()
    attach_shadow_journal(fsm_a, config)
    attach_execution_truth_hardening(fsm_a, config)
    fsm_a.emit("EVT:TRADE_EXECUTED", payload=payload_a, why="WS_ORDER_UPDATE_FILLED", rid="rid-warm-a")

    fsm_b = FSMCore()
    attach_shadow_journal(fsm_b, config)
    attach_execution_truth_hardening(fsm_b, config)
    seen_b = []
    fsm_b.listen("EVT:TRADE_EXECUTED", lambda msg: seen_b.append(msg.pld["orderId"]))
    fsm_b.emit("EVT:TRADE_EXECUTED", payload=payload_b, why="WS_ORDER_UPDATE_FILLED", rid="rid-warm-b")

    assert seen_b == ["7788"]
    records = _read_jsonl(journal_path)
    assert len([r for r in records if r["event_name"] == "HARDENING:TRADE_EXECUTED_WARM_STATE_HIT"]) == 0
    assert len([r for r in records if r["event_name"] == "HARDENING:TRADE_EXECUTED_WARM_STATE_MISS"]) == 2


def test_degraded_identity_is_not_seeded_and_remains_visible_after_restart(tmp_path):
    journal_path = tmp_path / "journal.jsonl"
    warm_state_path = tmp_path / "warm_state.json"
    config = _make_config(journal_path, warm_state_path)

    payload = {"symbol": "BTCUSDT", "orderId": "8899"}

    fsm_a = FSMCore()
    attach_shadow_journal(fsm_a, config)
    attach_execution_truth_hardening(fsm_a, config)
    seen_a = []
    fsm_a.listen("EVT:TRADE_EXECUTED", lambda msg: seen_a.append(msg.pld["orderId"]))
    fsm_a.emit("EVT:TRADE_EXECUTED", payload=payload, why="polling_fill", rid="rid-degraded")

    fsm_b = FSMCore()
    attach_shadow_journal(fsm_b, config)
    attach_execution_truth_hardening(fsm_b, config)
    seen_b = []
    fsm_b.listen("EVT:TRADE_EXECUTED", lambda msg: seen_b.append(msg.pld["orderId"]))
    fsm_b.emit("EVT:TRADE_EXECUTED", payload=payload, why="polling_fill", rid="rid-degraded")

    assert seen_a == ["8899"]
    assert seen_b == ["8899"]
    assert not warm_state_path.exists()

    records = _read_jsonl(journal_path)
    assert len([r for r in records if r["event_name"] == "HARDENING:TRADE_EXECUTED_IDENTITY_DEGRADED"]) == 2
    assert len([r for r in records if r["event_name"] == "RESTORE:EXECUTION_TRUTH_WARM_STATE_EMPTY"]) == 2
    assert len([r for r in records if r["event_name"] == "HARDENING:TRADE_EXECUTED_WARM_STATE_HIT"]) == 0


def test_corrupt_warm_state_load_is_observable_and_fail_open(tmp_path):
    journal_path = tmp_path / "journal.jsonl"
    warm_state_path = tmp_path / "warm_state.json"
    warm_state_path.write_text("{not-json", encoding="utf-8")
    config = _make_config(journal_path, warm_state_path)

    fsm = FSMCore()
    attach_shadow_journal(fsm, config)
    attach_execution_truth_hardening(fsm, config)
    seen = []
    fsm.listen("EVT:TRADE_EXECUTED", lambda msg: seen.append(msg.pld["orderId"]))
    fsm.emit(
        "EVT:TRADE_EXECUTED",
        payload={
            "symbol": "BTCUSDT",
            "orderId": "9900",
            "clientOrderId": "ENTRY-BTCUSDT-CORRUPT",
            "client_order_id": "ENTRY-BTCUSDT-CORRUPT",
        },
        why="WS_ORDER_UPDATE_FILLED",
        rid="rid-corrupt",
    )

    assert seen == ["9900"]
    records = _read_jsonl(journal_path)
    failed = [r for r in records if r["event_name"] == "RESTORE:EXECUTION_TRUTH_WARM_STATE_LOAD_FAILED"]
    assert len(failed) == 1
    assert failed[0]["restore_marker"] is True
    assert len([r for r in records if r["event_name"] == "HARDENING:TRADE_EXECUTED_WARM_STATE_MISS"]) == 1
