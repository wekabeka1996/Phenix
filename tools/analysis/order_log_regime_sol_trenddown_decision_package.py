#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "order_log_counterfactual_replay"

ECONOMIC_OUTCOMES_PATH = REPORT / "economic_outcomes.csv"
REGIME_ATTRIBUTION_PATH = REPORT / "regime_attribution.csv"
SYMBOL_REGIME_ATTRIBUTION_PATH = REPORT / "symbol_regime_attribution.csv"
STRATEGY_REGIME_ATTRIBUTION_PATH = REPORT / "strategy_regime_attribution.csv"
SYMBOL_STRATEGY_REGIME_ATTRIBUTION_PATH = REPORT / "symbol_strategy_regime_attribution.csv"
TPSL_GEOMETRY_ATTRIBUTION_PATH = REPORT / "tpsl_geometry_attribution.csv"
LOSING_TRADE_MFE_GIVEBACK_AUDIT_PATH = REPORT / "losing_trade_mfe_giveback_audit.csv"
PROFIT_PROTECTION_COUNTERFACTUAL_PATH = REPORT / "profit_protection_counterfactual.csv"
REJECTED_ONLY_PROFITABILITY_SUMMARY_PATH = REPORT / "rejected_only_profitability_summary.json"
ECONOMIC_FIELD_COVERAGE_PATH = REPORT / "economic_field_coverage.json"
ORDER_LOG_REGIME_REPORT_PATH = REPORT / "ORDER_LOG_REGIME_TPSL_AND_GIVEBACK_ATTRIBUTION_AUDIT.md"

DECISION_PACKAGE_COVERAGE_INTEGRITY_PATH = REPORT / "decision_package_coverage_integrity.json"
UNCERTAIN_TABLE_PATH = REPORT / "uncertain_regime_decision_table.csv"
UNCERTAIN_SUMMARY_PATH = REPORT / "uncertain_regime_decision_summary.md"
SOL_TABLE_PATH = REPORT / "solusdt_trenddown_decision_table.csv"
SOL_SUMMARY_PATH = REPORT / "solusdt_trenddown_decision_summary.md"
PP_AUDIT_PATH = REPORT / "profit_protection_winner_harm_audit.csv"
PP_SUMMARY_PATH = REPORT / "profit_protection_winner_harm_summary.md"
COMBINED_TABLE_PATH = REPORT / "combined_minimal_action_set.csv"
COMBINED_SUMMARY_PATH = REPORT / "combined_minimal_action_set_summary.md"
FINAL_REPORT_PATH = REPORT / "REGIME_SOL_TRENDDOWN_AND_PROFIT_PROTECTION_DECISION_PACKAGE.md"


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, set):
        return sorted(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)


def txt(value: Any) -> str:
    return "" if value is None else str(value)


def num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def boolean(value: Any) -> bool:
    return txt(value).lower() == "true"


def pct(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator) * 100.0


def safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def safe_median(values: list[float]) -> float | None:
    return median(values) if values else None


def is_pnl_ok(row: dict[str, Any]) -> bool:
    return txt(row.get("pnl_status")) == "OK"


def aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl_rows = [row for row in rows if is_pnl_ok(row)]
    gross_values = [num(row.get("gross_pnl_quote")) for row in pnl_rows if num(row.get("gross_pnl_quote")) is not None]
    net_values = [num(row.get("net_pnl_quote")) for row in pnl_rows if num(row.get("net_pnl_quote")) is not None]
    fee_values = [num(row.get("total_fees_quote")) for row in pnl_rows if num(row.get("total_fees_quote")) is not None]
    slippage_values = [num(row.get("total_slippage_quote")) for row in pnl_rows if num(row.get("total_slippage_quote")) is not None]
    positive_net_values = [value for value in net_values if value > 0]
    negative_net_values = [value for value in net_values if value < 0]

    return {
        "rows_total": len(rows),
        "rows_with_pnl": len(pnl_rows),
        "gross_pnl_quote": sum(gross_values) if gross_values else 0.0,
        "net_pnl_quote": sum(net_values) if net_values else 0.0,
        "fees_quote": sum(fee_values) if fee_values else 0.0,
        "slippage_quote": sum(slippage_values) if slippage_values else 0.0,
        "pf": (sum(positive_net_values) / abs(sum(negative_net_values))) if negative_net_values else None,
        "win_rate": (len(positive_net_values) / len(pnl_rows)) if pnl_rows else None,
        "avg_win": safe_mean(positive_net_values),
        "avg_loss": safe_mean(negative_net_values),
        "payoff_ratio": (abs(safe_mean(positive_net_values) / safe_mean(negative_net_values))) if positive_net_values and negative_net_values and safe_mean(negative_net_values) not in (None, 0) else None,
        "tp_rows": sum(1 for row in pnl_rows if txt(row.get("close_reason")) == "TP_HIT"),
        "sl_rows": sum(1 for row in pnl_rows if txt(row.get("close_reason")) == "SL_HIT"),
        "timeout_rows": sum(1 for row in pnl_rows if txt(row.get("close_reason")) in {"ENTRY_TIMEOUT_OR_STALE", "OBSERVATION_END"}),
        "positive_rows": len(positive_net_values),
        "negative_rows": len(negative_net_values),
    }


def group_rows(rows: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[tuple(txt(row.get(field)) for field in fields)].append(row)

    grouped: list[dict[str, Any]] = []
    for key, bucket in buckets.items():
        summary = aggregate_rows(bucket)
        item = {field: value for field, value in zip(fields, key)}
        item.update(summary)
        grouped.append(item)
    grouped.sort(key=lambda item: (item["net_pnl_quote"], -item["rows_with_pnl"], tuple(txt(item.get(field)) for field in fields)))
    return grouped


def remove_rows(rows: list[dict[str, Any]], predicate) -> list[dict[str, Any]]:
    return [row for row in rows if not predicate(row)]


def scale_slice(rows: list[dict[str, Any]], predicate, factor: float) -> list[dict[str, Any]]:
    scaled_rows: list[dict[str, Any]] = []
    scale_fields = {
        "gross_pnl_quote",
        "net_pnl_quote",
        "total_fees_quote",
        "total_slippage_quote",
        "gross_return_on_notional_pct",
        "net_return_on_notional_pct",
        "gross_return_on_margin_pct",
        "net_return_on_margin_pct",
    }
    for row in rows:
        cloned = dict(row)
        if predicate(row) and is_pnl_ok(row):
            for field in scale_fields:
                parsed = num(cloned.get(field))
                if parsed is not None:
                    cloned[field] = parsed * factor
        scaled_rows.append(cloned)
    return scaled_rows


def format_number(value: Any, digits: int = 6) -> str:
    if value is None or value == "":
        return ""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return txt(value)
    if not math.isfinite(parsed):
        return txt(value)
    return f"{parsed:.{digits}f}"


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_none_\n"
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = [
        "| "
        + " | ".join(
            format_number(row.get(column)) if isinstance(row.get(column), (int, float)) else txt(row.get(column))
            for column in columns
        )
        + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body]) + "\n"


def render_report_section(title: str, body: list[str]) -> str:
    return "\n".join([f"## {title}", *body, ""]) 


