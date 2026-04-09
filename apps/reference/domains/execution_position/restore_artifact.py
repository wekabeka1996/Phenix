from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from apps.reference.config_models import (
    ExecutionPositionRestoreArtifactConfig,
    ExecutionPositionRestoreArtifactMode,
    ExecutionPositionStartupTruthArtifactConfig,
    ExecutionPositionStartupTruthArtifactMode,
)
from apps.reference.core.time import get_clock

LOG = logging.getLogger(__name__)

RESTORE_ARTIFACT_SCHEMA_VERSION = "1.0.0"
RESTORE_ARTIFACT_TYPE = "execution_position_restore_envelope_v1"
RESTORE_ARTIFACT_WRITER_COMPONENT = "execution_position"
STARTUP_TRUTH_ARTIFACT_SCHEMA_VERSION = "1.0.0"
STARTUP_TRUTH_ARTIFACT_TYPE = "execution_position_startup_truth_v1"
STARTUP_TRUTH_ARTIFACT_WRITER_COMPONENT = "execution_position"
RESTORE_PHASE_UNKNOWN = "UNKNOWN"
BRACKET_STATE_DEFERRED_PENDING_WAL = "DEFERRED_PENDING_WAL"
BRACKET_STATE_LINKED_ACTIVE = "LINKED_ACTIVE"
BRACKET_STATE_PARTIAL_LINKAGE = "PARTIAL_LINKAGE"
BRACKET_STATE_UNKNOWN = "UNKNOWN"
TRUTH_SOURCE_RUNTIME_LOCAL = "RUNTIME_LOCAL"
TRUTH_SOURCE_RESTORE_ARTIFACT = "RESTORE_ARTIFACT"
TRUTH_SOURCE_RESTORED_PENDING_WAL = "RESTORED_PENDING_WAL"
TRUTH_SOURCE_RECONSTRUCTED_GUARDIAN = "RECONSTRUCTED_GUARDIAN"
TRUTH_SOURCE_UNKNOWN = "UNKNOWN"


class DeferredBracketRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_order_id: str = Field(min_length=1)


class ExecutionPositionRestoreLifecycleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    manage_phase: str = Field(min_length=1)
    manage_truth_source: str = Field(
        min_length=1, default=TRUTH_SOURCE_UNKNOWN)
    close_phase: str = Field(min_length=1)
    bracket_state: str = Field(min_length=1)
    bracket_truth_source: str = Field(
        min_length=1, default=TRUTH_SOURCE_UNKNOWN)
    live_reconcile_required: bool = Field(default=True)
    deferred_bracket_ref: Optional[DeferredBracketRef] = Field(default=None)

    @model_validator(mode="after")
    def _validate_deferred_ref(self) -> "ExecutionPositionRestoreLifecycleRecord":
        if self.bracket_state == BRACKET_STATE_DEFERRED_PENDING_WAL:
            if self.deferred_bracket_ref is None:
                raise ValueError(
                    "deferred_bracket_ref is required when bracket_state=DEFERRED_PENDING_WAL"
                )
        elif self.deferred_bracket_ref is not None:
            raise ValueError(
                "deferred_bracket_ref is only allowed when bracket_state=DEFERRED_PENDING_WAL"
            )
        return self


class ExecutionPositionRestoreEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    artifact_type: Literal["execution_position_restore_envelope_v1"]
    generated_at_ms: int = Field(ge=0)
    writer_component: Literal["execution_position"]
    requires_live_reconcile: bool = Field(default=True)
    active_lifecycles: List[ExecutionPositionRestoreLifecycleRecord] = Field(
        default_factory=list
    )


class ExecutionPositionRestoreDarkReadMismatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    field: str = Field(min_length=1)
    mismatch_class: Literal[
        "exact_field_mismatch",
        "heuristic_only_field",
        "artifact_only_field",
        "unknown_vs_guessed_mismatch",
    ]
    artifact_value: Optional[str] = None
    heuristic_value: Optional[str] = None


