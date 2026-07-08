"""Deterministic AgentIntent dry-run validation and append-only local ledger."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
import uuid
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .agent_intent import AgentIntentV0


LEDGER_FILENAME = "agent_intent_dry_run_ledger_v1.jsonl"
LEDGER_REF = "aurora-publication://agent-intents/dry-run-ledger/v1"
MAX_ROW_BYTES = 64 * 1024
MAX_LEDGER_READ_BYTES = 8 * 1024 * 1024
ACTIVE_LEDGER_MAX_BYTES = 4 * 1024 * 1024
LOCK_TIMEOUT_SECONDS = 5.0
MAX_QUERY_LIMIT = 100
ARCHIVE_DIRECTORY = "archives"
ROTATION_PACKAGE_ID = "aurora-agent-control-p21.v0"
MANIFEST_INDEX_FILENAME = "archive_manifest_index_v1.json"
RECOVERY_PACKAGE_ID = "aurora-agent-control-p22.v0"
QueryScope = Literal["active", "archives", "active_plus_archives"]
_PATH_LOCKS: dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()
_FORBIDDEN_KEYS = {
    "api_key", "api_secret", "secret", "access_token", "authorization",
    "exchange_order_id", "client_order_id", "order_id", "fill_id",
}
_SECRET_VALUE = re.compile(r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+\S+|\b(?:api[_-]?key|secret)\s*[=:]\s*\S+)", re.I)
MECHANICAL_ACTIONS = {
    "DRY_RUN_OPEN_LONG", "DRY_RUN_OPEN_SHORT", "DRY_RUN_CLOSE",
    "DRY_RUN_PROTECT", "DRY_RUN_CANCEL", "DRY_RUN_AMEND",
}

ValidationStatus = Literal[
    "dry_run_valid", "dry_run_rejected_schema", "dry_run_rejected_missing_packet",
    "dry_run_rejected_missing_capability", "dry_run_rejected_parity_unacknowledged",
    "dry_run_rejected_expired_context", "dry_run_rejected_symbol_unknown",
    "dry_run_rejected_action_out_of_scope", "dry_run_blocked_by_package_scope",
]


class CapabilityCheckV0(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: Literal["pass", "warn", "reject", "not_applicable"]
    detail: str = Field(max_length=360)
    raw_ref: Optional[str] = None


class EstimatedOrderShapeV0(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    side: str
    shape: str
    quantity: Optional[str] = None
    limit_price: Optional[str] = None
    stop_price: Optional[str] = None
    reduce_only_requested: bool
    non_executable: Literal[True] = True


class AgentIntentDryRunResultV0(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent-intent-dry-run-result/v0"] = "agent-intent-dry-run-result/v0"
    dry_run_id: str = Field(pattern=r"^dryrun_[0-9a-f]{24}$")
    intent_id: str
    created_ts_ms: int
    packet_ref: str
    validation_status: ValidationStatus
    mechanical_status: Literal["ready", "warning", "rejected", "not_applicable"]
    policy_context_status: Literal["pass", "warning", "rejected"]
    memory_context_status: Literal["attached", "missing"]
    parity_status: str
    operator_ack_status: str
    rejection_reasons: list[str] = Field(default_factory=list, max_length=16)
    warnings: list[str] = Field(default_factory=list, max_length=16)
    capability_checks: list[CapabilityCheckV0] = Field(default_factory=list, max_length=16)
    estimated_order_shape: Optional[EstimatedOrderShapeV0] = None
    would_require_execution_authority: bool
    submitted: Literal[False] = False
    exchange_touched: Literal[False] = False
    result_summary: str = Field(max_length=600)
    raw_refs: list[str] = Field(default_factory=list, max_length=24)


class AgentIntentDryRunRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent-intent-dry-run-record/v1"] = "agent-intent-dry-run-record/v1"
    intent: AgentIntentV0
    result: AgentIntentDryRunResultV0
    no_execution_proof: Literal[True] = True
    no_model_proof: Literal[True] = True
    no_secret_read_proof: Literal[True] = True


class DryRunLedgerStatsV0(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent-intent-dry-run-ledger-stats/v0"] = "agent-intent-dry-run-ledger-stats/v0"
    read_only: Literal[True] = True
    file_bytes: int
    max_read_bytes: int = MAX_LEDGER_READ_BYTES
    bounded_read: bool
    physical_lines: int
    valid_records: int
    malformed_rows: int
    partial_lines: int
    oversized_rows: int
    duplicate_identical_rows: int
    conflicting_duplicate_rows: int
    earliest_created_ts_ms: Optional[int] = None
    latest_created_ts_ms: Optional[int] = None
    submitted_count: int
    exchange_touched_count: int
    active_ledger_max_bytes: int = ACTIVE_LEDGER_MAX_BYTES
    rotation_recommended: bool
    archive_naming_pattern: Literal["agent_intent_dry_run_ledger_v1.YYYYMMDDTHHMMSSZ.jsonl"] = "agent_intent_dry_run_ledger_v1.YYYYMMDDTHHMMSSZ.jsonl"
    archive_query_policy: Literal["active_plus_archives"] = "active_plus_archives"
    hash_manifest_required: Literal[True] = True
    locking_scope: Literal["os_advisory_file_lock"] = "os_advisory_file_lock"
    multi_process_locking: Literal[True] = True
    archive_count: int = 0
    archive_valid_records: int = 0
    archive_bytes: int = 0
    archive_integrity_errors: int = 0


class DryRunArchiveManifestV0(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["agent-intent-dry-run-archive-manifest/v0"] = "agent-intent-dry-run-archive-manifest/v0"
    archive_filename: str = Field(pattern=r"^agent_intent_dry_run_ledger_v1\.\d{8}T\d{6}Z\.jsonl$")
    created_utc: str
    byte_size: int = Field(ge=1)
    row_count: int = Field(ge=1)
    valid_row_count: int = Field(ge=1)
    malformed_count: int = Field(ge=0)
    partial_count: int = Field(ge=0)
    oversized_count: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_active_ledger_path: str
    package_id: str = ROTATION_PACKAGE_ID
    rotation_id: str = Field(pattern=r"^rotation_[0-9a-f]{24}$")
    earliest_created_ts_ms: Optional[int] = None
    latest_created_ts_ms: Optional[int] = None
    reconstructed: bool = False
    reconstruction_id: Optional[str] = None
    operator_approval_ref: Optional[str] = None
    reconstruction_reason: Optional[str] = None
    source_archive_sha256: Optional[str] = None
    created_utc_ts: Optional[str] = None
    byte_count: Optional[int] = None
    physical_row_count: Optional[int] = None
    timestamp_min: Optional[int] = None
    timestamp_max: Optional[int] = None
    previous_archive_sha256: Optional[str] = None
    chain_position: Optional[int] = None
    chain_continuity_status: Optional[str] = None


class ArchiveIntegrityError(ValueError):
    def __init__(self, diagnostics: list[str]) -> None:
        self.diagnostics = diagnostics
        super().__init__("; ".join(diagnostics))


class RotationFaultInjected(RuntimeError):
    pass


def _dry_run_id(intent_id: str, packet_id: str) -> str:
    return "dryrun_" + hashlib.sha256(f"{intent_id}|{packet_id}".encode()).hexdigest()[:24]


def _packet_ref(packet: dict[str, Any]) -> str:
    return f"agent-feed://packet/{packet.get('packet_id', 'missing')}"


def validate_intent_dry_run(
    intent: AgentIntentV0,
    packet: dict[str, Any],
    *,
    now_ms: int,
    max_packet_age_ms: int = 120_000,
) -> AgentIntentDryRunResultV0:
    packet_ref = _packet_ref(packet)
    checks: list[CapabilityCheckV0] = []
    rejection: list[str] = []
    warnings: list[str] = []
    status: ValidationStatus = "dry_run_valid"
    mechanical = intent.action in MECHANICAL_ACTIONS
    if intent.expiry_ts_ms < now_ms:
        status = "dry_run_rejected_expired_context"
        rejection.append("intent context expired")
    produced = packet.get("produced_ts_ms")
    if not packet.get("packet_id") or packet_ref not in intent.used_packet_refs:
        status = "dry_run_rejected_missing_packet"
        rejection.append("referenced packet is absent or does not match")
    elif not isinstance(produced, int) or now_ms - produced > max_packet_age_ms or produced - now_ms > 10_000:
        status = "dry_run_rejected_expired_context"
        rejection.append("packet context is stale or clock-invalid")
    symbols = set(packet.get("symbols") or [])
    if intent.symbol not in symbols:
        status = "dry_run_rejected_symbol_unknown"
        rejection.append("intent symbol is not present in packet")
    market = next((item for item in packet.get("symbol_markets", []) if item.get("symbol") == intent.symbol), None)
    if market is None:
        status = "dry_run_rejected_symbol_unknown"
        rejection.append("symbol market card is absent")
    elif (market.get("meta") or {}).get("source_ownership") != "direct_main_publication":
        warnings.append("market source is not direct-main publication")
    execution = packet.get("execution_body") or {}
    invariants = {item.get("name"): item for item in execution.get("invariants", [])}
    isolation = invariants.get("no_order_execution_isolation") or {}
    isolation_pass = isolation.get("status") == "ready"
    checks.append(CapabilityCheckV0(
        name="no_order_execution_isolation",
        status="pass" if isolation_pass else "reject",
        detail=str(isolation.get("detail") or "no-order isolation evidence missing")[:360],
        raw_ref=isolation.get("raw_ref"),
    ))
    if not isolation_pass:
        status = "dry_run_blocked_by_package_scope"
        rejection.append("no-order isolation is not ready")
    descriptors = execution.get("capability_descriptors", [])
    descriptor_map = {
        (item.get("name"), item.get("symbol") or ""): item for item in descriptors
    }
    required = []
    if intent.action in {"DRY_RUN_OPEN_LONG", "DRY_RUN_OPEN_SHORT"}:
        required = [("exchange_filter_constraints", intent.symbol), ("precision_minimum_normalization", intent.symbol)]
    elif intent.action in {"DRY_RUN_CLOSE", "DRY_RUN_PROTECT"}:
        required = [
            ("reduce_only_order_parameter", ""),
            (("close_path_reduce_only_enforcement" if intent.action == "DRY_RUN_CLOSE" else "protect_path_reduce_only_enforcement"), ""),
        ]
    for name, symbol in required:
        item = descriptor_map.get((name, symbol))
        passed = item is not None and item.get("status") == "ready"
        checks.append(CapabilityCheckV0(
            name=name, status="pass" if passed else "reject",
            detail=str((item or {}).get("detail") or "required capability missing")[:360],
            raw_ref=(item or {}).get("raw_ref"),
        ))
        if not passed:
            status = "dry_run_rejected_missing_capability"
            rejection.append(f"required capability missing: {name}")
    parity = next((item for item in execution.get("filter_parity_acknowledgements", []) if item.get("symbol") == intent.symbol), {})
    parity_status = str(parity.get("parity_status") or "missing")
    ack_status = str(parity.get("ack_status") or "missing")
    if parity_status in {"risky_mismatch", "missing", "stale"} and mechanical:
        status = "dry_run_rejected_parity_unacknowledged"
        rejection.append(f"mechanical action rejected for parity={parity_status}")
    elif parity_status == "conservative_mismatch" and ack_status == "unacknowledged":
        warnings.append("conservative parity mismatch is unacknowledged")
        if mechanical:
            status = "dry_run_rejected_parity_unacknowledged"
            rejection.append("mechanical action requires operator parity acknowledgement")
    memory = packet.get("action_review_memory") or {}
    memory_refs = list(intent.used_memory_refs)
    index_ref = memory.get("scenario_memory_index_ref")
    if index_ref and index_ref not in memory_refs:
        warnings.append("intent did not cite current scenario-memory index")
    memory_status: Literal["attached", "missing"] = "attached" if memory_refs and index_ref else "missing"
    if memory_status == "missing":
        warnings.append("scenario memory context is missing")
    position = packet.get("position_life") or {}
    if intent.action in {"DRY_RUN_CLOSE", "DRY_RUN_PROTECT"} and not position.get("positions"):
        status = "dry_run_rejected_missing_capability"
        rejection.append("position lifecycle evidence is required")
        checks.append(CapabilityCheckV0(
            name="position_lifecycle_context", status="reject",
            detail="No position evidence exists in the packet; close/protect remains hypothetical.",
            raw_ref=(position.get("meta") or {}).get("source_refs", [None])[0],
        ))
    if intent.action in {"DRY_RUN_CANCEL", "DRY_RUN_AMEND"} and not intent.requested_execution_semantics.context_ref:
        status = "dry_run_rejected_missing_capability"
        rejection.append("referenced dry-run context is required")
    shape = None
    if mechanical:
        semantics = intent.requested_execution_semantics
        shape = EstimatedOrderShapeV0(
            symbol=intent.symbol,
            side=intent.side,
            shape=semantics.shape,
            quantity=str(semantics.quantity) if semantics.quantity is not None else None,
            limit_price=str(semantics.limit_price) if semantics.limit_price is not None else None,
            stop_price=str(semantics.stop_price) if semantics.stop_price is not None else None,
            reduce_only_requested=semantics.reduce_only_requested,
        )
    validation_ok = status == "dry_run_valid"
    raw_refs = list(dict.fromkeys(
        [packet_ref, *intent.used_memory_refs]
        + [check.raw_ref for check in checks if check.raw_ref]
        + ([parity.get("raw_ref")] if parity.get("raw_ref") else [])
    ))[:24]
    return AgentIntentDryRunResultV0(
        dry_run_id=_dry_run_id(intent.intent_id, str(packet.get("packet_id", "missing"))),
        intent_id=intent.intent_id,
        created_ts_ms=now_ms,
        packet_ref=packet_ref,
        validation_status=status,
        mechanical_status=("ready" if validation_ok and mechanical else "not_applicable" if validation_ok else "rejected"),
        policy_context_status="pass" if validation_ok and not warnings else "warning" if validation_ok else "rejected",
        memory_context_status=memory_status,
        parity_status=parity_status,
        operator_ack_status=ack_status,
        rejection_reasons=list(dict.fromkeys(rejection))[:16],
        warnings=list(dict.fromkeys(warnings))[:16],
        capability_checks=checks[:16],
        estimated_order_shape=shape,
        would_require_execution_authority=mechanical,
        result_summary=(
            f"{intent.action} accepted for non-executable dry-run classification only."
            if validation_ok else f"{intent.action} rejected in dry-run: {status}."
        ),
        raw_refs=raw_refs,
    )


def reject_raw_intent_schema(raw: dict[str, Any], packet: dict[str, Any], *, now_ms: int) -> AgentIntentDryRunResultV0:
    try:
        AgentIntentV0.model_validate(raw)
    except ValidationError as exc:
        intent_id = str(raw.get("intent_id") or "intent_invalid_schema")
        packet_ref = _packet_ref(packet)
        return AgentIntentDryRunResultV0(
            dry_run_id=_dry_run_id(intent_id, str(packet.get("packet_id", "missing"))),
            intent_id=intent_id,
            created_ts_ms=now_ms,
            packet_ref=packet_ref,
            validation_status="dry_run_rejected_schema",
            mechanical_status="rejected",
            policy_context_status="rejected",
            memory_context_status="missing",
            parity_status="missing",
            operator_ack_status="missing",
            rejection_reasons=[f"schema validation failed: {exc.errors()[0]['type']}"],
            warnings=[], capability_checks=[],
            would_require_execution_authority=False,
            result_summary="Intent rejected before dry-run validation because its schema is invalid.",
            raw_refs=[packet_ref],
        )
    raise ValueError("raw intent is schema-valid; use validate_intent_dry_run")


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _advisory_file_lock(path: Path, *, timeout_seconds: float = LOCK_TIMEOUT_SECONDS):
    """Cross-process exclusive advisory lock; fail closed on timeout."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        deadline = time.monotonic() + timeout_seconds
        locked = False
        while not locked:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError("dry-run ledger advisory lock timeout") from exc
                time.sleep(0.01)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _assert_safe_record(record: AgentIntentDryRunRecordV1) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in _FORBIDDEN_KEYS:
                    raise ValueError(f"forbidden dry-run ledger field: {key}")
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and _SECRET_VALUE.search(value):
            raise ValueError("secret-looking value rejected from dry-run ledger")
    visit(record.model_dump(mode="json", exclude_none=True))


