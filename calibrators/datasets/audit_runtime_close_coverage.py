from __future__ import annotations
from calibrators.datasets.builders.source_snapshot import load_source_snapshot_manifest

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


EXPECTED_DECISION_LEDGER = "logs/shadow_telemetry/decision_ledger_v1.jsonl"
EXPECTED_ORDER_LOG = "logs/order_log_v1.jsonl"
EXPECTED_TRADE_LIFECYCLE = "logs/trade_lifecycle.jsonl"
DEFAULT_REALIZED_ARTIFACT_DIR = (
    "artifacts/calibration_datasets/_smoke_03g_realized_outcome"
)
DEFAULT_REALIZED_TRADES = (
    "artifacts/calibration_datasets/_smoke_03g_realized_outcome/realized_trades.jsonl"
)
DEFAULT_REJECTED_ROWS = (
    "artifacts/calibration_datasets/_smoke_03g_realized_outcome/rejected_rows.jsonl"
)

ORDER_LOG_DISCOVERY_PATTERNS = [
    EXPECTED_ORDER_LOG,
    "logs/frozen/**/order_log_v1.jsonl",
    "reports/forensics/**/order_log_v1.jsonl",
]

TRADE_LIFECYCLE_DISCOVERY_PATTERNS = [
    EXPECTED_TRADE_LIFECYCLE,
    "logs/frozen/**/trade_lifecycle.jsonl",
    "reports/forensics/**/trade_lifecycle.jsonl",
]

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

UNMATCHED_BUCKETS = [
    "NOT_EXECUTED_OR_REJECTED",
    "ENTRY_SUBMITTED_NOT_FILLED",
    "ENTRY_FILLED_POSITION_STILL_OPEN",
    "CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED",
    "CLOSED_UNDER_RID_ALIAS_NOT_CANONICALIZED",
    "CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY",
    "REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY",
    "LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED",
    "TRADE_ID_BRIDGE_AVAILABLE_BUT_UNUSED",
    "BUILDER_CANONICALIZATION_GAP",
    "SOURCE_LOGGING_GAP",
    "INCONCLUSIVE",
]


@dataclass(frozen=True)
class SourceSurface:
    path: Path
    relative_path: str
    source_kind: str
    original_source_kind: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            rows.append({**payload, "_line_number": line_number})
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _parse_ts_ms(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            numeric = float(stripped)
        except ValueError:
            normalized = stripped.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp() * 1000)
    elif isinstance(value, (int, float)):
        numeric = float(value)
    else:
        return None
    if abs(numeric) < 10_000_000_000:
        return int(numeric * 1000)
    return int(numeric)


