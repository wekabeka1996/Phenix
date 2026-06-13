#!/usr/bin/env python3
"""Audit strategy registry visibility and direct ORDER_INTENT lineage coverage."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG = ROOT / "logs" / "order_log_v1.jsonl"
DEFAULT_OUTPUT = ROOT / "reports" / "order_log_v1_strategy_registry_coverage"
FINANCIAL_EVENT_TYPES = {"ORDER_PLACED", "ORDER_FILLED", "POSITION_CLOSED"}
STRATEGY_EVENT_TYPES = {
    "DECISION_INTENT_REJECTED",
    "ORDER_INTENT",
    "ORDER_PLACED",
    "ORDER_FILLED",
    "POSITION_CLOSED",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--order-log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    errors = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw in enumerate(handle, start=1):
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                errors += 1
                continue
            if isinstance(row, dict):
                row["_line"] = line_no
                rows.append(row)
            else:
                errors += 1
    return rows, errors


def value(row: dict[str, Any], field: str) -> Any:
    direct = row.get(field)
    if direct not in (None, ""):
        return direct
    metadata = row.get("metadata")
    return metadata.get(field) if isinstance(metadata, dict) else None


def lifecycle_key(row: dict[str, Any]) -> str:
    for field in ("lifecycle_id", "intent_id", "reservation_id", "rid"):
        candidate = value(row, field)
        if candidate not in (None, ""):
            return str(candidate)
    return ""


def configured_strategies() -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    profile_dir = ROOT / "config" / "aurora" / "strategies"
    for path in sorted(profile_dir.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict) or len(payload) != 1:
            continue
        strategy_id, config = next(iter(payload.items()))
        if not isinstance(config, dict):
            continue
        enabled = bool(config.get("enabled", False))
        mode = str(config.get("mode") or "").lower()
        if not enabled or mode == "disabled":
            status = "configured_disabled"
        elif mode == "shadow":
            status = "shadow_only"
        elif mode in {"observe", "observe_only"}:
            status = "observe_only"
        else:
            status = "configured_enabled"
        profiles[str(strategy_id)] = {
            "strategy_id": str(strategy_id),
            "status": status,
            "configured_enabled": enabled,
            "plugin_file": "",
            "runtime_handler": "",
            "can_emit_order_intent": True,
            "observed_in_current_runtime": False,
            "notes": f"discovered_from={path.relative_to(ROOT).as_posix()}",
        }
    return profiles


def latest_snapshot(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    snapshots = [
        row for row in rows
        if row.get("event_type") == "STRATEGY_REGISTRY_SNAPSHOT"
    ]
    if not snapshots:
        return {}
    strategies = snapshots[-1].get("strategies")
    if not isinstance(strategies, list):
        return {}
    return {
        str(item["strategy_id"]): dict(item)
        for item in strategies
        if isinstance(item, dict) and item.get("strategy_id")
    }


def percentage(present: int, total: int) -> str:
    return "n/a" if total == 0 else f"{100.0 * present / total:.1f}%"


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [str(cell).replace("|", "\\|").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_report(
    rows: list[dict[str, Any]],
    parse_errors: int,
    *,
    source: str = "logs/order_log_v1.jsonl",
) -> dict[str, Any]:
    configured = configured_strategies()
    snapshot = latest_snapshot(rows)
    discovered = set(configured) | set(snapshot)
    discovered.update(
        str(value(row, "strategy_id"))
        for row in rows
        if row.get("event_type") in STRATEGY_EVENT_TYPES
        and value(row, "strategy_id") not in (None, "")
    )

    reached_lifecycles = {
        lifecycle_key(row)
        for row in rows
        if row.get("event_type") in FINANCIAL_EVENT_TYPES and lifecycle_key(row)
    }
    events_by_strategy: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        strategy_id = value(row, "strategy_id")
        if strategy_id not in (None, ""):
            events_by_strategy[str(strategy_id)][str(row.get("event_type"))].append(row)

    coverage: list[dict[str, Any]] = []
    for strategy_id in sorted(discovered):
        profile = dict(configured.get(strategy_id, {}))
        profile.update(snapshot.get(strategy_id, {}))
        events = events_by_strategy[strategy_id]
        intents = events["ORDER_INTENT"]
        financially_active = any(events[event] for event in FINANCIAL_EVENT_TYPES)
        if not financially_active:
            financially_active = any(
                lifecycle_key(row) in reached_lifecycles for row in intents
            )
        warnings: list[str] = []
        if strategy_id not in snapshot:
            warnings.append("not_seen_in_live_registry_snapshot")
        if profile.get("configured_enabled") and not financially_active:
            warnings.append("configured_but_not_financially_active")
        if intents and any(value(row, "regime") in (None, "") for row in intents):
            warnings.append("order_intent_missing_regime")
        coverage.append({
            "strategy_id": strategy_id,
            "status": profile.get("status", "unknown"),
            "seen_in_registry_snapshot": strategy_id in snapshot,
            "seen_in_decision_rejected": bool(events["DECISION_INTENT_REJECTED"]),
            "seen_in_order_intent": bool(intents),
            "seen_in_order_placed": bool(events["ORDER_PLACED"]),
            "seen_in_order_filled": bool(events["ORDER_FILLED"]),
            "seen_in_position_closed": bool(events["POSITION_CLOSED"]),
            "financially_active": financially_active,
            "direct_intent_strategy_id_coverage": percentage(
                sum(value(row, "strategy_id") not in (None, "") for row in intents),
                len(intents),
            ),
            "direct_intent_regime_coverage": percentage(
                sum(value(row, "regime") not in (None, "") for row in intents),
                len(intents),
            ),
            "warnings": warnings,
        })

    return {
        "source": source,
        "parsed_rows": len(rows),
        "parse_errors": parse_errors,
        "registry_snapshot_count": sum(
            row.get("event_type") == "STRATEGY_REGISTRY_SNAPSHOT" for row in rows
        ),
        "financial_event_count": sum(
            row.get("event_type") in FINANCIAL_EVENT_TYPES for row in rows
        ),
        "strategies": coverage,
    }


def main() -> int:
    args = parse_args()
    rows, parse_errors = read_jsonl(args.order_log)
    try:
        source = args.order_log.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        source = str(args.order_log.resolve())
    report = build_report(rows, parse_errors, source=source)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "strategy_registry_coverage.json"
    md_path = args.output_dir / "strategy_registry_coverage.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    headers = [
        "strategy_id", "status", "registry", "rejected", "intent", "placed",
        "filled", "closed", "financially_active", "intent strategy_id", "intent regime",
        "warnings",
    ]
    table_rows = [
        [
            item["strategy_id"], item["status"], item["seen_in_registry_snapshot"],
            item["seen_in_decision_rejected"], item["seen_in_order_intent"],
            item["seen_in_order_placed"], item["seen_in_order_filled"],
            item["seen_in_position_closed"], item["financially_active"],
            item["direct_intent_strategy_id_coverage"],
            item["direct_intent_regime_coverage"], ", ".join(item["warnings"]),
        ]
        for item in report["strategies"]
    ]
    md_path.write_text(
        "# ORDER_LOG_V1 Strategy Registry Coverage\n\n"
        f"- Parsed rows: {report['parsed_rows']}\n"
        f"- Parse errors: {report['parse_errors']}\n"
        f"- Registry snapshots: {report['registry_snapshot_count']}\n"
        f"- Financial events (placed/fill/close only): {report['financial_event_count']}\n\n"
        + md_table(headers, table_rows)
        + "\n",
        encoding="utf-8",
    )
    print(md_path)
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
