from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from calibrators.datasets.builders.common import (
    DEFAULT_PROMOTION_MIN_REQUIRED_COVERAGE_PCT,
    DEFAULT_PROMOTION_MIN_REQUIRED_ROWS,
    compute_basic_data_quality_summary,
    normalize_side,
    normalize_symbol,
    safe_parse_int_ts,
    source_paths_for,
    validate_and_count,
    write_jsonl,
    write_manifest_json,
)
from calibrators.datasets.builders.source_snapshot import (
    SnapshotSourceSpec,
    snapshot_sources as build_source_snapshot,
)
from calibrators.datasets.schema_registry import validate_row


DATASET_SCHEMA_ID = "calibration_realized_trade_dataset_v1"
DATASET_VERSION = "1.0.0"
ORDER_LOG_CLOSE_EVENT = "POSITION_CLOSED"
ORDER_LOG_FILL_EVENT = "ORDER_FILLED"
ORDER_LOG_ENTRY_KIND = "ENTRY"
EXPECTED_DECISION_LEDGER = "logs/shadow_telemetry/decision_ledger_v1.jsonl"
EXPECTED_ORDER_LOG = "logs/order_log_v1.jsonl"
EXPECTED_TRADE_LIFECYCLE = "logs/trade_lifecycle.jsonl"
REJECT_TERMINAL_STATUSES = {
    "REJECTED",
    "REJECTED_UPSTREAM",
    "INVALID_REJECTED",
}
ALTERNATIVE_TERMINAL_EVENTS = {
    "DECISION_INTENT_REJECTED",
    "ORDER_CANCELLED",
    "ORDER_REJECTED",
    "ORDER_TIMEOUT",
}


@dataclass(frozen=True)
class SourceRecord:
    data: dict[str, Any]
    line_number: int
    source_path: str


@dataclass
class BuilderResult:
    realized_rows: list[dict[str, Any]]
    data_quality_summary: dict[str, Any]
    blockers: list[str]
    warnings: list[str]
    manifest: dict[str, Any]
    rejected_rows: list[dict[str, Any]]
    accepted_unresolved_rows: list[dict[str, Any]]
    canonicalization_report: dict[str, Any]


@dataclass(frozen=True)
class DenominatorCoverageStats:
    total_decision_rows: int
    rejected_or_not_executed_rows: int
    execution_eligible_rows: int
    entry_filled_rows: int
    close_expected_rows: int


@dataclass(frozen=True)
class DecisionRuntimeEvidence:
    rejected_or_not_executed: bool
    has_entry_fill: bool
    has_close_candidate: bool
    has_close_fill: bool
    has_close_submission: bool
    has_terminal_close: bool


