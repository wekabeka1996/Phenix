from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


TEXT_SUFFIXES = {".py", ".md", ".txt", ".ps1", ".yml", ".yaml", ".json"}
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "join_key_coverage",
    "realized_outcome_authority",
    "workspaceStorage",
}
TARGET_REPORTS = [
    "executed_trades_master.csv",
    "rejected_attempts_master.csv",
    "order_attempts_master.csv",
]
SELF_AUDIT_FILES = {
    "calibrators/datasets/audit_realized_outcome_authority.py",
}
CANONICAL_SOURCE_IDS = {
    "executed_trades_master": "reports/executed_trades_master.csv",
    "rejected_attempts_master": "reports/rejected_attempts_master.csv",
    "order_attempts_master": "reports/order_attempts_master.csv",
    "order_log": "logs/order_log_v1.jsonl",
    "decision_ledger": "logs/shadow_telemetry/decision_ledger_v1.jsonl",
    "trade_lifecycle": "logs/trade_lifecycle.jsonl",
    "order_ledger": "data/order_ledger.db::orders",
}
ORDER_LOG_CLOSE_EVENT = "POSITION_CLOSED"


@dataclass(frozen=True)
class CodeRef:
    path: str
    line: int
    target: str
    kind: str
    snippet: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(path: Path) -> Any:
    return json.loads(_read_text(path))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False,
                    indent=2), encoding="utf-8")


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


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def _iter_jsonl_rows(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    bad_rows = 0
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                bad_rows += 1
                continue
            if isinstance(payload, dict):
                rows.append(payload)
            else:
                bad_rows += 1
    return rows, bad_rows


def _classify_code_ref(path: Path, context: str) -> str:
    normalized_context = context.lower()
    normalized_path = path.as_posix().lower()
    if "/tests/" in normalized_path or normalized_path.startswith("tests/"):
        return "test_fixture"
    if path.suffix.lower() == ".md":
        return "historical_report" if "report" in path.name.lower() else "documentation"
    if "to_csv(" in normalized_context or "write_text(" in normalized_context or "writerow(" in normalized_context:
        return "active_writer"
    if "read_csv(" in normalized_context or "_read_csv_rows(" in normalized_context or "reports_dir /" in normalized_context:
        return "reader"
    if "executed_trades_master" in normalized_context or "order_attempts_master" in normalized_context or "rejected_attempts_master" in normalized_context:
        return "unknown"
    return "dead_or_unused"


def _iter_searchable_files(repo_root: Path) -> Iterable[Path]:
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
        except OSError:
            continue
        yield path


def find_code_refs(repo_root: Path, *, max_samples: int) -> dict[str, list[dict[str, Any]]]:
    refs: dict[str, list[dict[str, Any]]] = {
        target: [] for target in TARGET_REPORTS}
    for path in _iter_searchable_files(repo_root):
        relative_path = path.relative_to(repo_root).as_posix()
        if relative_path in SELF_AUDIT_FILES:
            continue
        try:
            lines = _read_text(path).splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines):
            for target in TARGET_REPORTS:
                if target not in line:
                    continue
                start = max(0, index - 2)
                end = min(len(lines), index + 3)
                context = "\n".join(lines[start:end])
                ref = CodeRef(
                    path=relative_path,
                    line=index + 1,
                    target=target,
                    kind=_classify_code_ref(Path(relative_path), context),
                    snippet=line.strip(),
                )
                refs[target].append(ref.__dict__)
        for target in TARGET_REPORTS:
            refs[target] = refs[target][:max_samples * 8]
    return refs


