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
from apps.reference.domains.execution_position.fsm_close import CloseState
from apps.reference.domains.execution_position.fsm_manage import ManageState


class _Bus:
    def __init__(self) -> None:
        self.domains = {}

    def emit(self, *args, **kwargs):
        return None

    def listen(self, *args, **kwargs):
        return None


def _configure_writer(fsm, tmp_path: Path, *, mode: str = "writer_only", flush_interval_ms: int = 25) -> Path:
    path = tmp_path / "execution_restore.json"
    fsm.config.domains.execution_position.restore_artifact = ExecutionPositionRestoreArtifactConfig(
        mode=mode,
        storage_path=str(path),
        flush_interval_ms=flush_interval_ms,
    )
    fsm._restore_artifact_writer = fsm._create_restore_artifact_writer()
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


def test_mode_off_produces_no_writer_activity(fsm_harness, tmp_path: Path) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path, mode="off")
    _set_runtime_state(fsm)

    wrote = fsm._persist_restore_artifact_snapshot(
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
    _set_runtime_state(fsm, manage_state=ManageState.WAIT_MODE, close_state=CloseState.CLOSE_COND)

    wrote = fsm._persist_restore_artifact_snapshot(
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
        "close_phase": "CLOSE_COND",
        "bracket_state": "UNKNOWN",
        "live_reconcile_required": True,
    }
    assert "contour_id" not in json.dumps(payload)
    assert "qty" not in record
    assert "equity" not in record
    assert "pnl" not in record
    assert "shadow" not in json.dumps(payload)
    assert "warm_state" not in json.dumps(payload)


def test_close_phase_unknown_and_bracket_state_unknown_when_exact_truth_absent(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    _set_runtime_state(fsm, with_close=False)

    fsm._persist_restore_artifact_snapshot(
        trigger="transition:manage",
        allow_empty=True,
    )

    record = _load_json(path)["active_lifecycles"][0]
    assert record["close_phase"] == "UNKNOWN"
    assert record["bracket_state"] == "UNKNOWN"


def test_deferred_bracket_ref_is_emitted_when_pending_wal_state_exists(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    _set_runtime_state(fsm, manage_state=ManageState.OPENED, close_state=CloseState.OPENED)
    fsm._pending_brackets["8631999001"] = {"symbol": "BTCUSDT"}

    fsm._persist_restore_artifact_snapshot(
        trigger="bracket_record:test",
        allow_empty=True,
    )

    record = _load_json(path)["active_lifecycles"][0]
    assert record["bracket_state"] == "DEFERRED_PENDING_WAL"
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

    fsm._persist_restore_artifact_snapshot(
        trigger="bracket_record:ambiguous",
        allow_empty=True,
    )

    record = _load_json(path)["active_lifecycles"][0]
    assert record["bracket_state"] == "UNKNOWN"
    assert "deferred_bracket_ref" not in record


def test_atomic_replace_preserves_previous_committed_artifact_on_failure(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    events = []
    path = _configure_writer(fsm, tmp_path)
    fsm._restore_artifact_writer._observability_hook = lambda event, payload: events.append((event, payload))
    _set_runtime_state(fsm, manage_state=ManageState.OPENED)
    assert fsm._persist_restore_artifact_snapshot(trigger="transition:open", allow_empty=True) is True
    previous = path.read_text(encoding="utf-8")

    _set_runtime_state(fsm, manage_state=ManageState.TRACKING)
    with patch("apps.reference.domains.execution_position.restore_artifact.os.replace", side_effect=OSError("disk full")):
        wrote = fsm._persist_restore_artifact_snapshot(
            trigger="transition:track",
            allow_empty=True,
        )

    assert wrote is False
    assert path.read_text(encoding="utf-8") == previous
    assert any(event == "RESTORE:EXECUTION_POSITION_ARTIFACT_WRITE_FAILED" for event, _ in events)


def test_successful_write_does_not_leave_partial_authoritative_target(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_writer(fsm, tmp_path)
    _set_runtime_state(fsm)

    fsm._persist_restore_artifact_snapshot(
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

    with patch("apps.reference.domains.execution_position.fsm.get_clock", return_value=SimpleNamespace(sleep_ms=_fake_sleep_ms)):
        with patch.object(fsm, "_persist_restore_artifact_snapshot", side_effect=[True, asyncio.CancelledError]) as persist:
            with pytest.raises(asyncio.CancelledError):
                await fsm._restore_artifact_loop()

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
    )

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian") as mock_guardian_cls:
        mock_guardian_cls.return_value.is_duplicate.return_value = False
        fsm = ExecPosFSM(config=fsm_config, fsm=_Bus())

    assert fsm.manage_flows == {}
    assert fsm.close_flows == {}
    assert path.read_text(encoding="utf-8") == "{not-json"