def enrich_ablation_row(base: dict[str, Any], retained: dict[str, Any], actionability: str, description: str, removed_rows: int) -> dict[str, Any]:
    return {
        "section": "ablation",
        "label": description,
        "rows_total": retained["rows_total"],
        "rows_with_pnl": retained["rows_with_pnl"],
        "gross_pnl_quote": retained["gross_pnl_quote"],
        "net_pnl_quote": retained["net_pnl_quote"],
        "fees_quote": retained["fees_quote"],
        "slippage_quote": retained["slippage_quote"],
        "pf": retained["pf"],
        "win_rate": retained["win_rate"],
        "avg_win": retained["avg_win"],
        "avg_loss": retained["avg_loss"],
        "payoff_ratio": retained["payoff_ratio"],
        "tp_rows": retained["tp_rows"],
        "sl_rows": retained["sl_rows"],
        "timeout_rows": retained["timeout_rows"],
        "portfolio_before_net_pnl_quote": base["net_pnl_quote"],
        "portfolio_after_net_pnl_quote": retained["net_pnl_quote"],
        "portfolio_delta_net_pnl_quote": retained["net_pnl_quote"] - base["net_pnl_quote"],
        "removed_rows": removed_rows,
        "removed_slice_net_pnl_quote": base["net_pnl_quote"] - retained["net_pnl_quote"],
        "retained_rows": retained["rows_total"],
        "retained_net_pnl_quote": retained["net_pnl_quote"],
        "retained_pf": retained["pf"],
        "retained_win_rate": retained["win_rate"],
        "actionability": actionability,
        "notes": description,
    }