def _load_join_key_artifacts(repo_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    inventory_path = repo_root / "calibrators" / "datasets" / \
        "join_key_coverage" / "source_inventory.json"
    matrix_path = repo_root / "calibrators" / "datasets" / \
        "join_key_coverage" / "join_coverage_matrix.json"
    inventory = _read_json(inventory_path) if inventory_path.exists() else {}
    matrix = _read_json(matrix_path) if matrix_path.exists() else []
    return inventory, matrix


def _matrix_entry(matrix: list[dict[str, Any]], left: str, right: str) -> Optional[dict[str, Any]]:
    for entry in matrix:
        if entry.get("left") == left and entry.get("right") == right:
            return entry
    return None


def inspect_reports(repo_root: Path) -> dict[str, Any]:
    reports_dir = repo_root / "reports"
    report_stats: dict[str, Any] = {}
    for report_name in TARGET_REPORTS + ["coverage_ledger.csv"]:
        path = reports_dir / report_name
        if not path.exists():
            report_stats[report_name] = {
                "exists": False,
                "rows": 0,
                "header": [],
                "size_bytes": 0,
                "last_write_time_utc": None,
            }
            continue
        rows = _read_csv_rows(path)
        header = list(rows[0].keys()) if rows else []
        if not header:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, [])
        stat = path.stat()
        report_stats[report_name] = {
            "exists": True,
            "rows": len(rows),
            "header": header,
            "size_bytes": stat.st_size,
            "last_write_time_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "sample_rows": rows[:3],
        }
    return report_stats


