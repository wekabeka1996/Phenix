import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from apps.reference.core.time import get_clock
from apps.reference.config_models import (
    ExecutionPositionRestoreArtifactConfig,
    ExecutionPositionRestoreArtifactMode,
    ExecutionPositionStartupTruthArtifactConfig,
)
from apps.reference.domains.execution_position.truth_hardening import get_execution_truth_hardening
from apps.reference.telemetry.trade_lifecycle_logger import append_trade_lifecycle_record
from apps.reference.domains.execution_position.restore_artifact import (
    DeferredBracketRef,
    LinkedBracketRef,
    STARTUP_TRUTH_ARTIFACT_SCHEMA_VERSION,
    STARTUP_TRUTH_ARTIFACT_TYPE,
    TRUTH_SOURCE_UNKNOWN,
    ExecutionPositionRestoreEnvelope,
    ExecutionPositionRestoreArtifactWriter,
    ExecutionPositionRestoreArtifactDarkReader,
    ExecutionPositionRestoreLifecycleRecord,
    ExecutionPositionRestoreAuthoritativeStatus,
    ExecutionPositionRestoreDarkReadStatus,
    ExecutionPositionStartupTruthArtifactWriter,
    ExecutionPositionStartupTruthRecord,
    ExecutionPositionStartupTruthSymbolRecord,
    ExecutionPositionStartupTruthUnknownSymbolRecord,
    ExecutionPositionStartupTruthSummary,
    ExecutionPositionStartupTruthCacheStatus,
    ExecutionPositionStartupTruthRestoreArtifactStatus,
    ExecutionPositionStartupTruthInputSnapshot,
)

if TYPE_CHECKING:
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

LOG = logging.getLogger(__name__)

RESTORE_PHASE_UNKNOWN = "UNKNOWN"
BRACKET_STATE_UNKNOWN = "UNKNOWN"
BRACKET_STATE_DEFERRED_PENDING_WAL = "DEFERRED_PENDING_WAL"
STARTUP_TRUTH_ARTIFACT_WRITER_COMPONENT = "execution_position"