def _relative_to_repo(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _classify_source_kind(path: Path, repo_root: Path, authority_relative_path: str) -> str:
    relative_path = _relative_to_repo(repo_root, path)
    if relative_path == authority_relative_path:
        return "current_workspace_authority"
    if relative_path.startswith("logs/frozen/") or relative_path.startswith("reports/forensics/"):
        return "supplemental_frozen"
    return "explicit_cli_override"


def _source_snapshot_note(explicit_override: bool) -> str | None:
    if explicit_override:
        return "selected_by_cli_override"
    return None


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _read_jsonl_records(path: Path) -> tuple[list[SourceRecord], list[str]]:
    records: list[SourceRecord] = []
    errors: list[str] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(
                    f"{path.as_posix()}:{line_number}: JSON decode error: {exc.msg}"
                )
                continue
            if not isinstance(payload, dict):
                errors.append(
                    f"{path.as_posix()}:{line_number}: expected object row, got {type(payload).__name__}"
                )
                continue
            records.append(
                SourceRecord(
                    data=payload,
                    line_number=line_number,
                    source_path=str(path),
                )
            )
    return records, errors


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    return date.fromisoformat(value)


def _within_date_range(ts_ms: Optional[int], date_start: Optional[date], date_end: Optional[date]) -> bool:
    if ts_ms is None:
        return date_start is None and date_end is None
    observed = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()
    if date_start is not None and observed < date_start:
        return False
    if date_end is not None and observed > date_end:
        return False
    return True


def _parse_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _decision_strategy_id(decision: dict[str, Any]) -> Optional[str]:
    if _as_text(decision.get("strategy_id")):
        return _as_text(decision.get("strategy_id"))
    summary = decision.get("causal_state_snapshot", {}).get(
        "candidate_intent_summary", {})
    return _as_text(summary.get("strategy_id"))


def _decision_side(decision: dict[str, Any]) -> Optional[str]:
    if _as_text(decision.get("side")):
        return _as_text(decision.get("side"))
    summary = decision.get("causal_state_snapshot", {}).get(
        "candidate_intent_summary", {})
    return _as_text(summary.get("side"))


def _decision_qty(decision: dict[str, Any]) -> Optional[float]:
    summary = decision.get("causal_state_snapshot", {}).get(
        "candidate_intent_summary", {})
    return _parse_float(summary.get("quantity"))


def _decision_intent_ts_ms(decision: dict[str, Any]) -> Optional[int]:
    for key in ("request_ts_ms", "response_ts_ms"):
        try:
            value = safe_parse_int_ts(decision.get(key))
        except ValueError:
            value = None
        if value is not None:
            return value
    snapshot = decision.get("causal_state_snapshot", {})
    try:
        return safe_parse_int_ts(snapshot.get("decision_basis_ts_ms"))
    except ValueError:
        return None


def _decision_filter_ts_ms(decision: dict[str, Any]) -> Optional[int]:
    return _decision_intent_ts_ms(decision)


def _decision_outcome_status(decision: dict[str, Any]) -> Optional[str]:
    explicit_status = _as_text(decision.get("outcome_status"))
    if explicit_status:
        return explicit_status
    invalid_reason_code = _as_text(decision.get("invalid_reason_code"))
    terminal_status = _as_text(decision.get("terminal_status"))
    accepted_or_rejected = _as_text(decision.get("accepted_or_rejected"))
    if invalid_reason_code == "OUTCOME_UNRESOLVED":
        return "UNRESOLVED_ACCEPTED"
    if invalid_reason_code == "TERMINAL_EVENT_MISSING":
        return "UNRESOLVED_TIMEOUT"
    if terminal_status in {"EXECUTED_AND_CLOSED", "BASELINE_FALLBACK_EXECUTED"}:
        return "REALIZED"
    if terminal_status == "INVALID_FOR_DATASET" and accepted_or_rejected == "ACCEPTED":
        return "UNRESOLVED_ACCEPTED"
    if terminal_status:
        return "NOT_APPLICABLE"
    return None


def _decision_revision_status(decision: dict[str, Any]) -> Optional[str]:
    explicit_status = _as_text(decision.get("revision_status"))
    if explicit_status:
        return explicit_status
    outcome_status = _decision_outcome_status(decision)
    invalid_reason_code = _as_text(decision.get("invalid_reason_code"))
    if outcome_status == "UNRESOLVED_ACCEPTED":
        return "SEED_PENDING_OUTCOME"
    if invalid_reason_code == "TERMINAL_EVENT_MISSING":
        return "TIMEOUT_FINAL"
    if outcome_status == "REALIZED":
        return "OUTCOME_FINAL"
    if outcome_status == "NOT_APPLICABLE":
        return "DECISION_TERMINAL"
    return None


def _is_accepted_unresolved_decision(decision: dict[str, Any]) -> bool:
    return _decision_outcome_status(decision) == "UNRESOLVED_ACCEPTED"


def _build_accepted_unresolved_record(
    decision_record: SourceRecord,
) -> dict[str, Any]:
    decision = decision_record.data
    return {
        "reason": "ACCEPTED_UNRESOLVED",
        "decision_id": _as_text(decision.get("decision_id")),
        "rid": _as_text(decision.get("rid")),
        "lifecycle_id": _as_text(decision.get("lifecycle_id")),
        "terminal_status": _as_text(decision.get("terminal_status")),
        "outcome_status": _decision_outcome_status(decision),
        "revision_status": _decision_revision_status(decision),
        "accepted_or_rejected": _as_text(decision.get("accepted_or_rejected")),
        "dataset_visibility": _as_text(decision.get("dataset_visibility")),
        "invalid_reason_code": _as_text(decision.get("invalid_reason_code")),
        "realized_pnl_net": decision.get("realized_pnl_net"),
        "fees": decision.get("fees"),
        "close_reason": decision.get("close_reason"),
        "close_ts_ms": decision.get("close_ts_ms"),
        "source_path": decision_record.source_path,
        "line_number": decision_record.line_number,
    }


def _derive_outcome(close_row: dict[str, Any], gross_pnl: Optional[float], realized_pnl_net: Optional[float]) -> str:
    metric = realized_pnl_net if realized_pnl_net is not None else gross_pnl
    if metric is not None:
        if metric > 0:
            return "closed_win"
        if metric < 0:
            return "closed_loss"
        return "closed_flat"
    close_reason = _as_text(close_row.get("close_reason")
                            ) or _as_text(close_row.get("why"))
    if close_reason:
        return f"closed_{close_reason.lower()}"
    return "closed_unresolved"


def _close_join_candidates(raw_rid: Optional[str]) -> list[tuple[str, str]]:
    if not raw_rid:
        return []
    candidates: list[tuple[str, str]] = [(raw_rid, "exact_rid")]
    if ":" in raw_rid:
        prefix = raw_rid.split(":", 1)[0].strip()
        if prefix and prefix != raw_rid:
            candidates.append((prefix, "rid_suffix_trim"))
    return candidates


def _close_quality_score(candidate: dict[str, Any]) -> tuple[int, int, int, int]:
    row = candidate["record"].data
    has_realized = 1 if _parse_float(
        row.get("realized_pnl_net")) is not None else 0
    has_fees = 1 if _parse_float(row.get("fees")) is not None else 0
    resolved = 1 if _as_text(row.get("pnl_status")) == "resolved" else 0
    timestamp = safe_parse_int_ts(row.get("timestamp"))
    return (has_realized, has_fees, resolved, timestamp or -1)


def _select_canonical_close(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str], bool]:
    warnings: list[str] = []
    sorted_candidates = sorted(
        candidates,
        key=_close_quality_score,
        reverse=True,
    )
    selected = sorted_candidates[0]
    ambiguous = False
    if len(sorted_candidates) > 1:
        warnings.append(
            f"Duplicate close candidates for rid {selected['canonical_rid']}: {len(sorted_candidates)} rows"
        )
        top_score = _close_quality_score(sorted_candidates[0])
        second_score = _close_quality_score(sorted_candidates[1])
        if top_score[:-1] == second_score[:-1]:
            warnings.append(
                f"Latest timestamp selected for equally valid close candidates on rid {selected['canonical_rid']}"
            )
            if top_score[-1] == second_score[-1]:
                ambiguous = True
    return selected, warnings, ambiguous


def _sum_floats(values: list[Optional[float]]) -> Optional[float]:
    parsed = [value for value in values if value is not None]
    if not parsed:
        return None
    return float(sum(parsed))


def _coverage_pct(count: int, total: int) -> Optional[float]:
    if total <= 0:
        return None
    return round((count / total) * 100.0, 4)


def _event_type(row: dict[str, Any]) -> str:
    return (
        _as_text(row.get("event_type"))
        or _as_text(row.get("status"))
        or _as_text(row.get("event"))
        or "UNKNOWN"
    )


def _order_log_is_close_fill(row: dict[str, Any]) -> bool:
    if _event_type(row) != ORDER_LOG_FILL_EVENT:
        return False
    order_kind = (_as_text(row.get("order_kind")) or "").upper()
    close_reason = _as_text(row.get("close_reason"))
    return order_kind in {"CLOSE", "EXIT", "TP", "SL"} or close_reason is not None


def _order_log_is_close_submitted(row: dict[str, Any]) -> bool:
    event_type = _event_type(row)
    if event_type not in {"ORDER_INTENT", "ORDER_PLACED"}:
        return False
    order_kind = (_as_text(row.get("order_kind")) or "").upper()
    close_reason = _as_text(row.get("close_reason"))
    rid = _as_text(row.get("rid")) or ""
    return order_kind in {"CLOSE", "EXIT", "TP", "SL"} or close_reason is not None or rid.startswith("ppsreq:")


def _trade_lifecycle_is_fill(row: dict[str, Any]) -> bool:
    event_type = _event_type(row)
    trigger_event = (_as_text(row.get("trigger_event")) or "").upper()
    return event_type in {"EXECUTION_FILL_INGRESS", "TRADE_EXECUTED"} or trigger_event == "TRADE_EXECUTED"


def _trade_lifecycle_is_close(row: dict[str, Any]) -> bool:
    event_type = _event_type(row)
    status = (_as_text(row.get("status")) or "").upper()
    close_reason = _as_text(row.get("close_reason"))
    return bool(
        event_type == ORDER_LOG_CLOSE_EVENT
        or "CLOSE" in event_type
        or status in {"CLOSED", "EXECUTED_AND_CLOSED", "COMPLETED"}
        or row.get("close_ts_ms") not in (None, "")
        or (close_reason is not None and status not in REJECT_TERMINAL_STATUSES)
    )


