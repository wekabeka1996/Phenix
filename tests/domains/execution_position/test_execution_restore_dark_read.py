import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.reference.config_models import (
    ExecutionPositionRestoreArtifactConfig,
    ExecutionPositionRestoreArtifactMode,
    ExecutionPositionStartupTruthArtifactConfig,
    ExecutionPositionStartupTruthArtifactMode,
)
from apps.reference.domains.execution_position.fsm_close import CloseState
from apps.reference.domains.execution_position.fsm_manage import ManageState
from apps.reference.domains.execution_position.restore_artifact import (
    ExecutionPositionRestoreEnvelope,
    ExecutionPositionRestoreLifecycleRecord,
    TRUTH_SOURCE_RUNTIME_LOCAL,
    TRUTH_SOURCE_UNKNOWN,
)


def _configure_dark_read(
    fsm,
    tmp_path: Path,
    *,
    age_ms: int | None = 300000,
) -> Path:
    path = tmp_path / "execution_restore.json"
    fsm.config.domains.execution_position.restore_artifact = ExecutionPositionRestoreArtifactConfig(
        mode=ExecutionPositionRestoreArtifactMode.DARK_READ,
        storage_path=str(path),
        flush_interval_ms=30000,
        dark_read_max_artifact_age_ms=age_ms,
    )
    fsm._restore_artifact_writer = fsm._create_restore_artifact_writer()
    fsm._restore_artifact_dark_reader = fsm._create_restore_artifact_dark_reader()
    return path


def _configure_startup_truth_writer(fsm, tmp_path: Path) -> Path:
    path = tmp_path / "startup_truth.jsonl"
    fsm.config.domains.execution_position.startup_truth_artifact = ExecutionPositionStartupTruthArtifactConfig(
        mode=ExecutionPositionStartupTruthArtifactMode.WRITER_ONLY,
        storage_path=str(path),
    )
    fsm._startup_truth_artifact_writer = fsm._create_startup_truth_artifact_writer()
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


def _write_envelope(path: Path, envelope: ExecutionPositionRestoreEnvelope) -> None:
    path.write_text(
        json.dumps(envelope.model_dump(mode="json", exclude_none=True), sort_keys=True),
        encoding="utf-8",
    )


def _matching_envelope(fsm, *, generated_at_ms: int = 1_775_000_000_000) -> ExecutionPositionRestoreEnvelope:
    record = fsm._build_execution_restore_artifact_records()[0]
    return ExecutionPositionRestoreEnvelope(
        schema_version="1.0.0",
        artifact_type="execution_position_restore_envelope_v1",
        generated_at_ms=generated_at_ms,
        writer_component="execution_position",
        requires_live_reconcile=True,
        active_lifecycles=[record],
    )


