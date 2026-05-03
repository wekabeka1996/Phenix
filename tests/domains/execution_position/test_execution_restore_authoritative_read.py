import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from apps.reference.config_models import (
    ExecutionPositionRestoreArtifactConfig,
    ExecutionPositionRestoreArtifactMode,
    ExecutionPositionStartupTruthArtifactConfig,
    ExecutionPositionStartupTruthArtifactMode,
)
from apps.reference.domains.execution_position.flows.close.fsm_close import CloseState
from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageState
from apps.reference.domains.execution_position.state.order_index import OrderIndex
from apps.reference.domains.execution_position.state.restore_artifact import (
    BRACKET_STATE_DEFERRED_PENDING_WAL,
    BRACKET_STATE_LINKED_ACTIVE,
    BRACKET_STATE_UNKNOWN,
    ExecutionPositionRestoreEnvelope,
    ExecutionPositionRestoreLifecycleRecord,
    LinkedBracketRef,
    TRUTH_SOURCE_RESTORE_ARTIFACT,
    TRUTH_SOURCE_RUNTIME_LOCAL,
    TRUTH_SOURCE_UNKNOWN,
)


def _configure_authoritative(
    fsm,
    tmp_path: Path,
    *,
    age_ms: int | None = 300000,
) -> Path:
    path = tmp_path / "execution_restore.json"
    fsm.config.domains.execution_position.restore_artifact = ExecutionPositionRestoreArtifactConfig(
        mode=ExecutionPositionRestoreArtifactMode.AUTHORITATIVE,
        storage_path=str(path),
        flush_interval_ms=30000,
        dark_read_max_artifact_age_ms=age_ms,
    )
    fsm._startup_truth_orchestrator._restore_artifact_writer = fsm._startup_truth_orchestrator._create_restore_artifact_writer()
    fsm._startup_truth_orchestrator._restore_artifact_dark_reader = fsm._startup_truth_orchestrator._create_restore_artifact_dark_reader()
    return path


def _configure_startup_truth_writer(fsm, tmp_path: Path) -> Path:
    path = tmp_path / "startup_truth.jsonl"
    fsm.config.domains.execution_position.startup_truth_artifact = ExecutionPositionStartupTruthArtifactConfig(
        mode=ExecutionPositionStartupTruthArtifactMode.WRITER_ONLY,
        storage_path=str(path),
    )
    fsm._startup_truth_orchestrator._startup_truth_artifact_writer = fsm._startup_truth_orchestrator._create_startup_truth_artifact_writer()
    return path


def _configure_terminal_identity_cache(
    fsm,
    tmp_path: Path,
    *,
    configured_name: str = "execution_terminal_identity_cache_v1.json",
) -> Path:
    path = tmp_path / configured_name
    warm_state = fsm.config.domains.execution_position.event_dedup.warm_state
    warm_state.enabled = True
    warm_state.storage_path = str(path)
    warm_state.max_entries = 2000
    hardening = fsm._execution_truth_hardening
    hardening.warm_state_enabled = True
    hardening.warm_state_storage_path = path
    hardening.warm_state_max_entries = 2000
    return path