class ExecutionPositionRestoreDarkReadMismatchCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exact_match: int = Field(default=0, ge=0)
    exact_field_mismatch: int = Field(default=0, ge=0)
    heuristic_only_field: int = Field(default=0, ge=0)
    artifact_only_field: int = Field(default=0, ge=0)
    unknown_vs_guessed_mismatch: int = Field(default=0, ge=0)


class ExecutionPositionRestoreDarkReadStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(min_length=1, default="off")
    attempted: bool = False
    artifact_path: Optional[str] = Field(default=None, min_length=1)
    artifact_state: Literal[
        "not_attempted",
        "missing",
        "not_readable",
        "corrupt",
        "stale",
        "valid",
    ] = "not_attempted"
    parse_success: bool = False
    comparison_outcome: Literal[
        "not_attempted",
        "not_compared",
        "exact_match",
        "mismatch",
    ] = "not_attempted"
    artifact_generated_at_ms: Optional[int] = Field(default=None, ge=0)
    artifact_age_ms: Optional[int] = Field(default=None, ge=0)
    stale_after_ms: Optional[int] = Field(default=None, gt=0)
    mixed_certainty: bool = False
    mixed_certainty_symbols: List[str] = Field(default_factory=list)
    artifact_record_count: int = Field(default=0, ge=0)
    heuristic_record_count: int = Field(default=0, ge=0)
    mismatch_counts: ExecutionPositionRestoreDarkReadMismatchCounts = Field(
        default_factory=ExecutionPositionRestoreDarkReadMismatchCounts
    )
    mismatch_samples: List[ExecutionPositionRestoreDarkReadMismatch] = Field(
        default_factory=list
    )


class ExecutionPositionRestoreAuthoritativeSymbolStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    manage_phase_value: str = Field(min_length=1, default=RESTORE_PHASE_UNKNOWN)
    manage_phase_restore_status: Literal["exact", "unknown"] = "unknown"
    close_phase_value: str = Field(min_length=1, default=RESTORE_PHASE_UNKNOWN)
    close_phase_restore_status: Literal["exact", "unknown"] = "unknown"
    bracket_state_value: str = Field(min_length=1, default=BRACKET_STATE_UNKNOWN)
    bracket_state_restore_status: Literal["exact", "unknown"] = "unknown"
    live_reconcile_required: bool = True
    deferred_entry_order_id: Optional[str] = Field(default=None, min_length=1)
    portfolio_presence: Literal["unknown", "present", "absent"] = "unknown"
    runtime_override_fields: List[str] = Field(default_factory=list)
    unresolved_reasons: List[str] = Field(default_factory=list)


class ExecutionPositionRestoreAuthoritativeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(min_length=1, default="off")
    attempted: bool = False
    artifact_path: Optional[str] = Field(default=None, min_length=1)
    artifact_state: Literal[
        "not_attempted",
        "missing",
        "not_readable",
        "corrupt",
        "stale",
        "valid",
    ] = "not_attempted"
    parse_success: bool = False
    artifact_generated_at_ms: Optional[int] = Field(default=None, ge=0)
    artifact_age_ms: Optional[int] = Field(default=None, ge=0)
    stale_after_ms: Optional[int] = Field(default=None, gt=0)
    mixed_certainty: bool = False
    mixed_certainty_symbols: List[str] = Field(default_factory=list)
    artifact_record_count: int = Field(default=0, ge=0)
    applied_record_count: int = Field(default=0, ge=0)
    restored_exact_field_count: int = Field(default=0, ge=0)
    restored_unknown_field_count: int = Field(default=0, ge=0)
    symbol_statuses: List[ExecutionPositionRestoreAuthoritativeSymbolStatus] = Field(
        default_factory=list
    )


class ExecutionPositionStartupTruthInputSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    positions_fetch_succeeded: bool = False
    pre_cleanup_open_orders_fetch_succeeded: bool = False
    post_cleanup_open_orders_fetch_succeeded: bool = False
    guardian_link_existing_invoked: bool = False
    guardian_cleanup_invoked: bool = False
    position_symbols_observed: List[str] = Field(default_factory=list)
    pre_cleanup_order_symbols_observed: List[str] = Field(default_factory=list)
    guardian_symbols_observed: List[str] = Field(default_factory=list)
    fresh_order_symbols_observed: List[str] = Field(default_factory=list)


class ExecutionPositionStartupTruthSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbols_reconstructed: int = Field(ge=0)
    order_index_registrations: int = Field(ge=0)
    unresolved_symbols: int = Field(ge=0)


class ExecutionPositionStartupTruthSymbolRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    status: Literal["reconstructed", "unresolved"]
    sl_order_id: Optional[str] = Field(default=None, min_length=1)
    tp_order_id: Optional[str] = Field(default=None, min_length=1)
    bracket_truth_source: str = Field(
        min_length=1, default=TRUTH_SOURCE_UNKNOWN)
    manage_truth_source: str = Field(
        min_length=1, default=TRUTH_SOURCE_UNKNOWN)
    order_index_registrations: int = Field(default=0, ge=0)
    unresolved_reasons: List[str] = Field(default_factory=list)


class ExecutionPositionStartupTruthRestoreArtifactStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Optional[str] = Field(default=None, min_length=1)
    write_attempted: bool = False
    write_succeeded: bool = False


class ExecutionPositionStartupTruthCacheStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legacy_config_key: str = Field(min_length=1, default="event_dedup.warm_state")
    truth_class: Literal["cache_only"] = "cache_only"
    authoritative: bool = False
    cache_kind: Literal["exact_terminal_fill_identity_dedupe_seed"] = (
        "exact_terminal_fill_identity_dedupe_seed"
    )
    status: Literal[
        "not_available",
        "not_attempted",
        "disabled",
        "empty",
        "loaded",
        "load_failed",
    ] = "not_available"
    configured_path: Optional[str] = Field(default=None, min_length=1)
    active_path: Optional[str] = Field(default=None, min_length=1)
    legacy_alias_path: Optional[str] = Field(default=None, min_length=1)
    compatibility_mode: str = Field(min_length=1, default="configured_path")
    entries_loaded: int = Field(default=0, ge=0)


class ExecutionPositionStartupTruthRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    artifact_type: Literal["execution_position_startup_truth_v1"]
    ts_ms: int = Field(ge=0)
    writer_component: Literal["execution_position"]
    startup_trigger: str = Field(min_length=1)
    failure_reason: Optional[str] = Field(default=None, min_length=1)
    reconcile_sequence: List[str] = Field(default_factory=list)
    symbols_considered: List[str] = Field(default_factory=list)
    fresh_open_order_count: int = Field(default=0, ge=0)
    input_snapshot: ExecutionPositionStartupTruthInputSnapshot
    runtime_truth_summary: ExecutionPositionStartupTruthSummary
    runtime_truth_records: List[ExecutionPositionStartupTruthSymbolRecord] = Field(
        default_factory=list
    )
    restore_artifact: ExecutionPositionStartupTruthRestoreArtifactStatus = Field(
        default_factory=ExecutionPositionStartupTruthRestoreArtifactStatus
    )
    restore_authoritative: ExecutionPositionRestoreAuthoritativeStatus = Field(
        default_factory=ExecutionPositionRestoreAuthoritativeStatus
    )
    restore_dark_read: ExecutionPositionRestoreDarkReadStatus = Field(
        default_factory=ExecutionPositionRestoreDarkReadStatus
    )
    execution_truth_cache: ExecutionPositionStartupTruthCacheStatus = Field(
        default_factory=ExecutionPositionStartupTruthCacheStatus
    )


