import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.domains.execution_position.flows.close.fsm_close import CloseFlowFSM, CloseState
from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageFlowFSM, ManageState
from apps.reference.telemetry.shadow_journal import (
    DEFAULT_CRITICAL_EVENTS,
    ShadowCriticalEventJournal,
    attach_shadow_journal,
)
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message


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


def _make_manage_config():
    cfg = MagicMock()
    cfg.trading.execution.anti_race_close_ms = 800
    cfg.trading.execution.manage.auto = True
    cfg.trading.execution.manage.emergency = None
    cfg.trading.execution.manage.brackets = None
    cfg.trailing = None
    cfg.strategies.aurora.assets = {}
    cfg.strategies.aurora.decision.bar_gating = None
    return cfg


def test_manage_flow_decision_is_shadow_recorded(tmp_path):
    path = tmp_path / "manage.jsonl"
    journal = ShadowCriticalEventJournal(path=str(path))
    manage = ManageFlowFSM(config=_make_manage_config())
    manage.set_shadow_journal(journal)
    manage.state = ManageState.TRACKING
    manage.symbol = "BTCUSDT"
    manage.position_qty = Decimal("0.1")
    manage.position_entry_price = Decimal("50000")
    manage.position_side = "BUY"
    manage.position_open_ts = 1.0

    message = Message(
        op="UPD",
        verb="MARKET_DATA",
        src="ws",
        dst="execution_position",
        rid="rid-manage-close",
        why="manage_close_test",
        pld={"symbol": "BTCUSDT", "last_price": "49900"},
    )

    with patch.object(manage, "_get_max_hold_sec", return_value=1):
        result = manage.handle(message)

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "CLOSE"
    assert manage.state == ManageState.TRACKING

    records = _read_jsonl(path)
    assert len(records) == 1
    assert records[0]["event_name"] == "DEC:CLOSE"
    assert records[0]["truth_owner"] == "ManageFlowFSM"
    assert records[0]["local_state_before"]["state"] == "TRACKING"
    assert records[0]["local_state_after"]["state"] == "TRACKING"
    assert records[0]["payload_fragment"]["reason"] == "MAX_HOLD_TIME_EXCEEDED"
    assert records[0]["payload_fragment"]["max_hold_sec"] == 1
    assert records[0]["payload_fragment"]["reduce_only"] is True


def test_close_flow_decision_is_shadow_recorded(tmp_path):
    path = tmp_path / "close.jsonl"
    journal = ShadowCriticalEventJournal(path=str(path))
    close_flow = CloseFlowFSM()
    close_flow.set_shadow_journal(journal)
    close_flow.state = CloseState.OPENED
    close_flow.position_active = True
    close_flow.position_open_ts = 1.0

    message = Message(
        op="CMD",
        verb="CLOSE",
        src="decision_making",
        dst="execution_position",
        rid="rid-close-shadow",
        why="regime_change",
        pld={
            "symbol": "BTCUSDT",
            "reason": "signal_flip",
            "qty": "0.1",
            "trace": "decision:signal_flip",
        },
    )

    result = close_flow.handle(message)

    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "CLOSE"
    assert close_flow.state == CloseState.DONE
    assert close_flow.position_active is False
    assert close_flow.last_close_reason == "signal_flip"
    assert close_flow.last_close_qty == "0.1"
    assert close_flow.last_close_symbol == "BTCUSDT"

    records = _read_jsonl(path)
    assert len(records) == 3
    close_record = next(
        record for record in records if record["event_name"] == "DEC:CLOSE")
    assert close_record["truth_owner"] == "CloseFlowFSM"
    assert close_record["payload_fragment"]["reason"] == "signal_flip"
    assert close_record["payload_fragment"]["trigger"] == "CMD:CLOSE"
    assert close_record["payload_fragment"]["reduce_only"] is True
    assert close_record["local_state_after"]["last_close_reason"] == "signal_flip"
    assert close_record["local_state_after"]["last_close_qty"] == "0.1"
    assert close_record["local_state_after"]["last_close_symbol"] == "BTCUSDT"