def _write_terminal_identity_cache(
    path: Path,
    *,
    order_id: str = "7777",
    client_order_id: str = "ENTRY-BTCUSDT-CACHE-1",
    state_type: str = "execution_terminal_identity_cache_v1",
) -> None:
    now_ms = int(time.time() * 1000)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "state_type": state_type,
                "truth_class": "cache_only",
                "authoritative": False,
                "cache_kind": "exact_terminal_fill_identity_dedupe_seed",
                "generated_at_ms": now_ms,
                "retention_ms": 86400000,
                "max_entries": 2000,
                "entries": [
                    {
                        "key": (
                            f"trade_executed:BTCUSDT:order_id={order_id}:"
                            f"client_order_id={client_order_id}"
                        ),
                        "ts_ms": now_ms,
                        "symbol": "BTCUSDT",
                        "order_id": order_id,
                        "client_order_id": client_order_id,
                        "identity_quality": "order_lifecycle_contract_identity",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_envelope(path: Path, envelope: ExecutionPositionRestoreEnvelope) -> None:
    path.write_text(
        json.dumps(envelope.model_dump(
            mode="json", exclude_none=True), sort_keys=True),
        encoding="utf-8",
    )


def _record(
    *,
    symbol: str = "BTCUSDT",
    manage_phase: str = "TRACKING",
    close_phase: str = "OPENED",
    bracket_state: str = BRACKET_STATE_UNKNOWN,
    deferred_entry_order_id: str | None = None,
    linked_bracket_ref: dict | None = None,
) -> ExecutionPositionRestoreLifecycleRecord:
    kwargs = {
        "symbol": symbol,
        "manage_phase": manage_phase,
        "manage_truth_source": TRUTH_SOURCE_RUNTIME_LOCAL,
        "close_phase": close_phase,
        "bracket_state": bracket_state,
        "bracket_truth_source": TRUTH_SOURCE_UNKNOWN,
        "live_reconcile_required": True,
    }
    if deferred_entry_order_id:
        kwargs["deferred_bracket_ref"] = {
            "entry_order_id": deferred_entry_order_id}
    if linked_bracket_ref:
        kwargs["linked_bracket_ref"] = linked_bracket_ref
    return ExecutionPositionRestoreLifecycleRecord.model_validate(kwargs)


def _load_startup_truth_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_authoritative_read_restores_exact_manage_and_close_fields_from_envelope(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path)
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=1_775_000_000_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[_record()],
        ),
    )

    result = fsm._startup_truth_orchestrator._run_restore_artifact_authoritative_read(
        now_ms=1_775_000_001_000)

    assert result.attempted is True
    assert result.parse_success is True
    assert result.artifact_state == "valid"
    assert result.applied_record_count == 1
    assert result.restored_exact_field_count == 2
    assert result.restored_unknown_field_count == 1
    assert fsm.manage_flows["BTCUSDT"].state == ManageState.TRACKING
    assert fsm.close_flows["BTCUSDT"].state == CloseState.OPENED
    assert fsm._manage_truth_source_for(
        "BTCUSDT") == TRUTH_SOURCE_RESTORE_ARTIFACT
    assert "BTCUSDT" not in fsm._symbol_brackets
    assert result.symbol_statuses[0].manage_phase_restore_status == "exact"
    assert result.symbol_statuses[0].close_phase_restore_status == "exact"
    assert result.symbol_statuses[0].bracket_state_restore_status == "unknown"


def test_authoritative_read_keeps_linked_bracket_state_unknown_without_lineage(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path)
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=1_775_000_000_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[
                _record(
                    manage_phase="OPENED",
                    close_phase="OPENED",
                    bracket_state=BRACKET_STATE_LINKED_ACTIVE,
                )
            ],
        ),
    )

    result = fsm._startup_truth_orchestrator._run_restore_artifact_authoritative_read(
        now_ms=1_775_000_001_000)

    assert result.artifact_state == "valid"
    symbol_status = result.symbol_statuses[0]
    assert symbol_status.bracket_state_value == BRACKET_STATE_UNKNOWN
    assert symbol_status.bracket_state_restore_status == "unknown"
    assert "bracket_lineage_not_restorable_from_envelope" in symbol_status.unresolved_reasons
    current = fsm._startup_truth_orchestrator._build_execution_restore_artifact_records()[
        0]
    assert current.bracket_state == BRACKET_STATE_UNKNOWN


def test_authoritative_read_restores_linked_bracket_state_exact_with_lineage(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path)
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=1_775_000_000_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[
                _record(
                    manage_phase="OPENED",
                    close_phase="OPENED",
                    bracket_state=BRACKET_STATE_LINKED_ACTIVE,
                    linked_bracket_ref={
                        "entry_order_id": "entry-1",
                        "entry_client_order_id": "ENTRY-CLIENT-1",
                        "sl_order_id": "sl-1",
                        "tp_order_id": "tp-1",
                        "sl_client_order_id": "SL-CLIENT-1",
                        "tp_client_order_id": "TP-CLIENT-1",
                    },
                )
            ],
        ),
    )

    result = fsm._startup_truth_orchestrator._run_restore_artifact_authoritative_read(
        now_ms=1_775_000_001_000)

    symbol_status = result.symbol_statuses[0]
    assert symbol_status.bracket_state_value == BRACKET_STATE_LINKED_ACTIVE
    assert symbol_status.bracket_state_restore_status == "exact"
    assert "bracket_lineage_not_restorable_from_envelope" not in symbol_status.unresolved_reasons
    current = fsm._startup_truth_orchestrator._build_execution_restore_artifact_records()[
        0]
    assert current.bracket_state == BRACKET_STATE_LINKED_ACTIVE
    assert current.linked_bracket_ref == LinkedBracketRef(
        entry_order_id="entry-1",
        entry_client_order_id="ENTRY-CLIENT-1",
        sl_order_id="sl-1",
        tp_order_id="tp-1",
        sl_client_order_id="SL-CLIENT-1",
        tp_client_order_id="TP-CLIENT-1",
    )
    assert fsm.manage_flows["BTCUSDT"].entry_order_id == "entry-1"
    assert fsm.manage_flows["BTCUSDT"].entry_client_order_id == "ENTRY-CLIENT-1"
    assert fsm.manage_flows["BTCUSDT"].sl_order_id == "sl-1"
    assert fsm.manage_flows["BTCUSDT"].tp_order_id == "tp-1"