class StartupTruthOrchestrator:
    def __init__(self, fsm: "ExecPosFSM") -> None:
        self._fsm = fsm
        self._restore_artifact_writer = self._create_restore_artifact_writer()
        self._restore_artifact_dark_reader = self._create_restore_artifact_dark_reader()
        self._startup_truth_artifact_writer = self._create_startup_truth_artifact_writer()
        self._restore_artifact_loop_started: bool = False

    def _create_restore_artifact_writer(
        self,
    ) -> Optional[ExecutionPositionRestoreArtifactWriter]:
        try:
            candidate = self._fsm.config.domains.execution_position.restore_artifact
        except Exception:
            return None

        if not isinstance(candidate, ExecutionPositionRestoreArtifactConfig):
            return None

        return ExecutionPositionRestoreArtifactWriter(
            candidate,
            observability_hook=self._fsm._emit_observability_event,
            logger=LOG,
        )

    def _restore_artifact_mode(self) -> Optional[ExecutionPositionRestoreArtifactMode]:
        try:
            candidate = self._fsm.config.domains.execution_position.restore_artifact
        except Exception:
            return None
        if not isinstance(candidate, ExecutionPositionRestoreArtifactConfig):
            return None
        return candidate.mode

    def _authoritative_restore_enabled(self) -> bool:
        return self._restore_artifact_mode() == ExecutionPositionRestoreArtifactMode.AUTHORITATIVE

    def _create_restore_artifact_dark_reader(
        self,
    ) -> Optional[ExecutionPositionRestoreArtifactDarkReader]:
        try:
            candidate = self._fsm.config.domains.execution_position.restore_artifact
        except Exception:
            return None

        if not isinstance(candidate, ExecutionPositionRestoreArtifactConfig):
            return None

        return ExecutionPositionRestoreArtifactDarkReader(
            candidate,
            logger=LOG,
        )

    def _create_startup_truth_artifact_writer(
        self,
    ) -> Optional[ExecutionPositionStartupTruthArtifactWriter]:
        try:
            candidate = self._fsm.config.domains.execution_position.startup_truth_artifact
        except Exception:
            return None

        if not isinstance(candidate, ExecutionPositionStartupTruthArtifactConfig):
            return None

        return ExecutionPositionStartupTruthArtifactWriter(
            candidate,
            observability_hook=self._fsm._emit_observability_event,
            logger=LOG,
        )

    def _restore_artifact_symbol_candidates(self) -> List[str]:
        symbols: Set[str] = set()
        symbols.update(str(sym).upper()
                       for sym in self._fsm.manage_flows.keys())
        symbols.update(str(sym).upper()
                       for sym in self._fsm.close_flows.keys())
        symbols.update(str(sym).upper()
                       for sym in self._fsm._symbol_brackets.keys())
        for pending in dict(self._fsm._pending_brackets).values():
            if not isinstance(pending, dict):
                continue
            symbol = str(pending.get("symbol") or "").strip().upper()
            if symbol:
                symbols.add(symbol)
        return sorted(symbols)

    def _build_execution_restore_artifact_records(
        self,
    ) -> List[ExecutionPositionRestoreLifecycleRecord]:
        records: List[ExecutionPositionRestoreLifecycleRecord] = []
        for symbol in self._restore_artifact_symbol_candidates():
            record = self._build_execution_restore_artifact_record(symbol)
            if record is not None:
                records.append(record)
        return records

    def _build_execution_restore_artifact_record(
        self,
        symbol: str,
    ) -> Optional[ExecutionPositionRestoreLifecycleRecord]:
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return None

        manage_flow = self._fsm.manage_flows.get(symbol_key)
        close_flow = self._fsm.close_flows.get(symbol_key)
        manage_phase = self._fsm._manage_state_value(
            manage_flow) or RESTORE_PHASE_UNKNOWN
        close_phase = self._fsm._close_state_value(
            close_flow) or RESTORE_PHASE_UNKNOWN
        bracket_snapshot = self._fsm._resolve_restore_artifact_bracket_snapshot(
            symbol_key)

        has_active_manage = self._fsm._has_active_lifecycle_for_symbol(
            symbol_key)
        has_active_close = close_phase not in ("", "FLAT")
        if not (has_active_manage or has_active_close or bracket_snapshot["restore_relevant"]):
            return None

        record_kwargs: Dict[str, Any] = {
            "symbol": symbol_key,
            "manage_phase": manage_phase,
            "manage_truth_source": self._fsm._manage_truth_source_for(symbol_key),
            "close_phase": close_phase,
            "bracket_state": bracket_snapshot["bracket_state"],
            "bracket_truth_source": bracket_snapshot["bracket_truth_source"],
            "live_reconcile_required": True,
        }
        if (
            bracket_snapshot["bracket_state"] == BRACKET_STATE_DEFERRED_PENDING_WAL
            and bracket_snapshot["deferred_entry_order_id"]
        ):
            record_kwargs["deferred_bracket_ref"] = DeferredBracketRef(
                entry_order_id=str(
                    bracket_snapshot["deferred_entry_order_id"]),
            )
        if bracket_snapshot["bracket_state"] in {
            "LINKED_ACTIVE",
            "PARTIAL_LINKAGE",
        } and (
            bracket_snapshot["sl_order_id"] or bracket_snapshot["tp_order_id"]
        ):
            record_kwargs["linked_bracket_ref"] = LinkedBracketRef(
                entry_order_id=bracket_snapshot["entry_order_id"],
                entry_client_order_id=bracket_snapshot["entry_client_order_id"],
                sl_order_id=bracket_snapshot["sl_order_id"],
                tp_order_id=bracket_snapshot["tp_order_id"],
                sl_client_order_id=bracket_snapshot["sl_client_order_id"],
                tp_client_order_id=bracket_snapshot["tp_client_order_id"],
            )
        return ExecutionPositionRestoreLifecycleRecord(**record_kwargs)

    def _restore_semantics_signature(
        self,
        symbol: str,
    ) -> Tuple[Any, ...]:
        symbol_key = str(symbol or "").strip().upper()
        manage_phase = self._fsm._manage_state_value(
            self._fsm.manage_flows.get(symbol_key)) or RESTORE_PHASE_UNKNOWN
        close_phase = self._fsm._close_state_value(
            self._fsm.close_flows.get(symbol_key)) or RESTORE_PHASE_UNKNOWN
        bracket_snapshot = self._fsm._resolve_restore_artifact_bracket_snapshot(
            symbol_key)
        has_active_manage = self._fsm._has_active_lifecycle_for_symbol(
            symbol_key)
        has_active_close = close_phase not in ("", "FLAT")
        return (
            manage_phase,
            close_phase,
            str(bracket_snapshot["bracket_state"]),
            (
                str(bracket_snapshot["deferred_entry_order_id"])
                if bracket_snapshot["deferred_entry_order_id"]
                else None
            ),
            (
                str(bracket_snapshot["entry_order_id"])
                if bracket_snapshot["entry_order_id"]
                else None
            ),
            (
                str(bracket_snapshot["entry_client_order_id"])
                if bracket_snapshot["entry_client_order_id"]
                else None
            ),
            (
                str(bracket_snapshot["sl_order_id"])
                if bracket_snapshot["sl_order_id"]
                else None
            ),
            (
                str(bracket_snapshot["tp_order_id"])
                if bracket_snapshot["tp_order_id"]
                else None
            ),
            (
                str(bracket_snapshot["sl_client_order_id"])
                if bracket_snapshot["sl_client_order_id"]
                else None
            ),
            (
                str(bracket_snapshot["tp_client_order_id"])
                if bracket_snapshot["tp_client_order_id"]
                else None
            ),
            bool(
                has_active_manage or has_active_close or bracket_snapshot["restore_relevant"]),
        )

    def _append_restart_truth_record(
        self,
        *,
        event_type: str,
        symbol: str,
        sl_order_id: Optional[str],
        tp_order_id: Optional[str],
        order_index_registrations: int,
        unresolved_reasons: Optional[List[str]] = None,
    ) -> None:
        record = {
            "record_kind": "execution_restart_truth",
            "event_type": event_type,
            "ts_ms": get_clock().now_ms(),
            "symbol": str(symbol or "").strip().upper() or None,
            "sl_order_id": str(sl_order_id or "").strip() or None,
            "tp_order_id": str(tp_order_id or "").strip() or None,
            "bracket_truth_source": self._fsm._symbol_bracket_truth_source_for(symbol),
            "manage_truth_source": self._fsm._manage_truth_source_for(symbol),
            "order_index_registrations": int(order_index_registrations),
            "unresolved_reasons": list(unresolved_reasons or []) or None,
        }
        filtered = {key: value for key,
                    value in record.items() if value is not None}
        append_trade_lifecycle_record(
            filtered,
            log_file=self._fsm._trade_lifecycle_log_path(),
        )
        self._fsm._emit_observability_event(event_type, filtered)

    def _restore_artifact_has_state(self) -> bool:
        return any(self._build_execution_restore_artifact_records())

    def _persist_restore_artifact_snapshot(
        self,
        *,
        trigger: str,
        allow_empty: bool,
    ) -> bool:
        writer = self._restore_artifact_writer
        if writer is None:
            return False
        return writer.persist(self, trigger=trigger, allow_empty=allow_empty)

    def _append_startup_truth_artifact_record(
        self,
        *,
        trigger: str,
        failure_reason: Optional[str],
        input_snapshot: Dict[str, Any],
        symbols_considered: List[str],
        fresh_open_order_count: int,
        runtime_truth: Dict[str, Any],
        restore_artifact_write_attempted: bool,
        restore_artifact_write_succeeded: bool,
        restore_authoritative: Optional[ExecutionPositionRestoreAuthoritativeStatus] = None,
        restore_dark_read: Optional[ExecutionPositionRestoreDarkReadStatus] = None,
        execution_truth_cache: Optional[ExecutionPositionStartupTruthCacheStatus] = None,
    ) -> bool:
        writer = self._startup_truth_artifact_writer
        if writer is None:
            return False

        runtime_summary = runtime_truth.get(
            "summary") if isinstance(runtime_truth, dict) else {}
        runtime_records = runtime_truth.get(
            "records") if isinstance(runtime_truth, dict) else []
        unknown_truth_records = self._build_startup_truth_unknown_records(
            symbols_considered=symbols_considered,
            input_snapshot=input_snapshot,
            runtime_truth_records=runtime_records,
            restore_authoritative=restore_authoritative,
        )
        restore_writer = self._restore_artifact_writer
        restore_artifact_path = restore_writer.storage_path if restore_writer is not None else None

        try:
            record = ExecutionPositionStartupTruthRecord(
                schema_version=STARTUP_TRUTH_ARTIFACT_SCHEMA_VERSION,
                artifact_type=STARTUP_TRUTH_ARTIFACT_TYPE,
                ts_ms=get_clock().now_ms(),
                writer_component=STARTUP_TRUTH_ARTIFACT_WRITER_COMPONENT,
                startup_trigger=trigger,
                failure_reason=str(failure_reason or "").strip() or None,
                reconcile_sequence=[
                    "authoritative_restore_read",
                    "collect_startup_symbols",
                    "guardian_link_existing_from_rest",
                    "guardian_cleanup_orphans",
                    "fetch_post_cleanup_open_orders",
                    "reconstruct_runtime_bracket_truth",
                    "dark_read_compare",
                    "persist_restore_artifact_snapshot",
                ],
                symbols_considered=sorted(
                    {
                        str(symbol).strip().upper()
                        for symbol in symbols_considered
                        if str(symbol).strip()
                    }
                ),
                fresh_open_order_count=int(fresh_open_order_count),
                input_snapshot=ExecutionPositionStartupTruthInputSnapshot(
                    positions_fetch_succeeded=bool(
                        input_snapshot.get("positions_fetch_succeeded", False)
                    ),
                    pre_cleanup_open_orders_fetch_succeeded=bool(
                        input_snapshot.get(
                            "pre_cleanup_open_orders_fetch_succeeded", False)
                    ),
                    post_cleanup_open_orders_fetch_succeeded=bool(
                        input_snapshot.get(
                            "post_cleanup_open_orders_fetch_succeeded", False)
                    ),
                    guardian_link_existing_invoked=bool(
                        input_snapshot.get(
                            "guardian_link_existing_invoked", False)
                    ),
                    guardian_cleanup_invoked=bool(
                        input_snapshot.get("guardian_cleanup_invoked", False)
                    ),
                    position_symbols_observed=sorted(
                        {
                            str(symbol).strip().upper()
                            for symbol in input_snapshot.get("position_symbols_observed", [])
                            if str(symbol).strip()
                        }
                    ),
                    pre_cleanup_order_symbols_observed=sorted(
                        {
                            str(symbol).strip().upper()
                            for symbol in input_snapshot.get(
                                "pre_cleanup_order_symbols_observed",
                                [],
                            )
                            if str(symbol).strip()
                        }
                    ),
                    guardian_symbols_observed=sorted(
                        {
                            str(symbol).strip().upper()
                            for symbol in input_snapshot.get("guardian_symbols_observed", [])
                            if str(symbol).strip()
                        }
                    ),
                    fresh_order_symbols_observed=sorted(
                        {
                            str(symbol).strip().upper()
                            for symbol in input_snapshot.get("fresh_order_symbols_observed", [])
                            if str(symbol).strip()
                        }
                    ),
                ),
                runtime_truth_summary=ExecutionPositionStartupTruthSummary(
                    symbols_reconstructed=int(
                        runtime_summary.get("symbols_reconstructed", 0)
                    ),
                    order_index_registrations=int(
                        runtime_summary.get("order_index_registrations", 0)
                    ),
                    unresolved_symbols=int(
                        runtime_summary.get("unresolved_symbols", 0)
                    ),
                ),
                runtime_truth_records=[
                    ExecutionPositionStartupTruthSymbolRecord(
                        symbol=str(item.get("symbol") or "").strip().upper(),
                        status=(
                            "unresolved"
                            if str(item.get("status") or "").strip().lower()
                            == "unresolved"
                            else "reconstructed"
                        ),
                        sl_order_id=str(item.get("sl_order_id")
                                        or "").strip() or None,
                        tp_order_id=str(item.get("tp_order_id")
                                        or "").strip() or None,
                        bracket_truth_source=str(
                            item.get(
                                "bracket_truth_source") or TRUTH_SOURCE_UNKNOWN
                        ).strip()
                        or TRUTH_SOURCE_UNKNOWN,
                        manage_truth_source=str(
                            item.get(
                                "manage_truth_source") or TRUTH_SOURCE_UNKNOWN
                        ).strip()
                        or TRUTH_SOURCE_UNKNOWN,
                        order_index_registrations=int(
                            item.get("order_index_registrations", 0)
                        ),
                        unresolved_reasons=[
                            str(reason)
                            for reason in item.get("unresolved_reasons", [])
                            if str(reason).strip()
                        ],
                    )
                    for item in runtime_records
                    if str(item.get("symbol") or "").strip()
                ],
                unknown_truth_records=unknown_truth_records,
                restore_artifact=ExecutionPositionStartupTruthRestoreArtifactStatus(
                    path=restore_artifact_path,
                    write_attempted=bool(restore_artifact_write_attempted),
                    write_succeeded=bool(restore_artifact_write_succeeded),
                ),
                restore_authoritative=(
                    restore_authoritative
                    or ExecutionPositionRestoreAuthoritativeStatus()
                ),
                restore_dark_read=restore_dark_read or ExecutionPositionRestoreDarkReadStatus(),
                execution_truth_cache=(
                    execution_truth_cache or self._execution_truth_cache_status()
                ),
            )
        except Exception as exc:
            self._fsm._emit_observability_event(
                "RESTORE:EXECUTION_POSITION_STARTUP_TRUTH_BUILD_FAILED",
                {
                    "startup_trigger": trigger,
                    "failure_reason": type(exc).__name__,
                },
            )
            return False

        return writer.append_record(record)

    def _build_startup_truth_unknown_records(
        self,
        *,
        symbols_considered: List[str],
        input_snapshot: Dict[str, Any],
        runtime_truth_records: List[Dict[str, Any]],
        restore_authoritative: Optional[ExecutionPositionRestoreAuthoritativeStatus],
    ) -> List[ExecutionPositionStartupTruthUnknownSymbolRecord]:
        status = restore_authoritative or ExecutionPositionRestoreAuthoritativeStatus()
        if status.artifact_state not in {"missing", "not_readable", "corrupt", "stale"}:
            return []

        artifact_reason = {
            "missing": "authoritative_artifact_missing",
            "not_readable": "authoritative_artifact_not_readable",
            "corrupt": "authoritative_artifact_corrupt",
            "stale": "authoritative_artifact_stale",
        }.get(status.artifact_state)
        if not artifact_reason:
            return []

        observed_input_map: Dict[str, Set[str]] = {}

        def _remember(symbols: List[str], source: str) -> None:
            for raw_symbol in symbols:
                symbol = str(raw_symbol or "").strip().upper()
                if not symbol:
                    continue
                observed_input_map.setdefault(symbol, set()).add(source)

        _remember(symbols_considered, "symbols_considered")
        _remember(
            list(input_snapshot.get("position_symbols_observed", [])),
            "position_symbols_observed",
        )
        _remember(
            list(input_snapshot.get("pre_cleanup_order_symbols_observed", [])),
            "pre_cleanup_order_symbols_observed",
        )
        _remember(
            list(input_snapshot.get("guardian_symbols_observed", [])),
            "guardian_symbols_observed",
        )
        _remember(
            list(input_snapshot.get("fresh_order_symbols_observed", [])),
            "fresh_order_symbols_observed",
        )

        authoritative_symbols = {
            str(item.symbol).strip().upper()
            for item in status.symbol_statuses
            if str(item.symbol).strip()
        }
        reconstructed_symbols = {
            str(item.get("symbol") or "").strip().upper()
            for item in runtime_truth_records
            if str(item.get("status") or "").strip().lower() == "reconstructed"
            and str(item.get("symbol") or "").strip()
        }
        portfolio_symbols = {
            str(symbol).strip().upper()
            for symbol in input_snapshot.get("position_symbols_observed", [])
            if str(symbol).strip()
        }
        positions_fetch_succeeded = bool(
            input_snapshot.get("positions_fetch_succeeded", False))

        unknown_rows: List[ExecutionPositionStartupTruthUnknownSymbolRecord] = []
        for symbol in sorted(observed_input_map):
            if symbol in authoritative_symbols or symbol in reconstructed_symbols:
                continue

            portfolio_presence = "unknown"
            if positions_fetch_succeeded:
                portfolio_presence = "present" if symbol in portfolio_symbols else "absent"

            reason_codes = [artifact_reason]
            if portfolio_presence == "present":
                reason_codes.append(
                    "portfolio_present_without_restored_lifecycle_truth")

            unknown_rows.append(
                ExecutionPositionStartupTruthUnknownSymbolRecord(
                    symbol=symbol,
                    authoritative_artifact_state=status.artifact_state,
                    portfolio_presence=portfolio_presence,
                    reconstructed_exact_truth_present=False,
                    observed_inputs=sorted(
                        observed_input_map.get(symbol) or []),
                    reason_codes=reason_codes,
                )
            )

        return unknown_rows

    def _execution_truth_cache_status(self) -> ExecutionPositionStartupTruthCacheStatus:
        hardening = get_execution_truth_hardening(self)
        if hardening is None:
            return ExecutionPositionStartupTruthCacheStatus()
        try:
            return ExecutionPositionStartupTruthCacheStatus.model_validate(
                hardening.cache_status_snapshot()
            )
        except Exception:
            return ExecutionPositionStartupTruthCacheStatus()

    def _run_restore_artifact_dark_read_comparison(
        self,
        *,
        now_ms: Optional[int] = None,
    ) -> ExecutionPositionRestoreDarkReadStatus:
        reader = self._restore_artifact_dark_reader
        if reader is None:
            return ExecutionPositionRestoreDarkReadStatus()

        heuristic_records = self._build_execution_restore_artifact_records()
        result = reader.compare_against(heuristic_records, now_ms=now_ms)
        if not result.attempted:
            return result

        if result.artifact_state == "missing":
            LOG.info(
                "Execution restore dark-read: artifact missing at startup (%s)",
                result.artifact_path,
            )
        elif result.artifact_state == "corrupt":
            LOG.warning(
                "Execution restore dark-read: artifact corrupt at startup (%s)",
                result.artifact_path,
            )
        elif result.artifact_state == "not_readable":
            LOG.warning(
                "Execution restore dark-read: artifact not readable at startup (%s)",
                result.artifact_path,
            )
        elif result.artifact_state == "stale":
            LOG.warning(
                "Execution restore dark-read: artifact stale at startup (%s, age_ms=%s, stale_after_ms=%s)",
                result.artifact_path,
                result.artifact_age_ms,
                result.stale_after_ms,
            )

        if result.comparison_outcome == "mismatch":
            LOG.warning(
                "Execution restore dark-read mismatch: path=%s artifact_state=%s exact_field_mismatch=%s heuristic_only=%s artifact_only=%s unknown_vs_guessed=%s mixed_certainty=%s",
                result.artifact_path,
                result.artifact_state,
                result.mismatch_counts.exact_field_mismatch,
                result.mismatch_counts.heuristic_only_field,
                result.mismatch_counts.artifact_only_field,
                result.mismatch_counts.unknown_vs_guessed_mismatch,
                result.mixed_certainty,
            )
        elif result.comparison_outcome == "exact_match":
            LOG.info(
                "Execution restore dark-read exact match: path=%s artifact_state=%s record_count=%s",
                result.artifact_path,
                result.artifact_state,
                result.artifact_record_count,
            )
        return result

    def _run_restore_artifact_authoritative_read(
        self,
        *,
        now_ms: Optional[int] = None,
    ) -> ExecutionPositionRestoreAuthoritativeStatus:
        mode = self._restore_artifact_mode()
        status = ExecutionPositionRestoreAuthoritativeStatus(
            mode=mode.value if mode is not None else "off",
            attempted=True,
        )
        if mode != ExecutionPositionRestoreArtifactMode.AUTHORITATIVE:
            status.attempted = False
            return status

        try:
            reader_cfg = self._fsm.config.domains.execution_position.restore_artifact
        except Exception:
            reader_cfg = None
        if not isinstance(reader_cfg, ExecutionPositionRestoreArtifactConfig):
            status.artifact_state = "not_attempted"
            status.attempted = False
            return status

        artifact_path = str(reader_cfg.storage_path)
        status.artifact_path = artifact_path
        status.stale_after_ms = reader_cfg.dark_read_max_artifact_age_ms
        path = Path(artifact_path)

        if not path.exists():
            status.artifact_state = "missing"
            LOG.warning(
                "Execution restore authoritative read: artifact missing at startup (%s)",
                artifact_path,
            )
            return status

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            status.artifact_state = "not_readable"
            LOG.warning(
                "Execution restore authoritative read: artifact not readable at startup (%s): %s",
                artifact_path,
                exc,
            )
            return status

        if not raw.strip():
            status.artifact_state = "corrupt"
            LOG.warning(
                "Execution restore authoritative read: artifact empty/corrupt at startup (%s)",
                artifact_path,
            )
            return status

        try:
            payload = json.loads(raw)
            envelope = ExecutionPositionRestoreEnvelope.model_validate(payload)
        except Exception as exc:
            status.artifact_state = "corrupt"
            LOG.warning(
                "Execution restore authoritative read: artifact corrupt at startup (%s): %s",
                artifact_path,
                exc,
            )
            return status

        status.parse_success = True
        status.artifact_generated_at_ms = envelope.generated_at_ms
        status.artifact_record_count = len(envelope.active_lifecycles)
        effective_now_ms = int(
            now_ms if now_ms is not None else get_clock().now_ms())
        if envelope.generated_at_ms <= effective_now_ms:
            status.artifact_age_ms = effective_now_ms - envelope.generated_at_ms
        if (
            status.stale_after_ms is not None
            and status.artifact_age_ms is not None
            and status.artifact_age_ms > status.stale_after_ms
        ):
            status.artifact_state = "stale"
            LOG.warning(
                "Execution restore authoritative read: artifact stale at startup (%s, age_ms=%s, stale_after_ms=%s)",
                artifact_path,
                status.artifact_age_ms,
                status.stale_after_ms,
            )
            return status

        status.artifact_state = "valid"
        status.mixed_certainty_symbols = sorted(
            {
                record.symbol
                for record in envelope.active_lifecycles
                if any(
                    value == RESTORE_PHASE_UNKNOWN
                    for value in (
                        str(record.manage_phase).strip().upper(),
                        str(record.close_phase).strip().upper(),
                        str(record.bracket_state).strip().upper(),
                    )
                )
                and len(
                    {
                        str(record.manage_phase).strip().upper(),
                        str(record.close_phase).strip().upper(),
                        str(record.bracket_state).strip().upper(),
                    }
                    - {RESTORE_PHASE_UNKNOWN}
                )
                > 0
            }
        )
        status.mixed_certainty = bool(status.mixed_certainty_symbols)

        for record in envelope.active_lifecycles:
            # 0R-3 SEAM (6A→6B): This call crosses into 6B (authoritative apply / runtime mutation)
            # territory. The mutating method _apply_authoritative_restore_record is intentionally
            # retained in ExecPosFSM (not extracted into 6A) because it writes ManageFlow/CloseFlow
            # runtime state. This cross-call is the temporary seam; Package 6B will own this
            # invocation and no longer require 6A to drive it.
            symbol_status = self._fsm._apply_authoritative_restore_record(
                record)
            status.symbol_statuses.append(symbol_status)
            status.applied_record_count += 1
            for field_name in (
                "manage_phase_restore_status",
                "close_phase_restore_status",
                "bracket_state_restore_status",
            ):
                if getattr(symbol_status, field_name) == "exact":
                    status.restored_exact_field_count += 1
                else:
                    status.restored_unknown_field_count += 1

        LOG.info(
            "Execution restore authoritative read applied: path=%s records=%s exact_fields=%s unknown_fields=%s mixed_certainty=%s",
            artifact_path,
            status.applied_record_count,
            status.restored_exact_field_count,
            status.restored_unknown_field_count,
            status.mixed_certainty,
        )
        return status

    def _finalize_restore_authoritative_status(
        self,
        status: ExecutionPositionRestoreAuthoritativeStatus,
        *,
        positions_fetch_succeeded: bool,
        position_symbols: Set[str],
    ) -> ExecutionPositionRestoreAuthoritativeStatus:
        if not status.attempted or not status.symbol_statuses:
            return status

        current_records = {
            record.symbol: record
            for record in self._build_execution_restore_artifact_records()
        }
        for symbol_status in status.symbol_statuses:
            symbol_key = str(symbol_status.symbol or "").strip().upper()
            if positions_fetch_succeeded:
                symbol_status.portfolio_presence = (
                    "present" if symbol_key in position_symbols else "absent"
                )
            if (
                symbol_status.portfolio_presence == "absent"
                and (
                    symbol_status.manage_phase_restore_status == "exact"
                    or symbol_status.close_phase_restore_status == "exact"
                    or symbol_status.bracket_state_restore_status == "exact"
                )
            ):
                symbol_status.unresolved_reasons.append(
                    "portfolio_symbol_absent")
            if (
                symbol_status.portfolio_presence == "present"
                and symbol_status.manage_phase_restore_status == "unknown"
                and symbol_status.close_phase_restore_status == "unknown"
                and symbol_status.bracket_state_restore_status == "unknown"
            ):
                symbol_status.unresolved_reasons.append(
                    "portfolio_present_without_restored_lifecycle_truth"
                )

            current_record = current_records.get(symbol_key)
            if current_record is None:
                continue

            if symbol_status.manage_phase_value != str(current_record.manage_phase):
                symbol_status.runtime_override_fields.append("manage_phase")
            if symbol_status.close_phase_value != str(current_record.close_phase):
                symbol_status.runtime_override_fields.append("close_phase")
            if symbol_status.bracket_state_value != str(current_record.bracket_state):
                symbol_status.runtime_override_fields.append("bracket_state")

        return status

    def _schedule_restore_artifact_loop(self) -> None:
        if self._restore_artifact_loop_started:
            return
        if self._restore_artifact_writer is None:
            return
        if not self._restore_artifact_writer.writes_enabled():
            return
        loop = self._fsm._get_async_loop()
        if not loop:
            LOG.debug("Restore artifact loop deferred: no event loop active")
            return
        self._fsm._submit_async(self._restore_artifact_loop(), loop)
        self._restore_artifact_loop_started = True

    async def _restore_artifact_loop(self) -> None:
        writer = self._restore_artifact_writer
        if writer is None or not writer.writes_enabled():
            return

        while True:
            try:
                await get_clock().sleep_ms(writer.flush_interval_ms)
                self._persist_restore_artifact_snapshot(
                    trigger="periodic",
                    allow_empty=False,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                LOG.warning("restore artifact loop error: %s", e)

    def _portfolio_event_trace_snapshot(self) -> List[Dict[str, Any]]:
        return [
            dict(self._fsm._portfolio_event_stage_traces[trace_id])
            for trace_id in self._fsm._portfolio_event_stage_trace_order
            if trace_id in self._fsm._portfolio_event_stage_traces
        ]
