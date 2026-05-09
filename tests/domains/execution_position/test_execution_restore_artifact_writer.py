import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.config_models import (
    ExecutionPositionRestoreArtifactConfig,
    ExecutionPositionRestoreArtifactMode,
)
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.flows.close.fsm_close import CloseState
from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageState
from apps.reference.domains.execution_position.state.restore_artifact import (
    TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN,
    TRUTH_SOURCE_RESTORED_PENDING_WAL,
    TRUTH_SOURCE_RUNTIME_LOCAL,
    TRUTH_SOURCE_UNKNOWN,
)


class _Bus:
    def __init__(self) -> None:
        self.domains = {}

    def emit(self, *args, **kwargs):
        return None

    def listen(self, *args, **kwargs):
        return None


def _configure_writer(
    fsm,
    tmp_path: Path,
    *,
    mode: str = "writer_only",
    flush_interval_ms: int = 25,
    dark_read_max_artifact_age_ms: int = 300000,
) -> Path:
    path = tmp_path / "execution_restore.json"
    fsm.config.domains.execution_position.restore_artifact = ExecutionPositionRestoreArtifactConfig(
        mode=mode,
        storage_path=str(path),
        flush_interval_ms=flush_interval_ms,
        dark_read_max_artifact_age_ms=dark_read_max_artifact_age_ms,
    )
    fsm._startup_truth_orchestrator._restore_artifact_writer = fsm._startup_truth_orchestrator._create_restore_artifact_writer()
    return path


def _set_runtime_state(
    fsm,
    *,
    symbol: str = "BTCUSDT",
    manage_state=ManageState.TRACKING,
    manage_active: bool = True,
    close_state=CloseState.OPENED,
    with_close: bool = True,
) -> None:
    fsm.manage_flows.clear()
    fsm.close_flows.clear()
    fsm._pending_brackets.clear()
    fsm._symbol_brackets.clear()
    fsm._symbol_bracket_truth_source.clear()
    manage_flow = MagicMock()
    manage_flow.state = manage_state
    manage_flow.has_active_lifecycle.return_value = manage_active
    fsm.manage_flows[symbol] = manage_flow
    if with_close:
        close_flow = MagicMock()
        close_flow.state = close_state
        fsm.close_flows[symbol] = close_flow
    else:
        fsm.close_flows.pop(symbol, None)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sample_close_submission_contour(
    *,
    symbol: str = "BTCUSDT",
    qty: str = "0.04",
) -> dict:
    return {
        "close_cmd_rid": f"RID-CLOSE-{symbol}",
        "truth_classification": "POSITION_PRESENT_AND_SUBMITTABLE",
        "truth_reason": "matched_live_position",
        "position_amount_at_close_request": "0.25",
        "bridge_payload": {
            "symbol": symbol,
            "reason": "MANUAL_CLOSE",
            "qty": qty,
            "idempotent_key": f"IDEM-{symbol}",
            "trigger": "CMD:CLOSE",
            "command_trigger": "manual_close",
            "close_guard_prevalidated": False,
        },
        "submission_payload": {
            "symbol": symbol,
            "side": "SELL",
            "quantity": qty,
            "client_order_id": f"CLOSE-{symbol}-CLIENT-1",
            "partial_close": True,
        },
        "submit_boundary_result": {
            "outcome": "submitted",
            "status": "NEW",
            "order_id": f"close-{symbol}-1",
        },
    }


def test_mode_off_produces_no_writer_activity(fsm_harness, tmp_path: Path) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path, mode="off")
    _set_runtime_state(fsm)

    wrote = fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="transition:test",
        allow_empty=True,
    )

    assert wrote is False
    assert not path.exists()