def test_authoritative_read_restores_deferred_pending_only_when_pending_wal_matches(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path)
    fsm._pending_brackets["8631999001"] = {"symbol": "BTCUSDT"}
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=1_775_000_000_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[
                _record(
                    manage_phase="OPENED",
                    close_phase="OPENED",
                    bracket_state=BRACKET_STATE_DEFERRED_PENDING_WAL,
                    deferred_entry_order_id="8631999001",
                )
            ],
        ),
    )

    result = fsm._startup_truth_orchestrator._run_restore_artifact_authoritative_read(
        now_ms=1_775_000_001_000)

    symbol_status = result.symbol_statuses[0]
    assert symbol_status.bracket_state_value == BRACKET_STATE_DEFERRED_PENDING_WAL
    assert symbol_status.bracket_state_restore_status == "exact"
    current = fsm._startup_truth_orchestrator._build_execution_restore_artifact_records()[
        0]
    assert current.bracket_state == BRACKET_STATE_DEFERRED_PENDING_WAL
    assert current.deferred_bracket_ref.entry_order_id == "8631999001"


def test_authoritative_read_handles_not_readable_without_applying_truth(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path)
    path.write_text("{}", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
        result = fsm._startup_truth_orchestrator._run_restore_artifact_authoritative_read(
            now_ms=1_775_000_001_000
        )

    assert result.attempted is True
    assert result.artifact_state == "not_readable"
    assert result.parse_success is False
    assert fsm.manage_flows == {}
    assert fsm.close_flows == {}


@pytest.mark.asyncio
async def test_startup_reconcile_authoritative_corrupt_artifact_is_visible_and_non_authoritative(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    path.write_text("{not-json", encoding="utf-8")
    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": "BTCUSDT", "positionAmt": "0.10"}]
    )
    fsm.adapter.get_open_orders = AsyncMock(side_effect=[[], []])

    await fsm._startup_order_guardian_reconcile()

    rows = _load_startup_truth_rows(startup_truth_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["restore_authoritative"]["attempted"] is True
    assert row["restore_authoritative"]["artifact_state"] == "corrupt"
    assert row["restore_authoritative"]["parse_success"] is False
    assert row["restore_dark_read"]["attempted"] is False
    assert fsm.manage_flows == {}
    assert fsm.close_flows == {}


def test_authoritative_read_handles_stale_artifact_without_applying_truth(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path, age_ms=1000)
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=1_775_000_000_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[_record()],
        ),
    )

    result = fsm._startup_truth_orchestrator._run_restore_artifact_authoritative_read(
        now_ms=1_775_000_010_500)

    assert result.parse_success is True
    assert result.artifact_state == "stale"
    assert result.artifact_age_ms == 10500
    assert fsm.manage_flows == {}
    assert fsm.close_flows == {}


def test_authoritative_read_handles_mixed_certainty_without_promoting_unknown_fields(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path)
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=1_775_000_000_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[
                _record(
                    manage_phase="TRACKING",
                    close_phase="UNKNOWN",
                    bracket_state=BRACKET_STATE_LINKED_ACTIVE,
                )
            ],
        ),
    )

    result = fsm._startup_truth_orchestrator._run_restore_artifact_authoritative_read(
        now_ms=1_775_000_001_000)

    assert result.parse_success is True
    assert result.artifact_state == "valid"
    assert result.mixed_certainty is True
    assert result.mixed_certainty_symbols == ["BTCUSDT"]
    assert fsm.manage_flows["BTCUSDT"].state == ManageState.TRACKING
    assert "BTCUSDT" not in fsm.close_flows
    current = fsm._startup_truth_orchestrator._build_execution_restore_artifact_records()[
        0]
    assert current.manage_phase == "TRACKING"
    assert current.close_phase == "UNKNOWN"
    assert current.bracket_state == "UNKNOWN"
    symbol_status = result.symbol_statuses[0]
    assert symbol_status.manage_phase_restore_status == "exact"
    assert symbol_status.close_phase_restore_status == "unknown"
    assert symbol_status.bracket_state_restore_status == "unknown"
    assert "bracket_lineage_not_restorable_from_envelope" in symbol_status.unresolved_reasons


