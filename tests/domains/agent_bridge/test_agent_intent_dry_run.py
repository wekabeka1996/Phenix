from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import multiprocessing
import subprocess
import sys

import pytest
from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.reference.domains.agent_bridge.agent_intent import AgentIntentV0
from apps.reference.domains.agent_bridge.agent_intent_dry_run import (
    AgentIntentDryRunLedger,
    AgentIntentDryRunRecordV1,
    AgentIntentDryRunResultV0,
    reject_raw_intent_schema,
    validate_intent_dry_run,
    ACTIVE_LEDGER_MAX_BYTES,
    ArchiveIntegrityError,
    RotationFaultInjected,
)
from apps.reference.domains.agent_bridge.routes import register_agent_feed_routes


NOW = 1_800_000_000_000


def _multiprocess_append_worker(directory: str, record_json: str, queue) -> None:
    try:
        ledger = AgentIntentDryRunLedger(Path(directory))
        record = AgentIntentDryRunRecordV1.model_validate_json(record_json)
        queue.put((ledger.append(record), None))
    except Exception as exc:  # pragma: no cover - returned to parent for assertion
        queue.put((False, repr(exc)))


def _packet(*, btc_parity="conservative_mismatch", btc_ack="unacknowledged") -> dict:
    return {
        "packet_id": "afp_aaaaaaaa",
        "produced_ts_ms": NOW,
        "read_only": True,
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "symbol_markets": [
            {"symbol": symbol, "meta": {"freshness": "fresh", "source_ownership": "direct_main_publication"}}
            for symbol in ("BTCUSDT", "ETHUSDT")
        ],
        "execution_body": {
            "invariants": [{"name": "no_order_execution_isolation", "status": "ready", "detail": "adapter absent", "raw_ref": "fixture://isolation"}],
            "capability_descriptors": [
                {"name": name, "symbol": symbol, "status": "ready", "detail": "fixture ready", "raw_ref": f"fixture://{name}/{symbol}"}
                for symbol in ("BTCUSDT", "ETHUSDT")
                for name in ("exchange_filter_constraints", "precision_minimum_normalization")
            ] + [
                {"name": "reduce_only_order_parameter", "status": "ready", "detail": "fixture ready", "raw_ref": "fixture://reduce"},
                {"name": "close_path_reduce_only_enforcement", "status": "ready", "detail": "fixture ready", "raw_ref": "fixture://close"},
                {"name": "protect_path_reduce_only_enforcement", "status": "ready", "detail": "fixture ready", "raw_ref": "fixture://protect"},
            ],
            "filter_parity_acknowledgements": [
                {"symbol": "BTCUSDT", "parity_status": btc_parity, "ack_status": btc_ack, "raw_ref": "fixture://btc-parity"},
                {"symbol": "ETHUSDT", "parity_status": "match", "ack_status": "not_required", "raw_ref": "fixture://eth-parity"},
            ],
        },
        "position_life": {"positions": [], "meta": {"source_refs": ["fixture://positions"]}},
        "action_review_memory": {
            "scenario_memory_index_ref": "aurora-publication://scenario-memory/index/v0",
            "unresolved_review_count": 0,
        },
    }