def test_restore_artifact_writes_minimum_envelope_shape_from_runtime_state(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    _set_runtime_state(fsm, manage_state=ManageState.WAIT_MODE,
                       close_state=CloseState.CLOSE_COND)

    wrote = fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="transition:manage",
        allow_empty=True,
    )

    assert wrote is True
    payload = _load_json(path)
    assert payload["schema_version"] == "1.0.0"
    assert payload["artifact_type"] == "execution_position_restore_envelope_v1"
    assert payload["writer_component"] == "execution_position"
    assert payload["requires_live_reconcile"] is True
    assert isinstance(payload["generated_at_ms"], int)
    assert len(payload["active_lifecycles"]) == 1

    record = payload["active_lifecycles"][0]
    assert record == {
        "symbol": "BTCUSDT",
        "manage_phase": "WAIT_MODE",
        "manage_truth_source": TRUTH_SOURCE_RUNTIME_LOCAL,
        "close_phase": "CLOSE_COND",
        "bracket_state": "UNKNOWN",
        "bracket_truth_source": TRUTH_SOURCE_UNKNOWN,
        "live_reconcile_required": True,
    }
    assert "contour_id" not in json.dumps(payload)
    assert "qty" not in record
    assert "equity" not in record
    assert "pnl" not in record
    assert "shadow" not in json.dumps(payload)
    assert "warm_state" not in json.dumps(payload)


def test_restore_artifact_writes_close_submission_contour_when_present(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    _set_runtime_state(fsm, manage_state=ManageState.TRACKING,
                       close_state=CloseState.OPENED)
    fsm.close_flows["BTCUSDT"].close_submission_restore_truth = _sample_close_submission_contour()

    wrote = fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="transition:close_contour",
        allow_empty=True,
    )

    assert wrote is True
    record = _load_json(path)["active_lifecycles"][0]
    assert record["close_submission_contour"]["truth_classification"] == "POSITION_PRESENT_AND_SUBMITTABLE"
    assert record["close_submission_contour"]["submission_payload"]["client_order_id"] == "CLOSE-BTCUSDT-CLIENT-1"
    assert record["close_submission_contour"]["submit_boundary_result"]["order_id"] == "close-BTCUSDT-1"


def test_authoritative_reset_removes_symbol_from_restore_artifact(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    symbol = "BTCUSDT"
    fsm.manage_flows.clear()
    fsm.close_flows.clear()
    fsm._pending_brackets.clear()
    fsm._symbol_brackets.clear()
    fsm._symbol_bracket_truth_source.clear()

    manage_flow = fsm.manage_flow(symbol)
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = symbol
    manage_flow.position_qty = "0.10"
    manage_flow.position_entry_price = "100.0"
    manage_flow.entry_order_id = "entry-order"
    manage_flow.entry_client_order_id = "ENTRY-1"
    manage_flow.sl_order_id = "sl-order"
    manage_flow.tp_order_id = "tp-order"

    close_flow = fsm.close_flow(symbol)
    close_flow.state = CloseState.OPENED
    close_flow.position_active = True

    fsm._set_symbol_brackets_snapshot(
        symbol,
        sl_order_id="sl-order",
        tp_order_id="tp-order",
    )
    fsm._pending_brackets["entry-order"] = {"symbol": symbol}

    wrote = fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="before_reset",
        allow_empty=True,
    )
    assert wrote is True
    payload = _load_json(path)
    assert len(payload["active_lifecycles"]) == 1

    with patch(
        "apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared"
    ):
        changed = fsm._apply_authoritative_local_close_reset(
            symbol,
            reason="unit_test_reset",
            source="unit_test",
        )

    assert changed is True

    wrote = fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="after_reset",
        allow_empty=True,
    )
    assert wrote is True
    payload = _load_json(path)
    assert payload["active_lifecycles"] == []


def test_authoritative_reset_clears_contour_when_close_state_already_flat(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    symbol = "BTCUSDT"
    fsm.manage_flows.clear()
    fsm.close_flows.clear()
    fsm._pending_brackets.clear()
    fsm._symbol_brackets.clear()
    fsm._symbol_bracket_truth_source.clear()

    manage_flow = fsm.manage_flow(symbol)
    manage_flow.state = ManageState.FLAT
    manage_flow.has_active_lifecycle = MagicMock(return_value=False)

    close_flow = fsm.close_flow(symbol)
    close_flow.state = CloseState.FLAT
    close_flow.position_active = False
    close_flow.close_submission_restore_truth = _sample_close_submission_contour()

    wrote = fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="before_reset_flat_contour",
        allow_empty=True,
    )
    assert wrote is True
    payload = _load_json(path)
    assert len(payload["active_lifecycles"]) == 1
    assert (
        payload["active_lifecycles"][0]["close_submission_contour"]["truth_classification"]
        == "POSITION_PRESENT_AND_SUBMITTABLE"
    )

    with patch(
        "apps.reference.domains.execution_position.fsm.write_pending_brackets_cleared"
    ):
        changed = fsm._apply_authoritative_local_close_reset(
            symbol,
            reason="unit_test_reset_flat_contour",
            source="unit_test",
        )

    assert changed is True
    assert close_flow.close_submission_restore_truth is None

    wrote = fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="after_reset_flat_contour",
        allow_empty=True,
    )
    assert wrote is True
    payload = _load_json(path)
    assert payload["active_lifecycles"] == []