class AgentIntentDryRunLedger:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.path = self.directory / LEDGER_FILENAME
        self.archive_directory = self.directory / ARCHIVE_DIRECTORY
        self.lock_path = self.directory / f"{LEDGER_FILENAME}.lock"
        self._lock = _path_lock(self.path)

    @contextmanager
    def _critical_section(self):
        with self._lock:
            with _advisory_file_lock(self.lock_path):
                yield

    def _scan_path(self, path: Path) -> tuple[list[AgentIntentDryRunRecordV1], DryRunLedgerStatsV0]:
        try:
            file_bytes = path.stat().st_size
            with path.open("rb") as handle:
                bounded = file_bytes > MAX_LEDGER_READ_BYTES
                if bounded:
                    handle.seek(file_bytes - MAX_LEDGER_READ_BYTES)
                payload = handle.read(MAX_LEDGER_READ_BYTES)
        except FileNotFoundError:
            return [], DryRunLedgerStatsV0(
                file_bytes=0, bounded_read=False, physical_lines=0, valid_records=0,
                malformed_rows=0, partial_lines=0, oversized_rows=0,
                duplicate_identical_rows=0, conflicting_duplicate_rows=0,
                submitted_count=0, exchange_touched_count=0, rotation_recommended=False,
            )
        partial = 0
        if bounded:
            first_break = payload.find(b"\n")
            if first_break < 0:
                payload = b""
            else:
                payload = payload[first_break + 1:]
                partial += 1
        if payload and not payload.endswith(b"\n"):
            last_break = payload.rfind(b"\n")
            payload = payload[:last_break + 1] if last_break >= 0 else b""
            partial += 1
        raw_lines = payload.splitlines()
        rows: list[AgentIntentDryRunRecordV1] = []
        canonical_by_id: dict[str, str] = {}
        malformed = oversized = identical = conflicting = 0
        for raw in raw_lines:
            if not raw.strip():
                continue
            if len(raw) + 1 > MAX_ROW_BYTES:
                oversized += 1
                continue
            try:
                row = AgentIntentDryRunRecordV1.model_validate_json(raw)
                _assert_safe_record(row)
            except (ValidationError, ValueError, UnicodeDecodeError):
                malformed += 1
                continue
            canonical = row.model_dump_json(exclude_none=True)
            previous = canonical_by_id.get(row.result.dry_run_id)
            if previous is not None:
                if previous == canonical:
                    identical += 1
                else:
                    conflicting += 1
                continue
            canonical_by_id[row.result.dry_run_id] = canonical
            rows.append(row)
        created = [row.result.created_ts_ms for row in rows]
        return rows, DryRunLedgerStatsV0(
            file_bytes=file_bytes, bounded_read=bounded, physical_lines=len(raw_lines) + partial,
            valid_records=len(rows), malformed_rows=malformed, partial_lines=partial,
            oversized_rows=oversized, duplicate_identical_rows=identical,
            conflicting_duplicate_rows=conflicting,
            earliest_created_ts_ms=min(created) if created else None,
            latest_created_ts_ms=max(created) if created else None,
            submitted_count=sum(1 for row in rows if row.result.submitted),
            exchange_touched_count=sum(1 for row in rows if row.result.exchange_touched),
            rotation_recommended=file_bytes >= ACTIVE_LEDGER_MAX_BYTES,
        )

    def _scan(self) -> tuple[list[AgentIntentDryRunRecordV1], DryRunLedgerStatsV0]:
        return self._scan_path(self.path)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _archive_inventory_locked(self) -> tuple[list[tuple[DryRunArchiveManifestV0, Path, list[AgentIntentDryRunRecordV1]]], list[str]]:
        if not self.archive_directory.exists():
            return [], []
        diagnostics: list[str] = []
        valid: list[tuple[DryRunArchiveManifestV0, Path, list[AgentIntentDryRunRecordV1]]] = []
        manifest_paths = sorted(self.archive_directory.glob("agent_intent_dry_run_ledger_v1.*.manifest.json"))
        referenced: set[str] = set()
        for manifest_path in manifest_paths:
            try:
                manifest = DryRunArchiveManifestV0.model_validate_json(manifest_path.read_bytes())
                archive_path = self.archive_directory / manifest.archive_filename
                if archive_path.parent.resolve() != self.archive_directory.resolve():
                    raise ValueError("archive path escaped archive directory")
                referenced.add(manifest.archive_filename)
                payload = archive_path.read_bytes()
                if len(payload) != manifest.byte_size:
                    raise ValueError("archive byte size mismatch")
                if hashlib.sha256(payload).hexdigest() != manifest.sha256:
                    raise ValueError("archive SHA-256 mismatch")
                rows, stats = self._scan_path(archive_path)
                if stats.bounded_read or stats.partial_lines or stats.malformed_rows or stats.oversized_rows or stats.conflicting_duplicate_rows:
                    raise ValueError("archive row integrity validation failed")
                if stats.physical_lines != manifest.row_count or stats.valid_records != manifest.valid_row_count:
                    raise ValueError("archive manifest row count mismatch")
                if manifest.malformed_count or manifest.partial_count or manifest.oversized_count:
                    raise ValueError("archive manifest declares corrupt source evidence")
                valid.append((manifest, archive_path, rows))
            except (OSError, ValueError, ValidationError) as exc:
                diagnostics.append(f"{manifest_path.name}: {exc}")
        for archive_path in sorted(self.archive_directory.glob("agent_intent_dry_run_ledger_v1.*.jsonl")):
            if archive_path.name not in referenced:
                diagnostics.append(f"{archive_path.name}: archive manifest missing")
        rotation_ids: dict[str, str] = {}
        archive_hashes: dict[str, str] = {}
        for manifest, _, _ in valid:
            previous_rotation = rotation_ids.setdefault(manifest.rotation_id, manifest.archive_filename)
            if previous_rotation != manifest.archive_filename:
                diagnostics.append(f"{manifest.archive_filename}: duplicate rotation id with {previous_rotation}")
            previous_hash = archive_hashes.setdefault(manifest.sha256, manifest.archive_filename)
            if previous_hash != manifest.archive_filename:
                diagnostics.append(f"{manifest.archive_filename}: duplicate archive hash with {previous_hash}")
        for temporary in sorted(self.archive_directory.glob(".*.tmp")):
            diagnostics.append(f"{temporary.name}: leftover rotation temporary file")
        return valid, diagnostics

    def rotate(self, *, created_utc: Optional[str] = None, fault_stage: Optional[str] = None) -> DryRunArchiveManifestV0:
        """Explicit transactional rotation; never called from query or append."""
        with self._critical_section():
            rows, stats = self._scan()
            corrupt = stats.bounded_read or stats.partial_lines or stats.malformed_rows or stats.oversized_rows or stats.conflicting_duplicate_rows
            if corrupt:
                raise ValueError("active ledger contains partial/corrupt evidence; rotation rejected")
            if not rows or not self.path.exists() or stats.file_bytes == 0:
                raise ValueError("active ledger has no records to rotate")
            payload = self.path.read_bytes()
            if not payload.endswith(b"\n"):
                raise ValueError("active ledger has trailing partial evidence; rotation rejected")
            if created_utc is None:
                created_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                stamp = datetime.strptime(created_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            except ValueError as exc:
                raise ValueError("created_utc must be UTC YYYY-MM-DDTHH:MM:SSZ") from exc
            archive_filename = f"agent_intent_dry_run_ledger_v1.{stamp}.jsonl"
            manifest_filename = f"agent_intent_dry_run_ledger_v1.{stamp}.manifest.json"
            digest = hashlib.sha256(payload).hexdigest()
            rotation_id = "rotation_" + hashlib.sha256(f"{archive_filename}|{digest}|{created_utc}".encode()).hexdigest()[:24]
            manifest = DryRunArchiveManifestV0(
                archive_filename=archive_filename, created_utc=created_utc,
                byte_size=len(payload), row_count=stats.physical_lines,
                valid_row_count=stats.valid_records, malformed_count=stats.malformed_rows,
                partial_count=stats.partial_lines, oversized_count=stats.oversized_rows,
                sha256=digest, source_active_ledger_path=str(self.path.resolve()),
                rotation_id=rotation_id, earliest_created_ts_ms=stats.earliest_created_ts_ms,
                latest_created_ts_ms=stats.latest_created_ts_ms,
            )
            self.archive_directory.mkdir(parents=True, exist_ok=True)
            archive_path = self.archive_directory / archive_filename
            manifest_path = self.archive_directory / manifest_filename
            if archive_path.exists() or manifest_path.exists():
                raise FileExistsError("rotation target already exists")
            nonce = uuid.uuid4().hex
            archive_tmp = self.archive_directory / f".{archive_filename}.{nonce}.tmp"
            manifest_tmp = self.archive_directory / f".{manifest_filename}.{nonce}.tmp"
            active_tmp = self.directory / f".{LEDGER_FILENAME}.{nonce}.tmp"
            faulted = False
            def inject(stage: str) -> None:
                nonlocal faulted
                if fault_stage == stage:
                    faulted = True
                    raise RotationFaultInjected(stage)
            try:
                inject("before_archive_temp_write")
                with archive_tmp.open("xb") as handle:
                    handle.write(payload); handle.flush(); os.fsync(handle.fileno())
                inject("after_archive_temp_write_before_rename")
                os.replace(archive_tmp, archive_path)
                inject("after_archive_rename_before_manifest_write")
                manifest_payload = (manifest.model_dump_json(exclude_none=True) + "\n").encode("utf-8")
                with manifest_tmp.open("xb") as handle:
                    handle.write(manifest_payload); handle.flush(); os.fsync(handle.fileno())
                inject("after_manifest_temp_write_before_rename")
                os.replace(manifest_tmp, manifest_path)
                self._fsync_directory(self.archive_directory)
                inject("after_manifest_rename_before_active_reset")
                with active_tmp.open("xb") as handle:
                    handle.flush(); os.fsync(handle.fileno())
                os.replace(active_tmp, self.path)
                self._fsync_directory(self.directory)
                inject("after_active_reset")
            finally:
                if not faulted:
                    for temporary in (archive_tmp, manifest_tmp, active_tmp):
                        try:
                            temporary.unlink()
                        except FileNotFoundError:
                            pass
            return manifest

    def archives(self) -> dict[str, Any]:
        with self._critical_section():
            valid, diagnostics = self._archive_inventory_locked()
            return {
                "schema_version": "agent-intent-dry-run-archives/v0", "read_only": True,
                "items": [manifest.model_dump(mode="json", exclude_none=True) for manifest, _, _ in valid],
                "diagnostics": diagnostics,
            }

    def _build_manifest_index_locked(self, *, generated_utc: str, persist: bool) -> dict[str, Any]:
        valid, diagnostics = self._archive_inventory_locked()
        active_rows, active_stats = self._scan()
        valid_manifest_names = {
            archive_path.with_suffix(".manifest.json").name for _, archive_path, _ in valid
        }
        entries: list[dict[str, Any]] = []
        source_hasher = hashlib.sha256()
        if self.archive_directory.exists():
            for path in sorted(self.archive_directory.glob("agent_intent_dry_run_ledger_v1.*.manifest.json")):
                source_hasher.update(path.name.encode("utf-8")); source_hasher.update(b"\0")
                try:
                    source_hasher.update(path.read_bytes())
                except OSError:
                    pass
                if path.name not in valid_manifest_names:
                    entries.append({
                        "manifest_filename": path.name, "integrity_status": "invalid",
                        "diagnostics": [item for item in diagnostics if item.startswith(path.name)],
                    })
        archived_by_id: dict[str, AgentIntentDryRunRecordV1] = {}
        for manifest, archive_path, rows in valid:
            entries.append({
                "manifest_filename": archive_path.with_suffix(".manifest.json").name,
                "archive_filename": manifest.archive_filename,
                "rotation_id": manifest.rotation_id, "byte_count": manifest.byte_size,
                "row_count": manifest.row_count, "valid_row_count": manifest.valid_row_count,
                "sha256": manifest.sha256,
                "earliest_created_ts_ms": manifest.earliest_created_ts_ms,
                "latest_created_ts_ms": manifest.latest_created_ts_ms,
                "source_active_ledger_path": manifest.source_active_ledger_path,
                "integrity_status": "valid", "diagnostics": [],
                "reconstructed": manifest.reconstructed,
                "previous_archive_sha256": manifest.previous_archive_sha256,
                "chain_position": manifest.chain_position,
                "chain_continuity_status": manifest.chain_continuity_status,
            })
            for row in rows:
                previous = archived_by_id.get(row.result.dry_run_id)
                if previous is not None and previous.model_dump_json(exclude_none=True) != row.model_dump_json(exclude_none=True):
                    diagnostics.append(f"conflicting archived dry_run_id: {row.result.dry_run_id}")
                archived_by_id.setdefault(row.result.dry_run_id, row)
        chain_counts = {"chain_start": 0, "continuous": 0, "gap": 0, "overlap": 0, "reconstructed": 0, "invalid": 0}
        previous_manifest: Optional[DryRunArchiveManifestV0] = None
        for position, (manifest, _, _) in enumerate(sorted(valid, key=lambda item: (item[0].earliest_created_ts_ms or 0, item[0].archive_filename))):
            if previous_manifest is None:
                status = "chain_start"
                chain_counts["chain_start"] += 1
            elif manifest.previous_archive_sha256 and manifest.previous_archive_sha256 == previous_manifest.sha256:
                status = "continuous"
                chain_counts["continuous"] += 1
            elif manifest.previous_archive_sha256:
                status = "gap_unknown_previous"
                chain_counts["gap"] += 1
                diagnostics.append(f"{manifest.archive_filename}: previous archive hash is unknown")
            else:
                status = "gap_unknown_previous"
                chain_counts["gap"] += 1
                diagnostics.append(f"{manifest.archive_filename}: previous archive hash missing")
            if previous_manifest is not None and manifest.earliest_created_ts_ms is not None and previous_manifest.latest_created_ts_ms is not None:
                if manifest.earliest_created_ts_ms <= previous_manifest.latest_created_ts_ms:
                    status = "timestamp_overlap"; chain_counts["overlap"] += 1
                    diagnostics.append(f"{manifest.archive_filename}: timestamp overlap")
                elif manifest.earliest_created_ts_ms > previous_manifest.latest_created_ts_ms + 1 and status == "continuous":
                    status = "timestamp_gap"; chain_counts["gap"] += 1
                    diagnostics.append(f"{manifest.archive_filename}: timestamp gap")
            if manifest.reconstructed:
                chain_counts["reconstructed"] += 1
                if status == "continuous": status = "reconstructed_continuity_partial"
            for entry in entries:
                if entry.get("archive_filename") == manifest.archive_filename:
                    entry["chain_position"] = position
                    entry["chain_continuity_status"] = status
                    break
            previous_manifest = manifest
        if self.archive_directory.exists():
            referenced = {entry.get("archive_filename") for entry in entries}
            for archive_path in sorted(self.archive_directory.glob("agent_intent_dry_run_ledger_v1.*.jsonl")):
                source_hasher.update(archive_path.name.encode("utf-8")); source_hasher.update(b"\0")
                if archive_path.name not in referenced:
                    entries.append({
                        "archive_filename": archive_path.name, "integrity_status": "uncommitted",
                        "diagnostics": [item for item in diagnostics if item.startswith(archive_path.name)],
                    })
        combined_ids = set(archived_by_id)
        for row in active_rows:
            previous = archived_by_id.get(row.result.dry_run_id)
            if previous is not None:
                if previous.model_dump_json(exclude_none=True) == row.model_dump_json(exclude_none=True):
                    diagnostics.append(f"active ledger not reset after archive commit: canonical duplicate {row.result.dry_run_id}")
                else:
                    diagnostics.append(f"active/archive conflicting duplicate id: {row.result.dry_run_id}")
            combined_ids.add(row.result.dry_run_id)
        diagnostics = list(dict.fromkeys(diagnostics))
        chain_counts["invalid"] = sum(1 for entry in entries if entry.get("integrity_status") != "valid")
        if chain_counts["invalid"] or any("conflicting" in item or "duplicate" in item for item in diagnostics):
            chain_verdict = "chain_invalid_fail_closed"
        elif chain_counts["gap"] or chain_counts["overlap"]:
            chain_verdict = "chain_partial_gap_detected"
        elif chain_counts["reconstructed"]:
            chain_verdict = "chain_valid_with_reconstructed_segments"
        else:
            chain_verdict = "chain_valid"
        index = {
            "schema_version": "agent-intent-dry-run-manifest-index/v1", "read_only": True,
            "generated_utc": generated_utc, "package_id": RECOVERY_PACKAGE_ID,
            "archive_manifests": sorted(entries, key=lambda item: (str(item.get("archive_filename", "")), str(item.get("manifest_filename", "")))),
            "rotation_ids": [manifest.rotation_id for manifest, _, _ in valid],
            "archive_filenames": [manifest.archive_filename for manifest, _, _ in valid],
            "total_active_rows": len(active_rows),
            "total_archive_rows": sum(len(rows) for _, _, rows in valid),
            "combined_valid_row_count": len(combined_ids),
            "corruption_counts": {
                "active_malformed": active_stats.malformed_rows,
                "active_partial": active_stats.partial_lines,
                "active_oversized": active_stats.oversized_rows,
                "archive_integrity_diagnostics": len(diagnostics),
            },
            "diagnostics": diagnostics,
            "chain_counts": chain_counts,
            "chain_verdict": chain_verdict,
            "index_source_hash": source_hasher.hexdigest(),
            "index_is_source_of_truth": False,
        }
        if persist:
            self.directory.mkdir(parents=True, exist_ok=True)
            target = self.directory / MANIFEST_INDEX_FILENAME
            temporary = self.directory / f".{MANIFEST_INDEX_FILENAME}.{uuid.uuid4().hex}.tmp"
            payload = (json.dumps(index, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
            try:
                with temporary.open("xb") as handle:
                    handle.write(payload); handle.flush(); os.fsync(handle.fileno())
                os.replace(temporary, target)
                self._fsync_directory(self.directory)
            finally:
                try: temporary.unlink()
                except FileNotFoundError: pass
            index["persisted_path"] = str(target.resolve())
        return index

    def rebuild_manifest_index(self, *, generated_utc: Optional[str] = None, persist: bool = True) -> dict[str, Any]:
        if generated_utc is None:
            generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._critical_section():
            return self._build_manifest_index_locked(generated_utc=generated_utc, persist=persist)

    def recover(self, *, created_utc: Optional[str] = None, quarantine_temporary_files: bool = False) -> dict[str, Any]:
        """Explicit recovery: quarantine only temporary files; never trust/delete orphan evidence."""
        if created_utc is None:
            created_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._critical_section():
            before = self._build_manifest_index_locked(generated_utc=created_utc, persist=False)
            candidates = []
            for root in (self.directory, self.archive_directory):
                if root.exists(): candidates.extend(sorted(root.glob(".*.tmp")))
            actions: list[dict[str, str]] = []
            if quarantine_temporary_files and candidates:
                quarantine = self.directory / "recovery_quarantine"
                quarantine.mkdir(parents=True, exist_ok=True)
                for source in candidates:
                    target = quarantine / source.name
                    if target.exists():
                        target = quarantine / f"{source.name}.{uuid.uuid4().hex}"
                    os.replace(source, target)
                    actions.append({"action": "quarantine_temporary", "source": source.name, "target": target.name})
                self._fsync_directory(quarantine)
            after = self._build_manifest_index_locked(generated_utc=created_utc, persist=False)
            report = {
                "schema_version": "agent-intent-dry-run-archive-recovery/v0", "read_only": True,
                "created_utc": created_utc, "package_id": RECOVERY_PACKAGE_ID,
                "quarantine_requested": quarantine_temporary_files,
                "detected_temporary_files": [path.name for path in candidates],
                "actions": actions, "before_diagnostics": before["diagnostics"],
                "after_diagnostics": after["diagnostics"],
                "unresolved_integrity_issues": len(after["diagnostics"]),
                "automatic_manifest_rebuild": False, "historical_evidence_deleted": False,
            }
            reports = self.directory / "recovery_reports"
            reports.mkdir(parents=True, exist_ok=True)
            stamp = datetime.strptime(created_utc, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y%m%dT%H%M%SZ")
            target = reports / f"archive_recovery_report.{stamp}.json"
            temporary = reports / f".{target.name}.{uuid.uuid4().hex}.tmp"
            payload = (json.dumps(report, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
            try:
                with temporary.open("xb") as handle:
                    handle.write(payload); handle.flush(); os.fsync(handle.fileno())
                if target.exists():
                    raise FileExistsError("recovery report target already exists")
                os.replace(temporary, target)
                self._fsync_directory(reports)
            finally:
                try: temporary.unlink()
                except FileNotFoundError: pass
            report["report_path"] = str(target.resolve())
            return report

    def reconstruct_orphan_manifest(
        self, *, archive_filename: str, operator_approval_ref: str,
        reconstruction_reason: str, created_utc: Optional[str] = None,
        fault_stage: Optional[str] = None,
    ) -> DryRunArchiveManifestV0:
        """Explicit operator-approved reconstruction; archive bytes are never changed."""
        if not operator_approval_ref.strip() or not reconstruction_reason.strip():
            raise ValueError("operator approval ref and reconstruction reason are required")
        if _SECRET_VALUE.search(operator_approval_ref) or _SECRET_VALUE.search(reconstruction_reason):
            raise ValueError("secret-looking reconstruction input rejected")
        if created_utc is None:
            created_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._critical_section():
            archive_path = self.archive_directory / archive_filename
            if archive_path.parent.resolve() != self.archive_directory.resolve() or not re.fullmatch(r"agent_intent_dry_run_ledger_v1\.\d{8}T\d{6}Z\.jsonl", archive_filename):
                raise ValueError("invalid orphan archive filename")
            manifest_path = archive_path.with_suffix(".manifest.json")
            if manifest_path.exists():
                raise FileExistsError("archive manifest already exists")
            try:
                payload = archive_path.read_bytes()
                rows, stats = self._scan_path(archive_path)
                if not payload or stats.bounded_read or stats.partial_lines or stats.malformed_rows or stats.oversized_rows or stats.conflicting_duplicate_rows:
                    raise ValueError("orphan archive validation failed")
                if not rows or not payload.endswith(b"\n"):
                    raise ValueError("orphan archive has no complete valid rows")
                digest = hashlib.sha256(payload).hexdigest()
                valid, _ = self._archive_inventory_locked()
                prior = sorted(valid, key=lambda item: item[0].archive_filename)
                previous_hash = prior[-1][0].sha256 if prior else None
                position = len(prior)
                reconstruction_id = "reconstruction_" + hashlib.sha256(f"{archive_filename}|{digest}|{operator_approval_ref}".encode()).hexdigest()[:24]
                rotation_id = "rotation_" + hashlib.sha256(f"reconstructed|{archive_filename}|{digest}".encode()).hexdigest()[:24]
                manifest = DryRunArchiveManifestV0(
                    archive_filename=archive_filename, created_utc=created_utc,
                    byte_size=len(payload), row_count=stats.physical_lines,
                    valid_row_count=stats.valid_records, malformed_count=0,
                    partial_count=0, oversized_count=0, sha256=digest,
                    source_active_ledger_path=str(self.path.resolve()), package_id=RECOVERY_PACKAGE_ID,
                    rotation_id=rotation_id, earliest_created_ts_ms=stats.earliest_created_ts_ms,
                    latest_created_ts_ms=stats.latest_created_ts_ms, reconstructed=True,
                    reconstruction_id=reconstruction_id, operator_approval_ref=operator_approval_ref,
                    reconstruction_reason=reconstruction_reason, source_archive_sha256=digest,
                    created_utc_ts=created_utc, byte_count=len(payload),
                    physical_row_count=stats.physical_lines, timestamp_min=stats.earliest_created_ts_ms,
                    timestamp_max=stats.latest_created_ts_ms, previous_archive_sha256=previous_hash,
                    chain_position=position,
                    chain_continuity_status="reconstructed_continuity_partial",
                )
                temporary = self.archive_directory / f".{manifest_path.name}.{uuid.uuid4().hex}.tmp"
                manifest_payload = (manifest.model_dump_json(exclude_none=True) + "\n").encode("utf-8")
                with temporary.open("xb") as handle:
                    handle.write(manifest_payload); handle.flush(); os.fsync(handle.fileno())
                if fault_stage == "before_reconstructed_manifest_rename":
                    raise RotationFaultInjected(fault_stage)
                os.replace(temporary, manifest_path)
                self._fsync_directory(self.archive_directory)
                if fault_stage == "after_reconstructed_manifest_rename":
                    raise RotationFaultInjected(fault_stage)
                return manifest
            except Exception as exc:
                reports = self.directory / "recovery_reports"; reports.mkdir(parents=True, exist_ok=True)
                stamp = datetime.strptime(created_utc, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y%m%dT%H%M%SZ")
                target = reports / f"reconstruction_diagnostic.{stamp}.{uuid.uuid4().hex[:8]}.json"
                temporary_report = reports / f".{target.name}.tmp"
                report = {"schema_version": "agent-intent-dry-run-reconstruction-diagnostic/v0", "archive_filename": archive_filename, "created_utc": created_utc, "trusted": manifest_path.exists(), "error": str(exc), "historical_evidence_deleted": False}
                with temporary_report.open("xb") as handle:
                    handle.write((json.dumps(report, sort_keys=True) + "\n").encode()); handle.flush(); os.fsync(handle.fileno())
                os.replace(temporary_report, target); self._fsync_directory(reports)
                raise

    def read(self) -> list[AgentIntentDryRunRecordV1]:
        with self._critical_section():
            return self._scan()[0]

    def stats(self) -> DryRunLedgerStatsV0:
        with self._critical_section():
            _, stats = self._scan()
            valid, diagnostics = self._archive_inventory_locked()
            return stats.model_copy(update={
                "archive_count": len(valid),
                "archive_valid_records": sum(len(rows) for _, _, rows in valid),
                "archive_bytes": sum(manifest.byte_size for manifest, _, _ in valid),
                "archive_integrity_errors": len(diagnostics),
            })

    def append(self, record: AgentIntentDryRunRecordV1) -> bool:
        encoded = (record.model_dump_json(exclude_none=True) + "\n").encode("utf-8")
        if len(encoded) > MAX_ROW_BYTES:
            raise ValueError("dry-run ledger row exceeds 64 KiB")
        _assert_safe_record(record)
        with self._critical_section():
            existing = {item.result.dry_run_id: item for item in self._scan()[0]}
            archives, diagnostics = self._archive_inventory_locked()
            if diagnostics:
                raise ArchiveIntegrityError(diagnostics)
            for _, _, archived_rows in archives:
                for archived in archived_rows:
                    existing.setdefault(archived.result.dry_run_id, archived)
            previous = existing.get(record.result.dry_run_id)
            if previous is not None:
                if previous.model_dump_json(exclude_none=True) == record.model_dump_json(exclude_none=True):
                    return False
                raise ValueError("conflicting duplicate dry_run_id")
            self.directory.mkdir(parents=True, exist_ok=True)
            needs_separator = False
            if self.path.exists() and self.path.stat().st_size:
                with self.path.open("rb") as existing_handle:
                    existing_handle.seek(-1, os.SEEK_END)
                    needs_separator = existing_handle.read(1) != b"\n"
            with self.path.open("ab") as handle:
                if needs_separator:
                    handle.write(b"\n")
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        return True

    def latest(
        self, *, symbol: Optional[str] = None, status: Optional[str] = None,
        action: Optional[str] = None, limit: int = 20, offset: int = 0,
    ) -> list[AgentIntentDryRunRecordV1]:
        if not 1 <= limit <= MAX_QUERY_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_QUERY_LIMIT}")
        if not 0 <= offset <= 100_000:
            raise ValueError("offset must be between 0 and 100000")
        rows = self.read()
        if symbol:
            rows = [row for row in rows if row.intent.symbol == symbol.strip().upper()]
        if status:
            rows = [row for row in rows if row.result.validation_status == status]
        if action:
            rows = [row for row in rows if row.intent.action == action.strip().upper()]
        ordered = sorted(rows, key=lambda row: (row.result.created_ts_ms, row.result.dry_run_id), reverse=True)
        return ordered[offset:offset + limit]

    def query(
        self, *, scope: QueryScope = "active", symbol: Optional[str] = None,
        status: Optional[str] = None, action: Optional[str] = None,
        limit: int = 20, offset: int = 0,
    ) -> dict[str, Any]:
        if not 1 <= limit <= MAX_QUERY_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_QUERY_LIMIT}")
        if not 0 <= offset <= 100_000:
            raise ValueError("offset must be between 0 and 100000")
        with self._critical_section():
            sourced: list[tuple[AgentIntentDryRunRecordV1, dict[str, Any]]] = []
            diagnostics: list[str] = []
            if scope in {"active", "active_plus_archives"}:
                active_rows, _ = self._scan()
                sourced.extend((row, {"kind": "active", "ledger": LEDGER_FILENAME}) for row in active_rows)
            if scope in {"archives", "active_plus_archives"}:
                archives, diagnostics = self._archive_inventory_locked()
                if diagnostics:
                    raise ArchiveIntegrityError(diagnostics)
                for manifest, archive_path, rows in archives:
                    source = {
                        "kind": "archive", "ledger": archive_path.name,
                        "manifest": archive_path.with_suffix(".manifest.json").name,
                        "sha256": manifest.sha256, "rotation_id": manifest.rotation_id,
                    }
                    sourced.extend((row, source) for row in rows)
            if symbol:
                sourced = [item for item in sourced if item[0].intent.symbol == symbol.strip().upper()]
            if status:
                sourced = [item for item in sourced if item[0].result.validation_status == status]
            if action:
                sourced = [item for item in sourced if item[0].intent.action == action.strip().upper()]
            sourced.sort(key=lambda item: (item[0].result.created_ts_ms, item[0].result.dry_run_id), reverse=True)
            unique: dict[str, tuple[AgentIntentDryRunRecordV1, dict[str, Any]]] = {}
            for row, source in sourced:
                previous = unique.get(row.result.dry_run_id)
                if previous is None:
                    unique[row.result.dry_run_id] = (row, source)
                elif previous[0].model_dump_json(exclude_none=True) != row.model_dump_json(exclude_none=True):
                    raise ArchiveIntegrityError([f"conflicting dry_run_id across ledgers: {row.result.dry_run_id}"])
                else:
                    diagnostics.append(f"canonical duplicate across ledgers: {row.result.dry_run_id}")
            ordered = list(unique.values())
            page = ordered[offset:offset + limit]
            items = []
            for row, source in page:
                payload = row.model_dump(mode="json")
                payload["source"] = source
                items.append(payload)
            return {
                "schema_version": "agent-intent-dry-run-read/v0", "read_only": True,
                "scope": scope, "limit": limit, "offset": offset,
                "total_matched": len(ordered), "items": items, "diagnostics": diagnostics,
            }


__all__ = [
    "AgentIntentDryRunLedger", "AgentIntentDryRunRecordV1", "AgentIntentDryRunResultV0", "ArchiveIntegrityError",
    "DryRunArchiveManifestV0",
    "CapabilityCheckV0", "DryRunLedgerStatsV0", "EstimatedOrderShapeV0", "LEDGER_FILENAME", "LEDGER_REF",
    "QueryScope", "validate_intent_dry_run", "reject_raw_intent_schema",
]