def test_authoritative_startup_skips_heuristic_snapshot_hydrate_even_with_positions(
    fsm_harness,
) -> None:
    fsm, _, _ = fsm_harness
    fsm.config.domains.execution_position.restore_artifact = ExecutionPositionRestoreArtifactConfig(
        mode=ExecutionPositionRestoreArtifactMode.AUTHORITATIVE,
        storage_path="ops/restore/execution_position_restore_envelope_v1.json",
        flush_interval_ms=30000,
        dark_read_max_artifact_age_ms=300000,
    )

    hydrated = fsm.restore_startup_from_snapshot_positions(
        {
            "BTCUSDT": {
                "quantity": 0.5,
                "avg_price": 101.25,
            }
        }
    )

    assert hydrated == 0
    assert fsm.manage_flows == {}
    assert fsm.close_flows == {}


@pytest.mark.asyncio
async def test_startup_reconcile_authoritative_missing_artifact_does_not_guess_from_portfolio(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    _configure_authoritative(fsm, tmp_path)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": "BTCUSDT", "positionAmt": "0.10"}]
    )
    fsm.adapter.get_open_orders = AsyncMock(side_effect=[[], []])

    await fsm._startup_order_guardian_reconcile()

    rows = _load_startup_truth_rows(startup_truth_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["restore_authoritative"]["attempted"] is True
    assert row["restore_authoritative"]["artifact_state"] == "missing"
    assert row["restore_dark_read"]["attempted"] is False
    assert row["reconcile_sequence"] == [
        "authoritative_restore_read",
        "collect_startup_symbols",
        "guardian_link_existing_from_rest",
        "guardian_cleanup_orphans",
        "fetch_post_cleanup_open_orders",
        "reconstruct_runtime_bracket_truth",
        "dark_read_compare",
        "persist_restore_artifact_snapshot",
    ]
    assert fsm.manage_flows == {}
    assert fsm.close_flows == {}
    assert row["unknown_truth_records"] == [
        {
            "symbol": "BTCUSDT",
            "lifecycle_truth_class": "unknown",
            "authoritative_artifact_state": "missing",
            "portfolio_presence": "present",
            "reconstructed_exact_truth_present": False,
            "observed_inputs": ["position_symbols_observed", "symbols_considered"],
            "reason_codes": [
                "authoritative_artifact_missing",
                "portfolio_present_without_restored_lifecycle_truth",
            ],
        }
    ]


@pytest.mark.asyncio
async def test_authoritative_startup_restore_succeeds_without_terminal_identity_cache_file(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path, age_ms=None)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    cache_path = _configure_terminal_identity_cache(fsm, tmp_path)
    fsm._execution_truth_hardening.load_warm_state()
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=4_102_444_800_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[_record()],
        ),
    )
    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(return_value=[])
    fsm.adapter.get_open_orders = AsyncMock(side_effect=[[], []])

    await fsm._startup_order_guardian_reconcile()

    assert fsm.manage_flows["BTCUSDT"].state == ManageState.TRACKING
    assert fsm.close_flows["BTCUSDT"].state == CloseState.OPENED
    rows = _load_startup_truth_rows(startup_truth_path)
    cache_status = rows[0]["execution_truth_cache"]
    assert cache_status["truth_class"] == "cache_only"
    assert cache_status["authoritative"] is False
    assert cache_status["status"] == "empty"
    assert cache_status["configured_path"] == str(cache_path)