def test_close_phase_unknown_and_bracket_state_unknown_when_exact_truth_absent(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    _set_runtime_state(fsm, with_close=False)

    fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="transition:manage",
        allow_empty=True,
    )

    record = _load_json(path)["active_lifecycles"][0]
    assert record["close_phase"] == "UNKNOWN"
    assert record["bracket_state"] == "UNKNOWN"
    assert record["manage_truth_source"] == TRUTH_SOURCE_RUNTIME_LOCAL
    assert record["bracket_truth_source"] == TRUTH_SOURCE_UNKNOWN


def test_deferred_bracket_ref_is_emitted_when_pending_wal_state_exists(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    _set_runtime_state(fsm, manage_state=ManageState.OPENED,
                       close_state=CloseState.OPENED)
    fsm._pending_brackets["8631999001"] = {"symbol": "BTCUSDT"}

    fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="bracket_record:test",
        allow_empty=True,
    )

    record = _load_json(path)["active_lifecycles"][0]
    assert record["bracket_state"] == "DEFERRED_PENDING_WAL"
    assert record["bracket_truth_source"] == TRUTH_SOURCE_RESTORED_PENDING_WAL
    assert record["deferred_bracket_ref"] == {"entry_order_id": "8631999001"}


def test_bracket_state_becomes_unknown_when_pending_bracket_lineage_is_ambiguous(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    _set_runtime_state(fsm)
    fsm._pending_brackets["8631000001"] = {"symbol": "BTCUSDT"}
    fsm._pending_brackets["8631000002"] = {"symbol": "BTCUSDT"}

    fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="bracket_record:ambiguous",
        allow_empty=True,
    )

    record = _load_json(path)["active_lifecycles"][0]
    assert record["bracket_state"] == "UNKNOWN"
    assert record["bracket_truth_source"] == TRUTH_SOURCE_UNKNOWN
    assert "deferred_bracket_ref" not in record


def test_guardian_reconstructed_bracket_truth_source_is_emitted(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    _set_runtime_state(fsm, manage_state=ManageState.FLAT, manage_active=False)
    fsm._set_symbol_brackets_snapshot(
        "BTCUSDT",
        sl_order_id="8631000001",
        tp_order_id="8631000002",
        truth_source=TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN,
    )

    fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="startup_order_guardian_reconcile",
        allow_empty=True,
    )

    record = _load_json(path)["active_lifecycles"][0]
    assert record["manage_phase"] == "FLAT"
    assert record["manage_truth_source"] == TRUTH_SOURCE_RUNTIME_LOCAL
    assert record["bracket_state"] == "LINKED_ACTIVE"
    assert record["bracket_truth_source"] == TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN


def test_restore_artifact_emits_linked_bracket_lineage_when_available(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    symbol = "BTCUSDT"
    _set_runtime_state(
        fsm,
        symbol=symbol,
        manage_state=ManageState.OPENED,
        close_state=CloseState.OPENED,
    )
    manage_flow = fsm.manage_flows[symbol]
    manage_flow.entry_order_id = "entry-1"
    manage_flow.entry_client_order_id = "ENTRY-CLIENT-1"
    manage_flow.sl_order_id = "sl-1"
    manage_flow.tp_order_id = "tp-1"
    manage_flow.sl_algo_client_id = "SL-CLIENT-1"
    manage_flow.tp_algo_client_id = "TP-CLIENT-1"
    fsm._set_symbol_brackets_snapshot(
        symbol,
        sl_order_id="sl-1",
        tp_order_id="tp-1",
        truth_source=TRUTH_SOURCE_RUNTIME_LOCAL,
    )

    fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="linked_bracket_lineage:test",
        allow_empty=True,
    )

    record = _load_json(path)["active_lifecycles"][0]
    assert record["bracket_state"] == "LINKED_ACTIVE"
    assert record["linked_bracket_ref"] == {
        "entry_order_id": "entry-1",
        "entry_client_order_id": "ENTRY-CLIENT-1",
        "sl_order_id": "sl-1",
        "tp_order_id": "tp-1",
        "sl_client_order_id": "SL-CLIENT-1",
        "tp_client_order_id": "TP-CLIENT-1",
    }