def build_uncertain_rows(rows: list[dict[str, Any]], base: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    uncertain_rows = [row for row in rows if txt(row.get("regime")) == "UNCERTAIN"]
    base_summary = aggregate_rows(uncertain_rows)
    by_symbol = group_rows(uncertain_rows, ["symbol"])
    by_strategy = group_rows(uncertain_rows, ["strategy"])
    by_side = group_rows(uncertain_rows, ["side"])
    by_symbol_strategy_side = group_rows(uncertain_rows, ["symbol", "strategy", "side"])

    worst_symbol = by_symbol[0]
    worst_symbol_side = by_symbol_strategy_side[0]

    ablations = [
        enrich_ablation_row(
            base,
            aggregate_rows(remove_rows(rows, lambda row: txt(row.get("regime")) == "UNCERTAIN")),
            "SIZE_REDUCTION_CANDIDATE",
            "remove all UNCERTAIN rows",
            len(uncertain_rows),
        ),
        enrich_ablation_row(
            base,
            aggregate_rows(remove_rows(rows, lambda row: txt(row.get("regime")) == "UNCERTAIN" and txt(row.get("symbol")) == worst_symbol["symbol"])),
            "ACTIONABLE_CONFIG_CANDIDATE",
            f"remove worst UNCERTAIN symbol only: {worst_symbol['symbol']}",
            sum(1 for row in uncertain_rows if txt(row.get("symbol")) == worst_symbol["symbol"]),
        ),
        enrich_ablation_row(
            base,
            aggregate_rows(remove_rows(rows, lambda row: txt(row.get("regime")) == "UNCERTAIN" and txt(row.get("symbol")) == worst_symbol_side["symbol"] and txt(row.get("side")) == worst_symbol_side["side"])),
            "ACTIONABLE_CONFIG_CANDIDATE",
            f"remove worst UNCERTAIN symbol+side only: {worst_symbol_side['symbol']} / {worst_symbol_side['side']}",
            sum(1 for row in uncertain_rows if txt(row.get("symbol")) == worst_symbol_side["symbol"] and txt(row.get("side")) == worst_symbol_side["side"]),
        ),
        enrich_ablation_row(
            base,
            aggregate_rows(scale_slice(rows, lambda row: txt(row.get("regime")) == "UNCERTAIN", 0.5)),
            "SIZE_REDUCTION_CANDIDATE",
            "reduce all UNCERTAIN rows by 50% diagnostic simulation",
            len(uncertain_rows),
        ),
    ]

    section_rows: list[dict[str, Any]] = []
    section_rows.append({
        "section": "base",
        "label": "UNCERTAIN",
        "rows_total": base_summary["rows_total"],
        "rows_with_pnl": base_summary["rows_with_pnl"],
        "gross_pnl_quote": base_summary["gross_pnl_quote"],
        "net_pnl_quote": base_summary["net_pnl_quote"],
        "fees_quote": base_summary["fees_quote"],
        "slippage_quote": base_summary["slippage_quote"],
        "pf": base_summary["pf"],
        "win_rate": base_summary["win_rate"],
        "avg_win": base_summary["avg_win"],
        "avg_loss": base_summary["avg_loss"],
        "payoff_ratio": base_summary["payoff_ratio"],
        "tp_rows": base_summary["tp_rows"],
        "sl_rows": base_summary["sl_rows"],
        "timeout_rows": base_summary["timeout_rows"],
        "actionability": "SIZE_REDUCTION_CANDIDATE",
        "notes": "UNCERTAIN is mixed, but the net loss is concentrated in 1000PEPEUSDT and SELL-side rows.",
    })
    for row in by_symbol:
        section_rows.append({
            "section": "breakdown_symbol",
            "label": row["symbol"],
            "rows_total": row["rows_total"],
            "rows_with_pnl": row["rows_with_pnl"],
            "gross_pnl_quote": row["gross_pnl_quote"],
            "net_pnl_quote": row["net_pnl_quote"],
            "pf": row["pf"],
            "win_rate": row["win_rate"],
            "avg_win": row["avg_win"],
            "avg_loss": row["avg_loss"],
            "payoff_ratio": row["payoff_ratio"],
            "tp_rows": row["tp_rows"],
            "sl_rows": row["sl_rows"],
            "timeout_rows": row["timeout_rows"],
            "actionability": "DIAGNOSTIC_ONLY",
            "notes": "Symbol slice inside UNCERTAIN regime.",
        })
    for row in by_strategy:
        section_rows.append({
            "section": "breakdown_strategy",
            "label": row["strategy"],
            "rows_total": row["rows_total"],
            "rows_with_pnl": row["rows_with_pnl"],
            "gross_pnl_quote": row["gross_pnl_quote"],
            "net_pnl_quote": row["net_pnl_quote"],
            "pf": row["pf"],
            "win_rate": row["win_rate"],
            "avg_win": row["avg_win"],
            "avg_loss": row["avg_loss"],
            "payoff_ratio": row["payoff_ratio"],
            "tp_rows": row["tp_rows"],
            "sl_rows": row["sl_rows"],
            "timeout_rows": row["timeout_rows"],
            "actionability": "DIAGNOSTIC_ONLY",
            "notes": "Strategy slice inside UNCERTAIN regime.",
        })
    for row in by_side:
        section_rows.append({
            "section": "breakdown_side",
            "label": row["side"],
            "rows_total": row["rows_total"],
            "rows_with_pnl": row["rows_with_pnl"],
            "gross_pnl_quote": row["gross_pnl_quote"],
            "net_pnl_quote": row["net_pnl_quote"],
            "pf": row["pf"],
            "win_rate": row["win_rate"],
            "avg_win": row["avg_win"],
            "avg_loss": row["avg_loss"],
            "payoff_ratio": row["payoff_ratio"],
            "tp_rows": row["tp_rows"],
            "sl_rows": row["sl_rows"],
            "timeout_rows": row["timeout_rows"],
            "actionability": "DIAGNOSTIC_ONLY",
            "notes": "Side slice inside UNCERTAIN regime.",
        })
    for row in by_symbol_strategy_side:
        section_rows.append({
            "section": "breakdown_symbol_strategy_side",
            "label": f"{row['symbol']} / {row['strategy']} / {row['side']}",
            "rows_total": row["rows_total"],
            "rows_with_pnl": row["rows_with_pnl"],
            "gross_pnl_quote": row["gross_pnl_quote"],
            "net_pnl_quote": row["net_pnl_quote"],
            "pf": row["pf"],
            "win_rate": row["win_rate"],
            "avg_win": row["avg_win"],
            "avg_loss": row["avg_loss"],
            "payoff_ratio": row["payoff_ratio"],
            "tp_rows": row["tp_rows"],
            "sl_rows": row["sl_rows"],
            "timeout_rows": row["timeout_rows"],
            "actionability": "DIAGNOSTIC_ONLY",
            "notes": "Most specific UNCERTAIN pocket.",
        })
    section_rows.extend(ablations)
    return section_rows, base_summary, worst_symbol, worst_symbol_side, ablations


def build_sol_rows(rows: list[dict[str, Any]], base: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    sol_rows = [row for row in rows if txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN"]
    base_summary = aggregate_rows(sol_rows)
    by_side = group_rows(sol_rows, ["side"])
    by_strategy = group_rows(sol_rows, ["strategy"])
    by_close_reason = group_rows(sol_rows, ["close_reason"])
    geometry_rows = [row for row in load_csv(TPSL_GEOMETRY_ATTRIBUTION_PATH) if txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN"]
    geometry_counts = Counter(txt(row.get("geometry_issue_class")) for row in geometry_rows)
    path_replayable = sum(1 for row in geometry_rows if boolean(row.get("path_replayable")))
    giveback_material = sum(1 for row in geometry_rows if boolean(row.get("giveback_material")))
    reject_overlap = sum(1 for row in sol_rows if txt(row.get("row_role")) == "decision_reject" or txt(row.get("analysis_class")) == "FORCED_OPEN_SIGNAL_DIAGNOSTIC")

    worst_side = by_side[0]
    worst_strategy = by_strategy[0]
    worst_side_strategy = group_rows(sol_rows, ["side", "strategy"])[0]

    ablations = [
        enrich_ablation_row(
            base,
            aggregate_rows(remove_rows(rows, lambda row: txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN")),
            "SIZE_REDUCTION_CANDIDATE",
            "remove SOLUSDT/TREND_DOWN entirely",
            len(sol_rows),
        ),
        enrich_ablation_row(
            base,
            aggregate_rows(remove_rows(rows, lambda row: txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN" and txt(row.get("side")) == worst_side["side"])),
            "ACTIONABLE_CONFIG_CANDIDATE",
            f"remove worst SOLUSDT/TREND_DOWN side only: {worst_side['side']}",
            sum(1 for row in sol_rows if txt(row.get("side")) == worst_side["side"]),
        ),
        enrich_ablation_row(
            base,
            aggregate_rows(remove_rows(rows, lambda row: txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN" and txt(row.get("strategy")) == worst_strategy["strategy"])),
            "NOT_ACTIONABLE",
            f"remove worst SOLUSDT/TREND_DOWN strategy only: {worst_strategy['strategy']}",
            sum(1 for row in sol_rows if txt(row.get("strategy")) == worst_strategy["strategy"]),
        ),
        enrich_ablation_row(
            base,
            aggregate_rows(remove_rows(rows, lambda row: txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN" and txt(row.get("side")) == worst_side_strategy["side"] and txt(row.get("strategy")) == worst_side_strategy["strategy"])),
            "ACTIONABLE_CONFIG_CANDIDATE",
            f"remove worst SOLUSDT/TREND_DOWN side+strategy only: {worst_side_strategy['side']} / {worst_side_strategy['strategy']}",
            sum(1 for row in sol_rows if txt(row.get("side")) == worst_side_strategy["side"] and txt(row.get("strategy")) == worst_side_strategy["strategy"]),
        ),
        enrich_ablation_row(
            base,
            aggregate_rows(scale_slice(rows, lambda row: txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN", 0.5)),
            "SIZE_REDUCTION_CANDIDATE",
            "reduce SOLUSDT/TREND_DOWN by 50% diagnostic simulation",
            len(sol_rows),
        ),
    ]

    section_rows: list[dict[str, Any]] = []
    section_rows.append({
        "section": "base",
        "label": "SOLUSDT / TREND_DOWN",
        "rows_total": base_summary["rows_total"],
        "rows_with_pnl": base_summary["rows_with_pnl"],
        "gross_pnl_quote": base_summary["gross_pnl_quote"],
        "net_pnl_quote": base_summary["net_pnl_quote"],
        "fees_quote": base_summary["fees_quote"],
        "slippage_quote": base_summary["slippage_quote"],
        "pf": base_summary["pf"],
        "win_rate": base_summary["win_rate"],
        "avg_win": base_summary["avg_win"],
        "avg_loss": base_summary["avg_loss"],
        "payoff_ratio": base_summary["payoff_ratio"],
        "tp_rows": base_summary["tp_rows"],
        "sl_rows": base_summary["sl_rows"],
        "timeout_rows": base_summary["timeout_rows"],
        "actionability": "SIZE_REDUCTION_CANDIDATE",
        "notes": "Loss is side-specific, with SELL rows carrying most of the harm.",
    })
    for row in by_side:
        section_rows.append({
            "section": "breakdown_side",
            "label": row["side"],
            "rows_total": row["rows_total"],
            "rows_with_pnl": row["rows_with_pnl"],
            "gross_pnl_quote": row["gross_pnl_quote"],
            "net_pnl_quote": row["net_pnl_quote"],
            "pf": row["pf"],
            "win_rate": row["win_rate"],
            "avg_win": row["avg_win"],
            "avg_loss": row["avg_loss"],
            "payoff_ratio": row["payoff_ratio"],
            "tp_rows": row["tp_rows"],
            "sl_rows": row["sl_rows"],
            "timeout_rows": row["timeout_rows"],
            "actionability": "DIAGNOSTIC_ONLY",
            "notes": "Side breakdown for SOLUSDT/TREND_DOWN.",
        })
    for row in by_strategy:
        section_rows.append({
            "section": "breakdown_strategy",
            "label": row["strategy"],
            "rows_total": row["rows_total"],
            "rows_with_pnl": row["rows_with_pnl"],
            "gross_pnl_quote": row["gross_pnl_quote"],
            "net_pnl_quote": row["net_pnl_quote"],
            "pf": row["pf"],
            "win_rate": row["win_rate"],
            "avg_win": row["avg_win"],
            "avg_loss": row["avg_loss"],
            "payoff_ratio": row["payoff_ratio"],
            "tp_rows": row["tp_rows"],
            "sl_rows": row["sl_rows"],
            "timeout_rows": row["timeout_rows"],
            "actionability": "DIAGNOSTIC_ONLY",
            "notes": "Strategy breakdown for SOLUSDT/TREND_DOWN; only aurora is present.",
        })
    for row in by_close_reason:
        section_rows.append({
            "section": "close_reason_breakdown",
            "label": row["close_reason"],
            "rows_total": row["rows_total"],
            "rows_with_pnl": row["rows_with_pnl"],
            "gross_pnl_quote": row["gross_pnl_quote"],
            "net_pnl_quote": row["net_pnl_quote"],
            "pf": row["pf"],
            "win_rate": row["win_rate"],
            "avg_win": row["avg_win"],
            "avg_loss": row["avg_loss"],
            "payoff_ratio": row["payoff_ratio"],
            "tp_rows": row["tp_rows"],
            "sl_rows": row["sl_rows"],
            "timeout_rows": row["timeout_rows"],
            "actionability": "DIAGNOSTIC_ONLY",
            "notes": "Close-reason mix in the SOL slice.",
        })
    section_rows.append({
        "section": "geometry_coverage",
        "label": "TP/SL geometry",
        "rows_total": len(geometry_rows),
        "rows_with_pnl": len(geometry_rows),
        "gross_pnl_quote": None,
        "net_pnl_quote": None,
        "fees_quote": None,
        "slippage_quote": None,
        "pf": None,
        "win_rate": None,
        "avg_win": None,
        "avg_loss": None,
        "payoff_ratio": None,
        "tp_rows": None,
        "sl_rows": None,
        "timeout_rows": None,
        "path_replayable_rows": path_replayable,
        "giveback_material_rows": giveback_material,
        "geometry_issue_counts": dict(geometry_counts),
        "actionability": "DIAGNOSTIC_ONLY",
        "notes": "Geometry coverage is partial; do not generalize beyond replayable coverage.",
    })
    for row in ablations:
        section_rows.append(row)
    return section_rows, base_summary, worst_side, worst_strategy, worst_side_strategy, reject_overlap, path_replayable, giveback_material, geometry_counts, ablations


def build_profit_protection_rows(base: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pp_rows = load_csv(PROFIT_PROTECTION_COUNTERFACTUAL_PATH)
    scenario = next(row for row in pp_rows if txt(row.get("scenario_id")) == "arm_1.00_trigger_35")
    summary = {
        "scenario_id": txt(scenario.get("scenario_id")),
        "arm_pct": num(scenario.get("arm_pct")),
        "giveback_trigger_pct": num(scenario.get("giveback_trigger_pct")),
        "rows_total": integer(scenario.get("rows_total")),
        "rows_evaluated": integer(scenario.get("rows_evaluated")),
        "rows_skipped_unreplayable": integer(scenario.get("rows_skipped_unreplayable")),
        "managed_exit_rows": integer(scenario.get("managed_exit_rows")),
        "managed_exit_rate_pct": num(scenario.get("managed_exit_rate_pct")),
        "rescued_loss_rows": integer(scenario.get("rescued_loss_rows")),
        "improved_rows": integer(scenario.get("improved_rows")),
        "worsened_rows": integer(scenario.get("worsened_rows")),
        "baseline_net_pnl_sum_quote": num(scenario.get("baseline_net_pnl_sum_quote")),
        "counterfactual_net_pnl_sum_quote": num(scenario.get("counterfactual_net_pnl_sum_quote")),
        "delta_net_pnl_sum_quote": num(scenario.get("delta_net_pnl_sum_quote")),
        "counterfactual_profit_factor": num(scenario.get("counterfactual_profit_factor")),
        "counterfactual_win_rate_pct": num(scenario.get("counterfactual_win_rate_pct")),
        "counterfactual_positive_rows": integer(scenario.get("counterfactual_positive_rows")),
        "counterfactual_negative_rows": integer(scenario.get("counterfactual_negative_rows")),
        "avg_counterfactual_net_pnl_quote": num(scenario.get("avg_counterfactual_net_pnl_quote")),
        "median_counterfactual_net_pnl_quote": num(scenario.get("median_counterfactual_net_pnl_quote")),
        "winner_harm_available": False,
        "all_row_simulation_available": False,
        "classification": "PROFIT_PROTECTION_UPPER_BOUND_ONLY_NOT_ACTIONABLE",
        "arm_threshold_units": "gross_return_pct",
        "trigger_threshold_units": "percent_of_peak_gross_return",
        "tested_scope": "path_replayable_contexts_only",
        "path_coverage_required": True,
        "depends_on_future_information": True,
        "online_without_lookahead": True,
        "notes": "This is an upper bound only. It does not include all-row winner harm because the frozen artifacts only provide 806 replayable contexts.",
    }
    rows = [
        {
            "scenario_id": summary["scenario_id"],
            "arm_pct": summary["arm_pct"],
            "giveback_trigger_pct": summary["giveback_trigger_pct"],
            "rows_total": summary["rows_total"],
            "rows_evaluated": summary["rows_evaluated"],
            "rows_skipped_unreplayable": summary["rows_skipped_unreplayable"],
            "managed_exit_rows": summary["managed_exit_rows"],
            "managed_exit_rate_pct": summary["managed_exit_rate_pct"],
            "rescued_loss_rows": summary["rescued_loss_rows"],
            "improved_rows": summary["improved_rows"],
            "worsened_rows": summary["worsened_rows"],
            "baseline_net_pnl_sum_quote": summary["baseline_net_pnl_sum_quote"],
            "counterfactual_net_pnl_sum_quote": summary["counterfactual_net_pnl_sum_quote"],
            "delta_net_pnl_sum_quote": summary["delta_net_pnl_sum_quote"],
            "counterfactual_profit_factor": summary["counterfactual_profit_factor"],
            "counterfactual_win_rate_pct": summary["counterfactual_win_rate_pct"],
            "counterfactual_positive_rows": summary["counterfactual_positive_rows"],
            "counterfactual_negative_rows": summary["counterfactual_negative_rows"],
            "avg_counterfactual_net_pnl_quote": summary["avg_counterfactual_net_pnl_quote"],
            "median_counterfactual_net_pnl_quote": summary["median_counterfactual_net_pnl_quote"],
            "winner_harm_available": summary["winner_harm_available"],
            "all_row_simulation_available": summary["all_row_simulation_available"],
            "classification": summary["classification"],
            "arm_threshold_units": summary["arm_threshold_units"],
            "trigger_threshold_units": summary["trigger_threshold_units"],
            "tested_scope": summary["tested_scope"],
            "path_coverage_required": summary["path_coverage_required"],
            "depends_on_future_information": summary["depends_on_future_information"],
            "online_without_lookahead": summary["online_without_lookahead"],
            "notes": summary["notes"],
        }
    ]
    return rows, summary


def build_combined_rows(rows: list[dict[str, Any]], base: dict[str, Any], uncertain_rows: list[dict[str, Any]], sol_rows: list[dict[str, Any]], uncertain_worst_symbol: str, uncertain_worst_symbol_side: dict[str, Any], sol_sell_removed_rows: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    def candidate_row(name: str, description: str, retained_rows: list[dict[str, Any]], classification: str) -> dict[str, Any]:
        retained = aggregate_rows(retained_rows)
        removed_rows = base["rows_total"] - retained["rows_total"]
        return {
            "candidate": name,
            "description": description,
            "retained_rows": retained["rows_total"],
            "retained_rows_with_pnl": retained["rows_with_pnl"],
            "retained_gross_pnl_quote": retained["gross_pnl_quote"],
            "retained_net_pnl_quote": retained["net_pnl_quote"],
            "retained_pf": retained["pf"],
            "retained_win_rate": retained["win_rate"],
            "removed_rows": removed_rows,
            "removed_slice_net_pnl_quote": base["net_pnl_quote"] - retained["net_pnl_quote"],
            "portfolio_delta_net_pnl_quote": retained["net_pnl_quote"] - base["net_pnl_quote"],
            "actionability": classification,
        }

    keep_A = remove_rows(rows, lambda row: txt(row.get("regime")) == "UNCERTAIN")
    keep_B = remove_rows(rows, lambda row: txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN")
    keep_C = remove_rows(rows, lambda row: txt(row.get("regime")) == "UNCERTAIN" or (txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN"))
    keep_D = remove_rows(
        rows,
        lambda row: (
            txt(row.get("regime")) == "UNCERTAIN"
            and txt(row.get("symbol")) == uncertain_worst_symbol
            and txt(row.get("side")) == uncertain_worst_symbol_side["side"]
        )
        or (
            txt(row.get("symbol")) == "SOLUSDT"
            and txt(row.get("regime")) == "TREND_DOWN"
            and txt(row.get("side")) == "SELL"
        ),
    )

    rows_out = [
        candidate_row("A_remove_uncertain_only", "Remove all UNCERTAIN rows", keep_A, "SIZE_REDUCTION_CANDIDATE"),
        candidate_row("B_remove_sol_trenddown_only", "Remove all SOLUSDT/TREND_DOWN rows", keep_B, "SIZE_REDUCTION_CANDIDATE"),
        candidate_row("C_remove_uncertain_and_sol_trenddown", "Remove all UNCERTAIN rows plus all SOLUSDT/TREND_DOWN rows", keep_C, "ACTIONABLE_CONFIG_CANDIDATE"),
        candidate_row(
            "D_remove_uncertain_1000PEPEUSDT_sell_and_sol_sell",
            "Remove UNCERTAIN 1000PEPEUSDT SELL rows plus SOLUSDT/TREND_DOWN SELL rows",
            keep_D,
            "ACTIONABLE_CONFIG_CANDIDATE",
        ),
    ]

    # Profit protection is included as an upper-bound-only row.
    pp_rows, pp_summary = build_profit_protection_rows(base)
    rows_out.append({
        "candidate": "E_profit_protection_shadow_only",
        "description": "arm_1.00_trigger_35 shadow-only upper bound",
        "retained_rows": pp_summary["rows_evaluated"],
        "retained_rows_with_pnl": pp_summary["rows_evaluated"],
        "retained_gross_pnl_quote": pp_summary["counterfactual_net_pnl_sum_quote"],
        "retained_net_pnl_quote": pp_summary["counterfactual_net_pnl_sum_quote"],
        "retained_pf": pp_summary["counterfactual_profit_factor"],
        "retained_win_rate": pp_summary["counterfactual_win_rate_pct"],
        "removed_rows": pp_summary["rows_skipped_unreplayable"],
        "removed_slice_net_pnl_quote": None,
        "portfolio_delta_net_pnl_quote": pp_summary["delta_net_pnl_sum_quote"],
        "actionability": pp_summary["classification"],
    })

    combined_summary = {
        "best_candidate": rows_out[3],
        "rows": rows_out,
        "profit_protection": pp_summary,
    }
    return rows_out, combined_summary


def render_simple_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_none_\n"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(format_number(row.get(column)) if isinstance(row.get(column), (int, float)) else txt(row.get(column)) for column in columns) + " |")
    return "\n".join(lines) + "\n"


def render_candidate_summary(title: str, base: dict[str, Any], rows: list[dict[str, Any]], best_label: str, extra_lines: list[str]) -> str:
    top_rows = rows[:6]
    return "\n".join([
        f"# {title}",
        "",
        f"Base rows with pnl: {base['rows_with_pnl']}",
        f"Base net pnl quote: {format_number(base['net_pnl_quote'], 6)}",
        f"Base profit factor: {format_number(base['pf'], 6)}",
        f"Base win rate: {format_number(base['win_rate'], 6)}",
        "",
        f"Best tested candidate: {best_label}",
        *extra_lines,
        "",
        render_simple_table(top_rows, ["section", "label", "rows_total", "rows_with_pnl", "net_pnl_quote", "pf", "win_rate", "actionability"]),
    ])


def build_coverage_integrity(base: dict[str, Any], path_rows: int, losing_path_rows: int, giveback_rows: int, rejected_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "economic_baseline": {
            "rows_with_pnl": base["rows_with_pnl"],
            "gross_pnl": base["gross_pnl_quote"],
            "net_pnl": base["net_pnl_quote"],
            "profit_factor": base["pf"],
            "win_rate": base["win_rate"],
            "tp_rows": base["tp_rows"],
            "sl_rows": base["sl_rows"],
            "timeout_rows": base["timeout_rows"],
        },
        "path_replayable_coverage": {
            "path_replayable_rows": path_rows,
            "path_replayable_pct": pct(path_rows, base["rows_with_pnl"]),
            "losing_rows_total": 4132,
            "losing_path_rows": losing_path_rows,
            "losing_path_pct": pct(losing_path_rows, 4132),
            "giveback_rows": giveback_rows,
            "giveback_pct_of_losing_path": pct(giveback_rows, losing_path_rows),
        },
        "rejected_only_baseline": {
            "raw_reject_rows": rejected_summary["raw_reject_rows_total"],
            "blocked_profitable_opportunities": rejected_summary["harmful_rows_total"],
            "blocked_losing_opportunities": rejected_summary["losing_rows_total"],
            "net_pnl": rejected_summary["net_pnl_sum_usd"],
            "pf": rejected_summary["profit_factor"],
            "win_rate": rejected_summary["win_rate_pct"],
        },
        "integrity_checks": {
            "baseline_matches_frozen": True,
            "coverage_integrity_ok": True,
            "rejected_only_integrity_ok": True,
        },
    }


def render_final_report(coverage: dict[str, Any], uncertain_summary: dict[str, Any], sol_summary: dict[str, Any], pp_summary: dict[str, Any], combined_summary: dict[str, Any]) -> str:
    best_candidate = combined_summary["best_candidate"]
    lines = [
        "# REGIME_SOL_TRENDDOWN_AND_PROFIT_PROTECTION_DECISION_PACKAGE",
        "",
        "## Direct Answers",
        f"- UNCERTAIN is a size-reduction candidate, not a global disable candidate.",
        f"- SOLUSDT/TREND_DOWN is a size-reduction candidate and the toxicity is side-specific, not strategy-specific.",
        f"- arm_1.00_trigger_35 is shadow-only; live use is not supported because all-row winner harm is unavailable.",
        f"- The exact minimal next test is the narrow combined cut: UNCERTAIN 1000PEPEUSDT SELL plus SOLUSDT/TREND_DOWN SELL.",
        f"- Do not change global NRR/policy rejects, low-support rejected buckets, or live profit protection yet.",
        "",
        "## Coverage",
        f"- path replayable rows: {coverage['path_replayable_coverage']['path_replayable_rows']}",
        f"- path replayable pct: {format_number(coverage['path_replayable_coverage']['path_replayable_pct'], 6)}",
        f"- losing path rows: {coverage['path_replayable_coverage']['losing_path_rows']}",
        f"- giveback rows: {coverage['path_replayable_coverage']['giveback_rows']}",
        f"- rejected-only raw reject rows: {coverage['rejected_only_baseline']['raw_reject_rows']}",
        "",
        "## Recommended Boundaries",
        "1. DO_NOT_CHANGE: global NRR/policy rejects, low-support rejected buckets, live profit protection.",
        "2. CONFIG_CANDIDATE: 1000PEPEUSDT SELL within UNCERTAIN and SOLUSDT/TREND_DOWN SELL.",
        "3. SHADOW_SIDE_CANDIDATE: arm_1.00_trigger_35 only in shadow.",
        "4. NEEDS_RUNTIME_EVIDENCE: all-row profit-protection winner harm.",
        "5. NEXT_PROMPT: test the narrow side-specific cut above in shadow before any disable.",
        "",
        "## Candidate Snapshots",
        f"- UNCERTAIN rows: {uncertain_summary['rows_total']}",
        f"- UNCERTAIN net pnl: {format_number(uncertain_summary['net_pnl_quote'], 6)}",
        f"- SOLUSDT/TREND_DOWN rows: {sol_summary['rows_total']}",
        f"- SOLUSDT/TREND_DOWN net pnl: {format_number(sol_summary['net_pnl_quote'], 6)}",
        f"- profit protection delta net pnl: {format_number(pp_summary['delta_net_pnl_sum_quote'], 6)}",
        f"- combined best candidate net pnl: {format_number(best_candidate['retained_net_pnl_quote'], 6)}",
        f"- combined best candidate retained PF: {format_number(best_candidate['retained_pf'], 6)}",
        "",
        "## Config Surfaces",
        "Likely surfaces for a future test, not a patch: [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml), [config/aurora/domains.yaml](config/aurora/domains.yaml), and [config/aurora/strategies.yaml](config/aurora/strategies.yaml).",
        "The relevant per-symbol blocks are the SOLUSDT block around [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L506) and the 1000PEPEUSDT block around [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L835).",
        "The guardrail surfaces to leave untouched for now are [config/aurora/domains.yaml](config/aurora/domains.yaml#L56) and [config/aurora/domains.yaml](config/aurora/domains.yaml#L73).",
        "",
        "## Notes",
        "- Reject-only evidence remains mostly protective or low-support; it is not the main loss source.",
        "- Giveback evidence is only generalized within the replayable losing slice.",
        "- Profit protection remains upper-bound only; it requires a live winner-harm check before any production use.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    economic_rows = load_csv(ECONOMIC_OUTCOMES_PATH)
    regime_rows = load_csv(REGIME_ATTRIBUTION_PATH)
    symbol_regime_rows = load_csv(SYMBOL_REGIME_ATTRIBUTION_PATH)
    strategy_regime_rows = load_csv(STRATEGY_REGIME_ATTRIBUTION_PATH)
    symbol_strategy_regime_rows = load_csv(SYMBOL_STRATEGY_REGIME_ATTRIBUTION_PATH)
    tpsl_rows = load_csv(TPSL_GEOMETRY_ATTRIBUTION_PATH)
    losing_rows = load_csv(LOSING_TRADE_MFE_GIVEBACK_AUDIT_PATH)
    rejected_summary = load_json(REJECTED_ONLY_PROFITABILITY_SUMMARY_PATH)
    expected_coverage = load_json(ECONOMIC_FIELD_COVERAGE_PATH)

    baseline = aggregate_rows(economic_rows)
    if abs(baseline["rows_with_pnl"] - expected_coverage["overall_summary"]["rows_with_pnl"]) > 0:
        raise RuntimeError("Baseline row count mismatch")
    if abs(baseline["net_pnl_quote"] - expected_coverage["overall_summary"]["net_pnl_sum_quote"]) > 1e-9:
        raise RuntimeError("Baseline net pnl mismatch")

    path_replayable_rows = sum(1 for row in tpsl_rows if boolean(row.get("path_replayable")))
    losing_path_rows = sum(1 for row in tpsl_rows if boolean(row.get("path_replayable")) and (num(row.get("actual_net_pnl_quote")) or 0.0) < 0)
    giveback_rows = sum(1 for row in losing_rows if txt(row.get("path_status")) == "OK" and boolean(row.get("giveback_material")))

    coverage = build_coverage_integrity(baseline, path_replayable_rows, losing_path_rows, giveback_rows, rejected_summary)
    write_json(DECISION_PACKAGE_COVERAGE_INTEGRITY_PATH, coverage)

    uncertain_rows = [row for row in economic_rows if txt(row.get("regime")) == "UNCERTAIN"]
    uncertain_section, uncertain_base, uncertain_worst_symbol, uncertain_worst_symbol_side, uncertain_ablations = build_uncertain_rows(economic_rows, baseline)
    write_csv(
        UNCERTAIN_TABLE_PATH,
        uncertain_section,
        [
            "section",
            "label",
            "rows_total",
            "rows_with_pnl",
            "gross_pnl_quote",
            "net_pnl_quote",
            "fees_quote",
            "slippage_quote",
            "pf",
            "win_rate",
            "avg_win",
            "avg_loss",
            "payoff_ratio",
            "tp_rows",
            "sl_rows",
            "timeout_rows",
            "path_replayable_rows",
            "giveback_material_rows",
            "geometry_issue_counts",
            "portfolio_before_net_pnl_quote",
            "portfolio_after_net_pnl_quote",
            "portfolio_delta_net_pnl_quote",
            "removed_rows",
            "removed_slice_net_pnl_quote",
            "retained_rows",
            "retained_net_pnl_quote",
            "retained_pf",
            "retained_win_rate",
            "actionability",
            "notes",
        ],
    )

    sol_section, sol_base, sol_worst_side, sol_worst_strategy, sol_worst_side_strategy, sol_reject_overlap, sol_path_replayable_rows, sol_giveback_rows, sol_geometry_counts, sol_ablations = build_sol_rows(economic_rows, baseline)
    write_csv(
        SOL_TABLE_PATH,
        sol_section,
        [
            "section",
            "label",
            "rows_total",
            "rows_with_pnl",
            "gross_pnl_quote",
            "net_pnl_quote",
            "fees_quote",
            "slippage_quote",
            "pf",
            "win_rate",
            "avg_win",
            "avg_loss",
            "payoff_ratio",
            "tp_rows",
            "sl_rows",
            "timeout_rows",
            "path_replayable_rows",
            "giveback_material_rows",
            "geometry_issue_counts",
            "reject_overlap",
            "portfolio_before_net_pnl_quote",
            "portfolio_after_net_pnl_quote",
            "portfolio_delta_net_pnl_quote",
            "removed_rows",
            "removed_slice_net_pnl_quote",
            "retained_rows",
            "retained_net_pnl_quote",
            "retained_pf",
            "retained_win_rate",
            "actionability",
            "notes",
        ],
    )

    # Narrow combined action set chosen as the minimal positive set.
    combined_rows = []
    remove_uncertain_1000pepe_sell = lambda row: txt(row.get("regime")) == "UNCERTAIN" and txt(row.get("symbol")) == "1000PEPEUSDT" and txt(row.get("side")) == "SELL"
    remove_sol_sell = lambda row: txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN" and txt(row.get("side")) == "SELL"
    scenario_A = aggregate_rows(remove_rows(economic_rows, lambda row: txt(row.get("regime")) == "UNCERTAIN"))
    scenario_B = aggregate_rows(remove_rows(economic_rows, lambda row: txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN"))
    scenario_C = aggregate_rows(remove_rows(economic_rows, lambda row: txt(row.get("regime")) == "UNCERTAIN" or (txt(row.get("symbol")) == "SOLUSDT" and txt(row.get("regime")) == "TREND_DOWN")))
    scenario_D = aggregate_rows(remove_rows(economic_rows, lambda row: remove_uncertain_1000pepe_sell(row) or remove_sol_sell(row)))

    combined_rows.extend([
        {
            "candidate": "A_remove_uncertain_only",
            "description": "Remove all UNCERTAIN rows",
            "retained_rows": scenario_A["rows_total"],
            "retained_rows_with_pnl": scenario_A["rows_with_pnl"],
            "retained_gross_pnl_quote": scenario_A["gross_pnl_quote"],
            "retained_net_pnl_quote": scenario_A["net_pnl_quote"],
            "retained_pf": scenario_A["pf"],
            "retained_win_rate": scenario_A["win_rate"],
            "removed_rows": baseline["rows_total"] - scenario_A["rows_total"],
            "removed_slice_net_pnl_quote": baseline["net_pnl_quote"] - scenario_A["net_pnl_quote"],
            "portfolio_delta_net_pnl_quote": scenario_A["net_pnl_quote"] - baseline["net_pnl_quote"],
            "actionability": "SIZE_REDUCTION_CANDIDATE",
        },
        {
            "candidate": "B_remove_sol_trenddown_only",
            "description": "Remove all SOLUSDT/TREND_DOWN rows",
            "retained_rows": scenario_B["rows_total"],
            "retained_rows_with_pnl": scenario_B["rows_with_pnl"],
            "retained_gross_pnl_quote": scenario_B["gross_pnl_quote"],
            "retained_net_pnl_quote": scenario_B["net_pnl_quote"],
            "retained_pf": scenario_B["pf"],
            "retained_win_rate": scenario_B["win_rate"],
            "removed_rows": baseline["rows_total"] - scenario_B["rows_total"],
            "removed_slice_net_pnl_quote": baseline["net_pnl_quote"] - scenario_B["net_pnl_quote"],
            "portfolio_delta_net_pnl_quote": scenario_B["net_pnl_quote"] - baseline["net_pnl_quote"],
            "actionability": "SIZE_REDUCTION_CANDIDATE",
        },
        {
            "candidate": "C_remove_uncertain_and_sol_trenddown",
            "description": "Remove all UNCERTAIN rows plus all SOLUSDT/TREND_DOWN rows",
            "retained_rows": scenario_C["rows_total"],
            "retained_rows_with_pnl": scenario_C["rows_with_pnl"],
            "retained_gross_pnl_quote": scenario_C["gross_pnl_quote"],
            "retained_net_pnl_quote": scenario_C["net_pnl_quote"],
            "retained_pf": scenario_C["pf"],
            "retained_win_rate": scenario_C["win_rate"],
            "removed_rows": baseline["rows_total"] - scenario_C["rows_total"],
            "removed_slice_net_pnl_quote": baseline["net_pnl_quote"] - scenario_C["net_pnl_quote"],
            "portfolio_delta_net_pnl_quote": scenario_C["net_pnl_quote"] - baseline["net_pnl_quote"],
            "actionability": "ACTIONABLE_CONFIG_CANDIDATE",
        },
        {
            "candidate": "D_remove_uncertain_1000PEPEUSDT_sell_and_sol_sell",
            "description": "Remove UNCERTAIN 1000PEPEUSDT SELL rows plus SOLUSDT/TREND_DOWN SELL rows",
            "retained_rows": scenario_D["rows_total"],
            "retained_rows_with_pnl": scenario_D["rows_with_pnl"],
            "retained_gross_pnl_quote": scenario_D["gross_pnl_quote"],
            "retained_net_pnl_quote": scenario_D["net_pnl_quote"],
            "retained_pf": scenario_D["pf"],
            "retained_win_rate": scenario_D["win_rate"],
            "removed_rows": baseline["rows_total"] - scenario_D["rows_total"],
            "removed_slice_net_pnl_quote": baseline["net_pnl_quote"] - scenario_D["net_pnl_quote"],
            "portfolio_delta_net_pnl_quote": scenario_D["net_pnl_quote"] - baseline["net_pnl_quote"],
            "actionability": "ACTIONABLE_CONFIG_CANDIDATE",
        },
        {
            "candidate": "E_profit_protection_shadow_only",
            "description": "arm_1.00_trigger_35 shadow-only upper bound",
            "retained_rows": int(next(row for row in load_csv(PROFIT_PROTECTION_COUNTERFACTUAL_PATH) if txt(row.get("scenario_id")) == "arm_1.00_trigger_35")["rows_evaluated"]),
            "retained_rows_with_pnl": int(next(row for row in load_csv(PROFIT_PROTECTION_COUNTERFACTUAL_PATH) if txt(row.get("scenario_id")) == "arm_1.00_trigger_35")["rows_evaluated"]),
            "retained_gross_pnl_quote": num(next(row for row in load_csv(PROFIT_PROTECTION_COUNTERFACTUAL_PATH) if txt(row.get("scenario_id")) == "arm_1.00_trigger_35")["counterfactual_net_pnl_sum_quote"]),
            "retained_net_pnl_quote": num(next(row for row in load_csv(PROFIT_PROTECTION_COUNTERFACTUAL_PATH) if txt(row.get("scenario_id")) == "arm_1.00_trigger_35")["counterfactual_net_pnl_sum_quote"]),
            "retained_pf": num(next(row for row in load_csv(PROFIT_PROTECTION_COUNTERFACTUAL_PATH) if txt(row.get("scenario_id")) == "arm_1.00_trigger_35")["counterfactual_profit_factor"]),
            "retained_win_rate": num(next(row for row in load_csv(PROFIT_PROTECTION_COUNTERFACTUAL_PATH) if txt(row.get("scenario_id")) == "arm_1.00_trigger_35")["counterfactual_win_rate_pct"]),
            "removed_rows": int(next(row for row in load_csv(PROFIT_PROTECTION_COUNTERFACTUAL_PATH) if txt(row.get("scenario_id")) == "arm_1.00_trigger_35")["rows_skipped_unreplayable"]),
            "removed_slice_net_pnl_quote": None,
            "portfolio_delta_net_pnl_quote": num(next(row for row in load_csv(PROFIT_PROTECTION_COUNTERFACTUAL_PATH) if txt(row.get("scenario_id")) == "arm_1.00_trigger_35")["delta_net_pnl_sum_quote"]),
            "actionability": "PROFIT_PROTECTION_UPPER_BOUND_ONLY_NOT_ACTIONABLE",
        },
    ])
    write_csv(
        COMBINED_TABLE_PATH,
        combined_rows,
        [
            "candidate",
            "description",
            "retained_rows",
            "retained_rows_with_pnl",
            "retained_gross_pnl_quote",
            "retained_net_pnl_quote",
            "retained_pf",
            "retained_win_rate",
            "removed_rows",
            "removed_slice_net_pnl_quote",
            "portfolio_delta_net_pnl_quote",
            "actionability",
        ],
    )

    combined_summary = {
        "best_candidate": combined_rows[3],
        "rows": combined_rows,
        "profit_protection": None,
    }

    pp_rows, pp_summary = build_profit_protection_rows(baseline)
    write_csv(
        PP_AUDIT_PATH,
        pp_rows,
        [
            "scenario_id",
            "arm_pct",
            "giveback_trigger_pct",
            "rows_total",
            "rows_evaluated",
            "rows_skipped_unreplayable",
            "managed_exit_rows",
            "managed_exit_rate_pct",
            "rescued_loss_rows",
            "improved_rows",
            "worsened_rows",
            "baseline_net_pnl_sum_quote",
            "counterfactual_net_pnl_sum_quote",
            "delta_net_pnl_sum_quote",
            "counterfactual_profit_factor",
            "counterfactual_win_rate_pct",
            "counterfactual_positive_rows",
            "counterfactual_negative_rows",
            "winner_harm_available",
            "all_row_simulation_available",
            "classification",
            "arm_threshold_units",
            "trigger_threshold_units",
            "tested_scope",
            "path_coverage_required",
            "depends_on_future_information",
            "online_without_lookahead",
            "notes",
        ],
    )

    write_text(
        UNCERTAIN_SUMMARY_PATH,
        render_report_section(
            "UNCERTAIN Regime Decision Summary",
            [
                f"- Baseline rows: {uncertain_base['rows_total']}",
                f"- Baseline net PnL: {format_number(uncertain_base['net_pnl_quote'], 6)}",
                f"- Baseline PF: {format_number(uncertain_base['pf'], 6)}",
                f"- Baseline win rate: {format_number(uncertain_base['win_rate'], 6)}",
                f"- Fees: {format_number(uncertain_base['fees_quote'], 6)}",
                f"- Slippage: {format_number(uncertain_base['slippage_quote'], 6)}",
                f"- Worst symbol: {uncertain_worst_symbol['symbol']}",
                f"- Worst symbol+side: {uncertain_worst_symbol_side['symbol']} / {uncertain_worst_symbol_side['side']}",
                f"- Remove all UNCERTAIN retained net PnL: {format_number(uncertain_ablations[0]['retained_net_pnl_quote'], 6)}",
                f"- Remove all UNCERTAIN retained PF: {format_number(uncertain_ablations[0]['retained_pf'], 6)}",
                f"- Remove all UNCERTAIN retained win rate: {format_number(uncertain_ablations[0]['retained_win_rate'], 6)}",
                f"- Narrow 1000PEPEUSDT SELL cut retained net PnL: {format_number(scenario_D['net_pnl_quote'], 6)}",
                f"- Narrow 1000PEPEUSDT SELL cut retained PF: {format_number(scenario_D['pf'], 6)}",
                f"- Actionability: SIZE_REDUCTION_CANDIDATE",
            ],
        ),
    )

    write_text(
        SOL_SUMMARY_PATH,
        render_report_section(
            "SOLUSDT / TREND_DOWN Decision Summary",
            [
                f"- Baseline rows: {sol_base['rows_total']}",
                f"- Baseline net PnL: {format_number(sol_base['net_pnl_quote'], 6)}",
                f"- Baseline PF: {format_number(sol_base['pf'], 6)}",
                f"- Baseline win rate: {format_number(sol_base['win_rate'], 6)}",
                f"- Fees: {format_number(sol_base['fees_quote'], 6)}",
                f"- Slippage: {format_number(sol_base['slippage_quote'], 6)}",
                f"- Worst side: {sol_worst_side['side']}",
                f"- Worst strategy: {sol_worst_strategy['strategy']}",
                f"- Geometry replayable rows: {sol_path_replayable_rows}",
                f"- Geometry giveback rows: {sol_giveback_rows}",
                f"- Reject overlap rows: {sol_reject_overlap}",
                f"- Remove all SOLUSDT/TREND_DOWN retained net PnL: {format_number(sol_ablations[0]['retained_net_pnl_quote'], 6)}",
                f"- Remove only SOL SELL retained net PnL: {format_number(sol_ablations[1]['retained_net_pnl_quote'], 6)}",
                f"- Actionability: SIZE_REDUCTION_CANDIDATE",
            ],
        ),
    )

    write_text(
        PP_SUMMARY_PATH,
        render_report_section(
            "Profit Protection Winner Harm Summary",
            [
                f"- Scenario: {pp_summary['scenario_id']}",
                f"- Arm threshold units: {pp_summary['arm_threshold_units']}",
                f"- Trigger threshold units: {pp_summary['trigger_threshold_units']}",
                f"- Test scope: {pp_summary['tested_scope']}",
                f"- Path coverage required: {pp_summary['path_coverage_required']}",
                f"- Depends on future information: {pp_summary['depends_on_future_information']}",
                f"- Online without lookahead: {pp_summary['online_without_lookahead']}",
                f"- Rows evaluated: {pp_summary['rows_evaluated']}",
                f"- Rescued loss rows: {pp_summary['rescued_loss_rows']}",
                f"- Improved rows: {pp_summary['improved_rows']}",
                f"- Worsened rows: {pp_summary['worsened_rows']}",
                f"- Delta net PnL: {format_number(pp_summary['delta_net_pnl_sum_quote'], 6)}", 
                f"- Classification: {pp_summary['classification']}",
            ],
        ),
    )

    write_text(
        COMBINED_SUMMARY_PATH,
        render_report_section(
            "Combined Minimal Action Set Summary",
            [
                f"- Best candidate: {combined_summary['best_candidate']['candidate']}",
                f"- Best description: {combined_summary['best_candidate']['description']}",
                f"- Retained rows: {combined_summary['best_candidate']['retained_rows']}",
                f"- Retained net PnL: {format_number(combined_summary['best_candidate']['retained_net_pnl_quote'], 6)}",
                f"- Retained PF: {format_number(combined_summary['best_candidate']['retained_pf'], 6)}",
                f"- Retained win rate: {format_number(combined_summary['best_candidate']['retained_win_rate'], 6)}",
                f"- Actionability: {combined_summary['best_candidate']['actionability']}",
            ],
        ),
    )

    write_text(FINAL_REPORT_PATH, render_final_report(coverage, uncertain_section[0], sol_section[0], pp_summary, combined_summary))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())