def _intent(*, action="OBSERVE", symbol="ETHUSDT", side="NONE", expiry=NOW + 60_000, packet_ref="agent-feed://packet/afp_aaaaaaaa") -> AgentIntentV0:
    return AgentIntentV0.model_validate({
        "intent_id": f"intent_test_{action.lower()}_{symbol.lower()}",
        "created_ts_ms": NOW - 1000,
        "source": "deterministic_fixture",
        "agent_id": "p18.test.fixture",
        "model_id": None,
        "model_call_ref": None,
        "rank": "unranked_no_model",
        "mode": "dry_run_no_execution",
        "symbol": symbol,
        "horizon": "micro_observation",
        "action": action,
        "side": side,
        "confidence": 0.5,
        "thesis": "Validate a deterministic no-execution fixture.",
        "invalidation": "Packet context becomes stale or unavailable.",
        "expected_scenarios": [{"scenario_id": "no_clear_scenario", "confidence": 0.7, "thesis": "The window may remain inconclusive."}],
        "used_packet_refs": [packet_ref],
        "used_memory_refs": ["aurora-publication://scenario-memory/index/v0"],
        "acknowledged_warnings": ["dry-run is not permission"],
        "requested_execution_semantics": {
            "shape": "MARKET" if action.startswith("DRY_RUN_") else "NONE",
            "quantity": "0.01" if action.startswith("DRY_RUN_OPEN") else None,
            "reduce_only_requested": action in {"DRY_RUN_CLOSE", "DRY_RUN_PROTECT"},
            "non_executable": True,
        },
        "risk_note": "No order may be submitted from this intent.",
        "expiry_ts_ms": expiry,
        "trace_id": f"trace_test_{action.lower()}_{symbol.lower()}",
    })


def test_agent_intent_is_no_model_immutable_and_rejects_provider_identity() -> None:
    intent = _intent()
    with pytest.raises(ValidationError):
        intent.symbol = "BTCUSDT"
    bad = intent.model_dump(mode="python")
    bad["model_id"] = "provider-model"
    with pytest.raises(ValidationError):
        AgentIntentV0.model_validate(bad)


def test_wait_observe_and_eth_open_are_dry_run_valid() -> None:
    observe = validate_intent_dry_run(_intent(), _packet(), now_ms=NOW)
    assert observe.validation_status == "dry_run_valid"
    assert observe.would_require_execution_authority is False
    opened = validate_intent_dry_run(
        _intent(action="DRY_RUN_OPEN_LONG", symbol="ETHUSDT", side="LONG"), _packet(), now_ms=NOW
    )
    assert opened.validation_status == "dry_run_valid"
    assert opened.would_require_execution_authority is True
    assert opened.estimated_order_shape and opened.estimated_order_shape.non_executable is True
    assert opened.submitted is False and opened.exchange_touched is False


def test_btc_open_rejects_unacknowledged_parity_and_risky_or_missing_parity() -> None:
    intent = _intent(action="DRY_RUN_OPEN_LONG", symbol="BTCUSDT", side="LONG")
    result = validate_intent_dry_run(intent, _packet(), now_ms=NOW)
    assert result.validation_status == "dry_run_rejected_parity_unacknowledged"
    for parity in ("risky_mismatch", "missing", "stale"):
        rejected = validate_intent_dry_run(intent, _packet(btc_parity=parity), now_ms=NOW)
        assert rejected.validation_status == "dry_run_rejected_parity_unacknowledged"


def test_close_without_position_and_missing_capability_reject() -> None:
    close = _intent(action="DRY_RUN_CLOSE", symbol="ETHUSDT", side="LONG")
    result = validate_intent_dry_run(close, _packet(), now_ms=NOW)
    assert result.validation_status == "dry_run_rejected_missing_capability"
    assert any("lifecycle" in reason for reason in result.rejection_reasons)
    packet = _packet()
    packet["execution_body"]["capability_descriptors"] = []
    opened = validate_intent_dry_run(
        _intent(action="DRY_RUN_OPEN_LONG", symbol="ETHUSDT", side="LONG"), packet, now_ms=NOW
    )
    assert opened.validation_status == "dry_run_rejected_missing_capability"


def test_expired_missing_packet_and_schema_rejections() -> None:
    expired = validate_intent_dry_run(_intent(expiry=NOW - 1), _packet(), now_ms=NOW)
    assert expired.validation_status == "dry_run_rejected_expired_context"
    missing = validate_intent_dry_run(
        _intent(packet_ref="agent-feed://packet/afp_bbbbbbbb"), _packet(), now_ms=NOW
    )
    assert missing.validation_status == "dry_run_rejected_missing_packet"
    schema = reject_raw_intent_schema({"intent_id": "intent_bad"}, _packet(), now_ms=NOW)
    assert schema.validation_status == "dry_run_rejected_schema"