def test_shadow_journal_captures_execution_lifecycle_bus_events(tmp_path):
    path = tmp_path / "bus.jsonl"
    fsm = FSMCore()
    attach_shadow_journal(fsm, _shadow_cfg(path))

    fsm.emit(
        "EVT:EXECUTION_GUARD_BLOCKED",
        payload={
            "ts_ms": 1775450000000,
            "symbol": "BTCUSDT",
            "rid": "rid-guard",
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
        },
        why="execution:local_manage_state_conflict",
        rid="rid-guard",
    )
    fsm.emit(
        "EVT:EXECUTION_DIVERGENCE_DETECTED",
        payload={
            "ts_ms": 1775450000001,
            "symbol": "BTCUSDT",
            "current_rid": "rid-div",
            "tracked_rid": "rid-stale-local",
            "lifecycle_id": "rid-stale-local",
            "local_manage_state": "TRACKING",
            "portfolio_state": "FLAT",
            "divergence_type": "rid_mismatch",
            "why": "execution:divergence_detected",
        },
        why="execution:divergence_detected",
        rid="rid-div",
    )
    fsm.emit(
        "EVT:EXIT_MATCH_ATTEMPTED",
        payload={
            "ts_ms": 1775450000002,
            "symbol": "BTCUSDT",
            "rid": "rid-exit",
            "event_type": "EXIT_MATCH_ATTEMPTED",
            "incoming_order_id": "order-1",
            "incoming_client_order_id": "tp1-order",
            "normalized_client_order_id": "TP1-ORDER",
            "inferred_role": "TP1",
            "local_expected_ids": {"tp1_order_id": "tp1-order"},
            "local_expected_ids_after": {"tp1_order_id": "tp1-order"},
            "matched": True,
            "match_reason": "matched_tp1_client_order_id_exact",
            "local_state_before": "BRACKETS_PLACED",
            "local_state_after": "BRACKETS_PLACED",
            "position_qty_before": "0.10",
            "position_qty_after": "0.05",
            "why": "execution:exit_match_attempted",
        },
        why="execution:exit_match_attempted",
        rid="rid-exit",
    )
    fsm.emit(
        "EVT:EXECUTION_TIDY_PERFORMED",
        payload={
            "ts_ms": 1775450000003,
            "symbol": "BTCUSDT",
            "source": "guardian_poll",
            "tidy_reason": "orphan_cleanup",
            "business_close_reconciled": False,
            "why": "guardian:orphan_cleanup:tidy",
        },
        why="guardian:orphan_cleanup:tidy",
        rid="rid-tidy",
    )
    fsm.emit(
        "EVT:EXECUTION_CLOSE_RECONCILED",
        payload={
            "ts_ms": 1775450000004,
            "symbol": "BTCUSDT",
            "source": "guardian_reconcile",
            "business_close_reconciled": True,
            "why": "guardian:close_reconciled",
        },
        why="guardian:close_reconciled",
        rid="rid-close",
    )

    records = _read_jsonl(path)
    assert {record["event_name"] for record in records} == {
        "EVT:EXECUTION_GUARD_BLOCKED",
        "EVT:EXECUTION_DIVERGENCE_DETECTED",
        "EVT:EXIT_MATCH_ATTEMPTED",
        "EVT:EXECUTION_TIDY_PERFORMED",
        "EVT:EXECUTION_CLOSE_RECONCILED",
    }

    guard_record = next(
        record for record in records if record["event_name"] == "EVT:EXECUTION_GUARD_BLOCKED")
    divergence_record = next(
        record for record in records if record["event_name"] == "EVT:EXECUTION_DIVERGENCE_DETECTED")
    exit_record = next(
        record for record in records if record["event_name"] == "EVT:EXIT_MATCH_ATTEMPTED")
    tidy_record = next(
        record for record in records if record["event_name"] == "EVT:EXECUTION_TIDY_PERFORMED")
    close_record = next(
        record for record in records if record["event_name"] == "EVT:EXECUTION_CLOSE_RECONCILED")

    assert guard_record["source_component"] == "execution_position.fsm"
    assert guard_record["source_path"] == "execution:guard"
    assert guard_record["payload_fragment"]["block_reason"] == "local_manage_state_conflict"
    assert guard_record["payload_fragment"]["position_qty"] == "0.10"
    assert divergence_record["source_component"] == "execution_position.fsm"
    assert divergence_record["payload_fragment"]["tracked_rid"] == "rid-stale-local"
    assert exit_record["source_component"] == "execution_position.fsm_manage"
    assert exit_record["source_path"] == "execution:manage_flow"
    assert exit_record["payload_fragment"]["inferred_role"] == "TP1"
    assert exit_record["payload_fragment"]["matched"] is True
    assert tidy_record["source_component"] == "execution_position.order_guardian"
    assert tidy_record["payload_fragment"]["business_close_reconciled"] is False
    assert close_record["source_component"] == "execution_position.order_guardian"
    assert close_record["payload_fragment"]["business_close_reconciled"] is True