@pytest.mark.asyncio
async def test_authoritative_startup_terminal_identity_cache_cannot_override_restore_truth(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path, age_ms=None)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    cache_path = _configure_terminal_identity_cache(fsm, tmp_path)
    _write_terminal_identity_cache(cache_path)
    fsm._execution_truth_hardening.load_warm_state()
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=4_102_444_800_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[_record()],
        ),
    )
    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(return_value=[])
    fsm.adapter.get_open_orders = AsyncMock(side_effect=[[], []])

    await fsm._startup_order_guardian_reconcile()

    assert fsm.manage_flows["BTCUSDT"].state == ManageState.TRACKING
    assert fsm.close_flows["BTCUSDT"].state == CloseState.OPENED
    rows = _load_startup_truth_rows(startup_truth_path)
    cache_status = rows[0]["execution_truth_cache"]
    assert cache_status["status"] == "loaded"
    assert rows[0]["restore_authoritative"]["symbol_statuses"][0]["manage_phase_value"] == "TRACKING"
    assert rows[0]["restore_authoritative"]["symbol_statuses"][0]["close_phase_value"] == "OPENED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("artifact_state", "age_ms"),
    [
        ("missing", None),
        ("corrupt", None),
        ("stale", 1000),
    ],
)
async def test_authoritative_startup_loaded_cache_does_not_fabricate_lifecycle_truth_when_restore_is_unusable(
    fsm_harness,
    tmp_path: Path,
    artifact_state: str,
    age_ms: int | None,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path, age_ms=age_ms)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    cache_path = _configure_terminal_identity_cache(fsm, tmp_path)
    _write_terminal_identity_cache(cache_path)
    fsm._execution_truth_hardening.load_warm_state()
    if artifact_state == "corrupt":
        path.write_text("{not-json", encoding="utf-8")
    elif artifact_state == "stale":
        _write_envelope(
            path,
            ExecutionPositionRestoreEnvelope(
                schema_version="1.0.0",
                artifact_type="execution_position_restore_envelope_v1",
                generated_at_ms=1_775_000_000_000,
                writer_component="execution_position",
                requires_live_reconcile=True,
                active_lifecycles=[_record()],
            ),
        )

    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": "BTCUSDT", "positionAmt": "0.10"}]
    )
    fsm.adapter.get_open_orders = AsyncMock(side_effect=[[], []])

    await fsm._startup_order_guardian_reconcile()

    rows = _load_startup_truth_rows(startup_truth_path)
    row = rows[0]
    assert row["execution_truth_cache"]["status"] == "loaded"
    assert row["restore_authoritative"]["artifact_state"] == artifact_state
    assert fsm.manage_flows == {}
    assert fsm.close_flows == {}
    assert row["unknown_truth_records"] == [
        {
            "symbol": "BTCUSDT",
            "lifecycle_truth_class": "unknown",
            "authoritative_artifact_state": artifact_state,
            "portfolio_presence": "present",
            "reconstructed_exact_truth_present": False,
            "observed_inputs": ["position_symbols_observed", "symbols_considered"],
            "reason_codes": [
                f"authoritative_artifact_{artifact_state}",
                "portfolio_present_without_restored_lifecycle_truth",
            ],
        }
    ]


@pytest.mark.asyncio
async def test_authoritative_startup_surfaces_cache_only_legacy_alias_compatibility_marker(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path, age_ms=None)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    configured_cache_path = tmp_path / "execution_terminal_identity_cache_v1.json"
    legacy_cache_path = tmp_path / "execution_truth_warm_state_v1.json"
    _write_terminal_identity_cache(
        legacy_cache_path,
        client_order_id="ENTRY-BTCUSDT-CACHE-LEGACY",
        state_type="execution_truth_warm_state_v1",
    )
    _configure_terminal_identity_cache(
        fsm,
        tmp_path,
        configured_name="execution_terminal_identity_cache_v1.json",
    )
    fsm._execution_truth_hardening.load_warm_state()
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=4_102_444_800_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[_record()],
        ),
    )
    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(return_value=[])
    fsm.adapter.get_open_orders = AsyncMock(side_effect=[[], []])

    await fsm._startup_order_guardian_reconcile()

    rows = _load_startup_truth_rows(startup_truth_path)
    cache_status = rows[0]["execution_truth_cache"]
    assert cache_status["truth_class"] == "cache_only"
    assert cache_status["compatibility_mode"] == "legacy_path_alias"
    assert cache_status["configured_path"] == str(configured_cache_path)
    assert cache_status["active_path"] == str(legacy_cache_path)
    assert cache_status["legacy_alias_path"] == str(legacy_cache_path)