def test_result_forbids_exchange_identifier_fields() -> None:
    data = validate_intent_dry_run(_intent(), _packet(), now_ms=NOW).model_dump(mode="python")
    data["exchange_order_id"] = "forbidden"
    with pytest.raises(ValidationError):
        AgentIntentDryRunResultV0.model_validate(data)


def test_dry_run_ledger_is_append_only_and_idempotent(tmp_path: Path) -> None:
    intent = _intent()
    result = validate_intent_dry_run(intent, _packet(), now_ms=NOW)
    record = AgentIntentDryRunRecordV1(intent=intent, result=result)
    ledger = AgentIntentDryRunLedger(tmp_path)
    assert ledger.append(record) is True
    before = ledger.path.read_bytes()
    assert ledger.append(record) is False
    assert ledger.path.read_bytes() == before
    assert ledger.latest(symbol="ETHUSDT")[0].result.dry_run_id == result.dry_run_id


def test_dry_run_read_routes_are_get_only(tmp_path: Path) -> None:
    intent = _intent()
    result = validate_intent_dry_run(intent, _packet(), now_ms=NOW)
    ledger = AgentIntentDryRunLedger(tmp_path / "ops/agent_bridge/agent_intents")
    ledger.append(AgentIntentDryRunRecordV1(intent=intent, result=result))
    app = FastAPI()
    register_agent_feed_routes(app, project_root=tmp_path)
    client = TestClient(app)
    assert client.get("/agent-intent/v0/health").json()["record_count"] == 1
    assert len(client.get("/agent-intent/v0/latest").json()["items"]) == 1
    query_item = client.get("/agent-intent/v0/query?symbol=ETHUSDT").json()["items"][0]
    assert query_item["intent"]["model_id"] is None
    assert client.get("/agent-intent/v0/stats").json()["valid_records"] == 1
    assert client.post("/agent-intent/v0/query").status_code == 405


def test_ledger_rejects_conflicting_duplicate_and_forbidden_values(tmp_path: Path) -> None:
    intent = _intent()
    result = validate_intent_dry_run(intent, _packet(), now_ms=NOW)
    record = AgentIntentDryRunRecordV1(intent=intent, result=result)
    ledger = AgentIntentDryRunLedger(tmp_path)
    assert ledger.append(record)
    conflict = AgentIntentDryRunRecordV1(
        intent=intent,
        result=result.model_copy(update={"result_summary": "conflicting payload"}),
    )
    with pytest.raises(ValueError, match="conflicting duplicate"):
        ledger.append(conflict)
    unsafe = AgentIntentDryRunRecordV1(
        intent=intent.model_copy(update={"intent_id": "intent_unsafe", "risk_note": "api_key=do-not-store"}),
        result=result.model_copy(update={"dry_run_id": "dryrun_111111111111111111111111", "intent_id": "intent_unsafe"}),
    )
    with pytest.raises(ValueError, match="secret-looking"):
        ledger.append(unsafe)


def test_ledger_tolerates_partial_malformed_and_oversized_rows(tmp_path: Path) -> None:
    intent = _intent()
    result = validate_intent_dry_run(intent, _packet(), now_ms=NOW)
    record = AgentIntentDryRunRecordV1(intent=intent, result=result)
    ledger = AgentIntentDryRunLedger(tmp_path)
    ledger.directory.mkdir(parents=True, exist_ok=True)
    valid = record.model_dump_json(exclude_none=True).encode()
    ledger.path.write_bytes(valid + b"\n{malformed}\n" + b"x" * (64 * 1024) + b"\n{partial")
    assert len(ledger.read()) == 1
    stats = ledger.stats()
    assert stats.valid_records == 1
    assert stats.malformed_rows == 1
    assert stats.oversized_rows == 1
    assert stats.partial_lines == 1
    next_record = AgentIntentDryRunRecordV1(
        intent=intent.model_copy(update={"intent_id": "intent_after_partial"}),
        result=result.model_copy(update={"dry_run_id": "dryrun_222222222222222222222222", "intent_id": "intent_after_partial"}),
    )
    assert ledger.append(next_record)
    assert len(ledger.read()) == 2


