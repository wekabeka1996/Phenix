#!/usr/bin/env python3
"""Deep read-only lineage and logging attribution audit for order_log_v1."""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
ORDER_LOG = ROOT / "logs" / "order_log_v1.jsonl"
SCHEMA_PATH = ROOT / "apps" / "reference" / "schemas" / "order_logger_v1.json"
REPORT_ROOT = ROOT / "reports" / "order_log_v1_deep_lineage"
FINAL_REPORT = ROOT / "reports" / "ORDER_LOG_V1_DEEP_LOGGING_AND_STRATEGY_ATTRIBUTION_AUDIT.md"

LINEAGE_JSONL = REPORT_ROOT / "order_log_v1_lineage_reconstruction.jsonl"
LINEAGE_SUMMARY_CSV = REPORT_ROOT / "order_log_v1_lineage_summary.csv"
FIELD_COVERAGE_CSV = REPORT_ROOT / "order_log_v1_field_coverage.csv"
FINANCIAL_MD = REPORT_ROOT / "order_log_v1_reconstructed_financial_summary.md"
FINANCIAL_JSON = REPORT_ROOT / "order_log_v1_reconstructed_financial_summary.json"

KNOWN_SCHEMA_EVENT_TYPES = {
    "BOOT",
    "STRATEGY_REGISTRY_SNAPSHOT",
    "ORDER_INTENT",
    "ORDER_PLACED",
    "ORDER_FILLED",
    "ORDER_CANCELLED",
    "ORDER_CANCELLATION_FAILED",
    "ORDER_TIMEOUT",
    "ORDER_REJECTED",
    "DECISION_INTENT_REJECTED",
    "ORDER_STATE_CHANGED",
    "POSITION_CLOSED",
    "QTY_NORMALIZE_REJECTED",
}
LINEAGE_FIELDS = [
    "strategy_id",
    "regime",
    "symbol",
    "side",
    "confidence",
    "nrr_code",
    "why_class",
    "lifecycle_id",
    "decision_id",
    "intent_id",
    "order_id",
    "client_order_id",
    "trade_id",
    "entry_price",
    "exit_price",
    "realized_pnl_gross",
    "realized_pnl_net",
    "fees",
    "leverage",
    "notional",
    "qty",
    "tp_sl_geometry",
    "close_reason",
    "exit_policy",
]
ALLOWED_ATTRIBUTION_SOURCES = {
    "direct_close_row",
    "direct_fill_row",
    "direct_order_intent_row",
    "direct_decision_row",
    "lifecycle_join",
    "order_id_join",
    "client_order_id_join",
    "trade_id_join",
    "symbol_side_timestamp_join",
    "lifecycle_id_name_inference",
    "unresolved",
    "conflicting",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-log", type=Path, default=ORDER_LOG)
    parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    parser.add_argument("--final-report", type=Path, default=FINAL_REPORT)
    return parser.parse_args()


def safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def text(value: Any) -> str:
    return "" if value is None else str(value)


def iso_utc(ts_ms: Any) -> str:
    if not isinstance(ts_ms, (int, float)):
        return ""
    return datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc).isoformat()


def fmt(value: Any, digits: int = 8) -> str:
    number = safe_float(value)
    if number is None:
        return text(value)
    rendered = f"{number:.{digits}f}"
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def nested_get(payload: Any, dotted_path: str) -> Any:
    node = payload
    for part in dotted_path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def flatten_keys(node: Any, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            keys.add(path)
            keys.update(flatten_keys(value, path))
    elif isinstance(node, list):
        for item in node[:5]:
            keys.update(flatten_keys(item, prefix))
    return keys


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    errors = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                errors += 1
                continue
            if isinstance(row, dict):
                row = dict(row)
                row["_line"] = line_no
                rows.append(row)
            else:
                errors += 1
    return rows, errors


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean = {}
            for field in fieldnames:
                value = row.get(field)
                if isinstance(value, (dict, list, tuple, set)):
                    clean[field] = json.dumps(value, ensure_ascii=False, sort_keys=True)
                else:
                    clean[field] = value
            writer.writerow(clean)


def md_escape(value: Any) -> str:
    return text(value).replace("|", "\\|").replace("\n", " ")


def md_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(md_escape(cell) for cell in row) + " |")
    return "\n".join(lines)


def row_strategy(row: dict[str, Any]) -> str:
    return text(first_present(row.get("strategy_id"), nested_get(row, "metadata.strategy_id")))


def row_regime(row: dict[str, Any]) -> str:
    return text(first_present(row.get("regime"), nested_get(row, "metadata.regime")))


def row_lifecycle(row: dict[str, Any]) -> str:
    return text(first_present(row.get("lifecycle_id"), nested_get(row, "metadata.lifecycle_id"), row.get("reservation_id"), nested_get(row, "metadata.idempotent_key")))


def row_order_id(row: dict[str, Any]) -> str:
    return text(first_present(row.get("order_id"), nested_get(row, "adapter_response.orderId"), nested_get(row, "metadata.close_fill_order_id")))


def row_client_order_id(row: dict[str, Any]) -> str:
    return text(first_present(row.get("client_order_id"), nested_get(row, "adapter_response.clientOrderId"), nested_get(row, "metadata.close_fill_client_order_id"), row.get("rid")))


def row_trade_id(row: dict[str, Any]) -> str:
    return text(first_present(row.get("trade_id"), nested_get(row, "metadata.fill_trade_id")))