def _dedupe_source_records(records: list[SourceRecord]) -> list[SourceRecord]:
    deduped: list[SourceRecord] = []
    seen: set[tuple[str, int]] = set()
    for record in records:
        key = (record.source_path, record.line_number)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _index_record(
    index: dict[str, list[SourceRecord]],
    key: Optional[str],
    record: SourceRecord,
) -> None:
    if key:
        index.setdefault(key, []).append(record)


def _collect_runtime_evidence_for_decision(
    decision_record: SourceRecord,
    *,
    order_records_by_rid: dict[str, list[SourceRecord]],
    order_records_by_lifecycle: dict[str, list[SourceRecord]],
    order_records_by_trade: dict[str, list[SourceRecord]],
    trade_records_by_rid: dict[str, list[SourceRecord]],
    trade_records_by_lifecycle: dict[str, list[SourceRecord]],
    trade_records_by_trade: dict[str, list[SourceRecord]],
    entry_fills_by_key: dict[str, list[SourceRecord]],
    close_candidates: list[dict[str, Any]],
) -> DecisionRuntimeEvidence:
    decision = decision_record.data
    rid = _as_text(decision.get("rid")) or ""
    lifecycle_id = _as_text(decision.get("lifecycle_id"))
    trade_id = _as_text(decision.get("trade_id"))

    order_rows = list(order_records_by_rid.get(rid, []))
    if lifecycle_id:
        order_rows.extend(order_records_by_lifecycle.get(lifecycle_id, []))
    if trade_id:
        order_rows.extend(order_records_by_trade.get(trade_id, []))
    order_rows = _dedupe_source_records(order_rows)

    trade_rows = list(trade_records_by_rid.get(rid, []))
    if lifecycle_id:
        trade_rows.extend(trade_records_by_lifecycle.get(lifecycle_id, []))
    if trade_id:
        trade_rows.extend(trade_records_by_trade.get(trade_id, []))
    trade_rows = _dedupe_source_records(trade_rows)

    entry_candidates = entry_fills_by_key.get(rid, [])
    if not entry_candidates and lifecycle_id:
        entry_candidates = entry_fills_by_key.get(lifecycle_id, [])

    has_entry_fill = bool(entry_candidates) or any(
        _trade_lifecycle_is_fill(record.data) for record in trade_rows
    )
    has_close_candidate = bool(close_candidates)
    has_close_fill = any(_order_log_is_close_fill(record.data)
                         for record in order_rows)
    has_close_submission = any(
        _order_log_is_close_submitted(record.data) for record in order_rows
    )
    has_terminal_close = any(
        _trade_lifecycle_is_close(record.data) for record in trade_rows
    )
    has_execution_evidence = bool(
        has_entry_fill
        or has_close_candidate
        or has_close_fill
        or has_close_submission
        or has_terminal_close
    )

    terminal_status = (_as_text(decision.get("terminal_status")) or "").upper()
    has_reject_signal = bool(
        terminal_status in REJECT_TERMINAL_STATUSES
        or any(_event_type(record.data) in ALTERNATIVE_TERMINAL_EVENTS for record in order_rows)
        or any(((_as_text(record.data.get("status")) or "").upper() in REJECT_TERMINAL_STATUSES) for record in trade_rows)
    )

    return DecisionRuntimeEvidence(
        rejected_or_not_executed=bool(
            has_reject_signal and not has_execution_evidence),
        has_entry_fill=has_entry_fill,
        has_close_candidate=has_close_candidate,
        has_close_fill=has_close_fill,
        has_close_submission=has_close_submission,
        has_terminal_close=has_terminal_close,
    )


def _build_denominator_coverage_stats(
    runtime_evidence_by_rid: dict[str, DecisionRuntimeEvidence],
) -> DenominatorCoverageStats:
    total_decision_rows = len(runtime_evidence_by_rid)
    rejected_or_not_executed_rows = 0
    execution_eligible_rows = 0
    entry_filled_rows = 0
    close_expected_rows = 0

    for evidence in runtime_evidence_by_rid.values():
        if evidence.rejected_or_not_executed:
            rejected_or_not_executed_rows += 1
        else:
            execution_eligible_rows += 1
        if evidence.has_entry_fill:
            entry_filled_rows += 1
        if not evidence.rejected_or_not_executed and (
            evidence.has_entry_fill
            or evidence.has_close_candidate
            or evidence.has_close_fill
            or evidence.has_close_submission
            or evidence.has_terminal_close
        ):
            close_expected_rows += 1

    return DenominatorCoverageStats(
        total_decision_rows=total_decision_rows,
        rejected_or_not_executed_rows=rejected_or_not_executed_rows,
        execution_eligible_rows=execution_eligible_rows,
        entry_filled_rows=entry_filled_rows,
        close_expected_rows=close_expected_rows,
    )


def _aggregate_entry_fills(candidates: list[SourceRecord]) -> Optional[dict[str, Any]]:
    if not candidates:
        return None
    timestamps: list[int] = []
    weighted_numerator = 0.0
    weighted_denominator = 0.0
    qty_values: list[Optional[float]] = []
    commission_values: list[Optional[float]] = []
    for candidate in candidates:
        row = candidate.data
        timestamp = safe_parse_int_ts(row.get("timestamp"))
        if timestamp is not None:
            timestamps.append(timestamp)
        qty = _parse_float(row.get("quantity"))
        price = _parse_float(row.get("price"))
        qty_values.append(qty)
        commission_values.append(_parse_float(
            row.get("metadata", {}).get("commission")))
        if qty is not None and price is not None:
            weighted_numerator += qty * price
            weighted_denominator += qty
    total_qty = _sum_floats(qty_values)
    return {
        "entry_ts_ms": min(timestamps) if timestamps else None,
        "qty": total_qty,
        "entry_price": (weighted_numerator / weighted_denominator) if weighted_denominator > 0 else None,
        "entry_fill_count": len(candidates),
        "entry_commission_total": _sum_floats(commission_values),
    }