@pytest.mark.asyncio
async def test_startup_reconcile_preserves_restored_exact_phase_when_portfolio_absent(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path, age_ms=None)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=4_102_444_800_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[_record()],
        ),
    )
    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(return_value=[])
    fsm.adapter.get_open_orders = AsyncMock(side_effect=[[], []])

    await fsm._startup_order_guardian_reconcile()

    assert fsm.manage_flows["BTCUSDT"].state == ManageState.TRACKING
    assert fsm.close_flows["BTCUSDT"].state == CloseState.OPENED
    assert fsm._manage_truth_source_for(
        "BTCUSDT") == TRUTH_SOURCE_RESTORE_ARTIFACT

    rows = _load_startup_truth_rows(startup_truth_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["restore_authoritative"]["artifact_state"] == "valid"
    assert row["restore_dark_read"]["attempted"] is False
    assert row["unknown_truth_records"] == []
    symbol_status = row["restore_authoritative"]["symbol_statuses"][0]
    assert symbol_status["portfolio_presence"] == "absent"
    assert "portfolio_symbol_absent" in symbol_status["unresolved_reasons"]
    assert symbol_status["runtime_override_fields"] == []


@pytest.mark.asyncio
async def test_startup_reconcile_surfaces_positive_runtime_override_after_authoritative_restore(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    symbol = "BTCUSDT"
    path = _configure_authoritative(fsm, tmp_path, age_ms=None)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    fsm._trade_lifecycle_log_path = lambda: str(
        tmp_path / "trade_lifecycle.jsonl")
    fsm.fsm.order_index = OrderIndex(ttl_sec=600)
    fsm._pending_brackets["8631999001"] = {"symbol": symbol}
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=4_102_444_800_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[
                _record(
                    symbol=symbol,
                    manage_phase="TRACKING",
                    close_phase="OPENED",
                    bracket_state=BRACKET_STATE_DEFERRED_PENDING_WAL,
                    deferred_entry_order_id="8631999001",
                )
            ],
        ),
    )

    async def _cleanup_orphans():
        fsm._pending_brackets.pop("8631999001", None)
        return None

    fsm.order_guardian.cleanup_orphans = AsyncMock(
        side_effect=_cleanup_orphans)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)

    def _resolve_context(*, client_order_id, exchange_order_id, symbol=None):
        if exchange_order_id == "8631145709":
            return {
                "symbol": symbol,
                "rid": "aurora_BTCUSDT_1775247901546",
                "parent_entry_order_id": "entry-btc-1",
                "tracked_bracket_order_id": "8631145709",
                "tracked_client_order_id": "SL-BTCUSDT-1",
                "bracket_role": "SL",
                "order_type": "STOP_MARKET",
                "reduce_only": True,
                "close_position": True,
            }
        if exchange_order_id == "8631145710":
            return {
                "symbol": symbol,
                "rid": "aurora_BTCUSDT_1775247901546",
                "parent_entry_order_id": "entry-btc-1",
                "tracked_bracket_order_id": "8631145710",
                "tracked_client_order_id": "TP-BTCUSDT-1",
                "bracket_role": "TP",
                "order_type": "TAKE_PROFIT_MARKET",
                "reduce_only": True,
                "close_position": True,
            }
        return None

    fsm.order_guardian.resolve_terminal_bracket_context = _resolve_context
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": symbol, "positionAmt": "0.10"}]
    )
    open_orders = [
        {
            "symbol": symbol,
            "orderId": "8631145709",
            "clientOrderId": "exchange-algo-sl",
            "side": "SELL",
            "type": "STOP_MARKET",
        },
        {
            "symbol": symbol,
            "orderId": "8631145710",
            "clientOrderId": "exchange-algo-tp",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
        },
    ]
    fsm.adapter.get_open_orders = AsyncMock(
        side_effect=[open_orders, open_orders])

    await fsm._startup_order_guardian_reconcile()

    rows = _load_startup_truth_rows(startup_truth_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["runtime_truth_summary"]["symbols_reconstructed"] == 1
    assert row["unknown_truth_records"] == []
    symbol_status = row["restore_authoritative"]["symbol_statuses"][0]
    assert symbol_status["bracket_state_restore_status"] == "exact"
    assert "bracket_state" in symbol_status["runtime_override_fields"]
    assert row["runtime_truth_records"][0]["manage_truth_source"] == TRUTH_SOURCE_RESTORE_ARTIFACT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("artifact_state", "age_ms"),
    [
        ("missing", None),
        ("corrupt", None),
        ("stale", 1000),
    ],
)
async def test_degraded_authoritative_startup_emits_explicit_unknown_rows_for_observed_symbols(
    fsm_harness,
    tmp_path: Path,
    artifact_state: str,
    age_ms: int | None,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path, age_ms=age_ms)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": "ETHUSDT", "positionAmt": "0.10"}]
    )
    fsm.adapter.get_open_orders = AsyncMock(side_effect=[[], []])

    if artifact_state == "corrupt":
        path.write_text("{not-json", encoding="utf-8")
    elif artifact_state == "stale":
        _write_envelope(
            path,
            ExecutionPositionRestoreEnvelope(
                schema_version="1.0.0",
                artifact_type="execution_position_restore_envelope_v1",
                generated_at_ms=1_775_000_000_000,
                writer_component="execution_position",
                requires_live_reconcile=True,
                active_lifecycles=[_record(symbol="ETHUSDT")],
            ),
        )

    await fsm._startup_order_guardian_reconcile()

    row = _load_startup_truth_rows(startup_truth_path)[0]
    assert row["restore_authoritative"]["artifact_state"] == artifact_state
    assert row["restore_authoritative"]["symbol_statuses"] == []
    assert row["runtime_truth_records"] == []
    assert row["unknown_truth_records"] == [
        {
            "symbol": "ETHUSDT",
            "lifecycle_truth_class": "unknown",
            "authoritative_artifact_state": artifact_state,
            "portfolio_presence": "present",
            "reconstructed_exact_truth_present": False,
            "observed_inputs": ["position_symbols_observed", "symbols_considered"],
            "reason_codes": [
                f"authoritative_artifact_{artifact_state}",
                "portfolio_present_without_restored_lifecycle_truth",
            ],
        }
    ]
    assert fsm.manage_flows == {}
    assert fsm.close_flows == {}