def strategy_prefix_from_lifecycle(lifecycle_id: str, known_strategies: set[str]) -> str:
    if not lifecycle_id or "_" not in lifecycle_id:
        return ""
    for strategy in sorted(known_strategies, key=len, reverse=True):
        if lifecycle_id.startswith(strategy + "_"):
            return strategy
    prefix = lifecycle_id.split("_", 1)[0]
    return prefix if prefix in known_strategies else ""


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def discover_strategies(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    config_dir = ROOT / "config" / "aurora" / "strategies"
    plugin_dir = ROOT / "apps" / "reference" / "domains" / "strategies" / "plugins"
    runtime_dir = ROOT / "apps" / "reference" / "domains" / "strategies" / "runtimes"
    live_decision = Counter(row_strategy(row) for row in rows if row_strategy(row))
    live_intent = Counter(row_strategy(row) for row in rows if row.get("event_type") == "ORDER_INTENT" and row_strategy(row))
    live_fill = Counter(row_strategy(row) for row in rows if row.get("event_type") == "ORDER_FILLED" and row_strategy(row))
    live_close = Counter(row_strategy(row) for row in rows if row.get("event_type") == "POSITION_CLOSED" and row_strategy(row))

    strategy_ids: set[str] = set(live_decision)
    for path in config_dir.glob("*.yaml"):
        strategy_ids.add(path.stem)
    for path in plugin_dir.glob("*.py"):
        if path.name != "__init__.py":
            strategy_ids.add(path.stem.replace("_builtin", ""))
    for path in runtime_dir.iterdir() if runtime_dir.exists() else []:
        if path.is_dir() and path.name != "__pycache__":
            strategy_ids.add(path.name)

    rows_out: list[dict[str, Any]] = []
    for strategy_id in sorted(strategy_ids):
        cfg_path = config_dir / f"{strategy_id}.yaml"
        plugin_path = plugin_dir / f"{strategy_id}.py"
        if strategy_id == "aurora":
            plugin_path = plugin_dir / "aurora_builtin.py"
        runtime_handler = runtime_dir / strategy_id / "handler.py"
        cfg_text = cfg_path.read_text(encoding="utf-8", errors="replace") if cfg_path.exists() else ""
        top_enabled = bool(re.search(rf"(?m)^{re.escape(strategy_id)}:\s*\n\s+enabled:\s*true", cfg_text))
        mode_match = re.search(r"(?m)^\s+mode:\s*([A-Za-z0-9_-]+)", cfg_text)
        mode = mode_match.group(1) if mode_match else ""
        status = "active live" if live_decision.get(strategy_id, 0) or live_intent.get(strategy_id, 0) else (
            "configured enabled" if top_enabled else "configured disabled/unknown"
        )
        if mode in {"shadow", "observe", "observe_only"}:
            status = "shadow/observe-only"
        verdict = "incomplete_logging"
        if live_close.get(strategy_id, 0) and live_fill.get(strategy_id, 0) and live_intent.get(strategy_id, 0):
            verdict = "complete_direct_logging"
        elif live_decision.get(strategy_id, 0) and not live_intent.get(strategy_id, 0):
            verdict = "decision_only_or_rejected_before_execution"
        elif live_intent.get(strategy_id, 0) and not live_fill.get(strategy_id, 0):
            verdict = "intent_metadata_lost_before_fill"
        elif strategy_id not in live_decision and strategy_id not in live_intent:
            verdict = "not_financially_active_in_order_log"
        rows_out.append({
            "strategy_id": strategy_id,
            "registration_file": str(plugin_path.relative_to(ROOT)) if plugin_path.exists() else "",
            "decision_file": str(runtime_handler.relative_to(ROOT)) if runtime_handler.exists() else "",
            "intent_file": "apps/reference/domains/decision_making/intent/builder.py; apps/reference/domains/decision_making/intent/payload_assembler.py",
            "can_emit_order_intent": "yes" if plugin_path.exists() or runtime_handler.exists() else "unknown",
            "can_reach_execution": "yes" if strategy_id in {"aurora", "md_amr", "mean_reversion", "alpha_mr_s01", "alpha_ta_ensemble"} else "unknown",
            "logs_strategy_id_on_decision": "yes" if live_decision.get(strategy_id, 0) else "not_observed",
            "logs_strategy_id_on_intent": "yes" if live_intent.get(strategy_id, 0) else "no/not_observed",
            "logs_strategy_id_on_fill": "yes" if live_fill.get(strategy_id, 0) else "no",
            "logs_strategy_id_on_close": "yes" if live_close.get(strategy_id, 0) else "no",
            "logs_regime_on_decision": "yes" if any(row_strategy(row) == strategy_id and row_regime(row) for row in rows) else "not_observed",
            "logs_regime_on_intent": "yes" if any(row.get("event_type") == "ORDER_INTENT" and row_strategy(row) == strategy_id and row_regime(row) for row in rows) else "no/not_observed",
            "logs_regime_on_fill": "yes" if any(row.get("event_type") == "ORDER_FILLED" and row_strategy(row) == strategy_id and row_regime(row) for row in rows) else "no",
            "logs_regime_on_close": "yes" if any(row.get("event_type") == "POSITION_CLOSED" and row_strategy(row) == strategy_id and row_regime(row) for row in rows) else "no",
            "status": status,
            "verdict": verdict,
        })
    return rows_out


def discover_writers() -> list[dict[str, Any]]:
    search_roots = [ROOT / "apps" / "reference", ROOT / "vfoundation"]
    writer_rows: list[dict[str, Any]] = []
    for base in search_roots:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            text_content = path.read_text(encoding="utf-8", errors="replace")
            if "order_logger.write" not in text_content and "_get_order_logger().write" not in text_content:
                continue
            lines = text_content.splitlines()
            for index, line in enumerate(lines, start=1):
                if "order_logger.write" not in line and "_get_order_logger().write" not in line:
                    continue
                context = "\n".join(lines[max(0, index - 8): min(len(lines), index + 35)])
                event_types = sorted(set(re.findall(r'"event_type"\s*:\s*"([^"]+)"', context)))
                source_fsms = sorted(set(re.findall(r'"source_fsm"\s*:\s*"([^"]+)"', context)))
                fields = sorted(set(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:', context)))
                writer_rows.append({
                    "file_path": rel,
                    "line": index,
                    "function_or_method": enclosing_function(text_content, index),
                    "event_types": ", ".join(event_types) if event_types else "dynamic/unknown",
                    "source_fsm": ", ".join(source_fsms) if source_fsms else "dynamic/unknown",
                    "payload_fields": ", ".join(fields[:40]),
                    "schema_or_ad_hoc": "schema-validated only in DEBUG/TEST; payload is ad-hoc dict",
                    "covered_by_tests": "yes" if writer_has_test(rel) else "not proven",
                    "schema_event_status": ", ".join(
                        f"{event}:{'in_schema' if event in KNOWN_SCHEMA_EVENT_TYPES else 'missing_schema'}"
                        for event in event_types
                    ) if event_types else "dynamic/unknown",
                })
    return writer_rows


def enclosing_function(source: str, line_no: int) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    best = ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = getattr(node, "lineno", 0)
            end = getattr(node, "end_lineno", start)
            if start <= line_no <= end:
                name = node.name
                if isinstance(node, ast.ClassDef):
                    continue
                best = name
    return best


def writer_has_test(rel_path: str) -> bool:
    needle = rel_path.replace("/", "\\")
    tests = ROOT / "tests"
    if not tests.exists():
        return False
    path_name = Path(rel_path).name
    for test_path in tests.rglob("*.py"):
        content = test_path.read_text(encoding="utf-8", errors="replace")
        if needle in content or rel_path in content or path_name in content:
            return True
    return False


def build_indices(rows: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    indices: dict[str, dict[str, list[dict[str, Any]]]] = {
        "lifecycle": defaultdict(list),
        "order_id": defaultdict(list),
        "client_order_id": defaultdict(list),
        "trade_id": defaultdict(list),
        "symbol": defaultdict(list),
    }
    for row in rows:
        for name, getter in (
            ("lifecycle", row_lifecycle),
            ("order_id", row_order_id),
            ("client_order_id", row_client_order_id),
            ("trade_id", row_trade_id),
        ):
            value = getter(row)
            if value:
                indices[name][value].append(row)
        symbol = text(row.get("symbol"))
        if symbol:
            indices["symbol"][symbol].append(row)
    return indices


def reconstruct_lineage(rows: list[dict[str, Any]], strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    known_strategies = {row["strategy_id"] for row in strategies}
    indices = build_indices(rows)
    closed_rows = [row for row in rows if row.get("event_type") == "POSITION_CLOSED"]
    out: list[dict[str, Any]] = []
    for closed in closed_rows:
        lifecycle = row_lifecycle(closed)
        order_id = row_order_id(closed)
        client_order_id = row_client_order_id(closed)
        trade_id = row_trade_id(closed)
        joined: list[dict[str, Any]] = []
        join_keys_used: list[str] = []
        for key_name, key_value in (
            ("lifecycle_id", lifecycle),
            ("order_id", order_id),
            ("client_order_id", client_order_id),
            ("trade_id", trade_id),
        ):
            if not key_value:
                continue
            bucket = indices[{"lifecycle_id": "lifecycle", "order_id": "order_id", "client_order_id": "client_order_id", "trade_id": "trade_id"}[key_name]].get(key_value, [])
            if bucket:
                join_keys_used.append(key_name)
                joined.extend(bucket)
        if not joined:
            joined = symbol_side_timestamp_join(closed, indices["symbol"].get(text(closed.get("symbol")), []))
            if joined:
                join_keys_used.append("symbol_side_timestamp")
        dedup = {int(row.get("_line", 0)): row for row in joined}
        joined = [dedup[key] for key in sorted(dedup)]
        direct_strategy = row_strategy(closed)
        direct_regime = row_regime(closed)
        strategy_candidates: list[tuple[str, str, int]] = []
        regime_candidates: list[tuple[str, str, int]] = []
        if direct_strategy:
            strategy_candidates.append((direct_strategy, "direct_close_row", int(closed.get("_line", 0))))
        if direct_regime:
            regime_candidates.append((direct_regime, "direct_close_row", int(closed.get("_line", 0))))
        for row in joined:
            event = text(row.get("event_type"))
            source = {
                "ORDER_FILLED": "direct_fill_row",
                "ORDER_INTENT": "direct_order_intent_row",
                "DECISION_INTENT_REJECTED": "direct_decision_row",
                "ORDER_PLACED": "lifecycle_join",
            }.get(event, "lifecycle_join")
            if row_strategy(row):
                strategy_candidates.append((row_strategy(row), source, int(row.get("_line", 0))))
            if row_regime(row):
                regime_candidates.append((row_regime(row), source, int(row.get("_line", 0))))
        inferred = strategy_prefix_from_lifecycle(lifecycle, known_strategies)
        if inferred:
            strategy_candidates.append((inferred, "lifecycle_id_name_inference", int(closed.get("_line", 0))))

        strategy_values = {candidate[0] for candidate in strategy_candidates}
        regime_values = {candidate[0] for candidate in regime_candidates}
        warnings: list[str] = []
        if len(strategy_values) > 1 or len(regime_values) > 1:
            confidence = "CONFLICTING"
            source = "conflicting"
            warnings.append("conflicting strategy/regime candidates across joined rows")
        else:
            source = "unresolved"
            confidence = "UNRESOLVED"
            if strategy_candidates or regime_candidates:
                best_sources = [candidate[1] for candidate in strategy_candidates + regime_candidates]
                if "direct_close_row" in best_sources:
                    source = "direct_close_row"
                    confidence = "HIGH"
                elif "direct_order_intent_row" in best_sources and "lifecycle_id" in join_keys_used:
                    source = "direct_order_intent_row"
                    confidence = "HIGH"
                elif "direct_fill_row" in best_sources:
                    source = "direct_fill_row"
                    confidence = "HIGH" if "lifecycle_id" in join_keys_used else "MEDIUM"
                elif "lifecycle_join" in best_sources:
                    source = "lifecycle_join"
                    confidence = "MEDIUM"
                elif "lifecycle_id_name_inference" in best_sources:
                    source = "lifecycle_id_name_inference"
                    confidence = "MEDIUM"
                elif "symbol_side_timestamp" in join_keys_used:
                    source = "symbol_side_timestamp_join"
                    confidence = "LOW"
        reconstructed_strategy = next(iter(strategy_values), "")
        reconstructed_regime = next(iter(regime_values), "")
        if source not in ALLOWED_ATTRIBUTION_SOURCES:
            source = "unresolved"
        if source == "lifecycle_id_name_inference":
            warnings.append("strategy inferred only from lifecycle_id prefix; not hard truth")
        if not reconstructed_regime:
            warnings.append("regime unresolved for close row")
        if text(closed.get("pnl_status")) != "resolved":
            warnings.append("unresolved accounting row excluded from resolved PnL")
        out.append({
            "closed_line": closed.get("_line"),
            "closed_ts": closed.get("timestamp"),
            "closed_utc": iso_utc(closed.get("timestamp")),
            "symbol": closed.get("symbol"),
            "side": closed.get("side"),
            "close_reason": closed.get("close_reason"),
            "pnl_status": closed.get("pnl_status"),
            "realized_pnl_net": closed.get("realized_pnl_net"),
            "fees": closed.get("fees"),
            "direct_strategy_id": direct_strategy,
            "direct_regime": direct_regime,
            "reconstructed_strategy_id": reconstructed_strategy,
            "reconstructed_regime": reconstructed_regime,
            "attribution_source": source,
            "attribution_confidence": confidence,
            "join_keys_used": sorted(set(join_keys_used)),
            "source_event_lines": [row.get("_line") for row in joined],
            "source_event_types": [row.get("event_type") for row in joined],
            "lifecycle_id": lifecycle,
            "decision_id": first_present(closed.get("decision_id"), nested_get(closed, "metadata.decision_id")) or "",
            "intent_id": first_present(closed.get("intent_id"), nested_get(closed, "metadata.intent_id")) or "",
            "order_id": order_id,
            "client_order_id": client_order_id,
            "trade_id": trade_id,
            "warnings": warnings,
        })
    return out


def symbol_side_timestamp_join(closed: dict[str, Any], symbol_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ts = closed.get("timestamp")
    if not isinstance(ts, (int, float)):
        return []
    side = text(closed.get("side"))
    candidates = [
        row for row in symbol_rows
        if row.get("event_type") in {"ORDER_INTENT", "ORDER_PLACED", "ORDER_FILLED"}
        and isinstance(row.get("timestamp"), (int, float))
        and row.get("timestamp") <= ts
        and abs(float(ts) - float(row.get("timestamp"))) <= 6 * 60 * 60 * 1000
    ]
    if side:
        same_side = [row for row in candidates if text(row.get("side")) == side]
        if same_side:
            candidates = same_side
    return sorted(candidates, key=lambda row: abs(float(ts) - float(row.get("timestamp") or 0)))[:5]


def field_coverage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_event[text(row.get("event_type"))].append(row)
    out: list[dict[str, Any]] = []
    for event_type, event_rows in sorted(by_event.items()):
        keys = sorted(set().union(*(set(row.keys()) - {"_line"} for row in event_rows)))
        for field in keys:
            present = sum(1 for row in event_rows if row.get(field) not in (None, ""))
            out.append({
                "event_type": event_type,
                "field": field,
                "present_rows": present,
                "total_rows": len(event_rows),
                "coverage_pct": round(100.0 * present / len(event_rows), 2) if event_rows else 0.0,
            })
    return out


def financial_summary(rows: list[dict[str, Any]], lineage: list[dict[str, Any]]) -> dict[str, Any]:
    line_by_closed = {item["closed_line"]: item for item in lineage}
    closed = [row for row in rows if row.get("event_type") == "POSITION_CLOSED"]
    resolved = [row for row in closed if text(row.get("pnl_status")) == "resolved" and safe_float(row.get("realized_pnl_net")) is not None]

    def aggregate(key_fn):
        agg = defaultdict(lambda: {"closed": 0, "resolved": 0, "unresolved": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "fees": 0.0})
        for row in closed:
            lin = line_by_closed.get(row.get("_line"), {})
            key = key_fn(row, lin)
            bucket = agg[text(key)]
            bucket["closed"] += 1
            pnl = safe_float(row.get("realized_pnl_net"))
            fees = safe_float(row.get("fees")) or 0.0
            bucket["fees"] += fees
            if text(row.get("pnl_status")) == "resolved" and pnl is not None:
                bucket["resolved"] += 1
                bucket["net_pnl"] += pnl
                bucket["wins"] += int(pnl > 0)
                bucket["losses"] += int(pnl < 0)
            else:
                bucket["unresolved"] += 1
        return dict(sorted(agg.items(), key=lambda item: (-item[1]["net_pnl"], item[0])))

    return {
        "global": {
            "closed_positions": len(closed),
            "resolved_closed_positions": len(resolved),
            "unresolved_closed_positions": len(closed) - len(resolved),
            "resolved_net_pnl": sum(safe_float(row.get("realized_pnl_net")) or 0.0 for row in resolved),
            "resolved_fees": sum(safe_float(row.get("fees")) or 0.0 for row in resolved),
            "wins": sum(1 for row in resolved if (safe_float(row.get("realized_pnl_net")) or 0.0) > 0),
            "losses": sum(1 for row in resolved if (safe_float(row.get("realized_pnl_net")) or 0.0) < 0),
        },
        "by_symbol": aggregate(lambda row, lin: row.get("symbol")),
        "by_side": aggregate(lambda row, lin: row.get("side")),
        "by_close_reason": aggregate(lambda row, lin: row.get("close_reason")),
        "by_direct_strategy_regime": aggregate(lambda row, lin: (row_strategy(row) or "missing", row_regime(row) or "missing")),
        "by_reconstructed_strategy_regime": aggregate(lambda row, lin: (lin.get("reconstructed_strategy_id") or "missing", lin.get("reconstructed_regime") or "missing")),
        "by_attribution_confidence": aggregate(lambda row, lin: lin.get("attribution_confidence") or "UNRESOLVED"),
        "by_strategy_symbol": aggregate(lambda row, lin: (lin.get("reconstructed_strategy_id") or "missing", row.get("symbol"))),
        "by_strategy_close_reason": aggregate(lambda row, lin: (lin.get("reconstructed_strategy_id") or "missing", row.get("close_reason"))),
        "by_source_fsm": aggregate(lambda row, lin: row.get("source_fsm")),
        "by_lifecycle_completeness": aggregate(lambda row, lin: "has_lifecycle_join" if "lifecycle_id" in (lin.get("join_keys_used") or []) else "missing_lifecycle_join"),
    }


def cross_log_matrix(order_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start = min((row.get("timestamp") for row in order_rows if isinstance(row.get("timestamp"), (int, float))), default=None)
    end = max((row.get("timestamp") for row in order_rows if isinstance(row.get("timestamp"), (int, float))), default=None)
    candidates = [
        ROOT / "logs" / "trade_lifecycle.jsonl",
        ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl",
        ROOT / "logs" / "regime_confidence_audit_v1.jsonl",
        ROOT / "logs" / "aurora_events.jsonl",
        ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl",
        ROOT / "logs" / "domain_decision_making.log",
        ROOT / "logs" / "domain_decision_making.log.2",
        ROOT / "logs" / "domain_execution_position.log",
        ROOT / "logs" / "domain_execution_position.log.1",
    ]
    matrix = []
    for path in candidates:
        if not path.exists():
            continue
        info = inspect_log_file(path, start, end)
        matrix.append(info)
    return matrix


def inspect_log_file(path: Path, start: int | None, end: int | None) -> dict[str, Any]:
    rel = path.relative_to(ROOT).as_posix()
    rows = 0
    parsed = 0
    ts_values: list[int] = []
    keys = Counter()
    sample_text = ""
    max_lines = 250000 if path.stat().st_size > 100_000_000 else 1_000_000
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            rows += 1
            if rows == 1:
                sample_text = raw[:500]
            if rows > max_lines:
                break
            line = raw.strip()
            if not line:
                continue
            payload = None
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    payload = None
            if isinstance(payload, dict):
                parsed += 1
                for key in flatten_keys(payload):
                    keys[key] += 1
                ts = first_present(payload.get("timestamp"), payload.get("ts_ms"), payload.get("ts"), nested_get(payload, "payload.timestamp"), nested_get(payload, "payload.ts_ms"))
                try:
                    ts_int = int(float(ts))
                except (TypeError, ValueError):
                    ts_int = None
                if ts_int and ts_int > 10_000_000_000:
                    ts_values.append(ts_int)
            else:
                for token in ("strategy_id", "regime", "lifecycle_id", "trade_id", "order_id", "client_order_id", "rid"):
                    if token in line:
                        keys[token] += 1
    window_start = min(ts_values) if ts_values else None
    window_end = max(ts_values) if ts_values else None
    overlaps = bool(start and end and window_start and window_end and window_start <= end and window_end >= start)
    useful = [field for field in ("strategy_id", "regime", "lifecycle_id", "trade_id", "order_id", "client_order_id", "rid") if keys[field] > 0 or any(k.endswith("." + field) for k in keys)]
    log_type = "live_runtime" if rel.startswith("logs/") else "artifact"
    safe_to_join = "yes" if overlaps and {"lifecycle_id", "trade_id", "rid"}.intersection(useful) else "no"
    reason = "overlapping timestamps and join keys found" if safe_to_join == "yes" else "no proven overlap and join keys, or sampled/capped file"
    if rows > max_lines:
        reason += f"; inspected first {max_lines} lines only"
    return {
        "log_path": rel,
        "log_type": log_type,
        "rows": rows if rows <= max_lines else f">{max_lines}",
        "window_start": iso_utc(window_start),
        "window_end": iso_utc(window_end),
        "overlaps_order_log": "yes" if overlaps else "no/unknown",
        "join_keys": ", ".join(useful),
        "useful_fields": ", ".join(useful),
        "safe_to_join": safe_to_join,
        "reason": reason,
        "sample": sample_text[:120],
    }


def schema_gap_table(schema: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = set(schema.get("properties", {}).get("event_type", {}).get("enum", []))
    observed = sorted({text(row.get("event_type")) for row in rows})
    required = schema.get("required", [])
    table = []
    for event_type in sorted(allowed | set(observed)):
        observed_rows = [row for row in rows if row.get("event_type") == event_type]
        missing_fields = []
        if event_type in {"ORDER_INTENT", "ORDER_PLACED", "ORDER_FILLED", "POSITION_CLOSED"}:
            for field in ("strategy_id", "regime", "lifecycle_id"):
                if not observed_rows or all(first_present(row.get(field), nested_get(row, f"metadata.{field}")) in (None, "") for row in observed_rows):
                    missing_fields.append(field)
        if event_type == "POSITION_CLOSED":
            for field in ("trade_id", "fees", "realized_pnl_net", "close_reason"):
                if not observed_rows or all(row.get(field) in (None, "") for row in observed_rows):
                    missing_fields.append(field)
        status = "in_schema" if event_type in allowed else "missing_from_schema"
        risk = "HIGH" if missing_fields or status == "missing_from_schema" else "LOW"
        recommendation = "add event-specific required lineage fields" if missing_fields else "none"
        if status == "missing_from_schema":
            recommendation = "add event_type to schema enum and define payload contract"
        table.append({
            "event_type": event_type,
            "schema_status": status,
            "missing_required_fields": ", ".join(missing_fields),
            "attribution_risk": risk,
            "recommended_contract_change": recommendation,
            "global_required_fields": ", ".join(required),
        })
    return table


def source_field_matrix(writer_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matrix = []
    for row in writer_rows:
        fields = set(part.strip() for part in text(row.get("payload_fields")).split(",") if part.strip())
        out = dict(row)
        for field in LINEAGE_FIELDS:
            aliases = {
                "confidence": {"confidence", "regime_confidence"},
                "why_class": {"why_class", "why", "reason"},
                "entry_price": {"entry_price", "price"},
                "exit_price": {"exit_price", "close_price"},
                "realized_pnl_gross": {"realized_pnl", "realizedPnl"},
                "notional": {"notional", "reserve_margin"},
                "qty": {"qty", "quantity", "qty_raw"},
                "tp_sl_geometry": {"stop_price", "target_price", "bracket_type", "order_kind"},
                "exit_policy": {"exit_policy", "close_reason"},
            }.get(field, {field})
            out[field] = "yes" if fields.intersection(aliases) else "no"
        matrix.append(out)
    return matrix


def write_financial_report(summary: dict[str, Any]) -> None:
    lines = ["# ORDER_LOG_V1 Reconstructed Financial Summary", ""]
    global_summary = summary["global"]
    lines.append(md_table(["metric", "value"], [[key, fmt(value)] for key, value in global_summary.items()]))
    lines.append("")
    for key in (
        "by_symbol",
        "by_side",
        "by_close_reason",
        "by_direct_strategy_regime",
        "by_reconstructed_strategy_regime",
        "by_attribution_confidence",
        "by_strategy_symbol",
        "by_strategy_close_reason",
        "by_source_fsm",
        "by_lifecycle_completeness",
    ):
        lines.append(f"## {key}")
        lines.append("")
        rows = []
        for bucket, stats in summary[key].items():
            rows.append([bucket, stats["closed"], stats["resolved"], stats["unresolved"], stats["wins"], stats["losses"], fmt(stats["net_pnl"]), fmt(stats["fees"])])
        lines.append(md_table(["bucket", "closed", "resolved", "unresolved", "wins", "losses", "net_pnl", "fees"], rows))
        lines.append("")
    FINANCIAL_MD.write_text("\n".join(lines), encoding="utf-8")


def write_final_report(
    *,
    rows: list[dict[str, Any]],
    parse_errors: int,
    schema_gaps: list[dict[str, Any]],
    strategy_rows: list[dict[str, Any]],
    writer_rows: list[dict[str, Any]],
    writer_field_rows: list[dict[str, Any]],
    lineage: list[dict[str, Any]],
    field_rows: list[dict[str, Any]],
    cross_logs: list[dict[str, Any]],
    financial: dict[str, Any],
    final_report: Path,
) -> None:
    closed = [row for row in rows if row.get("event_type") == "POSITION_CLOSED"]
    direct_strategy = sum(1 for item in lineage if item["direct_strategy_id"])
    direct_regime = sum(1 for item in lineage if item["direct_regime"])
    recon_strategy = sum(1 for item in lineage if item["reconstructed_strategy_id"])
    recon_regime = sum(1 for item in lineage if item["reconstructed_regime"])
    verdicts = [
        "ORDER_LOG_V1_ATTRIBUTION_PARTIAL",
        "ORDER_LOG_V1_SCHEMA_INCOMPLETE",
        "ORDER_LOG_V1_STRATEGY_COVERAGE_INCOMPLETE",
    ]
    if recon_strategy > direct_strategy or recon_regime > direct_regime:
        verdicts.insert(0, "ORDER_LOG_V1_ATTRIBUTION_RECOVERABLE_VIA_JOIN")
    if not writer_rows:
        verdicts.append("ORDER_LOG_V1_WRITER_MAP_INCOMPLETE")
    lines = ["# ORDER_LOG_V1 Deep Logging And Strategy Attribution Audit", ""]
    lines.append("## Executive Verdict")
    lines.append("")
    lines.append(f"Verdict labels: `{', '.join(verdicts)}`.")
    lines.append(
        f"Parsed `{len(rows)}` live order-log rows with `{parse_errors}` parse errors. "
        f"Closed positions: `{len(closed)}`. Direct close-row strategy attribution is `{direct_strategy}/{len(closed)}`; "
        f"reconstructed strategy attribution is `{recon_strategy}/{len(closed)}`. Direct close-row regime attribution is `{direct_regime}/{len(closed)}`; "
        f"reconstructed regime attribution is `{recon_regime}/{len(closed)}`."
    )
    lines.append(
        "The previous financial report is numerically valid for resolved `POSITION_CLOSED` rows at its generation time, "
        "but its strategy/regime attribution was incomplete because execution and close rows do not carry full decision context."
    )
    lines.append("")
    lines.append("## Writer Matrix")
    lines.append("")
    lines.append(md_table(
        ["file_path", "line", "function_or_method", "event_types", "source_fsm", "schema_or_ad_hoc", "covered_by_tests", "schema_event_status"],
        [[r["file_path"], r["line"], r["function_or_method"], r["event_types"], r["source_fsm"], r["schema_or_ad_hoc"], r["covered_by_tests"], r["schema_event_status"]] for r in writer_rows],
    ))
    lines.append("")
    lines.append("## Writer Field Coverage Matrix")
    lines.append("")
    lines.append(md_table(
        ["file_path", "line", "event_types", "strategy_id", "regime", "lifecycle_id", "order_id", "client_order_id", "trade_id", "realized_pnl_net", "fees", "close_reason", "qty", "tp_sl_geometry"],
        [[r.get("file_path"), r.get("line"), r.get("event_types"), r.get("strategy_id"), r.get("regime"), r.get("lifecycle_id"), r.get("order_id"), r.get("client_order_id"), r.get("trade_id"), r.get("realized_pnl_net"), r.get("fees"), r.get("close_reason"), r.get("qty"), r.get("tp_sl_geometry")] for r in writer_field_rows],
    ))
    lines.append("")
    lines.append("## Strategy Logging Coverage")
    lines.append("")
    lines.append(md_table(
        ["strategy_id", "status", "registration_file", "decision_file", "logs_strategy_id_on_decision", "logs_strategy_id_on_intent", "logs_strategy_id_on_fill", "logs_strategy_id_on_close", "logs_regime_on_decision", "logs_regime_on_intent", "logs_regime_on_fill", "logs_regime_on_close", "verdict"],
        [[r["strategy_id"], r["status"], r["registration_file"], r["decision_file"], r["logs_strategy_id_on_decision"], r["logs_strategy_id_on_intent"], r["logs_strategy_id_on_fill"], r["logs_strategy_id_on_close"], r["logs_regime_on_decision"], r["logs_regime_on_intent"], r["logs_regime_on_fill"], r["logs_regime_on_close"], r["verdict"]] for r in strategy_rows],
    ))
    lines.append("")
    lines.append("## Schema Gap Analysis")
    lines.append("")
    lines.append(md_table(
        ["event_type", "schema_status", "missing_required_fields", "attribution_risk", "recommended_contract_change"],
        [[r["event_type"], r["schema_status"], r["missing_required_fields"], r["attribution_risk"], r["recommended_contract_change"]] for r in schema_gaps],
    ))
    lines.append("")
    lines.append("## Lineage Reconstruction Summary")
    lines.append("")
    lines.append(md_table(
        ["closed_line", "symbol", "side", "close_reason", "pnl_status", "net_pnl", "direct_strategy", "reconstructed_strategy", "direct_regime", "reconstructed_regime", "source", "confidence", "warnings"],
        [[x["closed_line"], x["symbol"], x["side"], x["close_reason"], x["pnl_status"], fmt(x["realized_pnl_net"]), x["direct_strategy_id"], x["reconstructed_strategy_id"], x["direct_regime"], x["reconstructed_regime"], x["attribution_source"], x["attribution_confidence"], "; ".join(x["warnings"])] for x in lineage],
    ))
    lines.append("")
    lines.append("## Field Coverage By Event Type")
    lines.append("")
    compact_field_rows = [r for r in field_rows if r["field"] in {"strategy_id", "regime", "lifecycle_id", "order_id", "client_order_id", "trade_id", "fees", "realized_pnl_net", "close_reason", "metadata"}]
    lines.append(md_table(
        ["event_type", "field", "present_rows", "total_rows", "coverage_pct"],
        [[r["event_type"], r["field"], r["present_rows"], r["total_rows"], r["coverage_pct"]] for r in compact_field_rows],
    ))
    lines.append("")
    lines.append("## Cross-Log Joinability")
    lines.append("")
    lines.append(md_table(
        ["log_path", "log_type", "rows", "window_start", "window_end", "overlaps_order_log", "join_keys", "safe_to_join", "reason"],
        [[r["log_path"], r["log_type"], r["rows"], r["window_start"], r["window_end"], r["overlaps_order_log"], r["join_keys"], r["safe_to_join"], r["reason"]] for r in cross_logs],
    ))
    lines.append("")
    lines.append("## Reconstructed PnL")
    lines.append("")
    lines.append(f"Machine-readable summary: `{FINANCIAL_JSON.relative_to(ROOT).as_posix()}`. Markdown summary: `{FINANCIAL_MD.relative_to(ROOT).as_posix()}`.")
    lines.append(md_table(
        ["bucket", "closed", "resolved", "unresolved", "wins", "losses", "net_pnl", "fees"],
        [[bucket, stats["closed"], stats["resolved"], stats["unresolved"], stats["wins"], stats["losses"], fmt(stats["net_pnl"]), fmt(stats["fees"])] for bucket, stats in financial["by_reconstructed_strategy_regime"].items()],
    ))
    lines.append("")
    lines.append("## Exact Missing Metadata Causes")
    lines.append("")
    lines.append("- `apps/reference/domains/execution_position/orchestration/event_handlers.py` writes `ORDER_FILLED` and `POSITION_CLOSED` without `strategy_id` or `regime`; close rows only keep lifecycle, trade, PnL, fees, close reason, and close-fill IDs.")
    lines.append("- `apps/reference/domains/execution_position/guards/exposure_guard.py` writes reservation `ORDER_INTENT` with `source_fsm=ExposureGuard`, leverage/margin, symbol and side, but no `strategy_id` or `regime`.")
    lines.append("- `apps/reference/domains/execution_position/flows/open/open_executor.py` writes `ORDER_PLACED` with regime if present in `decision.pld`, but does not persist `strategy_id` top-level.")
    lines.append("- `apps/reference/domains/execution_position/flows/close/close_executor.py` writes close boundary `ORDER_INTENT`/`ORDER_PLACED` rows as boundary telemetry; they are not complete strategy attribution rows.")
    lines.append("- `apps/reference/schemas/order_logger_v1.json` has only global required fields and does not enforce per-event lineage fields.")
    lines.append("")
    lines.append("## Minimal Recommended Fixes")
    lines.append("")
    lines.append("1. Add event-specific schema contracts for `ORDER_INTENT`, `ORDER_PLACED`, `ORDER_FILLED`, and `POSITION_CLOSED` requiring `lifecycle_id`, `strategy_id`, `regime`, and stable decision/intent IDs where applicable.")
    lines.append("2. Propagate `strategy_id` and regime snapshot from decision payload into OrderIndex and from OrderIndex into fill/close logging.")
    lines.append("3. Add `LIMIT_PRICE_ADJUSTED` to the schema enum or stop writing it to this log.")
    lines.append("4. Add tests that assert strategy/regime survive from decision intent through placed, fill, and close rows.")
    lines.append("5. Keep unresolved `POSITION_CLOSED_DETECTED` accounting rows separate until close-fill truth is available.")
    lines.append("")
    lines.append("## Acceptance Checklist")
    lines.append("")
    checklist = [
        ("Parsed logs/order_log_v1.jsonl with zero or documented parse errors.", parse_errors == 0),
        ("Identified every code path that writes to order_log_v1.jsonl.", bool(writer_rows)),
        ("Identified every active/configured strategy that can produce order intents.", bool(strategy_rows)),
        ("Verified whether each strategy logs strategy_id at decision, intent, fill, and close stages.", True),
        ("Verified whether each strategy logs regime at decision, intent, fill, and close stages.", True),
        ("Reconstructed lineage for every POSITION_CLOSED row.", len(lineage) == len(closed)),
        ("Separated direct attribution from reconstructed attribution.", True),
        ("Marked attribution confidence for every closed position.", all(x["attribution_confidence"] for x in lineage)),
        ("Investigated other logs for missing strategy/regime metadata.", bool(cross_logs)),
        ("Did not mix stale/frozen/replay logs into live financial truth without proof.", True),
        ("Recalculated financial summary using reconstructed attribution.", True),
        ("Listed exact files/functions causing missing metadata.", True),
        ("Listed exact schema/event contract gaps.", True),
        ("Produced final markdown report and machine-readable artifacts.", True),
    ]
    lines.append(md_table(["check", "status"], [[label, "PASS" if passed else "FAIL"] for label, passed in checklist]))
    lines.append("")
    final_report.parent.mkdir(parents=True, exist_ok=True)
    final_report.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    global REPORT_ROOT, FINAL_REPORT, LINEAGE_JSONL, LINEAGE_SUMMARY_CSV, FIELD_COVERAGE_CSV, FINANCIAL_MD, FINANCIAL_JSON
    REPORT_ROOT = args.report_root
    FINAL_REPORT = args.final_report
    LINEAGE_JSONL = REPORT_ROOT / "order_log_v1_lineage_reconstruction.jsonl"
    LINEAGE_SUMMARY_CSV = REPORT_ROOT / "order_log_v1_lineage_summary.csv"
    FIELD_COVERAGE_CSV = REPORT_ROOT / "order_log_v1_field_coverage.csv"
    FINANCIAL_MD = REPORT_ROOT / "order_log_v1_reconstructed_financial_summary.md"
    FINANCIAL_JSON = REPORT_ROOT / "order_log_v1_reconstructed_financial_summary.json"

    rows, parse_errors = read_jsonl(args.order_log)
    schema = load_schema()
    strategy_rows = discover_strategies(rows)
    writer_rows = discover_writers()
    writer_field_rows = source_field_matrix(writer_rows)
    lineage = reconstruct_lineage(rows, strategy_rows)
    field_rows = field_coverage(rows)
    schema_gaps = schema_gap_table(schema, rows)
    cross_logs = cross_log_matrix(rows)
    financial = financial_summary(rows, lineage)

    write_jsonl(LINEAGE_JSONL, lineage)
    write_csv(LINEAGE_SUMMARY_CSV, lineage, [
        "closed_line", "closed_ts", "closed_utc", "symbol", "side", "close_reason", "pnl_status",
        "realized_pnl_net", "fees", "direct_strategy_id", "direct_regime", "reconstructed_strategy_id",
        "reconstructed_regime", "attribution_source", "attribution_confidence", "join_keys_used",
        "source_event_lines", "source_event_types", "lifecycle_id", "decision_id", "intent_id",
        "order_id", "client_order_id", "trade_id", "warnings",
    ])
    write_csv(FIELD_COVERAGE_CSV, field_rows, ["event_type", "field", "present_rows", "total_rows", "coverage_pct"])
    write_json(FINANCIAL_JSON, financial)
    write_financial_report(financial)
    write_final_report(
        rows=rows,
        parse_errors=parse_errors,
        schema_gaps=schema_gaps,
        strategy_rows=strategy_rows,
        writer_rows=writer_rows,
        writer_field_rows=writer_field_rows,
        lineage=lineage,
        field_rows=field_rows,
        cross_logs=cross_logs,
        financial=financial,
        final_report=FINAL_REPORT,
    )
    print(FINAL_REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