def _build_data_quality_summary(
    rows: list[dict[str, Any]],
    blockers: list[str],
    warnings: list[str],
    *,
    valid_rows: int,
    invalid_rows: int,
    denominator_stats: DenominatorCoverageStats,
    accepted_unresolved_rows_count: int,
    exact_identity_join_count: int,
    duplicate_close_candidates: int,
    blocker_duplicate_ambiguity_count: int,
) -> dict[str, Any]:
    has_realized_outcomes = any(
        row.get("realized_pnl_net") is not None or row.get(
            "gross_pnl") is not None
        for row in rows
    )
    exact_roundtrip_count = sum(
        1 for row in rows if row.get("exact_roundtrip"))
    promotion_blockers = list(blockers)
    if not has_realized_outcomes:
        promotion_blockers.append("NO_REALIZED_OUTCOMES")
    if exact_roundtrip_count == 0:
        promotion_blockers.append("NO_EXACT_ROUNDTRIPS")
    if rows and exact_roundtrip_count < len(rows):
        promotion_blockers.append("PARTIAL_EXACT_ROUNDTRIPS")
    if blocker_duplicate_ambiguity_count > 0:
        promotion_blockers.append("DUPLICATE_CLOSE_AMBIGUITY")
    source_path_blocker = any(
        not {"decision_ledger_v1.jsonl", "order_log_v1.jsonl"}.issubset(
            {Path(path).name for path in row.get("source_paths", [])}
        )
        for row in rows
    )
    if source_path_blocker:
        promotion_blockers.append("MISSING_REQUIRED_SOURCE_PATHS")

    summary = compute_basic_data_quality_summary(
        rows,
        promotion_blockers,
        warnings,
        rows_valid=valid_rows,
        rows_invalid=invalid_rows,
        has_realized_outcomes=has_realized_outcomes,
        exact_roundtrip_count=exact_roundtrip_count,
        empty_dataset_blocker="EMPTY_REALIZED_OUTCOME_DATASET",
        eligible_input_rows=denominator_stats.close_expected_rows,
        matched_rows=len(rows),
        unmatched_rows=max(
            denominator_stats.close_expected_rows - len(rows), 0),
        min_required_rows=DEFAULT_PROMOTION_MIN_REQUIRED_ROWS,
        min_required_coverage_pct=DEFAULT_PROMOTION_MIN_REQUIRED_COVERAGE_PCT,
        coverage_row_blocker="INSUFFICIENT_REALIZED_ROWS",
        coverage_pct_blocker="INSUFFICIENT_REALIZED_COVERAGE",
    )
    close_matched_rows = len(rows)
    summary.update(
        {
            "rows_emitted": len(rows),
            "coverage_denominator_kind": "close_expected_rows",
            "coverage_denominator_rows": denominator_stats.close_expected_rows,
            "total_decision_rows": denominator_stats.total_decision_rows,
            "rejected_or_not_executed_rows": denominator_stats.rejected_or_not_executed_rows,
            "execution_eligible_rows": denominator_stats.execution_eligible_rows,
            "entry_filled_rows": denominator_stats.entry_filled_rows,
            "close_expected_rows": denominator_stats.close_expected_rows,
            "close_matched_rows": close_matched_rows,
            "exact_roundtrip_rows": exact_roundtrip_count,
            "decision_to_execution_rate": _coverage_pct(
                denominator_stats.entry_filled_rows,
                denominator_stats.total_decision_rows,
            ),
            "execution_to_close_coverage_pct": _coverage_pct(
                close_matched_rows,
                denominator_stats.close_expected_rows,
            ),
            "close_to_exact_roundtrip_pct": _coverage_pct(
                exact_roundtrip_count,
                close_matched_rows,
            ),
            "total_decision_to_exact_roundtrip_pct": _coverage_pct(
                exact_roundtrip_count,
                denominator_stats.total_decision_rows,
            ),
            "accepted_unresolved_rows": accepted_unresolved_rows_count,
            "has_realized_outcomes": has_realized_outcomes,
            "exact_identity_join_count": exact_identity_join_count,
            "duplicate_close_candidates": duplicate_close_candidates,
            "blocker_duplicate_ambiguity_count": blocker_duplicate_ambiguity_count,
        }
    )
    summary["diagnostics_only"] = bool(
        summary.get("diagnostics_only")
        or exact_roundtrip_count < len(rows)
        or blocker_duplicate_ambiguity_count > 0
    )
    if summary["diagnostics_only"]:
        summary["promotion_grade"] = False
    return summary


def _generate_quality_report(
    summary: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
    *,
    source_snapshot_manifest: dict[str, Any] | None = None,
    source_snapshot_manifest_path: str | None = None,
) -> str:
    snapshot_missing = []
    snapshot_warnings = []
    if source_snapshot_manifest is not None:
        snapshot_missing = list(source_snapshot_manifest.get(
            "missing_required_sources", []))
        snapshot_warnings = list(source_snapshot_manifest.get("warnings", []))
    lines = [
        "# DATA_QUALITY_REPORT",
        "",
        "## Summary",
        f"- builder_valid: {summary.get('builder_valid')}",
        f"- schema_valid: {summary.get('schema_valid')}",
        f"- has_rows: {summary.get('has_rows')}",
        f"- rows_emitted: {summary.get('rows_emitted')}",
        f"- rows_valid: {summary.get('rows_valid')}",
        f"- rows_invalid: {summary.get('rows_invalid')}",
        f"- coverage_denominator_kind: {summary.get('coverage_denominator_kind')}",
        f"- coverage_denominator_rows: {summary.get('coverage_denominator_rows')}",
        f"- total_decision_rows: {summary.get('total_decision_rows')}",
        f"- rejected_or_not_executed_rows: {summary.get('rejected_or_not_executed_rows')}",
        f"- execution_eligible_rows: {summary.get('execution_eligible_rows')}",
        f"- entry_filled_rows: {summary.get('entry_filled_rows')}",
        f"- close_expected_rows: {summary.get('close_expected_rows')}",
        f"- close_matched_rows: {summary.get('close_matched_rows')}",
        f"- exact_roundtrip_rows: {summary.get('exact_roundtrip_rows')}",
        f"- decision_to_execution_rate: {summary.get('decision_to_execution_rate')}",
        f"- execution_to_close_coverage_pct: {summary.get('execution_to_close_coverage_pct')}",
        f"- close_to_exact_roundtrip_pct: {summary.get('close_to_exact_roundtrip_pct')}",
        f"- total_decision_to_exact_roundtrip_pct: {summary.get('total_decision_to_exact_roundtrip_pct')}",
        f"- eligible_input_rows: {summary.get('eligible_input_rows')}",
        f"- matched_rows: {summary.get('matched_rows')}",
        f"- unmatched_rows: {summary.get('unmatched_rows')}",
        f"- accepted_unresolved_rows: {summary.get('accepted_unresolved_rows')}",
        f"- match_coverage_pct: {summary.get('match_coverage_pct')}",
        f"- has_realized_outcomes: {summary.get('has_realized_outcomes')}",
        f"- exact_roundtrip_count: {summary.get('exact_roundtrip_count')}",
        f"- exact_roundtrip_coverage_pct: {summary.get('exact_roundtrip_coverage_pct')}",
        f"- min_required_rows: {summary.get('min_required_rows')}",
        f"- min_required_coverage_pct: {summary.get('min_required_coverage_pct')}",
        f"- coverage_grade: {summary.get('coverage_grade')}",
        f"- diagnostics_only: {summary.get('diagnostics_only')}",
        f"- promotion_grade: {summary.get('promotion_grade')}",
        f"- source_snapshot_manifest: {source_snapshot_manifest_path or 'none'}",
        f"- source_snapshot_missing_required_sources: {', '.join(snapshot_missing) or 'none'}",
        "",
        "## Source Snapshot",
        f"- snapshot_recorded: {source_snapshot_manifest is not None}",
        f"- snapshot_manifest_path: {source_snapshot_manifest_path or 'none'}",
        f"- missing_required_sources: {', '.join(snapshot_missing) or 'none'}",
        "",
        "### Snapshot Warnings",
    ]
    if snapshot_warnings:
        for warning in snapshot_warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Promotion Blockers",
    ])
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings"])
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")
    return "\n".join(lines)