def test_dark_read_reports_exact_match_for_valid_matching_artifact(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_dark_read(fsm, tmp_path)
    _set_runtime_state(fsm, manage_state=ManageState.TRACKING, close_state=CloseState.OPENED)
    fsm._set_symbol_brackets_snapshot(
        "BTCUSDT",
        sl_order_id="8631000001",
        tp_order_id="8631000002",
        truth_source=TRUTH_SOURCE_RUNTIME_LOCAL,
    )
    envelope = _matching_envelope(fsm, generated_at_ms=1_775_000_000_000)
    _write_envelope(path, envelope)

    result = fsm._run_restore_artifact_dark_read_comparison(now_ms=1_775_000_001_000)

    assert result.attempted is True
    assert result.parse_success is True
    assert result.artifact_state == "valid"
    assert result.comparison_outcome == "exact_match"
    assert result.mixed_certainty is False
    assert result.mismatch_counts.exact_field_mismatch == 0
    assert result.mismatch_counts.heuristic_only_field == 0
    assert result.mismatch_counts.artifact_only_field == 0
    assert result.mismatch_counts.unknown_vs_guessed_mismatch == 0


def test_dark_read_reports_explicit_mismatch_classes(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_dark_read(fsm, tmp_path)
    _set_runtime_state(fsm, manage_state=ManageState.TRACKING, close_state=CloseState.OPENED)
    fsm._pending_brackets["8631999001"] = {"symbol": "BTCUSDT"}

    envelope = ExecutionPositionRestoreEnvelope(
        schema_version="1.0.0",
        artifact_type="execution_position_restore_envelope_v1",
        generated_at_ms=1_775_000_000_000,
        writer_component="execution_position",
        requires_live_reconcile=True,
        active_lifecycles=[
            ExecutionPositionRestoreLifecycleRecord(
                symbol="BTCUSDT",
                manage_phase="UNKNOWN",
                manage_truth_source=TRUTH_SOURCE_RUNTIME_LOCAL,
                close_phase="DONE",
                bracket_state="UNKNOWN",
                bracket_truth_source=TRUTH_SOURCE_UNKNOWN,
                live_reconcile_required=True,
            )
        ],
    )
    _write_envelope(path, envelope)

    result = fsm._run_restore_artifact_dark_read_comparison(now_ms=1_775_000_001_000)

    assert result.comparison_outcome == "mismatch"
    assert result.mixed_certainty is True
    assert result.mismatch_counts.unknown_vs_guessed_mismatch >= 1
    assert result.mismatch_counts.exact_field_mismatch >= 1
    assert result.mismatch_counts.heuristic_only_field >= 1
    assert any(sample.field == "deferred_bracket_ref.entry_order_id" for sample in result.mismatch_samples)


def test_dark_read_reports_missing_artifact(fsm_harness, tmp_path: Path) -> None:
    fsm, _, _ = fsm_harness
    _configure_dark_read(fsm, tmp_path)
    _set_runtime_state(fsm)

    result = fsm._run_restore_artifact_dark_read_comparison(now_ms=1_775_000_001_000)

    assert result.attempted is True
    assert result.artifact_state == "missing"
    assert result.parse_success is False
    assert result.comparison_outcome == "not_compared"


def test_dark_read_reports_corrupt_artifact(fsm_harness, tmp_path: Path) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_dark_read(fsm, tmp_path)
    _set_runtime_state(fsm)
    path.write_text("{not-json", encoding="utf-8")

    result = fsm._run_restore_artifact_dark_read_comparison(now_ms=1_775_000_001_000)

    assert result.artifact_state == "corrupt"
    assert result.parse_success is False
    assert result.comparison_outcome == "not_compared"


def test_dark_read_reports_not_readable_artifact(fsm_harness, tmp_path: Path) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_dark_read(fsm, tmp_path)
    _set_runtime_state(fsm)
    path.write_text("{}", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
        result = fsm._run_restore_artifact_dark_read_comparison(
            now_ms=1_775_000_001_000
        )

    assert result.attempted is True
    assert result.artifact_state == "not_readable"
    assert result.parse_success is False
    assert result.comparison_outcome == "not_compared"


def test_dark_read_reports_stale_artifact(fsm_harness, tmp_path: Path) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_dark_read(fsm, tmp_path, age_ms=1000)
    _set_runtime_state(fsm)
    envelope = _matching_envelope(fsm, generated_at_ms=1_775_000_000_000)
    _write_envelope(path, envelope)

    result = fsm._run_restore_artifact_dark_read_comparison(now_ms=1_775_000_010_500)

    assert result.parse_success is True
    assert result.artifact_state == "stale"
    assert result.artifact_age_ms == 10500
    assert result.stale_after_ms == 1000


def test_dark_read_flags_mixed_certainty_artifact(fsm_harness, tmp_path: Path) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_dark_read(fsm, tmp_path)
    _set_runtime_state(fsm)
    envelope = ExecutionPositionRestoreEnvelope(
        schema_version="1.0.0",
        artifact_type="execution_position_restore_envelope_v1",
        generated_at_ms=1_775_000_000_000,
        writer_component="execution_position",
        requires_live_reconcile=True,
        active_lifecycles=[
            ExecutionPositionRestoreLifecycleRecord(
                symbol="BTCUSDT",
                manage_phase="TRACKING",
                manage_truth_source=TRUTH_SOURCE_RUNTIME_LOCAL,
                close_phase="UNKNOWN",
                bracket_state="UNKNOWN",
                bracket_truth_source=TRUTH_SOURCE_UNKNOWN,
                live_reconcile_required=True,
            )
        ],
    )
    _write_envelope(path, envelope)

    result = fsm._run_restore_artifact_dark_read_comparison(now_ms=1_775_000_001_000)

    assert result.parse_success is True
    assert result.mixed_certainty is True
    assert result.mixed_certainty_symbols == ["BTCUSDT"]


def test_dark_read_compare_does_not_mutate_runtime_state(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_dark_read(fsm, tmp_path)
    _set_runtime_state(fsm, manage_state=ManageState.TRACKING, close_state=CloseState.CLOSE_COND)
    envelope = _matching_envelope(fsm, generated_at_ms=1_775_000_000_000)
    _write_envelope(path, envelope)
    before = [record.model_dump(mode="json", exclude_none=True) for record in fsm._build_execution_restore_artifact_records()]

    result = fsm._run_restore_artifact_dark_read_comparison(now_ms=1_775_000_001_000)
    after = [record.model_dump(mode="json", exclude_none=True) for record in fsm._build_execution_restore_artifact_records()]

    assert result.comparison_outcome == "exact_match"
    assert before == after


@pytest.mark.asyncio
async def test_startup_reconcile_records_dark_read_status_without_changing_authority(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    restore_path = _configure_dark_read(fsm, tmp_path, age_ms=None)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    _set_runtime_state(fsm, manage_state=ManageState.TRACKING, close_state=CloseState.OPENED)
    _write_envelope(restore_path, _matching_envelope(fsm, generated_at_ms=4_102_444_800_000))

    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.adapter = None
    before = [record.model_dump(mode="json", exclude_none=True) for record in fsm._build_execution_restore_artifact_records()]

    await fsm._startup_order_guardian_reconcile()

    records = [
        json.loads(line)
        for line in startup_truth_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    dark_read = records[0]["restore_dark_read"]
    assert dark_read["attempted"] is True
    assert dark_read["artifact_state"] == "valid"
    assert dark_read["comparison_outcome"] == "exact_match"
    assert records[0]["restore_authoritative"]["attempted"] is False
    assert records[0]["reconcile_sequence"] == [
        "authoritative_restore_read",
        "collect_startup_symbols",
        "guardian_link_existing_from_rest",
        "guardian_cleanup_orphans",
        "fetch_post_cleanup_open_orders",
        "reconstruct_runtime_bracket_truth",
        "dark_read_compare",
        "persist_restore_artifact_snapshot",
    ]
    after = [record.model_dump(mode="json", exclude_none=True) for record in fsm._build_execution_restore_artifact_records()]
    assert before == after


@pytest.mark.asyncio
async def test_startup_reconcile_mismatch_artifact_does_not_change_runtime_authority(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    restore_path = _configure_dark_read(fsm, tmp_path, age_ms=None)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    _set_runtime_state(fsm, manage_state=ManageState.TRACKING, close_state=CloseState.OPENED)
    fsm._pending_brackets["8631999001"] = {"symbol": "BTCUSDT"}
    _write_envelope(
        restore_path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=4_102_444_800_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[
                ExecutionPositionRestoreLifecycleRecord(
                    symbol="BTCUSDT",
                    manage_phase="UNKNOWN",
                    manage_truth_source=TRUTH_SOURCE_RUNTIME_LOCAL,
                    close_phase="DONE",
                    bracket_state="UNKNOWN",
                    bracket_truth_source=TRUTH_SOURCE_UNKNOWN,
                    live_reconcile_required=True,
                )
            ],
        ),
    )

    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.adapter = None
    before = [
        record.model_dump(mode="json", exclude_none=True)
        for record in fsm._build_execution_restore_artifact_records()
    ]

    await fsm._startup_order_guardian_reconcile()

    records = [
        json.loads(line)
        for line in startup_truth_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    dark_read = records[0]["restore_dark_read"]
    assert dark_read["attempted"] is True
    assert dark_read["artifact_state"] == "valid"
    assert dark_read["comparison_outcome"] == "mismatch"
    assert records[0]["restore_authoritative"]["attempted"] is False
    assert dark_read["mismatch_counts"]["unknown_vs_guessed_mismatch"] >= 1
    assert dark_read["mismatch_counts"]["exact_field_mismatch"] >= 1
    assert dark_read["mismatch_counts"]["heuristic_only_field"] >= 1
    after = [
        record.model_dump(mode="json", exclude_none=True)
        for record in fsm._build_execution_restore_artifact_records()
    ]
    assert before == after