@pytest.mark.asyncio
async def test_degraded_authoritative_startup_emits_unknown_row_for_not_readable_artifact(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    path = _configure_authoritative(fsm, tmp_path, age_ms=None)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    path.write_text("{}", encoding="utf-8")
    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": "ETHUSDT", "positionAmt": "0.10"}]
    )
    fsm.adapter.get_open_orders = AsyncMock(side_effect=[[], []])

    with patch.object(
        Path,
        "read_text",
        autospec=True,
        side_effect=PermissionError("denied"),
    ):
        await fsm._startup_order_guardian_reconcile()

    row = _load_startup_truth_rows(startup_truth_path)[0]
    assert row["restore_authoritative"]["artifact_state"] == "not_readable"
    assert row["unknown_truth_records"] == [
        {
            "symbol": "ETHUSDT",
            "lifecycle_truth_class": "unknown",
            "authoritative_artifact_state": "not_readable",
            "portfolio_presence": "present",
            "reconstructed_exact_truth_present": False,
            "observed_inputs": ["position_symbols_observed", "symbols_considered"],
            "reason_codes": [
                "authoritative_artifact_not_readable",
                "portfolio_present_without_restored_lifecycle_truth",
            ],
        }
    ]


@pytest.mark.asyncio
async def test_degraded_authoritative_startup_does_not_emit_unknown_row_when_runtime_reconstruction_is_exact(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    symbol = "ETHUSDT"
    path = _configure_authoritative(fsm, tmp_path, age_ms=1000)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    fsm._trade_lifecycle_log_path = lambda: str(
        tmp_path / "trade_lifecycle.jsonl")
    fsm.fsm.order_index = OrderIndex(ttl_sec=600)
    _write_envelope(
        path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=1_775_000_000_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[_record(symbol=symbol)],
        ),
    )
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)

    def _resolve_context(*, client_order_id, exchange_order_id, symbol=None):
        if exchange_order_id == "8631145709":
            return {
                "symbol": symbol,
                "rid": "aurora_ETHUSDT_1775247901546",
                "parent_entry_order_id": "entry-eth-1",
                "tracked_bracket_order_id": "8631145709",
                "tracked_client_order_id": "SL-ETHUSDT-1",
                "bracket_role": "SL",
                "order_type": "STOP_MARKET",
                "reduce_only": True,
                "close_position": True,
            }
        if exchange_order_id == "8631145710":
            return {
                "symbol": symbol,
                "rid": "aurora_ETHUSDT_1775247901546",
                "parent_entry_order_id": "entry-eth-1",
                "tracked_bracket_order_id": "8631145710",
                "tracked_client_order_id": "TP-ETHUSDT-1",
                "bracket_role": "TP",
                "order_type": "TAKE_PROFIT_MARKET",
                "reduce_only": True,
                "close_position": True,
            }
        return None

    fsm.order_guardian.resolve_terminal_bracket_context = _resolve_context
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": symbol, "positionAmt": "0.10"}]
    )
    open_orders = [
        {
            "symbol": symbol,
            "orderId": "8631145709",
            "clientOrderId": "exchange-algo-sl",
            "side": "SELL",
            "type": "STOP_MARKET",
        },
        {
            "symbol": symbol,
            "orderId": "8631145710",
            "clientOrderId": "exchange-algo-tp",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
        },
    ]
    fsm.adapter.get_open_orders = AsyncMock(
        side_effect=[open_orders, open_orders])

    await fsm._startup_order_guardian_reconcile()

    row = _load_startup_truth_rows(startup_truth_path)[0]
    assert row["restore_authoritative"]["artifact_state"] == "stale"
    assert row["runtime_truth_records"][0]["status"] == "reconstructed"
    assert row["unknown_truth_records"] == []