def _generate_canonicalization_report_md(report: dict[str, Any]) -> str:
    lines = [
        "# CANONICALIZATION_REPORT",
        "",
        "## Summary",
        f"- close_rows_total: {report.get('close_rows_total', 0)}",
        f"- eligible_close_rows: {report.get('eligible_close_rows', 0)}",
        f"- exact_rid_matches: {report.get('exact_rid_matches', 0)}",
        f"- suffix_trim_matches: {report.get('suffix_trim_matches', 0)}",
        f"- duplicate_close_candidates: {report.get('duplicate_close_candidates', 0)}",
        f"- blocker_duplicate_ambiguity_count: {report.get('blocker_duplicate_ambiguity_count', 0)}",
        "",
        "## Rules",
    ]
    for rule in report.get("canonicalization_rules", []):
        lines.append(f"- {rule}")
    if report.get("duplicate_groups"):
        lines.extend(["", "## Duplicate Groups"])
        for group in report["duplicate_groups"][:20]:
            lines.append(
                f"- rid={group['rid']} candidate_count={group['candidate_count']} selected_join_kind={group['selected_join_kind']} ambiguous={group['ambiguous']}"
            )
    return "\n".join(lines)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def _generate_denominator_audit_report_md(payload: dict[str, Any]) -> str:
    rows = [
        ["total_decision_rows", payload.get("total_decision_rows")],
        ["rejected_or_not_executed_rows", payload.get(
            "rejected_or_not_executed_rows")],
        ["execution_eligible_rows", payload.get("execution_eligible_rows")],
        ["entry_filled_rows", payload.get("entry_filled_rows")],
        ["close_expected_rows", payload.get("close_expected_rows")],
        ["close_matched_rows", payload.get("close_matched_rows")],
        ["exact_roundtrip_rows", payload.get("exact_roundtrip_rows")],
        ["decision_to_execution_rate", payload.get(
            "decision_to_execution_rate")],
        ["execution_to_close_coverage_pct", payload.get(
            "execution_to_close_coverage_pct")],
        ["close_to_exact_roundtrip_pct", payload.get(
            "close_to_exact_roundtrip_pct")],
        ["total_decision_to_exact_roundtrip_pct", payload.get(
            "total_decision_to_exact_roundtrip_pct")],
        ["legacy_total_decision_close_coverage_pct", payload.get(
            "legacy_total_decision_close_coverage_pct")],
    ]
    return "\n".join(
        [
            "# DENOMINATOR_AUDIT",
            "",
            f"Generated at UTC: {payload.get('generated_at_utc')}",
            f"Coverage denominator kind: {payload.get('coverage_denominator_kind')}",
            "",
            _markdown_table(["metric", "value"], rows),
            "",
        ]
    )