def test_atomic_replace_preserves_previous_committed_artifact_on_failure(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    events = []
    path = _configure_writer(fsm, tmp_path)
    fsm._startup_truth_orchestrator._restore_artifact_writer._observability_hook = lambda event, payload: events.append(
        (event, payload))
    _set_runtime_state(fsm, manage_state=ManageState.OPENED)
    assert fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="transition:open", allow_empty=True) is True
    previous = path.read_text(encoding="utf-8")

    _set_runtime_state(fsm, manage_state=ManageState.TRACKING)
    with patch("apps.reference.domains.execution_position.state.restore_artifact.os.replace", side_effect=OSError("disk full")):
        wrote = fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
            trigger="transition:track",
            allow_empty=True,
        )

    assert wrote is False
    assert path.read_text(encoding="utf-8") == previous
    assert any(
        event == "RESTORE:EXECUTION_POSITION_ARTIFACT_WRITE_FAILED" for event, _ in events)


def test_successful_write_does_not_leave_partial_authoritative_target(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    _set_runtime_state(fsm)

    fsm._startup_truth_orchestrator._persist_restore_artifact_snapshot(
        trigger="transition:test",
        allow_empty=True,
    )

    assert path.exists()
    assert list(path.parent.glob("*.tmp")) == []


@pytest.mark.asyncio
async def test_periodic_flush_is_config_driven(fsm_harness, tmp_path: Path) -> None:
    fsm, _, _ = fsm_harness
    _configure_writer(fsm, tmp_path, flush_interval_ms=1234)
    _set_runtime_state(fsm)
    fsm.set_async_loop(asyncio.get_running_loop())

    calls = []

    async def _fake_sleep_ms(value):
        calls.append(value)
        if len(calls) > 1:
            raise asyncio.CancelledError
        return None

    with patch("apps.reference.domains.execution_position.state.startup_truth_orchestrator.get_clock", return_value=SimpleNamespace(sleep_ms=_fake_sleep_ms)):
        with patch.object(fsm._startup_truth_orchestrator, "_persist_restore_artifact_snapshot", side_effect=[True, asyncio.CancelledError]) as persist:
            with pytest.raises(asyncio.CancelledError):
                await fsm._startup_truth_orchestrator._restore_artifact_loop()

    assert calls == [1234, 1234]
    assert persist.call_args_list[0].kwargs == {
        "trigger": "periodic",
        "allow_empty": False,
    }


def test_shutdown_flush_writes_when_active_state_exists(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    _set_runtime_state(fsm)

    fsm.shutdown()

    assert path.exists()
    payload = _load_json(path)
    assert payload["active_lifecycles"][0]["symbol"] == "BTCUSDT"


def test_writer_only_startup_does_not_read_existing_restore_artifact(
    fsm_config,
    tmp_path: Path,
) -> None:
    path = tmp_path / "execution_restore.json"
    path.write_text("{not-json", encoding="utf-8")
    fsm_config.domains.execution_position.restore_artifact = ExecutionPositionRestoreArtifactConfig(
        mode=ExecutionPositionRestoreArtifactMode.WRITER_ONLY,
        storage_path=str(path),
        flush_interval_ms=250,
        dark_read_max_artifact_age_ms=300000,
    )

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls:
        mock_guardian_cls.return_value.is_duplicate.return_value = False
        fsm = ExecPosFSM(config=fsm_config, fsm=_Bus())

    assert fsm.manage_flows == {}
    assert fsm.close_flows == {}
    assert path.read_text(encoding="utf-8") == "{not-json"