@pytest.mark.asyncio
async def test_degraded_startup_truth_surface_makes_unknown_reconstructed_and_cache_only_categories_visible(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, _ = fsm_harness
    restore_path = _configure_authoritative(fsm, tmp_path, age_ms=1000)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)
    cache_path = _configure_terminal_identity_cache(fsm, tmp_path)
    _write_terminal_identity_cache(cache_path)
    fsm._execution_truth_hardening.load_warm_state()
    fsm._trade_lifecycle_log_path = lambda: str(
        tmp_path / "trade_lifecycle.jsonl")
    fsm.fsm.order_index = OrderIndex(ttl_sec=600)
    _write_envelope(
        restore_path,
        ExecutionPositionRestoreEnvelope(
            schema_version="1.0.0",
            artifact_type="execution_position_restore_envelope_v1",
            generated_at_ms=1_775_000_000_000,
            writer_component="execution_position",
            requires_live_reconcile=True,
            active_lifecycles=[_record(symbol="ETHUSDT")],
        ),
    )
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)

    def _resolve_context(*, client_order_id, exchange_order_id, symbol=None):
        if exchange_order_id == "8631145709":
            return {
                "symbol": symbol,
                "rid": "aurora_BTCUSDT_1775247901546",
                "parent_entry_order_id": "entry-btc-1",
                "tracked_bracket_order_id": "8631145709",
                "tracked_client_order_id": "SL-BTCUSDT-1",
                "bracket_role": "SL",
                "order_type": "STOP_MARKET",
                "reduce_only": True,
                "close_position": True,
            }
        if exchange_order_id == "8631145710":
            return {
                "symbol": symbol,
                "rid": "aurora_BTCUSDT_1775247901546",
                "parent_entry_order_id": "entry-btc-1",
                "tracked_bracket_order_id": "8631145710",
                "tracked_client_order_id": "TP-BTCUSDT-1",
                "bracket_role": "TP",
                "order_type": "TAKE_PROFIT_MARKET",
                "reduce_only": True,
                "close_position": True,
            }
        return None

    fsm.order_guardian.resolve_terminal_bracket_context = _resolve_context
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[
            {"symbol": "BTCUSDT", "positionAmt": "0.10"},
            {"symbol": "ETHUSDT", "positionAmt": "0.20"},
        ]
    )
    open_orders = [
        {
            "symbol": "BTCUSDT",
            "orderId": "8631145709",
            "clientOrderId": "exchange-algo-sl",
            "side": "SELL",
            "type": "STOP_MARKET",
        },
        {
            "symbol": "BTCUSDT",
            "orderId": "8631145710",
            "clientOrderId": "exchange-algo-tp",
            "side": "SELL",
            "type": "TAKE_PROFIT_MARKET",
        },
    ]
    fsm.adapter.get_open_orders = AsyncMock(
        side_effect=[open_orders, open_orders])

    await fsm._startup_order_guardian_reconcile()

    row = _load_startup_truth_rows(startup_truth_path)[0]
    assert row["restore_authoritative"]["artifact_state"] == "stale"
    assert row["runtime_truth_records"] == [
        {
            "symbol": "BTCUSDT",
            "status": "reconstructed",
            "sl_order_id": "8631145709",
            "tp_order_id": "8631145710",
            "bracket_truth_source": "RECONSTRUCTED_GUARDIAN",
            "manage_truth_source": "UNKNOWN",
            "order_index_registrations": 2,
            "unresolved_reasons": [],
        }
    ]
    assert row["unknown_truth_records"] == [
        {
            "symbol": "ETHUSDT",
            "lifecycle_truth_class": "unknown",
            "authoritative_artifact_state": "stale",
            "portfolio_presence": "present",
            "reconstructed_exact_truth_present": False,
            "observed_inputs": ["position_symbols_observed", "symbols_considered"],
            "reason_codes": [
                "authoritative_artifact_stale",
                "portfolio_present_without_restored_lifecycle_truth",
            ],
        }
    ]
    assert row["execution_truth_cache"]["truth_class"] == "cache_only"