def build_realized_outcome_dataset(
    *,
    out_dir: Optional[str | Path] = None,
    repo_root: Optional[str | Path] = None,
    decision_ledger: Optional[str | Path] = None,
    order_log: Optional[str | Path] = None,
    trade_lifecycle: Optional[str | Path] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    strict: bool = False,
    max_rows: Optional[int] = None,
    include_diagnostics: bool = True,
    snapshot_sources: bool = True,
) -> BuilderResult:
    if repo_root is None:
        repo_root = Path.cwd()
    else:
        repo_root = Path(repo_root)

    decision_path = Path(decision_ledger) if decision_ledger else repo_root / \
        "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl"
    order_log_path = Path(
        order_log) if order_log else repo_root / "logs" / "order_log_v1.jsonl"
    trade_lifecycle_path = Path(
        trade_lifecycle) if trade_lifecycle else repo_root / "logs" / "trade_lifecycle.jsonl"

    source_snapshot_manifest: dict[str, Any] | None = None
    source_snapshot_manifest_path: str | None = None
    if out_dir is not None and snapshot_sources:
        source_snapshot_manifest = build_source_snapshot(
            [
                SnapshotSourceSpec(
                    role="decision_ledger",
                    source_path=decision_path,
                    source_kind=_classify_source_kind(
                        decision_path, repo_root, EXPECTED_DECISION_LEDGER),
                    required=True,
                    notes=_source_snapshot_note(decision_ledger is not None),
                ),
                SnapshotSourceSpec(
                    role="order_log",
                    source_path=order_log_path,
                    source_kind=_classify_source_kind(
                        order_log_path, repo_root, EXPECTED_ORDER_LOG),
                    required=True,
                    notes=_source_snapshot_note(order_log is not None),
                ),
                SnapshotSourceSpec(
                    role="trade_lifecycle",
                    source_path=trade_lifecycle_path,
                    source_kind=_classify_source_kind(
                        trade_lifecycle_path, repo_root, EXPECTED_TRADE_LIFECYCLE),
                    required=False,
                    notes=_source_snapshot_note(trade_lifecycle is not None),
                ),
            ],
            out_dir,
            "realized_outcome_builder",
            strict=strict,
            repo_root=repo_root,
        )
        source_snapshot_manifest_path = "source_snapshot/source_snapshot_manifest.json"

    blockers: list[str] = []
    warnings: list[str] = []
    rejected_rows: list[dict[str, Any]] = []
    accepted_unresolved_rows: list[dict[str, Any]] = []
    realized_rows: list[dict[str, Any]] = []

    date_start_value = _parse_date(date_start)
    date_end_value = _parse_date(date_end)

    decision_records: list[SourceRecord] = []
    order_log_records: list[SourceRecord] = []
    trade_lifecycle_records: list[SourceRecord] = []
    decision_errors: list[str] = []
    order_log_errors: list[str] = []
    trade_lifecycle_errors: list[str] = []

    if decision_path.exists():
        decision_records, decision_errors = _read_jsonl_records(decision_path)
    else:
        blockers.append(f"MISSING_DECISION_LEDGER:{decision_path.as_posix()}")

    if order_log_path.exists():
        order_log_records, order_log_errors = _read_jsonl_records(
            order_log_path)
    else:
        blockers.append(f"MISSING_ORDER_LOG:{order_log_path.as_posix()}")

    if trade_lifecycle_path.exists():
        trade_lifecycle_records, trade_lifecycle_errors = _read_jsonl_records(
            trade_lifecycle_path)
    else:
        warnings.append(
            f"OPTIONAL_TRADE_LIFECYCLE_MISSING:{trade_lifecycle_path.as_posix()}")

    if decision_errors:
        warnings.append(f"DECISION_LEDGER_JSON_ERRORS:{len(decision_errors)}")
    if order_log_errors:
        warnings.append(f"ORDER_LOG_JSON_ERRORS:{len(order_log_errors)}")
    if trade_lifecycle_errors:
        warnings.append(
            f"TRADE_LIFECYCLE_JSON_ERRORS:{len(trade_lifecycle_errors)}")
    if strict and blockers:
        raise FileNotFoundError("; ".join(blockers))

    decisions_by_rid: dict[str, SourceRecord] = {}
    duplicate_decision_rids = 0
    eligible_decision_rows = 0
    for record in decision_records:
        row = record.data
        decision_ts_ms = _decision_filter_ts_ms(row)
        if not _within_date_range(decision_ts_ms, date_start_value, date_end_value):
            continue
        rid = _as_text(row.get("rid"))
        decision_id = _as_text(row.get("decision_id"))
        if not rid:
            rejected_rows.append(
                {
                    "reason": "MISSING_DECISION_RID",
                    "decision_id": decision_id,
                    "source_path": record.source_path,
                    "line_number": record.line_number,
                }
            )
            warnings.append(
                f"Decision row missing rid at {record.source_path}:{record.line_number}"
            )
            continue
        eligible_decision_rows += 1
        existing = decisions_by_rid.get(rid)
        if existing is not None:
            duplicate_decision_rids += 1
            warnings.append(f"Duplicate decision rid encountered: {rid}")
            existing_ts = _decision_filter_ts_ms(existing.data) or -1
            current_ts = decision_ts_ms or -1
            if current_ts < existing_ts:
                continue
            if current_ts == existing_ts and record.line_number <= existing.line_number:
                continue
        decisions_by_rid[rid] = record

    if max_rows is not None and max_rows >= 0:
        decisions_by_rid = dict(list(decisions_by_rid.items())[:max_rows])

    eligible_decision_rows = len(decisions_by_rid)

    entry_fills_by_key: dict[str, list[SourceRecord]] = {}
    close_candidates_by_rid: dict[str, list[dict[str, Any]]] = {}
    order_records_by_rid: dict[str, list[SourceRecord]] = {}
    order_records_by_lifecycle: dict[str, list[SourceRecord]] = {}
    order_records_by_trade: dict[str, list[SourceRecord]] = {}
    close_rows_total = 0
    exact_rid_matches = 0
    suffix_trim_matches = 0
    eligible_close_rows = 0
    for record in order_log_records:
        row = record.data
        _index_record(order_records_by_rid, _as_text(row.get("rid")), record)
        _index_record(order_records_by_lifecycle, _as_text(
            row.get("lifecycle_id")), record)
        _index_record(order_records_by_trade, _as_text(
            row.get("trade_id")), record)
        event_type = _as_text(row.get("event_type"))
        if event_type == ORDER_LOG_FILL_EVENT and _as_text(row.get("order_kind")) == ORDER_LOG_ENTRY_KIND:
            for key in (_as_text(row.get("lifecycle_id")), _as_text(row.get("rid"))):
                if not key:
                    continue
                entry_fills_by_key.setdefault(key, []).append(record)
            continue
        if event_type != ORDER_LOG_CLOSE_EVENT:
            continue

        close_rows_total += 1
        raw_rid = _as_text(row.get("rid"))
        matched_rid = None
        join_kind = None
        for candidate_rid, candidate_kind in _close_join_candidates(raw_rid):
            if candidate_rid in decisions_by_rid:
                matched_rid = candidate_rid
                join_kind = candidate_kind
                break
        if matched_rid is None:
            continue
        eligible_close_rows += 1
        if join_kind == "exact_rid":
            exact_rid_matches += 1
        elif join_kind == "rid_suffix_trim":
            suffix_trim_matches += 1
        close_candidates_by_rid.setdefault(matched_rid, []).append(
            {
                "canonical_rid": matched_rid,
                "join_kind": join_kind,
                "record": record,
            }
        )

    trade_records_by_rid: dict[str, list[SourceRecord]] = {}
    trade_records_by_lifecycle: dict[str, list[SourceRecord]] = {}
    trade_records_by_trade: dict[str, list[SourceRecord]] = {}
    for record in trade_lifecycle_records:
        row = record.data
        _index_record(trade_records_by_rid, _as_text(row.get("rid")), record)
        _index_record(trade_records_by_lifecycle, _as_text(
            row.get("lifecycle_id")), record)
        _index_record(trade_records_by_trade, _as_text(
            row.get("trade_id")), record)

    runtime_evidence_by_rid = {
        rid: _collect_runtime_evidence_for_decision(
            decision_record,
            order_records_by_rid=order_records_by_rid,
            order_records_by_lifecycle=order_records_by_lifecycle,
            order_records_by_trade=order_records_by_trade,
            trade_records_by_rid=trade_records_by_rid,
            trade_records_by_lifecycle=trade_records_by_lifecycle,
            trade_records_by_trade=trade_records_by_trade,
            entry_fills_by_key=entry_fills_by_key,
            close_candidates=close_candidates_by_rid.get(rid, []),
        )
        for rid, decision_record in decisions_by_rid.items()
    }
    denominator_stats = _build_denominator_coverage_stats(
        runtime_evidence_by_rid)

    duplicate_close_candidates = 0
    blocker_duplicate_ambiguity_count = 0
    duplicate_groups: list[dict[str, Any]] = []
    exact_identity_join_count = 0

    for rid, decision_record in decisions_by_rid.items():
        decision = decision_record.data
        if _is_accepted_unresolved_decision(decision):
            accepted_unresolved_rows.append(
                _build_accepted_unresolved_record(decision_record)
            )
            continue
        candidates = close_candidates_by_rid.get(rid, [])
        if not candidates:
            rejected_rows.append(
                {
                    "reason": "NO_MATCHING_CLOSE_EVENT",
                    "decision_id": _as_text(decision.get("decision_id")),
                    "rid": rid,
                    "source_path": decision_record.source_path,
                    "line_number": decision_record.line_number,
                }
            )
            continue

        selected_close, selection_warnings, ambiguous = _select_canonical_close(
            candidates)
        warnings.extend(selection_warnings)
        duplicate_count = max(len(candidates) - 1, 0)
        duplicate_close_candidates += duplicate_count
        if duplicate_count > 0:
            duplicate_groups.append(
                {
                    "rid": rid,
                    "candidate_count": len(candidates),
                    "selected_join_kind": selected_close["join_kind"],
                    "ambiguous": ambiguous,
                }
            )
        if ambiguous:
            blocker_duplicate_ambiguity_count += 1
            rejected_rows.append(
                {
                    "reason": "DUPLICATE_CLOSE_AMBIGUITY",
                    "decision_id": _as_text(decision.get("decision_id")),
                    "rid": rid,
                    "candidate_count": len(candidates),
                }
            )
            continue

        close_row = selected_close["record"].data
        entry_candidates = entry_fills_by_key.get(rid, [])
        decision_lifecycle_id = _as_text(decision.get("lifecycle_id"))
        if not entry_candidates and decision_lifecycle_id:
            entry_candidates = entry_fills_by_key.get(
                decision_lifecycle_id, [])
        entry_info = _aggregate_entry_fills(entry_candidates)

        gross_pnl = _parse_float(close_row.get(
            "metadata", {}).get("realized_pnl"))
        realized_pnl_net = _parse_float(close_row.get("realized_pnl_net"))
        fees = _parse_float(close_row.get("fees"))
        entry_ts_ms = entry_info.get("entry_ts_ms") if entry_info else None
        exit_ts_ms = safe_parse_int_ts(close_row.get("timestamp"))
        exact_roundtrip = bool(
            entry_ts_ms is not None and exit_ts_ms is not None)

        strategy_id = _decision_strategy_id(decision)
        side_raw = _decision_side(decision) or _as_text(close_row.get("side"))
        if not side_raw:
            rejected_rows.append(
                {
                    "reason": "MISSING_SIDE",
                    "decision_id": _as_text(decision.get("decision_id")),
                    "rid": rid,
                }
            )
            continue
        try:
            symbol = normalize_symbol(_as_text(decision.get(
                "symbol")) or _as_text(close_row.get("symbol")) or "")
            side = normalize_side(side_raw)
        except ValueError as exc:
            rejected_rows.append(
                {
                    "reason": f"NORMALIZATION_ERROR:{exc}",
                    "decision_id": _as_text(decision.get("decision_id")),
                    "rid": rid,
                }
            )
            continue

        row = {
            "dataset_schema": DATASET_SCHEMA_ID,
            "dataset_version": DATASET_VERSION,
            "attempt_id": _as_text(decision.get("attempt_id")),
            "decision_id": _as_text(decision.get("decision_id")),
            "rid": rid,
            "lifecycle_id": _as_text(decision.get("lifecycle_id")) or _as_text(close_row.get("lifecycle_id")),
            "symbol": symbol,
            "strategy_id": strategy_id,
            "side": side,
            "intent_ts_ms": _decision_intent_ts_ms(decision),
            "entry_ts_ms": entry_ts_ms,
            "exit_ts_ms": exit_ts_ms,
            "entry_price": entry_info.get("entry_price") if entry_info else None,
            "exit_price": _parse_float(close_row.get("metadata", {}).get("close_price")),
            "qty": (entry_info.get("qty") if entry_info else None) or _decision_qty(decision),
            "outcome": _derive_outcome(close_row, gross_pnl, realized_pnl_net),
            "gross_pnl": gross_pnl,
            "realized_pnl_net": realized_pnl_net,
            "fees": fees,
            "commission": fees,
            "mfe": None,
            "mae": None,
            "bars_held": None,
            "exact_roundtrip": exact_roundtrip,
            "terminal_status": _as_text(decision.get("terminal_status")) or _as_text(close_row.get("pnl_status")),
            "source_paths": source_paths_for(decision_record.source_path, selected_close["record"].source_path),
            "synthetic": False,
        }

        try:
            validate_row(DATASET_SCHEMA_ID, row)
        except Exception as exc:
            rejected_rows.append(
                {
                    "reason": f"SCHEMA_VALIDATION_ERROR:{exc}",
                    "decision_id": _as_text(decision.get("decision_id")),
                    "rid": rid,
                }
            )
            continue

        if not include_diagnostics and not exact_roundtrip:
            rejected_rows.append(
                {
                    "reason": "DIAGNOSTIC_ONLY_ROW_EXCLUDED",
                    "decision_id": _as_text(decision.get("decision_id")),
                    "rid": rid,
                }
            )
            continue

        realized_rows.append(row)
        exact_identity_join_count += 1

    valid_rows, invalid_rows, row_errors = validate_and_count(
        DATASET_SCHEMA_ID, realized_rows)
    if invalid_rows > 0:
        blockers.append(f"INVALID_REALIZED_ROWS:{invalid_rows}")
        warnings.extend(row_errors[:10])

    summary = _build_data_quality_summary(
        realized_rows,
        blockers,
        warnings,
        valid_rows=valid_rows,
        invalid_rows=invalid_rows,
        denominator_stats=denominator_stats,
        accepted_unresolved_rows_count=len(accepted_unresolved_rows),
        exact_identity_join_count=exact_identity_join_count,
        duplicate_close_candidates=duplicate_close_candidates,
        blocker_duplicate_ambiguity_count=blocker_duplicate_ambiguity_count,
    )
    blockers = list(summary["promotion_blockers"])
    warnings = list(summary["warnings"])

    canonicalization_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "close_rows_total": close_rows_total,
        "eligible_close_rows": eligible_close_rows,
        "exact_rid_matches": exact_rid_matches,
        "suffix_trim_matches": suffix_trim_matches,
        "duplicate_close_candidates": duplicate_close_candidates,
        "blocker_duplicate_ambiguity_count": blocker_duplicate_ambiguity_count,
        "duplicate_groups": duplicate_groups,
        "canonicalization_rules": [
            "Primary exact join key is decision_ledger rid to order_log POSITION_CLOSED rid.",
            "Close-event canonicalization allows a single trailing suffix trim at ':' for close rid values such as rid:TP.",
            "Only POSITION_CLOSED rows are eligible realized close evidence in v1.",
            "Duplicate close rows prefer realized_pnl_net + fees completeness, then resolved pnl_status, then latest timestamp.",
            "Duplicate close rows are never summed in v1.",
            "Entry enrichment uses exact ORDER_FILLED ENTRY rows keyed by decision rid through lifecycle_id or exact rid; missing entry data leaves exact_roundtrip false.",
        ],
    }

    denominator_audit = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "coverage_denominator_kind": "close_expected_rows",
        "total_decision_rows": denominator_stats.total_decision_rows,
        "rejected_or_not_executed_rows": denominator_stats.rejected_or_not_executed_rows,
        "execution_eligible_rows": denominator_stats.execution_eligible_rows,
        "entry_filled_rows": denominator_stats.entry_filled_rows,
        "close_expected_rows": denominator_stats.close_expected_rows,
        "close_matched_rows": summary.get("close_matched_rows"),
        "exact_roundtrip_rows": summary.get("exact_roundtrip_rows"),
        "decision_to_execution_rate": summary.get("decision_to_execution_rate"),
        "execution_to_close_coverage_pct": summary.get("execution_to_close_coverage_pct"),
        "close_to_exact_roundtrip_pct": summary.get("close_to_exact_roundtrip_pct"),
        "total_decision_to_exact_roundtrip_pct": summary.get("total_decision_to_exact_roundtrip_pct"),
        "legacy_total_decision_close_coverage_pct": _coverage_pct(
            summary.get("close_matched_rows") or 0,
            denominator_stats.total_decision_rows,
        ),
    }

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "builder": "realized_outcome_builder",
        "dataset_schema": DATASET_SCHEMA_ID,
        "dataset_version": DATASET_VERSION,
        "source_files": {
            "decision_ledger": decision_path.as_posix(),
            "order_log": order_log_path.as_posix(),
            "trade_lifecycle": trade_lifecycle_path.as_posix() if trade_lifecycle_path.exists() else None,
        },
        "source_row_counts": {
            "decision_ledger": len(decision_records),
            "order_log": len(order_log_records),
            "trade_lifecycle": len(trade_lifecycle_records),
        },
        "total_decision_rows": summary.get("total_decision_rows"),
        "rejected_or_not_executed_rows": summary.get("rejected_or_not_executed_rows"),
        "execution_eligible_rows": summary.get("execution_eligible_rows"),
        "entry_filled_rows": summary.get("entry_filled_rows"),
        "close_expected_rows": summary.get("close_expected_rows"),
        "close_matched_rows": summary.get("close_matched_rows"),
        "exact_roundtrip_rows": summary.get("exact_roundtrip_rows"),
        "decision_to_execution_rate": summary.get("decision_to_execution_rate"),
        "execution_to_close_coverage_pct": summary.get("execution_to_close_coverage_pct"),
        "close_to_exact_roundtrip_pct": summary.get("close_to_exact_roundtrip_pct"),
        "total_decision_to_exact_roundtrip_pct": summary.get("total_decision_to_exact_roundtrip_pct"),
        "coverage_denominator_kind": summary.get("coverage_denominator_kind"),
        "coverage_denominator_rows": summary.get("coverage_denominator_rows"),
        "eligible_decision_rows": eligible_decision_rows,
        "eligible_close_rows": eligible_close_rows,
        "exact_rid_matches": exact_rid_matches,
        "emitted_realized_rows": len(realized_rows),
        "accepted_unresolved_rows": len(accepted_unresolved_rows),
        "matched_rows": summary.get("matched_rows"),
        "unmatched_rows": summary.get("unmatched_rows"),
        "match_coverage_pct": summary.get("match_coverage_pct"),
        "exact_roundtrip_count": summary.get("exact_roundtrip_count"),
        "exact_roundtrip_coverage_pct": summary.get("exact_roundtrip_coverage_pct"),
        "min_required_rows": summary.get("min_required_rows"),
        "min_required_coverage_pct": summary.get("min_required_coverage_pct"),
        "coverage_grade": summary.get("coverage_grade"),
        "coverage_blockers": summary.get("coverage_blockers"),
        "duplicate_close_candidates": duplicate_close_candidates,
        "rejected_rows": len(rejected_rows),
        "promotion_blockers": blockers,
        "diagnostics_only": summary.get("diagnostics_only"),
        "promotion_grade": summary.get("promotion_grade"),
        "date_start": date_start,
        "date_end": date_end,
        "max_rows": max_rows,
        "include_diagnostics": include_diagnostics,
        "source_snapshot_requested": bool(out_dir is not None and snapshot_sources),
        "source_snapshot_manifest": source_snapshot_manifest_path,
        "source_snapshot": {
            "missing_required_sources": (
                list(source_snapshot_manifest.get(
                    "missing_required_sources", []))
                if source_snapshot_manifest is not None
                else []
            ),
            "warnings": (
                list(source_snapshot_manifest.get("warnings", []))
                if source_snapshot_manifest is not None
                else []
            ),
        },
        "duplicate_decision_rids": duplicate_decision_rids,
        "denominator_audit": denominator_audit,
        "data_quality": summary,
    }

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if realized_rows:
            write_jsonl(out_dir / "realized_trades.jsonl", realized_rows)
        if rejected_rows:
            write_jsonl(out_dir / "rejected_rows.jsonl", rejected_rows)
        if accepted_unresolved_rows:
            write_jsonl(
                out_dir / "accepted_unresolved_rows.jsonl",
                accepted_unresolved_rows,
            )
        write_manifest_json(out_dir / "dataset_manifest.json", manifest)
        write_manifest_json(
            out_dir / "canonicalization_report.json", canonicalization_report)
        write_manifest_json(
            out_dir / "denominator_audit.json", denominator_audit)
        (out_dir / "DATA_QUALITY_REPORT.md").write_text(
            _generate_quality_report(
                summary,
                blockers,
                warnings,
                source_snapshot_manifest=source_snapshot_manifest,
                source_snapshot_manifest_path=source_snapshot_manifest_path,
            ),
            encoding="utf-8",
        )
        (out_dir / "CANONICALIZATION_REPORT.md").write_text(
            _generate_canonicalization_report_md(canonicalization_report),
            encoding="utf-8",
        )
        (out_dir / "DENOMINATOR_AUDIT.md").write_text(
            _generate_denominator_audit_report_md(denominator_audit),
            encoding="utf-8",
        )

    return BuilderResult(
        realized_rows=realized_rows,
        data_quality_summary=summary,
        blockers=blockers,
        warnings=warnings,
        manifest=manifest,
        rejected_rows=rejected_rows,
        accepted_unresolved_rows=accepted_unresolved_rows,
        canonicalization_report=canonicalization_report,
    )