class ExecutionPositionRestoreArtifactWriter:
    """Writer-only whole-envelope persistence for execution_position restart truth."""

    def __init__(
        self,
        config: ExecutionPositionRestoreArtifactConfig,
        *,
        observability_hook: Optional[Callable[[
            str, Dict[str, Any]], None]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._config = config
        self._observability_hook = observability_hook
        self._logger = logger or LOG
        self._path = Path(config.storage_path)
        self._last_payload_json: Optional[str] = None

    @property
    def mode(self) -> ExecutionPositionRestoreArtifactMode:
        return self._config.mode

    @property
    def flush_interval_ms(self) -> int:
        return int(self._config.flush_interval_ms)

    @property
    def storage_path(self) -> str:
        return str(self._path)

    def writes_enabled(self) -> bool:
        return self.mode != ExecutionPositionRestoreArtifactMode.OFF

    def build_envelope(self, fsm: Any) -> ExecutionPositionRestoreEnvelope:
        records = fsm._build_execution_restore_artifact_records()
        return ExecutionPositionRestoreEnvelope(
            schema_version=RESTORE_ARTIFACT_SCHEMA_VERSION,
            artifact_type=RESTORE_ARTIFACT_TYPE,
            generated_at_ms=get_clock().now_ms(),
            writer_component=RESTORE_ARTIFACT_WRITER_COMPONENT,
            requires_live_reconcile=True,
            active_lifecycles=records,
        )

    def persist(
        self,
        fsm: Any,
        *,
        trigger: str,
        allow_empty: bool,
    ) -> bool:
        if not self.writes_enabled():
            return False

        envelope = self.build_envelope(fsm)
        if not envelope.active_lifecycles and not allow_empty:
            return False

        payload = envelope.model_dump(mode="json", exclude_none=True)
        serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        if serialized == self._last_payload_json:
            return False

        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Optional[Path] = None
        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=f"{path.name}.",
                suffix=".tmp",
                dir=str(path.parent),
            )
            temp_path = Path(tmp_name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(str(temp_path), str(path))
            temp_path = None
            self._fsync_parent_dir(path.parent)
            self._last_payload_json = serialized
            self._emit_observability(
                "RESTORE:EXECUTION_POSITION_ARTIFACT_WRITE_OK",
                {
                    "artifact_path": str(path),
                    "record_count": len(envelope.active_lifecycles),
                    "symbol_count": len({record.symbol for record in envelope.active_lifecycles}),
                    "trigger": trigger,
                },
            )
            return True
        except Exception as exc:
            self._emit_observability(
                "RESTORE:EXECUTION_POSITION_ARTIFACT_WRITE_FAILED",
                {
                    "artifact_path": str(path),
                    "record_count": len(envelope.active_lifecycles),
                    "symbol_count": len({record.symbol for record in envelope.active_lifecycles}),
                    "trigger": trigger,
                    "failure_reason": type(exc).__name__,
                    "failure_detail": str(exc),
                },
            )
            self._logger.warning(
                "execution restore artifact write failed (%s): %s",
                trigger,
                exc,
            )
            return False
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _emit_observability(self, event_name: str, payload: Dict[str, Any]) -> None:
        if self._observability_hook is None:
            return
        try:
            self._observability_hook(event_name, payload)
        except Exception:
            pass

    @staticmethod
    def _fsync_parent_dir(path: Path) -> None:
        try:
            dir_fd = os.open(str(path), os.O_RDONLY)
        except Exception:
            return
        try:
            os.fsync(dir_fd)
        except Exception:
            pass
        finally:
            try:
                os.close(dir_fd)
            except Exception:
                pass


class ExecutionPositionRestoreArtifactDarkReader:
    """Parse and diff the restore envelope without changing startup authority."""

    _COMPARE_FIELDS = (
        "manage_phase",
        "manage_truth_source",
        "close_phase",
        "bracket_state",
        "bracket_truth_source",
        "live_reconcile_required",
        "deferred_bracket_ref.entry_order_id",
    )

    def __init__(
        self,
        config: ExecutionPositionRestoreArtifactConfig,
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._config = config
        self._logger = logger or LOG
        self._path = Path(config.storage_path)

    def compare_against(
        self,
        heuristic_records: List[ExecutionPositionRestoreLifecycleRecord],
        *,
        now_ms: Optional[int] = None,
    ) -> ExecutionPositionRestoreDarkReadStatus:
        status = ExecutionPositionRestoreDarkReadStatus(
            mode=self._config.mode.value,
            attempted=True,
            artifact_path=str(self._path),
            stale_after_ms=self._config.dark_read_max_artifact_age_ms,
            heuristic_record_count=len(heuristic_records),
            comparison_outcome="not_compared",
        )

        if self._config.mode.name != "DARK_READ":
            status.attempted = False
            status.artifact_state = "not_attempted"
            status.comparison_outcome = "not_attempted"
            return status

        if not self._path.exists():
            status.artifact_state = "missing"
            return status

        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            status.artifact_state = "not_readable"
            self._logger.warning(
                "execution restore dark-read could not read artifact: %s", exc
            )
            return status

        if not raw.strip():
            status.artifact_state = "corrupt"
            return status

        try:
            payload = json.loads(raw)
            envelope = ExecutionPositionRestoreEnvelope.model_validate(payload)
        except Exception as exc:
            status.artifact_state = "corrupt"
            self._logger.warning(
                "execution restore dark-read found corrupt artifact: %s", exc
            )
            return status

        status.parse_success = True
        status.artifact_generated_at_ms = envelope.generated_at_ms
        status.artifact_record_count = len(envelope.active_lifecycles)
        effective_now_ms = int(now_ms if now_ms is not None else get_clock().now_ms())
        if envelope.generated_at_ms <= effective_now_ms:
            status.artifact_age_ms = effective_now_ms - envelope.generated_at_ms
        stale_after_ms = self._config.dark_read_max_artifact_age_ms
        if (
            stale_after_ms is not None
            and status.artifact_age_ms is not None
            and status.artifact_age_ms > stale_after_ms
        ):
            status.artifact_state = "stale"
        else:
            status.artifact_state = "valid"

        status.mixed_certainty_symbols = sorted(
            {
                record.symbol
                for record in envelope.active_lifecycles
                if self._has_mixed_certainty(record)
            }
        )
        status.mixed_certainty = bool(status.mixed_certainty_symbols)
        status.mismatch_counts, status.mismatch_samples = self._compare_records(
            envelope.active_lifecycles,
            heuristic_records,
        )
        if (
            status.mismatch_counts.exact_field_mismatch
            or status.mismatch_counts.heuristic_only_field
            or status.mismatch_counts.artifact_only_field
            or status.mismatch_counts.unknown_vs_guessed_mismatch
        ):
            status.comparison_outcome = "mismatch"
        else:
            status.comparison_outcome = "exact_match"
        return status

    def _compare_records(
        self,
        artifact_records: List[ExecutionPositionRestoreLifecycleRecord],
        heuristic_records: List[ExecutionPositionRestoreLifecycleRecord],
    ) -> tuple[
        ExecutionPositionRestoreDarkReadMismatchCounts,
        List[ExecutionPositionRestoreDarkReadMismatch],
    ]:
        counts = ExecutionPositionRestoreDarkReadMismatchCounts()
        samples: List[ExecutionPositionRestoreDarkReadMismatch] = []

        artifact_by_symbol = {
            str(record.symbol).strip().upper(): record for record in artifact_records
        }
        heuristic_by_symbol = {
            str(record.symbol).strip().upper(): record for record in heuristic_records
        }
        all_symbols = sorted(set(artifact_by_symbol.keys()) | set(heuristic_by_symbol.keys()))

        for symbol in all_symbols:
            artifact_record = artifact_by_symbol.get(symbol)
            heuristic_record = heuristic_by_symbol.get(symbol)
            for field_name in self._COMPARE_FIELDS:
                artifact_value = self._field_value(artifact_record, field_name)
                heuristic_value = self._field_value(heuristic_record, field_name)
                mismatch_class = self._classify_field_mismatch(
                    artifact_value,
                    heuristic_value,
                )
                if mismatch_class == "exact_match":
                    counts.exact_match += 1
                    continue

                setattr(
                    counts,
                    mismatch_class,
                    getattr(counts, mismatch_class) + 1,
                )
                if len(samples) < 64:
                    samples.append(
                        ExecutionPositionRestoreDarkReadMismatch(
                            symbol=symbol,
                            field=field_name,
                            mismatch_class=mismatch_class,
                            artifact_value=self._stringify_value(artifact_value),
                            heuristic_value=self._stringify_value(heuristic_value),
                        )
                    )

        return counts, samples

    @classmethod
    def _field_value(
        cls,
        record: Optional[ExecutionPositionRestoreLifecycleRecord],
        field_name: str,
    ) -> Any:
        if record is None:
            return None
        if field_name == "deferred_bracket_ref.entry_order_id":
            if record.deferred_bracket_ref is None:
                return None
            return record.deferred_bracket_ref.entry_order_id
        return getattr(record, field_name)

    @classmethod
    def _classify_field_mismatch(cls, artifact_value: Any, heuristic_value: Any) -> str:
        if artifact_value == heuristic_value:
            return "exact_match"
        if artifact_value is None and heuristic_value is not None:
            return "heuristic_only_field"
        if heuristic_value is None and artifact_value is not None:
            return "artifact_only_field"
        if cls._is_unknown_value(artifact_value) != cls._is_unknown_value(heuristic_value):
            return "unknown_vs_guessed_mismatch"
        return "exact_field_mismatch"

    @staticmethod
    def _stringify_value(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _is_unknown_value(value: Any) -> bool:
        return str(value).strip().upper() == RESTORE_PHASE_UNKNOWN if value is not None else False

    @staticmethod
    def _has_mixed_certainty(record: ExecutionPositionRestoreLifecycleRecord) -> bool:
        key_values = [
            str(record.manage_phase).strip().upper(),
            str(record.close_phase).strip().upper(),
            str(record.bracket_state).strip().upper(),
        ]
        unknown_count = sum(1 for value in key_values if value == RESTORE_PHASE_UNKNOWN)
        return 0 < unknown_count < len(key_values)


class ExecutionPositionStartupTruthArtifactWriter:
    """Append-only startup-truth summaries for execution_position restart reconciliation."""

    def __init__(
        self,
        config: ExecutionPositionStartupTruthArtifactConfig,
        *,
        observability_hook: Optional[Callable[[
            str, Dict[str, Any]], None]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._config = config
        self._observability_hook = observability_hook
        self._logger = logger or LOG
        self._path = Path(config.storage_path)

    @property
    def mode(self) -> ExecutionPositionStartupTruthArtifactMode:
        return self._config.mode

    @property
    def storage_path(self) -> str:
        return str(self._path)

    def writes_enabled(self) -> bool:
        return self.mode != ExecutionPositionStartupTruthArtifactMode.OFF

    def append_record(self, record: ExecutionPositionStartupTruthRecord) -> bool:
        if not self.writes_enabled():
            return False

        payload = record.model_dump(mode="json", exclude_none=True)
        serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            self._emit_observability(
                "RESTORE:EXECUTION_POSITION_STARTUP_TRUTH_ARTIFACT_WRITE_OK",
                {
                    "artifact_path": str(path),
                    "startup_trigger": record.startup_trigger,
                    "symbol_count": len(record.symbols_considered),
                    "reconstructed_symbols": record.runtime_truth_summary.symbols_reconstructed,
                    "unresolved_symbols": record.runtime_truth_summary.unresolved_symbols,
                },
            )
            return True
        except Exception as exc:
            self._emit_observability(
                "RESTORE:EXECUTION_POSITION_STARTUP_TRUTH_ARTIFACT_WRITE_FAILED",
                {
                    "artifact_path": str(path),
                    "startup_trigger": record.startup_trigger,
                    "symbol_count": len(record.symbols_considered),
                    "failure_reason": type(exc).__name__,
                    "failure_detail": str(exc),
                },
            )
            self._logger.warning(
                "execution startup truth artifact write failed (%s): %s",
                record.startup_trigger,
                exc,
            )
            return False

    def _emit_observability(self, event_name: str, payload: Dict[str, Any]) -> None:
        if self._observability_hook is None:
            return
        try:
            self._observability_hook(event_name, payload)
        except Exception:
            pass