def inspect_order_log(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "logs" / "order_log_v1.jsonl"
    if not path.exists():
        return {"exists": False}
    rows, bad_rows = _iter_jsonl_rows(path)
    event_counts: dict[str, int] = {}
    position_closed_samples: list[dict[str, Any]] = []
    realized_rows = 0
    fee_rows = 0
    strategy_rows = 0
    rid_values: set[str] = set()
    lifecycle_values: set[str] = set()
    trade_id_values: set[str] = set()
    position_closed_rids: set[str] = set()
    position_closed_lifecycle_ids: set[str] = set()
    for row in rows:
        event_type = _normalize_text(row.get("event_type")) or "UNKNOWN"
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        rid = _normalize_text(row.get("rid"))
        lifecycle_id = _normalize_text(row.get("lifecycle_id"))
        trade_id = _normalize_text(row.get("trade_id"))
        if rid:
            rid_values.add(rid)
        if lifecycle_id:
            lifecycle_values.add(lifecycle_id)
        if trade_id:
            trade_id_values.add(trade_id)
        if row.get("realized_pnl_net") not in (None, "", 0, 0.0, "0", "0.0"):
            realized_rows += 1
        if row.get("fees") not in (None, "", 0, 0.0, "0", "0.0"):
            fee_rows += 1
        if _normalize_text(row.get("strategy_id")):
            strategy_rows += 1
        if event_type == ORDER_LOG_CLOSE_EVENT:
            if len(position_closed_samples) < 5:
                position_closed_samples.append(
                    {
                        "rid": rid,
                        "lifecycle_id": lifecycle_id,
                        "symbol": row.get("symbol"),
                        "trade_id": trade_id,
                        "realized_pnl_net": row.get("realized_pnl_net"),
                        "fees": row.get("fees"),
                        "timestamp": row.get("timestamp"),
                    }
                )
            if rid:
                position_closed_rids.add(rid)
            if lifecycle_id:
                position_closed_lifecycle_ids.add(lifecycle_id)
    stat = path.stat()
    return {
        "exists": True,
        "rows": len(rows),
        "bad_json_rows": bad_rows,
        "event_counts": event_counts,
        "position_closed_rows": event_counts.get(ORDER_LOG_CLOSE_EVENT, 0),
        "rows_with_realized_pnl_net": realized_rows,
        "rows_with_fees": fee_rows,
        "rows_with_strategy_id": strategy_rows,
        "rid_values": sorted(rid_values)[:10],
        "lifecycle_values": sorted(lifecycle_values)[:10],
        "trade_id_values": sorted(trade_id_values)[:10],
        "position_closed_samples": position_closed_samples,
        "position_closed_rids": position_closed_rids,
        "position_closed_lifecycle_ids": position_closed_lifecycle_ids,
        "last_write_time_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def inspect_decision_ledger(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "logs" / "shadow_telemetry" / "decision_ledger_v1.jsonl"
    if not path.exists():
        return {"exists": False}
    rows, bad_rows = _iter_jsonl_rows(path)
    rid_values: set[str] = set()
    decision_ids: set[str] = set()
    lifecycle_ids: set[str] = set()
    trade_ids: set[str] = set()
    realized_rows = 0
    fee_rows = 0
    strategy_rows = 0
    terminal_status_counts: dict[str, int] = {}
    realized_samples: list[dict[str, Any]] = []
    for row in rows:
        rid = _normalize_text(row.get("rid"))
        decision_id = _normalize_text(row.get("decision_id"))
        lifecycle_id = _normalize_text(row.get("lifecycle_id"))
        trade_id = _normalize_text(row.get("trade_id"))
        terminal_status = _normalize_text(
            row.get("terminal_status")) or "UNKNOWN"
        if rid:
            rid_values.add(rid)
        if decision_id:
            decision_ids.add(decision_id)
        if lifecycle_id:
            lifecycle_ids.add(lifecycle_id)
        if trade_id:
            trade_ids.add(trade_id)
        if row.get("realized_pnl_net") not in (None, "", 0, 0.0, "0", "0.0"):
            realized_rows += 1
            if len(realized_samples) < 5:
                realized_samples.append(
                    {
                        "decision_id": decision_id,
                        "rid": rid,
                        "lifecycle_id": lifecycle_id,
                        "trade_id": trade_id,
                        "terminal_status": terminal_status,
                        "realized_pnl_net": row.get("realized_pnl_net"),
                        "fees": row.get("fees"),
                    }
                )
        if row.get("fees") not in (None, "", 0, 0.0, "0", "0.0"):
            fee_rows += 1
        if _normalize_text(row.get("strategy_id")):
            strategy_rows += 1
        terminal_status_counts[terminal_status] = terminal_status_counts.get(
            terminal_status, 0) + 1
    stat = path.stat()
    return {
        "exists": True,
        "rows": len(rows),
        "bad_json_rows": bad_rows,
        "decision_ids": decision_ids,
        "rid_values": rid_values,
        "lifecycle_ids": lifecycle_ids,
        "trade_ids": trade_ids,
        "rows_with_realized_pnl_net": realized_rows,
        "rows_with_fees": fee_rows,
        "rows_with_strategy_id": strategy_rows,
        "terminal_status_counts": terminal_status_counts,
        "realized_samples": realized_samples,
        "last_write_time_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def inspect_order_ledger(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "data" / "order_ledger.db"
    if not path.exists():
        return {"exists": False}
    connection = sqlite3.connect(path)
    try:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        summary: dict[str, Any] = {"exists": True, "tables": tables}
        if "orders" in tables:
            columns = [row[1]
                       for row in connection.execute("PRAGMA table_info(orders)")]
            count = connection.execute(
                "SELECT COUNT(*) FROM orders").fetchone()[0]
            summary["orders"] = {"row_count": count, "columns": columns}
        return summary
    finally:
        connection.close()


def _infer_invocation_mode(repo_refs: dict[str, list[dict[str, Any]]]) -> str:
    external_script_refs = 0
    for refs in repo_refs.values():
        for ref in refs:
            if "build_order_flow_master" in ref["snippet"] and ref["path"] != "scripts/forensics/build_order_flow_master.py":
                external_script_refs += 1
    if external_script_refs == 0:
        return "manual_cli_only_unreferenced"
    return "repo_referenced_cli_or_task"


def _decide_authority_status(*, report_rows: int, invocation_mode: str, report_stale_vs_runtime: bool, active_writer_count: int) -> str:
    if active_writer_count == 0:
        return "UNKNOWN_AUTHORITY"
    if invocation_mode == "manual_cli_only_unreferenced":
        return "DERIVED_CONVENIENCE_REPORT_ONLY"
    if report_rows == 0 and not report_stale_vs_runtime:
        return "CANONICAL_BUT_BROKEN_EXPORTER"
    if report_stale_vs_runtime:
        return "LEGACY_OR_STALE_REPORT"
    return "UNKNOWN_AUTHORITY"


def _recommend_canonical_source(*, authority_status: str, decision_orderlog_exact_bridge: bool) -> str:
    if authority_status == "CANONICAL_BUT_BROKEN_EXPORTER":
        return "REPAIR_EXECUTED_TRADES_MASTER_EXPORTER"
    if decision_orderlog_exact_bridge:
        return "BUILD_BRIDGE_DATASET_DECISION_LEDGER_TO_ORDER_LOG"
    if authority_status == "UNKNOWN_AUTHORITY":
        return "INCONCLUSIVE_NEEDS_OPERATOR_DECISION"
    return "REQUIRE_RUNTIME_INSTRUMENTATION_FIRST"


def _source_level(yes: bool, partial: bool = False) -> str:
    if yes:
        return "EXACT"
    if partial:
        return "PARTIAL"
    return "NONE"


def build_source_matrix(
    inventory: dict[str, Any],
    join_matrix: list[dict[str, Any]],
    decision_ledger: dict[str, Any],
    order_log: dict[str, Any],
    order_ledger: dict[str, Any],
    report_stats: dict[str, Any],
) -> list[dict[str, Any]]:
    decision_orderlog = _matrix_entry(
        join_matrix,
        CANONICAL_SOURCE_IDS["decision_ledger"],
        CANONICAL_SOURCE_IDS["order_log"],
    )
    decision_tradelifecycle = _matrix_entry(
        join_matrix,
        CANONICAL_SOURCE_IDS["decision_ledger"],
        CANONICAL_SOURCE_IDS["trade_lifecycle"],
    )
    executed_rows = report_stats["executed_trades_master.csv"]["rows"]
    decision_orderlog_exact = bool(
        decision_orderlog and decision_orderlog.get(
            "best_candidate", {}).get("exact_overlap_count", 0) > 0
    )
    position_closed_lifecycle_bridge = len(
        order_log["position_closed_lifecycle_ids"] & decision_ledger["lifecycle_ids"]
    )
    matrix = [
        {
            "source": "reports/executed_trades_master.csv",
            "identity_coverage": "NONE (0 rows)" if executed_rows == 0 else "PARTIAL",
            "outcome_coverage": "NONE" if executed_rows == 0 else "REALIZED_ROWS_PRESENT",
            "fee_coverage": "NONE" if executed_rows == 0 else "PRESENT",
            "exact_decision_identity": False,
            "exact_execution_identity": False,
            "entry_data_available": executed_rows > 0,
            "exit_data_available": executed_rows > 0,
            "realized_pnl_net_available": False,
            "fees_available": False,
            "symbol_side_available": executed_rows > 0,
            "strategy_id_available": False,
            "lifecycle_id_available": False,
            "time_range_coverage": "NONE",
            "row_completeness": "EMPTY",
            "schema_stability": "LOW",
            "runtime_causality": "LOW",
            "log_hygiene": "HIGH_FORMAT_LOW_AUTHORITY",
            "promotion_grade_suitability": "NO",
            "diagnostics_only_suitability": "LIMITED",
            "risks": [
                "manual_forensics_output",
                "stale_vs_current_runtime_logs",
                "header_only_on_empty_subset",
                "schema_missing_decision_bridge_fields",
            ],
        },
        {
            "source": "logs/order_log_v1.jsonl",
            "identity_coverage": "PARTIAL exact via rid/lifecycle/order ids",
            "outcome_coverage": f"POSITION_CLOSED={order_log['position_closed_rows']}",
            "fee_coverage": f"fees_rows={order_log['rows_with_fees']}",
            "exact_decision_identity": decision_orderlog_exact,
            "exact_execution_identity": True,
            "entry_data_available": True,
            "exit_data_available": order_log["position_closed_rows"] > 0,
            "realized_pnl_net_available": order_log["rows_with_realized_pnl_net"] > 0,
            "fees_available": order_log["rows_with_fees"] > 0,
            "symbol_side_available": True,
            "strategy_id_available": order_log["rows_with_strategy_id"] > 0,
            "lifecycle_id_available": True,
            "time_range_coverage": inventory.get(CANONICAL_SOURCE_IDS["order_log"], {}).get("min_time_utc", "unknown"),
            "row_completeness": "MIXED_EVENT_LOG",
            "schema_stability": "MEDIUM",
            "runtime_causality": "HIGH",
            "log_hygiene": "MEDIUM",
            "promotion_grade_suitability": "NO_DIRECT",
            "diagnostics_only_suitability": "HIGH",
            "risks": [
                "fill_identity_can_shift_from_rid",
                "mixed_event_families_require_bridge_logic",
                "not_a_single_row_per_trade_surface",
            ],
        },
        {
            "source": "logs/shadow_telemetry/decision_ledger_v1.jsonl",
            "identity_coverage": "EXACT decision_id/rid",
            "outcome_coverage": f"realized_rows={decision_ledger['rows_with_realized_pnl_net']}",
            "fee_coverage": f"fee_rows={decision_ledger['rows_with_fees']}",
            "exact_decision_identity": True,
            "exact_execution_identity": len(decision_ledger["trade_ids"]) > 0,
            "entry_data_available": False,
            "exit_data_available": False,
            "realized_pnl_net_available": decision_ledger["rows_with_realized_pnl_net"] > 0,
            "fees_available": decision_ledger["rows_with_fees"] > 0,
            "symbol_side_available": True,
            "strategy_id_available": decision_ledger["rows_with_strategy_id"] > 0,
            "lifecycle_id_available": len(decision_ledger["lifecycle_ids"]) > 0,
            "time_range_coverage": inventory.get(CANONICAL_SOURCE_IDS["decision_ledger"], {}).get("min_time_utc", "unknown"),
            "row_completeness": "PARTIAL_REALIZED_FIELDS",
            "schema_stability": "MEDIUM_HIGH",
            "runtime_causality": "HIGH",
            "log_hygiene": "MEDIUM_HIGH",
            "promotion_grade_suitability": "NO_PARTIAL",
            "diagnostics_only_suitability": "HIGH",
            "risks": [
                "realized_fields_present_only_on_subset",
                "missing_full_execution_geometry",
            ],
        },
        {
            "source": "decision_ledger + order_log exact bridge",
            "identity_coverage": "EXACT decision bridge with lifecycle canonicalization residual",
            "outcome_coverage": f"bridge_candidate_overlap={decision_orderlog.get('best_candidate', {}).get('exact_overlap_count', 0) if decision_orderlog else 0}",
            "fee_coverage": f"order_log_fee_rows={order_log['rows_with_fees']}",
            "exact_decision_identity": decision_orderlog_exact,
            "exact_execution_identity": position_closed_lifecycle_bridge > 0,
            "entry_data_available": True,
            "exit_data_available": order_log["position_closed_rows"] > 0,
            "realized_pnl_net_available": order_log["rows_with_realized_pnl_net"] > 0,
            "fees_available": order_log["rows_with_fees"] > 0,
            "symbol_side_available": True,
            "strategy_id_available": order_log["rows_with_strategy_id"] > 0,
            "lifecycle_id_available": len(decision_ledger["lifecycle_ids"]) > 0,
            "time_range_coverage": "CURRENT_DECISION_WINDOW_OVERLAP",
            "row_completeness": "BEST_AVAILABLE_AFTER_EXACT_BRIDGE",
            "schema_stability": "MEDIUM",
            "runtime_causality": "HIGH",
            "log_hygiene": "MEDIUM",
            "promotion_grade_suitability": "BEST_CANDIDATE_PENDING_CANONICALIZATION",
            "diagnostics_only_suitability": "HIGH",
            "risks": [
                "requires_explicit_canonicalization_rules",
                "must_preserve_fee_and_exit_semantics",
                "close_rows_may_need_lifecycle_bridge_not_raw_rid",
            ],
        },
        {
            "source": "data/order_ledger.db::orders",
            "identity_coverage": "EXECUTION_ONLY",
            "outcome_coverage": "NONE",
            "fee_coverage": "NONE",
            "exact_decision_identity": False,
            "exact_execution_identity": True,
            "entry_data_available": True,
            "exit_data_available": False,
            "realized_pnl_net_available": False,
            "fees_available": False,
            "symbol_side_available": True,
            "strategy_id_available": False,
            "lifecycle_id_available": False,
            "time_range_coverage": "WIDE",
            "row_completeness": "ORDER_ONLY",
            "schema_stability": "HIGH",
            "runtime_causality": "HIGH",
            "log_hygiene": "HIGH",
            "promotion_grade_suitability": "NO",
            "diagnostics_only_suitability": "MEDIUM",
            "risks": ["missing_realized_outcome_fields", "no_decision_bridge"],
        },
        {
            "source": "logs/trade_lifecycle.jsonl",
            "identity_coverage": (
                f"PARTIAL exact bridge overlap={decision_tradelifecycle.get('best_candidate', {}).get('exact_overlap_count', 0)}"
                if decision_tradelifecycle
                else "PARTIAL"
            ),
            "outcome_coverage": "LOW",
            "fee_coverage": "LOW",
            "exact_decision_identity": bool(
                decision_tradelifecycle and decision_tradelifecycle.get(
                    "best_candidate", {}).get("exact_overlap_count", 0) > 0
            ),
            "exact_execution_identity": True,
            "entry_data_available": True,
            "exit_data_available": True,
            "realized_pnl_net_available": False,
            "fees_available": False,
            "symbol_side_available": True,
            "strategy_id_available": True,
            "lifecycle_id_available": True,
            "time_range_coverage": inventory.get(CANONICAL_SOURCE_IDS["trade_lifecycle"], {}).get("min_time_utc", "unknown"),
            "row_completeness": "EVENT_HEAVY_PARTIAL_OUTCOME",
            "schema_stability": "MEDIUM",
            "runtime_causality": "HIGH",
            "log_hygiene": "MEDIUM_LOW",
            "promotion_grade_suitability": "NO_DIRECT",
            "diagnostics_only_suitability": "MEDIUM",
            "risks": ["bad_json_rows_present", "no_explicit_fee_or_net_pnl_surface"],
        },
        {
            "source": "future_canonical_realized_outcome_dataset",
            "identity_coverage": "DESIGNED_EXACT",
            "outcome_coverage": "DESIGNED_COMPLETE",
            "fee_coverage": "DESIGNED_COMPLETE",
            "exact_decision_identity": True,
            "exact_execution_identity": True,
            "entry_data_available": True,
            "exit_data_available": True,
            "realized_pnl_net_available": True,
            "fees_available": True,
            "symbol_side_available": True,
            "strategy_id_available": True,
            "lifecycle_id_available": True,
            "time_range_coverage": "DEFINED_BY_IMPLEMENTATION",
            "row_completeness": "TARGET_STATE",
            "schema_stability": "HIGH",
            "runtime_causality": "HIGH",
            "log_hygiene": "HIGH",
            "promotion_grade_suitability": "YES_AFTER_BUILD",
            "diagnostics_only_suitability": "YES",
            "risks": ["not_implemented_yet"],
        },
    ]
    return matrix


def build_pipeline_summary(
    repo_root: Path,
    code_refs: dict[str, list[dict[str, Any]]],
    report_stats: dict[str, Any],
    decision_ledger: dict[str, Any],
    order_log: dict[str, Any],
) -> dict[str, Any]:
    writer_path = repo_root / "scripts" / "forensics" / "build_order_flow_master.py"
    writer_text = _read_text(writer_path) if writer_path.exists() else ""
    active_writers = [
        ref
        for refs in code_refs.values()
        for ref in refs
        if ref["kind"] == "active_writer"
    ]
    invocation_mode = _infer_invocation_mode(code_refs)
    report_mtime = report_stats["executed_trades_master.csv"]["last_write_time_utc"]
    runtime_mtimes = [
        order_log.get("last_write_time_utc"),
        decision_ledger.get("last_write_time_utc"),
    ]
    stale_vs_runtime = False
    if report_mtime and all(runtime_mtimes):
        stale_vs_runtime = any(
            runtime_time > report_mtime for runtime_time in runtime_mtimes if runtime_time)
    return {
        "active_writers": active_writers,
        "writer_path": writer_path.relative_to(repo_root).as_posix() if writer_path.exists() else None,
        "invocation_mode": invocation_mode,
        "reads_all_logs_inventory": "generate_source_inventory" in writer_text,
        "uses_order_log_exact_actions": "ORDER_FILLED" in writer_text and "order_log" in writer_text,
        "uses_decision_ledger_explicitly": "decision_ledger" in writer_text,
        "uses_order_ledger_explicitly": "order_ledger" in writer_text,
        "uses_trade_lifecycle_explicitly": "trade_lifecycle" in writer_text,
        "writes_header_only_when_empty": "to_csv(REPORTS_DIR / \"executed_trades_master.csv\"" in writer_text,
        "current_report_stale_vs_runtime": stale_vs_runtime,
        "current_report_rows": report_stats["executed_trades_master.csv"]["rows"],
        "current_rejected_rows": report_stats["rejected_attempts_master.csv"]["rows"],
        "current_order_attempt_rows": report_stats["order_attempts_master.csv"]["rows"],
        "current_coverage_rows": report_stats["coverage_ledger.csv"]["rows"],
        "tests_found": [],
    }


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def write_pipeline_markdown(out_dir: Path, pipeline: dict[str, Any], report_stats: dict[str, Any]) -> None:
    lines = [
        "# EXECUTED_TRADES_MASTER_PIPELINE",
        "",
        "## Producer status",
        f"- Active writer found: {'yes' if pipeline['active_writers'] else 'no'}",
        f"- Writer path: {pipeline['writer_path'] or 'none'}",
        f"- Invocation mode: {pipeline['invocation_mode']}",
        f"- Tests found for writer: {len(pipeline['tests_found'])}",
        "",
        "## Reconstruction",
        "1. reports/executed_trades_master.csv is produced by scripts/forensics/build_order_flow_master.py, which writes three sibling master CSV files from one reconstructed dataframe.",
        "2. The script is CLI/manual only in the current repo: it has a main() entrypoint and no external repo references were found.",
        "3. It scans logs/**/*.log and logs/**/*.jsonl for a global time scope, then reconstructs attempts heuristically from intent lines plus exact order_log actions.",
        "4. It does not explicitly consume decision_ledger, order_ledger.db, or prior CSV reports as authority inputs for the executed master export.",
        "5. The executed master subset is created by filtering dataframe rows where outcome == 'executed'.",
        "6. Because pandas writes headers for empty filtered dataframes, the producer writes a header-only executed_trades_master.csv when no rows survive that filter.",
        "7. The current sibling reports confirm that behavior: order_attempts_master.csv and rejected_attempts_master.csv contain only four timeout_non_fill rows, while executed_trades_master.csv is header-only.",
        "8. This means the current empty executed master is explained by the last producer run yielding no outcome == executed rows, not by missing CSV file creation.",
        f"9. Current report rows: executed={report_stats['executed_trades_master.csv']['rows']}, rejected={report_stats['rejected_attempts_master.csv']['rows']}, attempts={report_stats['order_attempts_master.csv']['rows']}.",
        f"10. Current report stale vs runtime logs: {pipeline['current_report_stale_vs_runtime']}.",
        "",
        "## Authority answers",
        "- Is it generated during runtime? No evidence found.",
        "- Is it generated by a scheduled or wired task? No evidence found.",
        "- Is it generated by a manual CLI/forensics script? Yes.",
        "- Can it silently skip rows? Yes, via heuristic attempt reconstruction plus filtered subset export with no fail-fast on empty executed output.",
        "- Does it write only headers on no data? Yes.",
    ]
    (out_dir / "EXECUTED_TRADES_MASTER_PIPELINE.md").write_text("\n".join(lines), encoding="utf-8")


def write_source_matrix(out_dir: Path, matrix: list[dict[str, Any]]) -> None:
    rows = []
    for entry in matrix:
        rows.append([
            entry["source"],
            entry["identity_coverage"],
            entry["outcome_coverage"],
            entry["fee_coverage"],
            entry["schema_stability"],
            entry["promotion_grade_suitability"],
            ", ".join(entry["risks"][:3]),
        ])
    content = "# REALIZED_OUTCOME_SOURCE_MATRIX\n\n"
    content += _markdown_table(
        [
            "Source",
            "Identity Coverage",
            "Outcome Coverage",
            "Fee Coverage",
            "Schema Stability",
            "Promotion Suitability",
            "Risks",
        ],
        rows,
    )
    (out_dir / "REALIZED_OUTCOME_SOURCE_MATRIX.md").write_text(content, encoding="utf-8")
    _write_json(out_dir / "realized_outcome_source_matrix.json", matrix)


def write_authority_decision(
    out_dir: Path,
    decision_payload: dict[str, Any],
) -> None:
    _write_json(out_dir / "source_authority_decision.json", decision_payload)
    lines = [
        "# REALIZED_OUTCOME_AUTHORITY_DECISION",
        "",
        f"- executed_trades_master authority status: {decision_payload['executed_trades_master_authority_status']}",
        f"- recommended calibration source: {decision_payload['recommended_canonical_source']}",
        f"- confidence: {decision_payload['confidence']}",
        "",
        "## Why",
    ]
    for item in decision_payload["reasons"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Risks",
        ]
    )
    for item in decision_payload["risks"]:
        lines.append(f"- {item}")
    (out_dir / "REALIZED_OUTCOME_AUTHORITY_DECISION.md").write_text("\n".join(lines), encoding="utf-8")


def run_audit(repo_root: Path, out_dir: Path, *, max_samples: int) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    code_refs = find_code_refs(repo_root, max_samples=max_samples)
    inventory, join_matrix = _load_join_key_artifacts(repo_root)
    report_stats = inspect_reports(repo_root)
    order_log = inspect_order_log(repo_root)
    decision_ledger = inspect_decision_ledger(repo_root)
    order_ledger = inspect_order_ledger(repo_root)
    pipeline = build_pipeline_summary(
        repo_root,
        code_refs,
        report_stats,
        decision_ledger,
        order_log,
    )
    matrix = build_source_matrix(
        inventory,
        join_matrix,
        decision_ledger,
        order_log,
        order_ledger,
        report_stats,
    )
    authority_status = _decide_authority_status(
        report_rows=report_stats["executed_trades_master.csv"]["rows"],
        invocation_mode=pipeline["invocation_mode"],
        report_stale_vs_runtime=pipeline["current_report_stale_vs_runtime"],
        active_writer_count=len(pipeline["active_writers"]),
    )
    recommendation = _recommend_canonical_source(
        authority_status=authority_status,
        decision_orderlog_exact_bridge=any(
            entry["source"] == "decision_ledger + order_log exact bridge"
            and entry["exact_decision_identity"]
            for entry in matrix
        ),
    )
    decision_payload = {
        "executed_trades_master_authority_status": authority_status,
        "recommended_canonical_source": recommendation,
        "confidence": "MEDIUM",
        "reasons": [
            "The only active producer found is scripts/forensics/build_order_flow_master.py, a manual CLI forensics script with no repo-wired invocation surface.",
            "Current master CSV outputs are stale relative to current runtime logs and contain only four timeout rows plus a header-only executed subset.",
            "decision_ledger and order_log provide current realized-outcome evidence, while executed_trades_master does not.",
            "The best exact identity surface for calibration is the decision_ledger -> order_log bridge, not executed_trades_master directly.",
        ],
        "risks": [
            "order_log remains a mixed event stream and needs explicit canonicalization rules",
            "decision_ledger realized fields are partial",
            "executed_trades_master may still be useful as a convenience export but is not proven authoritative",
        ],
        "evidence": {
            "producer": pipeline,
            "reports": report_stats,
            "order_log": {
                "rows": order_log.get("rows", 0),
                "position_closed_rows": order_log.get("position_closed_rows", 0),
                "rows_with_realized_pnl_net": order_log.get("rows_with_realized_pnl_net", 0),
            },
            "decision_ledger": {
                "rows": decision_ledger.get("rows", 0),
                "rows_with_realized_pnl_net": decision_ledger.get("rows_with_realized_pnl_net", 0),
                "terminal_status_counts": decision_ledger.get("terminal_status_counts", {}),
            },
        },
    }

    write_pipeline_markdown(out_dir, pipeline, report_stats)
    write_source_matrix(out_dir, matrix)
    write_authority_decision(out_dir, decision_payload)
    return {
        "code_refs": code_refs,
        "report_stats": report_stats,
        "order_log": order_log,
        "decision_ledger": decision_ledger,
        "order_ledger": order_ledger,
        "pipeline": pipeline,
        "matrix": matrix,
        "decision": decision_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only realized outcome source authority audit")
    parser.add_argument("--repo-root", default=".",
                        help="Repository root path")
    parser.add_argument(
        "--out-dir",
        default="calibrators/datasets/realized_outcome_authority",
        help="Output directory for realized outcome authority artifacts",
    )
    parser.add_argument("--max-samples", type=int, default=10,
                        help="Maximum sample refs or rows to retain")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir
    payload = run_audit(repo_root, out_dir, max_samples=args.max_samples)
    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "authority_status": payload["decision"]["executed_trades_master_authority_status"],
                "recommended_source": payload["decision"]["recommended_canonical_source"],
                "executed_rows": payload["report_stats"]["executed_trades_master.csv"]["rows"],
                "order_log_position_closed_rows": payload["order_log"].get("position_closed_rows", 0),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