def _ts_ms_to_iso(ts_ms: Optional[int]) -> Optional[str]:
    if ts_ms is None:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def _relative_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _resolve_path(repo_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _classify_workspace_surface_kind(relative_path: str, authority_relative_path: str) -> str:
    if relative_path == authority_relative_path:
        return "current_workspace_authority"
    if relative_path.startswith("logs/frozen/") or relative_path.startswith("reports/forensics/"):
        return "supplemental_frozen"
    return "explicit_cli_override"


def _is_authority_source_kind(source_kind: Any) -> bool:
    return source_kind in {"artifact_authority_snapshot", "current_workspace_authority"}


def _dedupe_surfaces(surfaces: Iterable[SourceSurface]) -> list[SourceSurface]:
    deduped: list[SourceSurface] = []
    seen: set[str] = set()
    for surface in surfaces:
        key = surface.path.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(surface)
    return deduped


def _find_snapshot_entry(manifest: dict[str, Any], role: str) -> dict[str, Any] | None:
    for entry in manifest.get("sources", []):
        if entry.get("role") == role:
            return entry
    return None


def _snapshot_surface_from_entry(
    repo_root: Path,
    artifact_dir: Path,
    entry: dict[str, Any] | None,
) -> SourceSurface | None:
    if not entry or not entry.get("exists") or not entry.get("copied_to"):
        return None
    path = (artifact_dir / str(entry["copied_to"])).resolve()
    if not path.exists():
        return None
    return SourceSurface(
        path=path,
        relative_path=_relative_path(repo_root, path),
        source_kind="artifact_authority_snapshot",
        original_source_kind=_normalize_text(entry.get("source_kind")),
    )


def _primary_audit_source_kind(order_surfaces: list[SourceSurface]) -> str:
    if any(surface.source_kind == "artifact_authority_snapshot" for surface in order_surfaces):
        return "artifact_authority_snapshot"
    if any(surface.source_kind == "current_workspace_authority" for surface in order_surfaces):
        return "current_workspace_authority"
    if order_surfaces:
        return "supplemental_frozen"
    return "missing_authority"


def _discover_surfaces(
    repo_root: Path,
    *,
    explicit_paths: Optional[Iterable[str | Path]],
    patterns: list[str],
    authority_relative_path: str,
) -> list[SourceSurface]:
    discovered: list[Path] = []
    if explicit_paths is not None:
        for value in explicit_paths:
            path = _resolve_path(repo_root, value)
            if path.exists() and path not in discovered:
                discovered.append(path)
    else:
        for pattern in patterns:
            for path in sorted(repo_root.glob(pattern)):
                if path.exists() and path not in discovered:
                    discovered.append(path.resolve())

    surfaces: list[SourceSurface] = []
    for path in discovered:
        relative_path = _relative_path(repo_root, path)
        source_kind = _classify_workspace_surface_kind(
            relative_path,
            authority_relative_path,
        )
        surfaces.append(
            SourceSurface(
                path=path,
                relative_path=relative_path,
                source_kind=source_kind,
            )
        )
    return surfaces


def _row_key(row: dict[str, Any]) -> tuple[str, int]:
    return (str(row.get("_source_path")), int(row.get("_line_number", 0)))


def _dedupe_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = _row_key(row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _event_type(row: dict[str, Any]) -> str:
    return (
        _normalize_text(row.get("event_type"))
        or _normalize_text(row.get("status"))
        or _normalize_text(row.get("event"))
        or "UNKNOWN"
    )


def _has_realized_fields(row: dict[str, Any]) -> bool:
    return row.get("realized_pnl_net") not in (None, "") or row.get("fees") not in (None, "")


def _trade_lifecycle_is_close(row: dict[str, Any]) -> bool:
    event_type = _event_type(row)
    status = (_normalize_text(row.get("status")) or "").upper()
    close_reason = _normalize_text(row.get("close_reason"))
    return bool(
        event_type == "POSITION_CLOSED"
        or "CLOSE" in event_type
        or status in {"CLOSED", "EXECUTED_AND_CLOSED", "COMPLETED"}
        or row.get("close_ts_ms") not in (None, "")
        or (close_reason is not None and status not in REJECT_TERMINAL_STATUSES)
    )


def _trade_lifecycle_is_fill(row: dict[str, Any]) -> bool:
    event_type = _event_type(row)
    trigger_event = (_normalize_text(row.get("trigger_event")) or "").upper()
    return event_type == "EXECUTION_FILL_INGRESS" or trigger_event == "TRADE_EXECUTED" or event_type == "TRADE_EXECUTED"


def _order_log_is_entry_fill(row: dict[str, Any]) -> bool:
    if _event_type(row) != "ORDER_FILLED":
        return False
    order_kind = (_normalize_text(row.get("order_kind")) or "ENTRY").upper()
    close_reason = _normalize_text(row.get("close_reason"))
    return order_kind == "ENTRY" and close_reason is None


def _order_log_is_close_fill(row: dict[str, Any]) -> bool:
    if _event_type(row) != "ORDER_FILLED":
        return False
    order_kind = (_normalize_text(row.get("order_kind")) or "").upper()
    close_reason = _normalize_text(row.get("close_reason"))
    return order_kind in {"CLOSE", "EXIT", "TP", "SL"} or close_reason is not None


def _order_log_is_close_submitted(row: dict[str, Any]) -> bool:
    event_type = _event_type(row)
    if event_type not in {"ORDER_INTENT", "ORDER_PLACED"}:
        return False
    order_kind = (_normalize_text(row.get("order_kind")) or "").upper()
    close_reason = _normalize_text(row.get("close_reason"))
    rid = _normalize_text(row.get("rid")) or ""
    return order_kind in {"CLOSE", "EXIT", "TP", "SL"} or close_reason is not None or rid.startswith("ppsreq:")


def _format_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _extract_decision_side(decision_row: dict[str, Any]) -> Optional[str]:
    candidate = decision_row.get("causal_state_snapshot", {}).get(
        "candidate_intent_summary", {})
    side = _normalize_text(decision_row.get(
        "side")) or _normalize_text(candidate.get("side"))
    return side


def _extract_decision_strategy(decision_row: dict[str, Any]) -> Optional[str]:
    candidate = decision_row.get("causal_state_snapshot", {}).get(
        "candidate_intent_summary", {})
    return _normalize_text(decision_row.get("strategy_id")) or _normalize_text(candidate.get("strategy_id"))


def _extract_decision_timestamp_ms(decision_row: dict[str, Any]) -> Optional[int]:
    candidate = decision_row.get("causal_state_snapshot", {})
    for value in (
        candidate.get("decision_basis_ts_ms"),
        decision_row.get("request_ts_ms"),
        decision_row.get("response_ts_ms"),
    ):
        parsed = _parse_ts_ms(value)
        if parsed is not None:
            return parsed
    return None


def _build_index(repo_root: Path, surfaces: list[SourceSurface]) -> dict[str, Any]:
    by_rid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_lifecycle: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_trade: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_suffix_alias: dict[str, list[dict[str, Any]]] = defaultdict(list)
    malformed_rows: list[dict[str, Any]] = []
    source_stats: list[dict[str, Any]] = []
    for surface in surfaces:
        rows = _read_jsonl(surface.path)
        source_stats.append(
            {
                "path": surface.relative_path,
                "source_kind": surface.source_kind,
                "original_source_kind": surface.original_source_kind,
                "rows": len(rows),
            }
        )
        for row in rows:
            payload = dict(row)
            payload["_source_path"] = surface.relative_path
            payload["_source_kind"] = surface.source_kind
            payload["_original_source_kind"] = surface.original_source_kind
            rid = _normalize_text(payload.get("rid"))
            lifecycle_id = _normalize_text(payload.get("lifecycle_id"))
            trade_id = _normalize_text(payload.get("trade_id"))
            event_type = _normalize_text(payload.get("event_type"))
            if rid is not None:
                by_rid[rid].append(payload)
                if ":" in rid:
                    by_suffix_alias[rid.split(":", 1)[0]].append(payload)
            if lifecycle_id is not None:
                by_lifecycle[lifecycle_id].append(payload)
            if trade_id is not None:
                by_trade[trade_id].append(payload)
            if event_type is None and rid is None and lifecycle_id is None and trade_id is None:
                malformed_rows.append(payload)
    return {
        "by_rid": by_rid,
        "by_lifecycle": by_lifecycle,
        "by_trade": by_trade,
        "by_suffix_alias": by_suffix_alias,
        "malformed_rows": malformed_rows,
        "source_stats": source_stats,
    }


def _decision_cohort_rows(
    decision_rows: list[dict[str, Any]],
    matched_rows: dict[str, dict[str, Any]],
    rejected_rows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    decision_by_rid = {
        _normalize_text(row.get("rid")): row
        for row in decision_rows
        if _normalize_text(row.get("rid")) is not None
    }
    if matched_rows or rejected_rows:
        cohort_rids = sorted({*matched_rows.keys(), *rejected_rows.keys()})
        return [decision_by_rid[rid] for rid in cohort_rids if rid in decision_by_rid]
    return list(decision_by_rid.values())


def _collect_order_summary(
    decision: dict[str, Any],
    order_index: dict[str, Any],
) -> dict[str, Any]:
    rid = decision["rid"]
    lifecycle_id = decision.get("lifecycle_id")
    trade_id = decision.get("trade_id")
    exact_rows = list(order_index["by_rid"].get(rid, []))
    suffix_alias_rows = [
        row
        for row in order_index["by_suffix_alias"].get(rid, [])
        if (_normalize_text(row.get("rid")) or "") != rid
    ]
    lifecycle_bridge_keys = [key for key in [
        lifecycle_id, rid, decision.get("downstream_rid")] if key]
    lifecycle_rows = []
    for key in lifecycle_bridge_keys:
        lifecycle_rows.extend(order_index["by_lifecycle"].get(key, []))
    trade_rows = list(order_index["by_trade"].get(
        trade_id, [])) if trade_id else []
    relevant_rows = _dedupe_rows(
        [*exact_rows, *suffix_alias_rows, *lifecycle_rows, *trade_rows])
    exact_event_counts = Counter(_event_type(row) for row in exact_rows)
    bridge_event_counts = Counter(
        _event_type(row) for row in _dedupe_rows([*suffix_alias_rows, *lifecycle_rows, *trade_rows])
    )
    position_closed_rows = [
        row for row in relevant_rows if _event_type(row) == "POSITION_CLOSED"]
    exact_position_closed_rows = [
        row for row in exact_rows if _event_type(row) == "POSITION_CLOSED"]
    suffix_position_closed_rows = [
        row for row in suffix_alias_rows if _event_type(row) == "POSITION_CLOSED"]
    lifecycle_position_closed_rows = [
        row for row in lifecycle_rows if _event_type(row) == "POSITION_CLOSED"]
    trade_position_closed_rows = [
        row for row in trade_rows if _event_type(row) == "POSITION_CLOSED"]
    has_authority_source = any(
        _is_authority_source_kind(row.get("_source_kind")) for row in relevant_rows)
    source_paths = sorted({str(row.get("_source_path"))
                          for row in relevant_rows})
    alias_suffixes = sorted(
        {
            (_normalize_text(row.get("rid")) or "").split(":", 1)[1]
            for row in suffix_alias_rows
            if ":" in (_normalize_text(row.get("rid")) or "")
        }
    )
    has_entry_fill = any(_order_log_is_entry_fill(row)
                         for row in relevant_rows)
    has_close_fill = any(_order_log_is_close_fill(row)
                         for row in relevant_rows)
    has_close_submitted = any(_order_log_is_close_submitted(row)
                              for row in relevant_rows)
    has_alt_terminal = any(_event_type(
        row) in ALTERNATIVE_TERMINAL_EVENTS for row in relevant_rows)
    has_realized_fields_without_position_closed = any(
        _has_realized_fields(row) for row in relevant_rows
    ) and not bool(position_closed_rows)
    malformed_count = sum(1 for row in relevant_rows if _normalize_text(
        row.get("event_type")) is None)

    if not relevant_rows:
        primary_bucket = "no order_log rows"
    elif malformed_count:
        primary_bucket = "malformed/incomplete rows"
    elif len(position_closed_rows) > 1:
        primary_bucket = "duplicate close candidates"
    elif suffix_position_closed_rows and not exact_position_closed_rows:
        primary_bucket = "suffix alias only"
    elif position_closed_rows:
        primary_bucket = "POSITION_CLOSED present"
    elif has_close_fill:
        primary_bucket = "close fill present"
    elif has_close_submitted:
        primary_bucket = "close submitted"
    elif has_realized_fields_without_position_closed:
        primary_bucket = "realized fields present without POSITION_CLOSED"
    elif has_alt_terminal:
        primary_bucket = "alternative terminal event present"
    elif has_entry_fill:
        primary_bucket = "entry fill present"
    else:
        primary_bucket = "order placed only"

    return {
        "primary_bucket": primary_bucket,
        "relevant_row_count": len(relevant_rows),
        "exact_row_count": len(exact_rows),
        "suffix_alias_row_count": len(suffix_alias_rows),
        "lifecycle_bridge_row_count": len(lifecycle_rows),
        "trade_bridge_row_count": len(trade_rows),
        "position_closed_count": len(position_closed_rows),
        "exact_position_closed_count": len(exact_position_closed_rows),
        "suffix_position_closed_count": len(suffix_position_closed_rows),
        "lifecycle_position_closed_count": len(lifecycle_position_closed_rows),
        "trade_position_closed_count": len(trade_position_closed_rows),
        "exact_event_counts": _format_counter(exact_event_counts),
        "bridge_event_counts": _format_counter(bridge_event_counts),
        "has_authority_source": has_authority_source,
        "source_paths": source_paths,
        "alias_suffixes": alias_suffixes,
        "has_entry_fill": has_entry_fill,
        "has_close_fill": has_close_fill,
        "has_close_submitted": has_close_submitted,
        "has_position_closed": bool(position_closed_rows),
        "has_alternative_terminal_event": has_alt_terminal,
        "has_realized_fields_without_position_closed": has_realized_fields_without_position_closed,
        "supplemental_only": bool(relevant_rows) and not has_authority_source,
    }


def _collect_trade_lifecycle_summary(
    decision: dict[str, Any],
    trade_index: dict[str, Any],
) -> dict[str, Any]:
    rid = decision["rid"]
    lifecycle_id = decision.get("lifecycle_id")
    trade_id = decision.get("trade_id")
    exact_rows = list(trade_index["by_rid"].get(rid, []))
    lifecycle_bridge_keys = [key for key in [
        lifecycle_id, rid, decision.get("downstream_rid")] if key]
    lifecycle_rows = []
    for key in lifecycle_bridge_keys:
        lifecycle_rows.extend(trade_index["by_lifecycle"].get(key, []))
    trade_rows = list(trade_index["by_trade"].get(
        trade_id, [])) if trade_id else []
    relevant_rows = _dedupe_rows([*exact_rows, *lifecycle_rows, *trade_rows])
    exact_status_counts = Counter(_event_type(row) for row in exact_rows)
    bridge_status_counts = Counter(
        _event_type(row) for row in _dedupe_rows([*lifecycle_rows, *trade_rows])
    )
    terminal_rows = [
        row for row in relevant_rows if _trade_lifecycle_is_close(row)]
    rejected_rows = [
        row
        for row in relevant_rows
        if (_normalize_text(row.get("status")) or "").upper() in REJECT_TERMINAL_STATUSES
    ]
    fill_rows = [row for row in relevant_rows if _trade_lifecycle_is_fill(row)]
    has_authority_source = any(
        _is_authority_source_kind(row.get("_source_kind")) for row in relevant_rows)
    return {
        "relevant_row_count": len(relevant_rows),
        "exact_row_count": len(exact_rows),
        "lifecycle_bridge_row_count": len(lifecycle_rows),
        "trade_bridge_row_count": len(trade_rows),
        "terminal_row_count": len(terminal_rows),
        "rejected_row_count": len(rejected_rows),
        "fill_row_count": len(fill_rows),
        "exact_status_counts": _format_counter(exact_status_counts),
        "bridge_status_counts": _format_counter(bridge_status_counts),
        "source_paths": sorted({str(row.get("_source_path")) for row in relevant_rows}),
        "has_authority_source": has_authority_source,
        "has_terminal_close": bool(terminal_rows),
        "has_rejected_terminal": bool(rejected_rows),
        "has_fill_ingress": bool(fill_rows),
        "has_lifecycle_bridge_rows": bool(lifecycle_rows),
        "has_trade_bridge_rows": bool(trade_rows),
    }


def _classify_unmatched(
    decision: dict[str, Any],
    order_summary: dict[str, Any],
    lifecycle_summary: dict[str, Any],
    *,
    authority_order_log_exists: bool,
) -> tuple[str, str]:
    terminal_status = (decision.get("terminal_status") or "").upper()
    if terminal_status in REJECT_TERMINAL_STATUSES or order_summary["has_alternative_terminal_event"] or lifecycle_summary["has_rejected_terminal"]:
        return (
            "NOT_EXECUTED_OR_REJECTED",
            "terminal status or runtime terminal evidence indicates rejection / non-execution",
        )
    if order_summary["has_position_closed"] and order_summary["supplemental_only"] and not authority_order_log_exists:
        return (
            "SOURCE_LOGGING_GAP",
            "supplemental order_log surface contains POSITION_CLOSED but authority order_log path is missing",
        )
    if order_summary["suffix_position_closed_count"] and not order_summary["exact_position_closed_count"]:
        return (
            "CLOSED_UNDER_RID_ALIAS_NOT_CANONICALIZED",
            "close evidence exists only under a suffix alias rid",
        )
    if not authority_order_log_exists and decision["realized_fields_present"] and not order_summary["has_position_closed"]:
        return (
            "REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY",
            "decision ledger carries realized fields while the authority order_log surface is missing",
        )
    if order_summary["has_position_closed"]:
        if order_summary["has_authority_source"]:
            return (
                "CLOSED_BUT_MISSING_ORDER_LOG_POSITION_CLOSED",
                "authority order_log contains POSITION_CLOSED but the row still remained unmatched",
            )
        return (
            "SOURCE_LOGGING_GAP",
            "close evidence exists only in supplemental order_log surfaces",
        )
    if lifecycle_summary["has_lifecycle_bridge_rows"] and lifecycle_summary["has_terminal_close"]:
        return (
            "LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED",
            "close / terminal lifecycle evidence exists through lifecycle_id bridge only",
        )
    if lifecycle_summary["has_trade_bridge_rows"] and lifecycle_summary["has_terminal_close"]:
        return (
            "TRADE_ID_BRIDGE_AVAILABLE_BUT_UNUSED",
            "close / terminal lifecycle evidence exists through trade_id bridge only",
        )
    if lifecycle_summary["has_terminal_close"]:
        return (
            "CLOSED_EVIDENCE_IN_TRADE_LIFECYCLE_ONLY",
            "trade_lifecycle contains terminal close evidence without order_log POSITION_CLOSED",
        )
    if decision["realized_fields_present"]:
        return (
            "REALIZED_FIELDS_IN_DECISION_LEDGER_ONLY",
            "decision ledger has realized fields but no order_log / trade_lifecycle close proof was found",
        )
    if order_summary["lifecycle_bridge_row_count"]:
        return (
            "LIFECYCLE_ID_BRIDGE_AVAILABLE_BUT_UNUSED",
            "order evidence is present only through lifecycle bridge keys",
        )
    if lifecycle_summary["has_trade_bridge_rows"] or order_summary["trade_bridge_row_count"]:
        return (
            "TRADE_ID_BRIDGE_AVAILABLE_BUT_UNUSED",
            "runtime evidence is present only through trade_id bridge keys",
        )
    if order_summary["has_close_fill"] or order_summary["has_close_submitted"]:
        return (
            "BUILDER_CANONICALIZATION_GAP",
            "close-like order evidence exists but no canonical POSITION_CLOSED join was emitted",
        )
    if order_summary["has_entry_fill"] or lifecycle_summary["has_fill_ingress"]:
        return (
            "ENTRY_FILLED_POSITION_STILL_OPEN",
            "entry fill evidence exists but no close evidence was found",
        )
    if order_summary["relevant_row_count"]:
        return (
            "ENTRY_SUBMITTED_NOT_FILLED",
            "runtime evidence shows submission / placement without fill or close",
        )
    return (
        "INCONCLUSIVE",
        "no decisive order_log or trade_lifecycle evidence was available for the unmatched decision",
    )


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def _render_unmatched_ledger_markdown(payload: dict[str, Any]) -> str:
    rows = payload["rows"]
    summary = payload["summary"]
    table_rows = [
        [
            row["decision_id"],
            row["rid"],
            row["symbol"],
            row["terminal_status"],
            row["emitted_realized_row"],
            row["rejected_reason"],
        ]
        for row in rows
    ]
    return "\n".join(
        [
            "# UNMATCHED_DECISION_LEDGER",
            "",
            f"Generated at UTC: {payload['generated_at_utc']}",
            "",
            f"Eligible decisions: {summary['eligible_decisions']}",
            f"Emitted realized rows: {summary['emitted_realized_rows']}",
            f"Unmatched decisions: {summary['unmatched_decisions']}",
            "",
            _markdown_table(
                [
                    "decision_id",
                    "rid",
                    "symbol",
                    "terminal_status",
                    "emitted_realized_row",
                    "rejected_reason",
                ],
                table_rows,
            ),
            "",
        ]
    )


def _render_order_taxonomy_markdown(payload: dict[str, Any]) -> str:
    summary_rows = [[key, value]
                    for key, value in payload["taxonomy_counts"].items()]
    sample_rows = [
        [
            row["decision_id"],
            row["rid"],
            row["primary_bucket"],
            row["relevant_row_count"],
            ", ".join(row["source_paths"]),
        ]
        for row in payload["decisions"][:20]
    ]
    return "\n".join(
        [
            "# ORDER_LOG_EVENT_TAXONOMY",
            "",
            f"Generated at UTC: {payload['generated_at_utc']}",
            "",
            f"Audit source kind: {payload.get('audit_source_kind')}",
            f"Authority order_log path exists: {payload['authority_order_log_exists']}",
            f"Source snapshot manifest: {payload.get('source_snapshot_manifest_path') or 'none'}",
            "",
            "## Taxonomy Counts",
            "",
            _markdown_table(["bucket", "count"], summary_rows),
            "",
            "## Warnings",
            "",
            *([f"- {warning}" for warning in payload.get("warnings", [])] or ["- none"]),
            "",
            "## Decision Samples",
            "",
            _markdown_table(
                ["decision_id", "rid", "primary_bucket", "rows", "source_paths"],
                sample_rows,
            ),
            "",
        ]
    )


def _render_lifecycle_markdown(payload: dict[str, Any]) -> str:
    summary_rows = [[key, value]
                    for key, value in payload["summary_counts"].items()]
    sample_rows = [
        [
            row["decision_id"],
            row["rid"],
            row["relevant_row_count"],
            row["terminal_row_count"],
            row["fill_row_count"],
            ", ".join(row["source_paths"]),
        ]
        for row in payload["decisions"][:20]
    ]
    return "\n".join(
        [
            "# LIFECYCLE_BRIDGE_AUDIT",
            "",
            f"Generated at UTC: {payload['generated_at_utc']}",
            "",
            f"Audit source kind: {payload.get('audit_source_kind')}",
            f"Source snapshot manifest: {payload.get('source_snapshot_manifest_path') or 'none'}",
            "",
            "## Summary Counts",
            "",
            _markdown_table(["metric", "count"], summary_rows),
            "",
            "## Warnings",
            "",
            *([f"- {warning}" for warning in payload.get("warnings", [])] or ["- none"]),
            "",
            "## Decision Samples",
            "",
            _markdown_table(
                [
                    "decision_id",
                    "rid",
                    "rows",
                    "terminal_rows",
                    "fill_rows",
                    "source_paths",
                ],
                sample_rows,
            ),
            "",
        ]
    )


def _render_unmatched_classification_markdown(payload: dict[str, Any]) -> str:
    count_rows = [[bucket, payload["classification_counts"].get(
        bucket, 0)] for bucket in UNMATCHED_BUCKETS]
    decision_rows = [
        [
            row["decision_id"],
            row["rid"],
            row["classification"],
            row["classification_reason"],
        ]
        for row in payload["rows"]
    ]
    return "\n".join(
        [
            "# UNMATCHED_CLASSIFICATION",
            "",
            f"Generated at UTC: {payload['generated_at_utc']}",
            "",
            f"Audit source kind: {payload.get('audit_source_kind')}",
            f"Source snapshot manifest: {payload.get('source_snapshot_manifest_path') or 'none'}",
            "",
            "## Counts",
            "",
            _markdown_table(["classification", "count"], count_rows),
            "",
            "## Warnings",
            "",
            *([f"- {warning}" for warning in payload.get("warnings", [])] or ["- none"]),
            "",
            "## Decisions",
            "",
            _markdown_table(
                ["decision_id", "rid", "classification", "classification_reason"],
                decision_rows,
            ),
            "",
        ]
    )


def analyze_runtime_close_coverage(
    repo_root: str | Path,
    *,
    realized_artifact_dir: str | Path | None = None,
    decision_ledger: str | Path | None = None,
    realized_trades: str | Path | None = None,
    rejected_rows: str | Path | None = None,
    order_logs: Optional[list[str | Path]] = None,
    trade_lifecycles: Optional[list[str | Path]] = None,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    artifact_dir = _resolve_path(
        repo_root,
        realized_artifact_dir or DEFAULT_REALIZED_ARTIFACT_DIR,
    )
    source_snapshot_manifest_path = artifact_dir / \
        "source_snapshot" / "source_snapshot_manifest.json"
    source_snapshot_manifest = (
        load_source_snapshot_manifest(source_snapshot_manifest_path)
        if source_snapshot_manifest_path.exists()
        else None
    )
    audit_warnings: list[str] = []
    if source_snapshot_manifest is None:
        audit_warnings.append("MISSING_SOURCE_SNAPSHOT")

    decision_snapshot_entry = (
        _find_snapshot_entry(source_snapshot_manifest, "decision_ledger")
        if source_snapshot_manifest is not None
        else None
    )
    decision_snapshot_surface = _snapshot_surface_from_entry(
        repo_root,
        artifact_dir,
        decision_snapshot_entry,
    )
    if decision_ledger is not None:
        decision_ledger_path = _resolve_path(repo_root, decision_ledger)
        decision_ledger_source_kind = _classify_workspace_surface_kind(
            _relative_path(repo_root, decision_ledger_path),
            EXPECTED_DECISION_LEDGER,
        )
    elif decision_snapshot_surface is not None:
        decision_ledger_path = decision_snapshot_surface.path
        decision_ledger_source_kind = decision_snapshot_surface.source_kind
    else:
        decision_ledger_path = _resolve_path(
            repo_root, EXPECTED_DECISION_LEDGER)
        decision_ledger_source_kind = (
            "current_workspace_authority"
            if decision_ledger_path.exists()
            else "missing_authority"
        )

    realized_trades_path = _resolve_path(
        repo_root,
        realized_trades or artifact_dir / "realized_trades.jsonl",
    )
    rejected_rows_path = _resolve_path(
        repo_root,
        rejected_rows or artifact_dir / "rejected_rows.jsonl",
    )

    decision_rows = _read_jsonl(
        decision_ledger_path) if decision_ledger_path.exists() else []
    realized_rows = _read_jsonl(
        realized_trades_path) if realized_trades_path.exists() else []
    rejected_rows_list = _read_jsonl(
        rejected_rows_path) if rejected_rows_path.exists() else []
    realized_by_rid = {
        _normalize_text(row.get("rid")): row
        for row in realized_rows
        if _normalize_text(row.get("rid")) is not None
    }
    rejected_by_rid = {
        _normalize_text(row.get("rid")): row
        for row in rejected_rows_list
        if _normalize_text(row.get("rid")) is not None
    }

    snapshot_order_surfaces: list[SourceSurface] = []
    snapshot_trade_surfaces: list[SourceSurface] = []
    if source_snapshot_manifest is not None and order_logs is None:
        surface = _snapshot_surface_from_entry(
            repo_root,
            artifact_dir,
            _find_snapshot_entry(source_snapshot_manifest, "order_log"),
        )
        if surface is not None:
            snapshot_order_surfaces.append(surface)
    if source_snapshot_manifest is not None and trade_lifecycles is None:
        surface = _snapshot_surface_from_entry(
            repo_root,
            artifact_dir,
            _find_snapshot_entry(source_snapshot_manifest, "trade_lifecycle"),
        )
        if surface is not None:
            snapshot_trade_surfaces.append(surface)

    workspace_order_surfaces = _discover_surfaces(
        repo_root,
        explicit_paths=order_logs,
        patterns=ORDER_LOG_DISCOVERY_PATTERNS,
        authority_relative_path=EXPECTED_ORDER_LOG,
    )
    workspace_trade_surfaces = _discover_surfaces(
        repo_root,
        explicit_paths=trade_lifecycles,
        patterns=TRADE_LIFECYCLE_DISCOVERY_PATTERNS,
        authority_relative_path=EXPECTED_TRADE_LIFECYCLE,
    )
    order_surfaces = _dedupe_surfaces(
        [*snapshot_order_surfaces, *workspace_order_surfaces])
    trade_surfaces = _dedupe_surfaces(
        [*snapshot_trade_surfaces, *workspace_trade_surfaces])
    order_index = _build_index(repo_root, order_surfaces)
    trade_index = _build_index(repo_root, trade_surfaces)
    cohort_rows = _decision_cohort_rows(
        decision_rows, realized_by_rid, rejected_by_rid)

    authority_order_log_exists = any(
        _is_authority_source_kind(surface.source_kind) for surface in order_surfaces)
    authority_trade_lifecycle_exists = any(
        _is_authority_source_kind(surface.source_kind) for surface in trade_surfaces)
    audit_source_kind = _primary_audit_source_kind(order_surfaces)

    ledger_rows: list[dict[str, Any]] = []
    taxonomy_rows: list[dict[str, Any]] = []
    lifecycle_rows: list[dict[str, Any]] = []
    unmatched_rows: list[dict[str, Any]] = []
    taxonomy_counts: Counter[str] = Counter()
    lifecycle_counts: Counter[str] = Counter()
    classification_counts: Counter[str] = Counter()
    alias_suffix_counts: Counter[str] = Counter()

    for decision_row in cohort_rows:
        rid = _normalize_text(decision_row.get("rid"))
        if rid is None:
            continue
        matched_row = realized_by_rid.get(rid)
        rejected_row = rejected_by_rid.get(rid)
        candidate_summary = decision_row.get(
            "causal_state_snapshot", {}).get("candidate_intent_summary", {})
        decision = {
            "decision_id": _normalize_text(decision_row.get("decision_id")),
            "rid": rid,
            "symbol": _normalize_text(decision_row.get("symbol")),
            "side": _extract_decision_side(decision_row),
            "strategy_id": _extract_decision_strategy(decision_row),
            "decision_timestamp_ms": _extract_decision_timestamp_ms(decision_row),
            "terminal_status": _normalize_text(decision_row.get("terminal_status")),
            "action": _normalize_text(decision_row.get("action")),
            "apply_result": _normalize_text(decision_row.get("apply_result")),
            "trade_id": _normalize_text(decision_row.get("trade_id")),
            "lifecycle_id": _normalize_text(decision_row.get("lifecycle_id")),
            "downstream_rid": _normalize_text(decision_row.get("downstream_rid")),
            "realized_pnl_net": decision_row.get("realized_pnl_net"),
            "fees": decision_row.get("fees"),
            "realized_fields_present": _has_realized_fields(decision_row),
            "emitted_realized_row": matched_row is not None,
            "rejected_reason": _normalize_text(rejected_row.get("reason")) if rejected_row else None,
            "decision_line_number": int(decision_row.get("_line_number", 0)),
            "proposed_action": _normalize_text(candidate_summary.get("proposed_action")),
        }

        order_summary = _collect_order_summary(decision, order_index)
        lifecycle_summary = _collect_trade_lifecycle_summary(
            decision, trade_index)
        taxonomy_counts[order_summary["primary_bucket"]] += 1
        lifecycle_counts["has_terminal_close"] += int(
            lifecycle_summary["has_terminal_close"])
        lifecycle_counts["has_rejected_terminal"] += int(
            lifecycle_summary["has_rejected_terminal"])
        lifecycle_counts["has_fill_ingress"] += int(
            lifecycle_summary["has_fill_ingress"])
        lifecycle_counts["has_lifecycle_bridge_rows"] += int(
            lifecycle_summary["has_lifecycle_bridge_rows"])
        lifecycle_counts["has_trade_bridge_rows"] += int(
            lifecycle_summary["has_trade_bridge_rows"])
        for suffix in order_summary["alias_suffixes"]:
            alias_suffix_counts[suffix] += 1

        ledger_entry = {
            "decision_id": decision["decision_id"],
            "rid": decision["rid"],
            "symbol": decision["symbol"],
            "side": decision["side"],
            "strategy_id": decision["strategy_id"],
            "decision_timestamp_ms": decision["decision_timestamp_ms"],
            "decision_timestamp_utc": _ts_ms_to_iso(decision["decision_timestamp_ms"]),
            "terminal_status": decision["terminal_status"],
            "action": decision["action"],
            "apply_result": decision["apply_result"],
            "trade_id": decision["trade_id"],
            "lifecycle_id": decision["lifecycle_id"],
            "realized_pnl_net": decision["realized_pnl_net"],
            "fees": decision["fees"],
            "emitted_realized_row": decision["emitted_realized_row"],
            "rejected_reason": decision["rejected_reason"],
            "proposed_action": decision["proposed_action"],
        }
        taxonomy_entry = {
            "decision_id": decision["decision_id"],
            "rid": decision["rid"],
            "emitted_realized_row": decision["emitted_realized_row"],
            **order_summary,
        }
        lifecycle_entry = {
            "decision_id": decision["decision_id"],
            "rid": decision["rid"],
            "emitted_realized_row": decision["emitted_realized_row"],
            **lifecycle_summary,
        }

        ledger_rows.append(ledger_entry)
        taxonomy_rows.append(taxonomy_entry)
        lifecycle_rows.append(lifecycle_entry)

        if not decision["emitted_realized_row"]:
            classification, reason = _classify_unmatched(
                decision,
                order_summary,
                lifecycle_summary,
                authority_order_log_exists=authority_order_log_exists,
            )
            classification_counts[classification] += 1
            unmatched_rows.append(
                {
                    **ledger_entry,
                    "classification": classification,
                    "classification_reason": reason,
                    "order_taxonomy_bucket": order_summary["primary_bucket"],
                    "order_source_paths": order_summary["source_paths"],
                    "lifecycle_source_paths": lifecycle_summary["source_paths"],
                }
            )

    unmatched_decision_payload = {
        "generated_at_utc": _utc_now(),
        "summary": {
            "eligible_decisions": len(ledger_rows),
            "emitted_realized_rows": sum(1 for row in ledger_rows if row["emitted_realized_row"]),
            "unmatched_decisions": sum(1 for row in ledger_rows if not row["emitted_realized_row"]),
        },
        "rows": ledger_rows,
    }
    order_taxonomy_payload = {
        "generated_at_utc": _utc_now(),
        "audit_source_kind": audit_source_kind,
        "authority_order_log_exists": authority_order_log_exists,
        "authority_order_log_path": EXPECTED_ORDER_LOG,
        "source_snapshot_manifest_path": (
            _relative_path(repo_root, source_snapshot_manifest_path)
            if source_snapshot_manifest_path.exists()
            else None
        ),
        "warnings": audit_warnings,
        "discovered_sources": order_index["source_stats"],
        "taxonomy_counts": _format_counter(taxonomy_counts),
        "alias_suffix_counts": _format_counter(alias_suffix_counts),
        "decisions": taxonomy_rows,
    }
    lifecycle_payload = {
        "generated_at_utc": _utc_now(),
        "audit_source_kind": audit_source_kind,
        "authority_trade_lifecycle_exists": authority_trade_lifecycle_exists,
        "authority_trade_lifecycle_path": EXPECTED_TRADE_LIFECYCLE,
        "source_snapshot_manifest_path": (
            _relative_path(repo_root, source_snapshot_manifest_path)
            if source_snapshot_manifest_path.exists()
            else None
        ),
        "warnings": audit_warnings,
        "discovered_sources": trade_index["source_stats"],
        "summary_counts": _format_counter(lifecycle_counts),
        "decisions": lifecycle_rows,
    }
    unmatched_classification_payload = {
        "generated_at_utc": _utc_now(),
        "audit_source_kind": audit_source_kind,
        "authority_order_log_exists": authority_order_log_exists,
        "source_snapshot_manifest_path": (
            _relative_path(repo_root, source_snapshot_manifest_path)
            if source_snapshot_manifest_path.exists()
            else None
        ),
        "warnings": audit_warnings,
        "classification_counts": _format_counter(classification_counts),
        "rows": unmatched_rows,
    }

    return {
        "source_inputs": {
            "repo_root": repo_root.as_posix(),
            "realized_artifact_dir": _relative_path(repo_root, artifact_dir),
            "audit_source_kind": audit_source_kind,
            "warnings": audit_warnings,
            "source_snapshot_manifest": {
                "path": _relative_path(repo_root, source_snapshot_manifest_path),
                "exists": source_snapshot_manifest is not None,
                "missing_required_sources": (
                    list(source_snapshot_manifest.get(
                        "missing_required_sources", []))
                    if source_snapshot_manifest is not None
                    else []
                ),
                "warnings": (
                    list(source_snapshot_manifest.get("warnings", []))
                    if source_snapshot_manifest is not None
                    else audit_warnings
                ),
            },
            "decision_ledger": {
                "path": _relative_path(repo_root, decision_ledger_path),
                "exists": decision_ledger_path.exists(),
                "rows": len(decision_rows),
                "source_kind": decision_ledger_source_kind,
            },
            "realized_trades": {
                "path": _relative_path(repo_root, realized_trades_path),
                "exists": realized_trades_path.exists(),
                "rows": len(realized_rows),
            },
            "rejected_rows": {
                "path": _relative_path(repo_root, rejected_rows_path),
                "exists": rejected_rows_path.exists(),
                "rows": len(rejected_rows_list),
            },
            "order_logs": order_index["source_stats"],
            "trade_lifecycles": trade_index["source_stats"],
            "authority_order_log_exists": authority_order_log_exists,
            "authority_trade_lifecycle_exists": authority_trade_lifecycle_exists,
        },
        "unmatched_decision_ledger": unmatched_decision_payload,
        "order_log_event_taxonomy": order_taxonomy_payload,
        "lifecycle_bridge_audit": lifecycle_payload,
        "unmatched_classification": unmatched_classification_payload,
    }


def write_runtime_close_coverage_artifacts(result: dict[str, Any], out_dir: str | Path) -> None:
    out_dir = Path(out_dir)
    unmatched_ledger = result["unmatched_decision_ledger"]
    order_taxonomy = result["order_log_event_taxonomy"]
    lifecycle_audit = result["lifecycle_bridge_audit"]
    unmatched_classification = result["unmatched_classification"]

    _write_csv(out_dir / "unmatched_decision_ledger.csv",
               unmatched_ledger["rows"])
    _write_json(out_dir / "unmatched_decision_ledger.json", unmatched_ledger)
    _write_text(
        out_dir / "UNMATCHED_DECISION_LEDGER.md",
        _render_unmatched_ledger_markdown(unmatched_ledger),
    )

    _write_json(out_dir / "order_log_event_taxonomy.json", order_taxonomy)
    _write_text(
        out_dir / "ORDER_LOG_EVENT_TAXONOMY.md",
        _render_order_taxonomy_markdown(order_taxonomy),
    )

    _write_json(out_dir / "lifecycle_bridge_audit.json", lifecycle_audit)
    _write_text(
        out_dir / "LIFECYCLE_BRIDGE_AUDIT.md",
        _render_lifecycle_markdown(lifecycle_audit),
    )

    _write_json(out_dir / "unmatched_classification.json",
                unmatched_classification)
    _write_text(
        out_dir / "UNMATCHED_CLASSIFICATION.md",
        _render_unmatched_classification_markdown(unmatched_classification),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit runtime close coverage for the 03G realized outcome smoke cohort",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for runtime close coverage artifacts",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root path (auto-detected if omitted)",
    )
    parser.add_argument(
        "--realized-artifact-dir",
        default=None,
        help="Realized dataset artifact directory. If it contains source_snapshot/source_snapshot_manifest.json, the audit prefers those retained sources.",
    )
    parser.add_argument(
        "--decision-ledger",
        default=None,
        help="Override decision ledger JSONL path",
    )
    parser.add_argument(
        "--realized-trades",
        default=None,
        help="Override 03G realized_trades.jsonl path",
    )
    parser.add_argument(
        "--rejected-rows",
        default=None,
        help="Override 03G rejected_rows.jsonl path",
    )
    parser.add_argument(
        "--order-log",
        action="append",
        default=None,
        help="Optional order_log JSONL path. Repeat to pass multiple supplemental sources.",
    )
    parser.add_argument(
        "--trade-lifecycle",
        action="append",
        default=None,
        help="Optional trade_lifecycle JSONL path. Repeat to pass multiple supplemental sources.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(
        __file__).resolve().parents[2]
    result = analyze_runtime_close_coverage(
        repo_root,
        realized_artifact_dir=args.realized_artifact_dir,
        decision_ledger=args.decision_ledger,
        realized_trades=args.realized_trades,
        rejected_rows=args.rejected_rows,
        order_logs=args.order_log,
        trade_lifecycles=args.trade_lifecycle,
    )
    write_runtime_close_coverage_artifacts(result, args.out_dir)
    unmatched_rows = result["unmatched_classification"]["rows"]
    print("Built runtime close coverage audit")
    print(
        f"  Eligible decisions: {result['unmatched_decision_ledger']['summary']['eligible_decisions']}")
    print(f"  Unmatched decisions: {len(unmatched_rows)}")
    print(
        f"  Authority order_log exists: {result['source_inputs']['authority_order_log_exists']}"
    )
    print(
        f"  Audit source kind: {result['source_inputs']['audit_source_kind']}")
    print(
        f"  Output dir: {Path(args.out_dir).resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
