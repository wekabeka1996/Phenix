from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from calibrators.datasets.audit_runtime_close_coverage import (
    ALTERNATIVE_TERMINAL_EVENTS,
    _build_index,
    _dedupe_rows,
    _event_type,
    _find_snapshot_entry,
    _normalize_text,
    _order_log_is_close_fill,
    _order_log_is_close_submitted,
    _resolve_path,
    _snapshot_surface_from_entry,
    _trade_lifecycle_is_close,
    analyze_runtime_close_coverage,
)
from calibrators.datasets.builders.source_snapshot import load_source_snapshot_manifest


CLOSE_SURFACE_BUCKETS = [
    "ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED",
    "ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT",
    "LIFECYCLE_ID_BRIDGE_AVAILABLE",
    "TRADE_ID_BRIDGE_AVAILABLE",
    "DECISION_LEDGER_REALIZED_ONLY",
    "BUILDER_CANONICALIZATION_GAP",
    "RUNTIME_LOGGING_GAP",
    "INCONCLUSIVE",
]

RUNTIME_DOMINANT_BUCKETS = {
    "ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED",
    "ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT",
    "RUNTIME_LOGGING_GAP",
}

BUILDER_DOMINANT_BUCKETS = {
    "LIFECYCLE_ID_BRIDGE_AVAILABLE",
    "TRADE_ID_BRIDGE_AVAILABLE",
    "BUILDER_CANONICALIZATION_GAP",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relative_to_repo(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _row_key(row: dict[str, Any]) -> tuple[str, int]:
    return (str(row.get("_source_path")), int(row.get("_line_number", 0)))


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


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def _format_counter(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _coverage_pct(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round((count / total) * 100.0, 4)


def _count_where(rows: list[dict[str, Any]], predicate: Any) -> int:
    return sum(1 for row in rows if predicate(row))


def _count_event(rows: list[dict[str, Any]], event_type: str) -> int:
    return sum(1 for row in rows if _event_type(row) == event_type)


def _partition_index_rows(
    decision: dict[str, Any],
    index: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    rid = decision["rid"]
    lifecycle_id = _normalize_text(decision.get("lifecycle_id"))
    trade_id = _normalize_text(decision.get("trade_id"))

    exact_rows = _dedupe_rows(list(index["by_rid"].get(rid, [])))
    exact_keys = {_row_key(row) for row in exact_rows}

    lifecycle_rows: list[dict[str, Any]] = []
    if lifecycle_id:
        lifecycle_rows = [
            row
            for row in index["by_lifecycle"].get(lifecycle_id, [])
            if _row_key(row) not in exact_keys
        ]
    lifecycle_rows = _dedupe_rows(lifecycle_rows)
    lifecycle_keys = exact_keys | {_row_key(row) for row in lifecycle_rows}

    trade_rows: list[dict[str, Any]] = []
    if trade_id:
        trade_rows = [
            row
            for row in index["by_trade"].get(trade_id, [])
            if _row_key(row) not in lifecycle_keys
        ]
    trade_rows = _dedupe_rows(trade_rows)

    return {
        "exact": exact_rows,
        "lifecycle_bridge": lifecycle_rows,
        "trade_bridge": trade_rows,
    }


def _surface_evidence(decision: dict[str, Any], order_index: dict[str, Any], trade_index: dict[str, Any]) -> dict[str, Any]:
    order_parts = _partition_index_rows(decision, order_index)
    trade_parts = _partition_index_rows(decision, trade_index)

    evidence = {
        "order_exact_row_count": len(order_parts["exact"]),
        "order_lifecycle_bridge_row_count": len(order_parts["lifecycle_bridge"]),
        "order_trade_bridge_row_count": len(order_parts["trade_bridge"]),
        "order_exact_event_counts": _format_counter(Counter(_event_type(row) for row in order_parts["exact"])),
        "order_lifecycle_bridge_event_counts": _format_counter(
            Counter(_event_type(row)
                    for row in order_parts["lifecycle_bridge"])
        ),
        "order_trade_bridge_event_counts": _format_counter(
            Counter(_event_type(row) for row in order_parts["trade_bridge"])
        ),
        "order_exact_position_closed_count": _count_event(order_parts["exact"], "POSITION_CLOSED"),
        "order_lifecycle_bridge_position_closed_count": _count_event(order_parts["lifecycle_bridge"], "POSITION_CLOSED"),
        "order_trade_bridge_position_closed_count": _count_event(order_parts["trade_bridge"], "POSITION_CLOSED"),
        "order_exact_close_fill_count": _count_where(order_parts["exact"], _order_log_is_close_fill),
        "order_lifecycle_bridge_close_fill_count": _count_where(order_parts["lifecycle_bridge"], _order_log_is_close_fill),
        "order_trade_bridge_close_fill_count": _count_where(order_parts["trade_bridge"], _order_log_is_close_fill),
        "order_exact_close_submitted_count": _count_where(order_parts["exact"], _order_log_is_close_submitted),
        "order_lifecycle_bridge_close_submitted_count": _count_where(order_parts["lifecycle_bridge"], _order_log_is_close_submitted),
        "order_trade_bridge_close_submitted_count": _count_where(order_parts["trade_bridge"], _order_log_is_close_submitted),
        "order_exact_alternative_terminal_count": sum(
            1 for row in order_parts["exact"] if _event_type(row) in ALTERNATIVE_TERMINAL_EVENTS
        ),
        "order_lifecycle_bridge_alternative_terminal_count": sum(
            1 for row in order_parts["lifecycle_bridge"] if _event_type(row) in ALTERNATIVE_TERMINAL_EVENTS
        ),
        "order_trade_bridge_alternative_terminal_count": sum(
            1 for row in order_parts["trade_bridge"] if _event_type(row) in ALTERNATIVE_TERMINAL_EVENTS
        ),
        "trade_exact_row_count": len(trade_parts["exact"]),
        "trade_lifecycle_bridge_row_count": len(trade_parts["lifecycle_bridge"]),
        "trade_trade_bridge_row_count": len(trade_parts["trade_bridge"]),
        "trade_exact_event_counts": _format_counter(Counter(_event_type(row) for row in trade_parts["exact"])),
        "trade_lifecycle_bridge_event_counts": _format_counter(
            Counter(_event_type(row)
                    for row in trade_parts["lifecycle_bridge"])
        ),
        "trade_trade_bridge_event_counts": _format_counter(
            Counter(_event_type(row) for row in trade_parts["trade_bridge"])
        ),
        "trade_exact_terminal_close_count": 0,
        "trade_lifecycle_bridge_terminal_close_count": 0,
        "trade_trade_bridge_terminal_close_count": 0,
    }

    evidence["trade_exact_terminal_close_count"] = _count_where(
        trade_parts["exact"], _trade_lifecycle_is_close
    )
    evidence["trade_lifecycle_bridge_terminal_close_count"] = _count_where(
        trade_parts["lifecycle_bridge"], _trade_lifecycle_is_close
    )
    evidence["trade_trade_bridge_terminal_close_count"] = _count_where(
        trade_parts["trade_bridge"], _trade_lifecycle_is_close
    )
    return evidence


def _has_any_order_close_evidence(evidence: dict[str, Any]) -> bool:
    return any(
        evidence[key] > 0
        for key in (
            "order_exact_position_closed_count",
            "order_lifecycle_bridge_position_closed_count",
            "order_trade_bridge_position_closed_count",
            "order_exact_close_fill_count",
            "order_lifecycle_bridge_close_fill_count",
            "order_trade_bridge_close_fill_count",
            "order_exact_close_submitted_count",
            "order_lifecycle_bridge_close_submitted_count",
            "order_trade_bridge_close_submitted_count",
        )
    )


def _has_any_trade_close_evidence(evidence: dict[str, Any]) -> bool:
    return any(
        evidence[key] > 0
        for key in (
            "trade_exact_terminal_close_count",
            "trade_lifecycle_bridge_terminal_close_count",
            "trade_trade_bridge_terminal_close_count",
        )
    )


def _classify_close_surface_bucket(decision: dict[str, Any], evidence: dict[str, Any]) -> tuple[str, str]:
    any_order_close_evidence = _has_any_order_close_evidence(evidence)
    any_trade_close_evidence = _has_any_trade_close_evidence(evidence)
    any_alt_terminal = any(
        evidence[key] > 0
        for key in (
            "order_exact_alternative_terminal_count",
            "order_lifecycle_bridge_alternative_terminal_count",
            "order_trade_bridge_alternative_terminal_count",
        )
    )

    if (
        bool(decision.get("realized_fields_present"))
        and not any_order_close_evidence
        and not any_trade_close_evidence
    ):
        return (
            "DECISION_LEDGER_REALIZED_ONLY",
            "decision ledger carries realized fields but no close evidence was found in order_log or trade_lifecycle",
        )

    if evidence["order_lifecycle_bridge_position_closed_count"] > 0:
        return (
            "LIFECYCLE_ID_BRIDGE_AVAILABLE",
            "authority order_log snapshot contains POSITION_CLOSED only on lifecycle_id bridge keys, not on the exact decision rid",
        )

    if evidence["order_trade_bridge_position_closed_count"] > 0:
        return (
            "TRADE_ID_BRIDGE_AVAILABLE",
            "authority order_log snapshot contains POSITION_CLOSED only on trade_id bridge keys, not on the exact decision rid",
        )

    if evidence["order_exact_position_closed_count"] > 0:
        return (
            "BUILDER_CANONICALIZATION_GAP",
            "authority order_log snapshot contains an exact-rid POSITION_CLOSED row but the realized builder still left the decision unmatched",
        )

    if any_alt_terminal:
        return (
            "ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT",
            "order_log emits alternative terminal events for the decision while canonical POSITION_CLOSED remains absent",
        )

    if any_trade_close_evidence:
        return (
            "ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED",
            "trade_lifecycle proves the position closed but authority order_log lacks a canonical POSITION_CLOSED row for the decision rid",
        )

    if any_order_close_evidence:
        return (
            "RUNTIME_LOGGING_GAP",
            "close-like order evidence exists without trade_lifecycle terminal close proof or canonical POSITION_CLOSED emission",
        )

    return (
        "INCONCLUSIVE",
        "no decisive close evidence remained after comparing exact and bridge surfaces",
    )


def _load_snapshot_surfaces(repo_root: Path, artifact_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = artifact_dir / "source_snapshot" / "source_snapshot_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Missing source snapshot manifest: {manifest_path}")
    manifest = load_source_snapshot_manifest(manifest_path)
    decision_surface = _snapshot_surface_from_entry(
        repo_root,
        artifact_dir,
        _find_snapshot_entry(manifest, "decision_ledger"),
    )
    order_surface = _snapshot_surface_from_entry(
        repo_root,
        artifact_dir,
        _find_snapshot_entry(manifest, "order_log"),
    )
    trade_surface = _snapshot_surface_from_entry(
        repo_root,
        artifact_dir,
        _find_snapshot_entry(manifest, "trade_lifecycle"),
    )
    if decision_surface is None:
        raise FileNotFoundError("Missing snapshot decision ledger surface")
    if order_surface is None:
        raise FileNotFoundError("Missing snapshot order_log surface")
    return manifest, {
        "decision": decision_surface,
        "order": order_surface,
        "trade": trade_surface,
        "manifest_path": manifest_path,
    }


def _recommend_next_package(bucket_counts: Counter[str]) -> tuple[str, list[str]]:
    runtime_rows = sum(bucket_counts[bucket]
                       for bucket in RUNTIME_DOMINANT_BUCKETS)
    builder_rows = sum(bucket_counts[bucket]
                       for bucket in BUILDER_DOMINANT_BUCKETS)
    decision_rows = bucket_counts["DECISION_LEDGER_REALIZED_ONLY"]
    inconclusive_rows = bucket_counts["INCONCLUSIVE"]

    if runtime_rows > 0 and runtime_rows >= max(builder_rows, decision_rows, inconclusive_rows):
        return (
            "03T_RUNTIME_POSITION_CLOSED_EMISSION_REPAIR",
            [
                f"runtime-oriented buckets account for {runtime_rows} / {sum(bucket_counts.values())} close-expected unmatched rows",
                f"{bucket_counts['ORDER_LOG_MISSING_POSITION_CLOSED_BUT_TRADE_LIFECYCLE_CLOSED']} rows already prove closure in trade_lifecycle while canonical POSITION_CLOSED is absent",
                f"{bucket_counts['ORDER_LOG_HAS_ALTERNATIVE_TERMINAL_EVENT']} rows emit alternative terminal order events instead of canonical close emission",
            ],
        )
    if builder_rows > 0 and builder_rows >= max(decision_rows, inconclusive_rows):
        return (
            "03S_REALIZED_BUILDER_NARROW_BRIDGE_REPAIR",
            [
                f"builder-oriented buckets account for {builder_rows} / {sum(bucket_counts.values())} close-expected unmatched rows",
                f"{bucket_counts['LIFECYCLE_ID_BRIDGE_AVAILABLE']} rows expose lifecycle bridge close evidence that v1 builder does not currently consume",
                f"{bucket_counts['BUILDER_CANONICALIZATION_GAP']} rows already have canonical POSITION_CLOSED on the exact rid but still remain unmatched",
            ],
        )
    if decision_rows > 0 and decision_rows >= inconclusive_rows:
        return (
            "03U_DECISION_LEDGER_REALIZED_FIELD_AUTHORITY_AUDIT",
            [
                f"decision-ledger-only realized evidence appears on {decision_rows} / {sum(bucket_counts.values())} close-expected unmatched rows",
                "the unresolved surface is field authority rather than close event linkage",
            ],
        )
    return (
        "03C_REPLAY_FREEZE_MANIFESTS",
        [
            f"{inconclusive_rows} rows remain inconclusive after comparing snapshot order_log, trade_lifecycle, and decision ledger surfaces",
            "the next safe step is to audit replay freeze manifests before changing builders or runtime emission",
        ],
    )


def analyze_close_surface_reconciliation(
    repo_root: str | Path,
    *,
    realized_artifact_dir: str | Path,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    artifact_dir = _resolve_path(repo_root, realized_artifact_dir)
    manifest, snapshot_surfaces = _load_snapshot_surfaces(
        repo_root, artifact_dir)
    decision_surface = snapshot_surfaces["decision"]
    order_surface = snapshot_surfaces["order"]
    trade_surface = snapshot_surfaces["trade"]
    generated_at = _utc_now()

    baseline = analyze_runtime_close_coverage(
        repo_root,
        realized_artifact_dir=artifact_dir,
        decision_ledger=decision_surface.path,
        realized_trades=artifact_dir / "realized_trades.jsonl",
        rejected_rows=artifact_dir / "rejected_rows.jsonl",
        order_logs=[order_surface.path],
        trade_lifecycles=[
            trade_surface.path] if trade_surface is not None else [],
    )

    order_index = _build_index(repo_root, [order_surface])
    trade_index = _build_index(
        repo_root, [trade_surface] if trade_surface is not None else [])

    close_expected_unmatched = [
        dict(row)
        for row in baseline["unmatched_classification"]["rows"]
        if row.get("close_expected") and not row.get("emitted_realized_row")
    ]
    close_expected_unmatched.sort(
        key=lambda row: (
            int(row.get("decision_timestamp_ms") or 0),
            str(row.get("rid") or ""),
        )
    )

    ledger_rows: list[dict[str, Any]] = []
    bucket_counts: Counter[str] = Counter()
    exact_order_position_closed_rows = 0
    lifecycle_bridge_position_closed_rows = 0
    trade_bridge_position_closed_rows = 0
    trade_lifecycle_closed_rows = 0
    alternative_terminal_rows = 0
    decision_realized_fields_rows = 0
    runtime_logging_gap_rows = 0

    for row in close_expected_unmatched:
        row["realized_fields_present"] = bool(
            row.get("realized_pnl_net") is not None or row.get(
                "fees") is not None
        )
        evidence = _surface_evidence(row, order_index, trade_index)
        bucket, bucket_reason = _classify_close_surface_bucket(row, evidence)
        bucket_counts[bucket] += 1

        exact_order_position_closed_rows += int(
            evidence["order_exact_position_closed_count"] > 0)
        lifecycle_bridge_position_closed_rows += int(
            evidence["order_lifecycle_bridge_position_closed_count"] > 0)
        trade_bridge_position_closed_rows += int(
            evidence["order_trade_bridge_position_closed_count"] > 0)
        trade_lifecycle_closed_rows += int(
            _has_any_trade_close_evidence(evidence))
        alternative_terminal_rows += int(
            evidence["order_exact_alternative_terminal_count"] > 0
            or evidence["order_lifecycle_bridge_alternative_terminal_count"] > 0
            or evidence["order_trade_bridge_alternative_terminal_count"] > 0
        )
        decision_realized_fields_rows += int(row["realized_fields_present"])
        runtime_logging_gap_rows += int(bucket == "RUNTIME_LOGGING_GAP")

        ledger_rows.append(
            {
                "decision_id": row.get("decision_id"),
                "rid": row.get("rid"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "strategy_id": row.get("strategy_id"),
                "decision_timestamp_ms": row.get("decision_timestamp_ms"),
                "decision_timestamp_utc": row.get("decision_timestamp_utc"),
                "terminal_status": row.get("terminal_status"),
                "trade_id": row.get("trade_id"),
                "lifecycle_id": row.get("lifecycle_id"),
                "realized_pnl_net": row.get("realized_pnl_net"),
                "fees": row.get("fees"),
                "realized_fields_present": row.get("realized_fields_present"),
                "close_surface_bucket": bucket,
                "close_surface_bucket_reason": bucket_reason,
                **evidence,
            }
        )

    recommended_next_package, recommendation_basis = _recommend_next_package(
        bucket_counts)

    ledger_payload = {
        "generated_at_utc": generated_at,
        "audit_source_kind": "artifact_authority_snapshot",
        "source_snapshot_manifest_path": _relative_to_repo(repo_root, snapshot_surfaces["manifest_path"]),
        "summary": {
            "total_close_expected_unmatched_rows": len(ledger_rows),
            "close_expected_rows": baseline["denominator_audit"].get("close_expected_rows"),
            "close_matched_rows": baseline["denominator_audit"].get("close_matched_rows"),
            "close_unmatched_rows": len(ledger_rows),
            "execution_to_close_coverage_pct": baseline["denominator_audit"].get("execution_to_close_coverage_pct"),
            "legacy_total_decision_close_coverage_pct": baseline["denominator_audit"].get("legacy_total_decision_close_coverage_pct"),
            "bucket_counts": {bucket: bucket_counts.get(bucket, 0) for bucket in CLOSE_SURFACE_BUCKETS},
        },
        "rows": ledger_rows,
    }

    matrix_rows = []
    for bucket in CLOSE_SURFACE_BUCKETS:
        count = bucket_counts.get(bucket, 0)
        examples = [row["rid"]
                    for row in ledger_rows if row["close_surface_bucket"] == bucket][:3]
        matrix_rows.append(
            {
                "bucket": bucket,
                "count": count,
                "pct_of_close_expected_unmatched": _coverage_pct(count, len(ledger_rows)),
                "example_rids": examples,
            }
        )

    matrix_payload = {
        "generated_at_utc": generated_at,
        "audit_source_kind": "artifact_authority_snapshot",
        "source_snapshot_manifest_path": _relative_to_repo(repo_root, snapshot_surfaces["manifest_path"]),
        "total_close_expected_unmatched_rows": len(ledger_rows),
        "bucket_counts": {bucket: bucket_counts.get(bucket, 0) for bucket in CLOSE_SURFACE_BUCKETS},
        "matrix_rows": matrix_rows,
        "dominant_axes": {
            "runtime_surface_rows": sum(bucket_counts[bucket] for bucket in RUNTIME_DOMINANT_BUCKETS),
            "builder_surface_rows": sum(bucket_counts[bucket] for bucket in BUILDER_DOMINANT_BUCKETS),
            "decision_ledger_surface_rows": bucket_counts["DECISION_LEDGER_REALIZED_ONLY"],
            "inconclusive_rows": bucket_counts["INCONCLUSIVE"],
        },
        "recommended_next_package": recommended_next_package,
        "recommendation_basis": recommendation_basis,
    }

    order_vs_trade_payload = {
        "generated_at_utc": generated_at,
        "audit_source_kind": "artifact_authority_snapshot",
        "source_snapshot_manifest_path": _relative_to_repo(repo_root, snapshot_surfaces["manifest_path"]),
        "summary": {
            "rows_with_exact_order_position_closed": exact_order_position_closed_rows,
            "rows_with_lifecycle_bridge_position_closed": lifecycle_bridge_position_closed_rows,
            "rows_with_trade_bridge_position_closed": trade_bridge_position_closed_rows,
            "rows_with_trade_lifecycle_terminal_close": trade_lifecycle_closed_rows,
            "rows_with_order_log_alternative_terminal_event": alternative_terminal_rows,
            "rows_with_decision_ledger_realized_fields": decision_realized_fields_rows,
            "rows_classified_runtime_logging_gap": runtime_logging_gap_rows,
        },
        "rows": ledger_rows,
    }

    decision_realized_payload = {
        "generated_at_utc": generated_at,
        "audit_source_kind": "artifact_authority_snapshot",
        "source_snapshot_manifest_path": _relative_to_repo(repo_root, snapshot_surfaces["manifest_path"]),
        "summary": {
            "rows_with_decision_ledger_realized_fields": decision_realized_fields_rows,
            "decision_ledger_realized_only_rows": bucket_counts["DECISION_LEDGER_REALIZED_ONLY"],
            "rows_with_realized_fields_and_bridge_position_closed": sum(
                1
                for row in ledger_rows
                if row["realized_fields_present"] and row["order_lifecycle_bridge_position_closed_count"] > 0
            ),
        },
        "rows": [row for row in ledger_rows if row["realized_fields_present"]],
    }

    return {
        "generated_at_utc": generated_at,
        "source_inputs": {
            "audit_source_kind": "artifact_authority_snapshot",
            "realized_artifact_dir": _relative_to_repo(repo_root, artifact_dir),
            "source_snapshot_manifest_path": _relative_to_repo(repo_root, snapshot_surfaces["manifest_path"]),
            "decision_ledger": _relative_to_repo(repo_root, decision_surface.path),
            "order_log": _relative_to_repo(repo_root, order_surface.path),
            "trade_lifecycle": _relative_to_repo(repo_root, trade_surface.path) if trade_surface is not None else None,
        },
        "denominator_audit": baseline["denominator_audit"],
        "close_expected_unmatched_ledger": ledger_payload,
        "close_surface_reconciliation_matrix": matrix_payload,
        "order_log_vs_trade_lifecycle_close_audit": order_vs_trade_payload,
        "decision_ledger_realized_fields_audit": decision_realized_payload,
    }


def _render_close_expected_unmatched_ledger_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    rows = [
        [
            row["rid"],
            row["symbol"],
            row["close_surface_bucket"],
            row["terminal_status"],
            row["order_exact_position_closed_count"],
            row["order_lifecycle_bridge_position_closed_count"],
            row["trade_exact_terminal_close_count"],
            row["realized_fields_present"],
        ]
        for row in payload["rows"]
    ]
    return "\n".join(
        [
            "# CLOSE_EXPECTED_UNMATCHED_LEDGER",
            "",
            f"Generated at UTC: {payload['generated_at_utc']}",
            f"Audit source kind: {payload['audit_source_kind']}",
            f"Source snapshot manifest: {payload['source_snapshot_manifest_path']}",
            "",
            f"Close-expected unmatched rows: {summary['total_close_expected_unmatched_rows']}",
            f"Close-expected denominator rows: {summary['close_expected_rows']}",
            f"Matched close rows: {summary['close_matched_rows']}",
            f"Execution-to-close coverage pct: {summary['execution_to_close_coverage_pct']}",
            f"Legacy total-decision close coverage pct: {summary['legacy_total_decision_close_coverage_pct']}",
            "",
            "## Bucket Counts",
            "",
            _markdown_table(
                ["bucket", "count"],
                [[bucket, summary["bucket_counts"].get(
                    bucket, 0)] for bucket in CLOSE_SURFACE_BUCKETS],
            ),
            "",
            "## Rows",
            "",
            _markdown_table(
                [
                    "rid",
                    "symbol",
                    "bucket",
                    "terminal_status",
                    "exact_pos_closed",
                    "lifecycle_bridge_pos_closed",
                    "trade_exact_close",
                    "decision_realized_fields",
                ],
                rows,
            ),
            "",
        ]
    )


def _render_close_surface_reconciliation_matrix_markdown(payload: dict[str, Any]) -> str:
    matrix_rows = [
        [
            row["bucket"],
            row["count"],
            row["pct_of_close_expected_unmatched"],
            ", ".join(row["example_rids"]),
        ]
        for row in payload["matrix_rows"]
    ]
    axis_rows = [[key, value]
                 for key, value in payload["dominant_axes"].items()]
    return "\n".join(
        [
            "# CLOSE_SURFACE_RECONCILIATION_MATRIX",
            "",
            f"Generated at UTC: {payload['generated_at_utc']}",
            f"Audit source kind: {payload['audit_source_kind']}",
            f"Source snapshot manifest: {payload['source_snapshot_manifest_path']}",
            "",
            f"Total close-expected unmatched rows: {payload['total_close_expected_unmatched_rows']}",
            f"Recommended next package: {payload['recommended_next_package']}",
            "",
            "## Dominant Axes",
            "",
            _markdown_table(["axis", "rows"], axis_rows),
            "",
            "## Bucket Matrix",
            "",
            _markdown_table(["bucket", "count", "pct_of_13",
                            "example_rids"], matrix_rows),
            "",
            "## Recommendation Basis",
            "",
            *[f"- {line}" for line in payload["recommendation_basis"]],
            "",
        ]
    )


def _render_order_vs_trade_audit_markdown(payload: dict[str, Any]) -> str:
    summary_rows = [[key, value] for key, value in payload["summary"].items()]
    detail_rows = [
        [
            row["rid"],
            row["close_surface_bucket"],
            row["order_exact_position_closed_count"],
            row["order_lifecycle_bridge_position_closed_count"],
            row["trade_exact_terminal_close_count"],
            row["order_exact_event_counts"],
            row["order_lifecycle_bridge_event_counts"],
        ]
        for row in payload["rows"]
    ]
    return "\n".join(
        [
            "# ORDER_LOG_VS_TRADE_LIFECYCLE_CLOSE_AUDIT",
            "",
            f"Generated at UTC: {payload['generated_at_utc']}",
            f"Audit source kind: {payload['audit_source_kind']}",
            f"Source snapshot manifest: {payload['source_snapshot_manifest_path']}",
            "",
            "## Summary",
            "",
            _markdown_table(["metric", "value"], summary_rows),
            "",
            "## Close Surface Comparison",
            "",
            _markdown_table(
                [
                    "rid",
                    "bucket",
                    "exact_pos_closed",
                    "lifecycle_bridge_pos_closed",
                    "trade_exact_close",
                    "exact_order_events",
                    "lifecycle_bridge_order_events",
                ],
                detail_rows,
            ),
            "",
        ]
    )


def _render_decision_realized_fields_audit_markdown(payload: dict[str, Any]) -> str:
    summary_rows = [[key, value] for key, value in payload["summary"].items()]
    detail_rows = [
        [
            row["rid"],
            row["close_surface_bucket"],
            row["realized_pnl_net"],
            row["fees"],
            row["order_lifecycle_bridge_position_closed_count"],
        ]
        for row in payload["rows"]
    ]
    return "\n".join(
        [
            "# DECISION_LEDGER_REALIZED_FIELDS_AUDIT",
            "",
            f"Generated at UTC: {payload['generated_at_utc']}",
            f"Audit source kind: {payload['audit_source_kind']}",
            f"Source snapshot manifest: {payload['source_snapshot_manifest_path']}",
            "",
            "## Summary",
            "",
            _markdown_table(["metric", "value"], summary_rows),
            "",
            "## Rows With Decision Ledger Realized Fields",
            "",
            _markdown_table(
                [
                    "rid",
                    "bucket",
                    "realized_pnl_net",
                    "fees",
                    "lifecycle_bridge_pos_closed",
                ],
                detail_rows or [["none", 0, 0, 0, 0]],
            ),
            "",
        ]
    )


def write_close_surface_reconciliation_artifacts(result: dict[str, Any], out_dir: str | Path) -> None:
    out_dir = Path(out_dir)
    ledger = result["close_expected_unmatched_ledger"]
    matrix = result["close_surface_reconciliation_matrix"]
    order_vs_trade = result["order_log_vs_trade_lifecycle_close_audit"]
    decision_fields = result["decision_ledger_realized_fields_audit"]

    _write_json(out_dir / "CLOSE_EXPECTED_UNMATCHED_LEDGER.json", ledger)
    _write_csv(out_dir / "CLOSE_EXPECTED_UNMATCHED_LEDGER.csv", ledger["rows"])
    _write_text(
        out_dir / "CLOSE_EXPECTED_UNMATCHED_LEDGER.md",
        _render_close_expected_unmatched_ledger_markdown(ledger),
    )

    _write_json(out_dir / "CLOSE_SURFACE_RECONCILIATION_MATRIX.json", matrix)
    _write_text(
        out_dir / "CLOSE_SURFACE_RECONCILIATION_MATRIX.md",
        _render_close_surface_reconciliation_matrix_markdown(matrix),
    )

    _write_text(
        out_dir / "ORDER_LOG_VS_TRADE_LIFECYCLE_CLOSE_AUDIT.md",
        _render_order_vs_trade_audit_markdown(order_vs_trade),
    )

    _write_text(
        out_dir / "DECISION_LEDGER_REALIZED_FIELDS_AUDIT.md",
        _render_decision_realized_fields_audit_markdown(decision_fields),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit close-surface reconciliation for close-expected unmatched realized rows",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        help="Output directory for 03R close-surface reconciliation artifacts",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root path (auto-detected if omitted)",
    )
    parser.add_argument(
        "--realized-artifact-dir",
        required=True,
        help="Realized dataset artifact directory that contains source_snapshot/source_snapshot_manifest.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(
        __file__).resolve().parents[2]
    result = analyze_close_surface_reconciliation(
        repo_root,
        realized_artifact_dir=args.realized_artifact_dir,
    )
    write_close_surface_reconciliation_artifacts(result, args.out_dir)
    print("Built close surface reconciliation audit")
    print(
        f"  Close-expected unmatched rows: {result['close_expected_unmatched_ledger']['summary']['total_close_expected_unmatched_rows']}"
    )
    print(
        f"  Recommended next package: {result['close_surface_reconciliation_matrix']['recommended_next_package']}"
    )
    print(f"  Output dir: {Path(args.out_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