def test_ledger_process_local_concurrency_and_query_filters(tmp_path: Path) -> None:
    ledger_a = AgentIntentDryRunLedger(tmp_path)
    ledger_b = AgentIntentDryRunLedger(tmp_path)
    records = []
    for index in range(12):
        action = "OBSERVE" if index % 2 == 0 else "WAIT"
        intent = _intent(action=action).model_copy(update={"intent_id": f"intent_concurrent_{index}"})
        result = validate_intent_dry_run(intent, _packet(), now_ms=NOW + index)
        records.append(AgentIntentDryRunRecordV1(intent=intent, result=result))
    with ThreadPoolExecutor(max_workers=6) as pool:
        appended = list(pool.map(lambda pair: pair[0].append(pair[1]), [
            (ledger_a if index % 2 == 0 else ledger_b, record) for index, record in enumerate(records)
        ]))
    assert all(appended)
    assert ledger_a.stats().valid_records == 12
    assert len(ledger_a.latest(action="OBSERVE", status="dry_run_valid", limit=3, offset=1)) == 3
    with pytest.raises(ValueError, match="limit"):
        ledger_a.latest(limit=101)


def test_ledger_cross_process_advisory_lock_and_retention_policy(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = []
    for index in range(6):
        intent = _intent(action="OBSERVE").model_copy(update={"intent_id": f"intent_process_{index}"})
        result = validate_intent_dry_run(intent, _packet(), now_ms=NOW + index)
        record = AgentIntentDryRunRecordV1(intent=intent, result=result)
        process = context.Process(
            target=_multiprocess_append_worker,
            args=(str(tmp_path), record.model_dump_json(exclude_none=True), queue),
        )
        processes.append(process)
        process.start()
    for process in processes:
        process.join(15)
        assert process.exitcode == 0
    outcomes = [queue.get(timeout=2) for _ in processes]
    assert all(appended and error is None for appended, error in outcomes)
    ledger = AgentIntentDryRunLedger(tmp_path)
    stats = ledger.stats()
    assert stats.valid_records == 6
    assert stats.multi_process_locking is True
    assert stats.locking_scope == "os_advisory_file_lock"
    assert stats.active_ledger_max_bytes == ACTIVE_LEDGER_MAX_BYTES
    assert stats.rotation_recommended is False
    assert stats.archive_query_policy == "active_plus_archives"
    assert stats.hash_manifest_required is True


def _record(index: int, *, action: str = "OBSERVE", symbol: str = "ETHUSDT") -> AgentIntentDryRunRecordV1:
    intent = _intent(action=action, symbol=symbol).model_copy(update={"intent_id": f"intent_rotation_{index}"})
    result = validate_intent_dry_run(intent, _packet(), now_ms=NOW + index)
    return AgentIntentDryRunRecordV1(intent=intent, result=result)


def test_transactional_rotation_manifest_and_scoped_queries(tmp_path: Path) -> None:
    ledger = AgentIntentDryRunLedger(tmp_path / "ops/agent_bridge/agent_intents")
    records = [_record(index) for index in range(3)]
    for record in records:
        assert ledger.append(record)
    active_bytes = ledger.path.read_bytes()
    manifest = ledger.rotate(created_utc="2026-07-04T12:34:56Z")
    archive = ledger.archive_directory / manifest.archive_filename
    manifest_path = ledger.archive_directory / "agent_intent_dry_run_ledger_v1.20260704T123456Z.manifest.json"
    assert ledger.path.read_bytes() == b""
    assert archive.read_bytes() == active_bytes
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest.sha256
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["rotation_id"] == manifest.rotation_id
    assert not list(ledger.archive_directory.glob("*.tmp"))
    assert ledger.query(scope="active", limit=10)["items"] == []
    archived = ledger.query(scope="archives", limit=10)
    assert len(archived["items"]) == 3
    assert all(item["source"]["kind"] == "archive" for item in archived["items"])
    combined = ledger.query(scope="active_plus_archives", limit=2, offset=1)
    assert combined["total_matched"] == 3 and len(combined["items"]) == 2
    stats = ledger.stats()
    assert stats.archive_count == 1 and stats.archive_valid_records == 3
    assert stats.archive_bytes == len(active_bytes) and stats.archive_integrity_errors == 0
    assert ledger.append(records[0]) is False


def test_rotation_rejects_partial_and_archive_hash_mismatch(tmp_path: Path) -> None:
    ledger = AgentIntentDryRunLedger(tmp_path / "ops/agent_bridge/agent_intents")
    assert ledger.append(_record(10))
    ledger.path.write_bytes(ledger.path.read_bytes() + b"{partial")
    with pytest.raises(ValueError, match="partial/corrupt"):
        ledger.rotate(created_utc="2026-07-04T12:35:00Z")
    assert not ledger.archive_directory.exists()
    ledger.path.write_bytes(ledger.path.read_bytes().removesuffix(b"{partial"))
    manifest = ledger.rotate(created_utc="2026-07-04T12:35:01Z")
    archive = ledger.archive_directory / manifest.archive_filename
    tampered = bytearray(archive.read_bytes())
    tampered[0] = ord("[") if tampered[0] != ord("[") else ord("{")
    archive.write_bytes(tampered)
    with pytest.raises(ArchiveIntegrityError, match="SHA-256 mismatch"):
        ledger.query(scope="archives", limit=10)
    assert ledger.stats().archive_integrity_errors == 1


def test_rotation_cli_and_active_plus_archive_filtering(tmp_path: Path) -> None:
    ledger = AgentIntentDryRunLedger(tmp_path / "ops/agent_bridge/agent_intents")
    assert ledger.append(_record(20, action="OBSERVE", symbol="BTCUSDT"))
    completed = subprocess.run(
        [sys.executable, "scripts/agent_intent_dry_run.py", "rotate", "--project-root", str(tmp_path), "--created-utc", "2026-07-04T12:36:00Z"],
        cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    assert output["schema_version"] == "agent-intent-dry-run-archive-manifest/v0"
    assert ledger.append(_record(21, action="WAIT", symbol="ETHUSDT"))
    filtered = ledger.query(scope="active_plus_archives", symbol="BTCUSDT", action="OBSERVE", limit=10)
    assert filtered["total_matched"] == 1
    assert filtered["items"][0]["source"]["kind"] == "archive"


def test_archive_routes_are_get_only_and_surface_integrity_errors(tmp_path: Path) -> None:
    ledger = AgentIntentDryRunLedger(tmp_path / "ops/agent_bridge/agent_intents")
    assert ledger.append(_record(30))
    manifest = ledger.rotate(created_utc="2026-07-04T12:37:00Z")
    app = FastAPI()
    register_agent_feed_routes(app, project_root=tmp_path)
    client = TestClient(app)
    response = client.get("/agent-intent/v0/query?scope=archives&limit=10")
    assert response.status_code == 200
    assert response.json()["items"][0]["source"]["kind"] == "archive"
    assert client.get("/agent-intent/v0/archives").json()["items"][0]["rotation_id"] == manifest.rotation_id
    assert client.get("/agent-intent/v0/archive-stats").json()["archive_count"] == 1
    assert client.get("/agent-intent/v0/manifest-index").json()["combined_valid_row_count"] == 1
    assert client.post("/agent-intent/v0/archives").status_code == 405
    archive = ledger.archive_directory / manifest.archive_filename
    archive.write_bytes(archive.read_bytes() + b"corrupt")
    failed = client.get("/agent-intent/v0/query?scope=archives&limit=10")
    assert failed.status_code == 503
    assert failed.json()["detail"]["error"] == "archive_integrity_failed"


@pytest.mark.parametrize("stage,expected", [
    ("before_archive_temp_write", "active_valid"),
    ("after_archive_temp_write_before_rename", "temporary"),
    ("after_archive_rename_before_manifest_write", "orphan_archive"),
    ("after_manifest_temp_write_before_rename", "orphan_and_temporary"),
    ("after_manifest_rename_before_active_reset", "active_duplicate"),
    ("after_active_reset", "committed"),
])
def test_rotation_fault_injection_states_are_detectable(tmp_path: Path, stage: str, expected: str) -> None:
    directory = tmp_path / stage / "ops/agent_bridge/agent_intents"
    ledger = AgentIntentDryRunLedger(directory)
    assert ledger.append(_record(100 + len(stage)))
    with pytest.raises(RotationFaultInjected, match=stage):
        ledger.rotate(created_utc="2026-07-04T13:00:00Z", fault_stage=stage)
    index = ledger.rebuild_manifest_index(generated_utc="2026-07-04T13:01:00Z", persist=False)
    if expected == "active_valid":
        assert ledger.query(scope="active", limit=10)["total_matched"] == 1
        assert index["diagnostics"] == []
    elif expected == "temporary":
        assert any("temporary" in item for item in index["diagnostics"])
        with pytest.raises(ArchiveIntegrityError):
            ledger.query(scope="archives", limit=10)
    elif expected == "orphan_archive":
        assert any("manifest missing" in item for item in index["diagnostics"])
    elif expected == "orphan_and_temporary":
        assert any("manifest missing" in item for item in index["diagnostics"])
        assert any("temporary" in item for item in index["diagnostics"])
    elif expected == "active_duplicate":
        assert any("active ledger not reset" in item for item in index["diagnostics"])
        combined = ledger.query(scope="active_plus_archives", limit=10)
        assert combined["total_matched"] == 1
        assert any("canonical duplicate" in item for item in combined["diagnostics"])
    else:
        assert ledger.path.read_bytes() == b""
        assert ledger.query(scope="archives", limit=10)["total_matched"] == 1
        assert index["diagnostics"] == []


def test_explicit_recovery_quarantines_temps_but_preserves_orphan(tmp_path: Path) -> None:
    ledger = AgentIntentDryRunLedger(tmp_path / "ops/agent_bridge/agent_intents")
    assert ledger.append(_record(200))
    with pytest.raises(RotationFaultInjected):
        ledger.rotate(created_utc="2026-07-04T13:02:00Z", fault_stage="after_manifest_temp_write_before_rename")
    report = ledger.recover(created_utc="2026-07-04T13:03:00Z", quarantine_temporary_files=True)
    assert report["actions"] and report["historical_evidence_deleted"] is False
    assert any("manifest missing" in item for item in report["after_diagnostics"])
    assert not any("temporary" in item for item in report["after_diagnostics"])
    assert list((ledger.directory / "recovery_quarantine").iterdir())
    assert Path(report["report_path"]).exists()


def test_manifest_index_detects_duplicate_rotation_hash_and_active_conflict(tmp_path: Path) -> None:
    ledger = AgentIntentDryRunLedger(tmp_path / "ops/agent_bridge/agent_intents")
    first = _record(300)
    assert ledger.append(first)
    manifest_a = ledger.rotate(created_utc="2026-07-04T13:04:00Z")
    assert ledger.append(_record(301))
    manifest_b = ledger.rotate(created_utc="2026-07-04T13:05:00Z")
    manifest_b_path = ledger.archive_directory / "agent_intent_dry_run_ledger_v1.20260704T130500Z.manifest.json"
    raw_b = json.loads(manifest_b_path.read_text(encoding="utf-8"))
    raw_b["rotation_id"] = manifest_a.rotation_id
    manifest_b_path.write_text(json.dumps(raw_b) + "\n", encoding="utf-8")
    index = ledger.rebuild_manifest_index(generated_utc="2026-07-04T13:06:00Z", persist=True)
    assert any("duplicate rotation id" in item for item in index["diagnostics"])
    assert Path(index["persisted_path"]).exists()
    # Restore unique rotation then make archive B a byte-identical/hash-identical committed archive.
    raw_b["rotation_id"] = manifest_b.rotation_id
    archive_a = ledger.archive_directory / manifest_a.archive_filename
    archive_b = ledger.archive_directory / manifest_b.archive_filename
    archive_b.write_bytes(archive_a.read_bytes())
    raw_b.update({
        "sha256": manifest_a.sha256, "byte_size": manifest_a.byte_size,
        "row_count": manifest_a.row_count, "valid_row_count": manifest_a.valid_row_count,
        "earliest_created_ts_ms": manifest_a.earliest_created_ts_ms,
        "latest_created_ts_ms": manifest_a.latest_created_ts_ms,
    })
    manifest_b_path.write_text(json.dumps(raw_b) + "\n", encoding="utf-8")
    duplicate_hash_index = ledger.rebuild_manifest_index(generated_utc="2026-07-04T13:07:00Z", persist=False)
    assert any("duplicate archive hash" in item for item in duplicate_hash_index["diagnostics"])
    # A non-cooperative writer creates a conflicting active duplicate; combined query fails closed.
    conflict = first.model_copy(update={"result": first.result.model_copy(update={"result_summary": "conflict"})})
    ledger.path.write_text(conflict.model_dump_json(exclude_none=True) + "\n", encoding="utf-8")
    with pytest.raises(ArchiveIntegrityError):
        ledger.query(scope="active_plus_archives", limit=10)


def test_orphan_manifest_row_and_byte_count_diagnostics(tmp_path: Path) -> None:
    ledger = AgentIntentDryRunLedger(tmp_path / "ops/agent_bridge/agent_intents")
    assert ledger.append(_record(400))
    manifest = ledger.rotate(created_utc="2026-07-04T13:08:00Z")
    manifest_path = ledger.archive_directory / "agent_intent_dry_run_ledger_v1.20260704T130800Z.manifest.json"
    archive_path = ledger.archive_directory / manifest.archive_filename
    archive_path.rename(archive_path.with_suffix(".missing"))
    assert any("No such file" in item or "cannot find" in item.lower() for item in ledger.archives()["diagnostics"])
    archive_path.with_suffix(".missing").rename(archive_path)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["row_count"] += 1
    manifest_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    assert any("row count mismatch" in item for item in ledger.archives()["diagnostics"])
    raw["row_count"] -= 1; raw["byte_size"] += 1
    manifest_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    assert any("byte size mismatch" in item for item in ledger.archives()["diagnostics"])


def test_operator_approved_orphan_manifest_reconstruction(tmp_path: Path) -> None:
    ledger = AgentIntentDryRunLedger(tmp_path / "ops/agent_bridge/agent_intents")
    assert ledger.append(_record(500))
    original = ledger.rotate(created_utc="2026-07-04T14:00:00Z")
    manifest_path = ledger.archive_directory / "agent_intent_dry_run_ledger_v1.20260704T140000Z.manifest.json"
    manifest_path.unlink()
    archive_path = ledger.archive_directory / original.archive_filename
    before = archive_path.read_bytes()
    reconstructed = ledger.reconstruct_orphan_manifest(
        archive_filename=original.archive_filename,
        operator_approval_ref="operator-approval://p23-fixture",
        reconstruction_reason="Restore validated orphan fixture manifest.",
        created_utc="2026-07-04T14:01:00Z",
    )
    assert reconstructed.reconstructed is True
    assert reconstructed.operator_approval_ref == "operator-approval://p23-fixture"
    assert reconstructed.source_archive_sha256 == hashlib.sha256(before).hexdigest()
    assert archive_path.read_bytes() == before
    assert ledger.query(scope="archives", limit=10)["total_matched"] == 1


@pytest.mark.parametrize("mutation", ["malformed", "secret", "submitted", "forbidden_order_id"])
def test_orphan_reconstruction_rejects_unsafe_rows(tmp_path: Path, mutation: str) -> None:
    ledger = AgentIntentDryRunLedger(tmp_path / mutation / "ops/agent_bridge/agent_intents")
    ledger.archive_directory.mkdir(parents=True)
    filename = "agent_intent_dry_run_ledger_v1.20260704T140200Z.jsonl"
    archive = ledger.archive_directory / filename
    raw = _record(510).model_dump(mode="json", exclude_none=True)
    if mutation == "malformed": archive.write_bytes(b"{bad}\n")
    else:
        if mutation == "secret": raw["intent"]["risk_note"] = "api_key=forbidden"
        elif mutation == "submitted": raw["result"]["submitted"] = True
        else: raw["result"]["order_id"] = "forbidden"
        archive.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="validation failed"):
        ledger.reconstruct_orphan_manifest(
            archive_filename=filename, operator_approval_ref="operator-approval://fixture",
            reconstruction_reason="Validate unsafe fixture.", created_utc="2026-07-04T14:03:00Z",
        )
    assert not archive.with_suffix(".manifest.json").exists()
    assert list((ledger.directory / "recovery_reports").glob("reconstruction_diagnostic.*.json"))


def test_reconstructed_manifest_crash_states_and_chain_route(tmp_path: Path) -> None:
    for stage, trusted in (("before_reconstructed_manifest_rename", False), ("after_reconstructed_manifest_rename", True)):
        ledger = AgentIntentDryRunLedger(tmp_path / stage / "ops/agent_bridge/agent_intents")
        assert ledger.append(_record(520 + int(trusted)))
        original = ledger.rotate(created_utc="2026-07-04T14:04:00Z")
        manifest_path = ledger.archive_directory / "agent_intent_dry_run_ledger_v1.20260704T140400Z.manifest.json"
        manifest_path.unlink()
        with pytest.raises(RotationFaultInjected):
            ledger.reconstruct_orphan_manifest(
                archive_filename=original.archive_filename, operator_approval_ref="operator-approval://fault",
                reconstruction_reason="Fault injection.", created_utc="2026-07-04T14:05:00Z", fault_stage=stage,
            )
        assert manifest_path.exists() is trusted
    app = FastAPI(); register_agent_feed_routes(app, project_root=tmp_path / "after_reconstructed_manifest_rename")
    client = TestClient(app)
    chain = client.get("/agent-intent/v0/manifest-chain")
    assert chain.status_code == 200
    assert chain.json()["items"][0]["reconstructed"] is True
    assert client.post("/agent-intent/v0/manifest-chain").status_code == 405


def test_hash_chain_gap_and_timestamp_overlap_are_diagnostic(tmp_path: Path) -> None:
    ledger = AgentIntentDryRunLedger(tmp_path / "ops/agent_bridge/agent_intents")
    assert ledger.append(_record(530)); ledger.rotate(created_utc="2026-07-04T14:06:00Z")
    assert ledger.append(_record(531)); ledger.rotate(created_utc="2026-07-04T14:07:00Z")
    index = ledger.rebuild_manifest_index(generated_utc="2026-07-04T14:08:00Z", persist=False)
    assert index["chain_verdict"] == "chain_partial_gap_detected"
    assert any("previous archive hash missing" in item for item in index["diagnostics"])
    second_path = ledger.archive_directory / "agent_intent_dry_run_ledger_v1.20260704T140700Z.manifest.json"
    second = json.loads(second_path.read_text(encoding="utf-8"))
    second["previous_archive_sha256"] = index["archive_manifests"][0]["sha256"]
    second["earliest_created_ts_ms"] = index["archive_manifests"][0]["latest_created_ts_ms"]
    second_path.write_text(json.dumps(second) + "\n", encoding="utf-8")
    overlap = ledger.rebuild_manifest_index(generated_utc="2026-07-04T14:09:00Z", persist=False)
    assert any("timestamp overlap" in item for item in overlap["diagnostics"])
