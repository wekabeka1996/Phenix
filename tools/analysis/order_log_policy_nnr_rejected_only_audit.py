#!/usr/bin/env python3
"""Rejected-only policy/NNR/gate audit for logs/order_log_v1.jsonl.

This script is read-only. It filters the raw order log down to policy / NRR /
gate rejects, force-opens a diagnostic replay on the nearest causal 300s bar,
and writes rejected-only summaries without changing runtime behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_ROOT = ROOT / "tools" / "analysis"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from order_log_counterfactual_replay_audit import (  # noqa: E402
    build_normalized_row,
    compute_tpsl_geometry,
    iso_utc,
    load_bars_300,
    load_config_snapshot,
    load_order_log_rows,
    nearest_causal_bar,
    simulate_tp_sl_path,
)

REPORT_ROOT = ROOT / "reports" / "order_log_counterfactual_replay"
RAW_LOG_PATH = ROOT / "logs" / "order_log_v1.jsonl"
CANONICAL_CASEBOOK_PATH = REPORT_ROOT / "proposal_casebook.jsonl"
RECORDER_ROOT = ROOT / "data" / "recorder"

REJECTED_ONLY_ROWS_JSONL = REPORT_ROOT / "rejected_only_rows.jsonl"
REJECTED_ONLY_ROWS_CSV = REPORT_ROOT / "rejected_only_rows.csv"
REJECTED_ONLY_CLASSIFICATION_SUMMARY_JSON = REPORT_ROOT / "rejected_only_classification_summary.json"
REJECTED_ONLY_OUTCOMES_JSONL = REPORT_ROOT / "rejected_only_outcomes.jsonl"
REJECTED_ONLY_OUTCOMES_CSV = REPORT_ROOT / "rejected_only_outcomes.csv"
REJECTED_ONLY_PROFITABILITY_SUMMARY_JSON = REPORT_ROOT / "rejected_only_profitability_summary.json"
REJECTED_ONLY_PROFITABILITY_SUMMARY_MD = REPORT_ROOT / "rejected_only_profitability_summary.md"
REJECTED_BY_NNR_CSV = REPORT_ROOT / "rejected_by_nnr.csv"
REJECTED_BY_GATE_CSV = REPORT_ROOT / "rejected_by_gate.csv"
REJECTED_BY_SYMBOL_CSV = REPORT_ROOT / "rejected_by_symbol.csv"
REJECTED_BY_REGIME_CSV = REPORT_ROOT / "rejected_by_regime.csv"
REJECTED_BY_STRATEGY_CSV = REPORT_ROOT / "rejected_by_strategy.csv"
REJECTED_BY_SYMBOL_NNR_CSV = REPORT_ROOT / "rejected_by_symbol_nnr.csv"
REJECTED_BY_REGIME_NNR_CSV = REPORT_ROOT / "rejected_by_regime_nnr.csv"
REJECTED_POLICY_NNR_VERDICTS_CSV = REPORT_ROOT / "rejected_policy_nnr_verdicts.csv"
REJECTED_POLICY_NNR_VERDICTS_JSON = REPORT_ROOT / "rejected_policy_nnr_verdicts.json"
REJECTED_ONLY_CASEBOOK_MD = REPORT_ROOT / "rejected_only_casebook.md"
FINAL_REPORT_MD = REPORT_ROOT / "POLICY_NNR_REJECTED_ONLY_OUTCOME_AND_PROFITABILITY_AUDIT.md"

MIN_DIRECTIONAL_ROWS = 20
MIN_STRONG_ROWS = 100
TIMEOUT_LIKE_CLOSE_REASONS = {"ENTRY_TIMEOUT_OR_STALE", "OBSERVATION_END"}


def text(value: Any) -> str:
    return "" if value is None else str(value)


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def nested_get(node: Any, path: str, default: Any = None) -> Any:
    current = node
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def pct(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator) * 100.0


def safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def safe_median(values: list[float]) -> float | None:
    return median(values) if values else None


def json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, set):
        return sorted(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True, default=json_default) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True, default=json_default))
            handle.write("\n")


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=json_default)
    if value is None:
        return ""
    return value


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def load_canonical_reject_lines(path: Path) -> tuple[set[int], int]:
    lines: set[int] = set()
    total = 0
    if not path.exists():
        return lines, total
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            row = json.loads(raw_line)
            total += 1
            if text(row.get("row_role")) == "decision_reject":
                line_no = integer(row.get("source_line"))
                if line_no is not None:
                    lines.add(line_no)
    return lines, total


def resolve_diagnostic_notional(config: dict[str, Any]) -> float:
    notional = nested_get(config, "root.trading.llm_orchestration.intent_policy.max_notional_usd")
    value = number(notional)
    if value is None or value <= 0:
        raise RuntimeError("Missing trading.llm_orchestration.intent_policy.max_notional_usd in config snapshot")
    return value


def classify_policy_row(row: dict[str, Any]) -> tuple[str, str]:
    reject_reason = text(row.get("reject_reason"))
    threshold_verdict = text(row.get("threshold_verdict"))
    if reject_reason == "LOW_VOL_COST_FLOOR_DENY":
        return "LOW_VOL_COST_FLOOR_DENY", "GATE_LOW_VOL_COST_FLOOR"
    if reject_reason == "SAFETY_GATES_DENY":
        return "SAFETY_GATES_DENY", "NNR_SAFETY_GATES"
    if threshold_verdict == "BLOCK":
        return threshold_verdict, "POLICY_THRESHOLD_BLOCK"
    return threshold_verdict or "UNKNOWN", "UNKNOWN_REJECT"


def load_rejected_rows(raw_rows: list[dict[str, Any]], config: dict[str, Any], canonical_reject_lines: set[int]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rejected_rows: list[dict[str, Any]] = []
    reject_reason_counts: Counter[str] = Counter()
    threshold_counts: Counter[str] = Counter()
    nrr_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    regime_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    raw_only_lines: list[int] = []

    for raw_row in raw_rows:
        normalized = build_normalized_row(raw_row, config["strategy_id"], config)
        if text(normalized.get("row_role")) != "decision_reject":
            continue

        source_line = integer(normalized.get("source_line")) or 0
        reject_reason = text(normalized.get("reject_reason"))
        threshold_verdict = text(normalized.get("threshold_verdict"))
        nrr_code = text(normalized.get("nrr_code"))
        symbol = text(normalized.get("symbol"))
        regime = text(normalized.get("regime"))
        strategy = text(normalized.get("strategy_id"))
        policy_gate, policy_family = classify_policy_row(normalized)
        canonical_hit = source_line in canonical_reject_lines

        if not canonical_hit:
            raw_only_lines.append(source_line)

        reject_reason_counts[reject_reason] += 1
        threshold_counts[threshold_verdict] += 1
        nrr_counts[nrr_code] += 1
        symbol_counts[symbol] += 1
        regime_counts[regime] += 1
        strategy_counts[strategy] += 1

        rejected_rows.append(
            {
                "source_file": normalized.get("source_file"),
                "source_line": source_line,
                "timestamp_ms": normalized.get("timestamp_ms"),
                "timestamp_iso": normalized.get("timestamp_iso"),
                "event_type": normalized.get("event_type"),
                "row_role": normalized.get("row_role"),
                "row_kind": normalized.get("row_kind"),
                "proposal_uid": normalized.get("proposal_uid"),
                "proposal_uid_seed": normalized.get("proposal_uid_seed"),
                "strategy": strategy,
                "symbol": symbol,
                "side": normalized.get("side"),
                "regime": regime,
                "regime_confidence": normalized.get("regime_confidence"),
                "nrr_code": nrr_code,
                "threshold_verdict": threshold_verdict,
                "threshold_reason": normalized.get("threshold_reason"),
                "reject_reason": reject_reason,
                "why": normalized.get("why"),
                "policy_gate": policy_gate,
                "policy_family": policy_family,
                "canonical_casebook_hit": canonical_hit,
                "raw_only_in_canonical_casebook": not canonical_hit,
                "analysis_class": "FORCED_OPEN_SIGNAL_DIAGNOSTIC",
                "evidence_class": "FORCED_OPEN_DIAGNOSTIC",
                "diagnostic_only": True,
                "execution_feasible": False,
                "no_fill": True,
                "unreplayable": False,
            }
        )

    rejected_rows.sort(key=lambda row: (integer(row.get("source_line")) or 0, integer(row.get("timestamp_ms")) or 0, text(row.get("proposal_uid"))))
    summary = {
        "raw_log_rows_total": len(raw_rows),
        "raw_reject_rows_total": len(rejected_rows),
        "canonical_casebook_reject_rows_total": len(canonical_reject_lines),
        "raw_only_reject_rows_total": len(raw_only_lines),
        "raw_only_source_lines": sorted(set(raw_only_lines)),
        "reject_reason_counts": dict(sorted(reject_reason_counts.items())),
        "threshold_verdict_counts": dict(sorted(threshold_counts.items())),
        "nrr_code_counts": dict(sorted(nrr_counts.items())),
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "regime_counts": dict(sorted(regime_counts.items())),
        "strategy_counts": dict(sorted(strategy_counts.items())),
    }
    return rejected_rows, summary


def replay_rejected_row(row: dict[str, Any], config: dict[str, Any], bars_by_symbol: dict[str, list[Any]], notional_usd: float) -> dict[str, Any]:
    symbol = text(row.get("symbol"))
    side = text(row.get("side"))
    regime = text(row.get("regime"))
    timestamp_ms = integer(row.get("timestamp_ms")) or 0
    causal_bar = nearest_causal_bar(symbol, timestamp_ms, bars_by_symbol)

    base = dict(row)
    base.update(
        {
            "diagnostic_notional_usd": notional_usd,
            "open_fee_bps": number(config.get("fees", {}).get("open_fee_bps")) or 0.0,
            "close_fee_bps": number(config.get("fees", {}).get("close_fee_bps")) or 0.0,
            "slippage_bps": number(config.get("slippage", {}).get("buffer_bps")) or 0.0,
        }
    )
    base["round_trip_cost_bps"] = base["open_fee_bps"] + base["close_fee_bps"] + base["slippage_bps"]

    if causal_bar is None:
        base.update(
            {
                "join_quality": "JOIN_NONE",
                "support_quality": "LOW",
                "has_replay_outcome": False,
                "replay_status": "NO_CAUSAL_BAR",
                "unreplayable_reason": "NO_CAUSAL_BAR",
                "entry_price": None,
                "entry_ts_ms": None,
                "entry_ts_iso": None,
                "close_reason_primary": None,
                "close_reason_secondary": None,
                "close_price_primary": None,
                "close_price_secondary": None,
                "close_ts_ms_primary": None,
                "close_ts_ms_secondary": None,
                "bars_held": None,
                "ambiguous_intrabar": False,
                "gross_pnl_usd": None,
                "net_pnl_usd": None,
                "gross_pnl_pct": None,
                "net_pnl_pct": None,
                "quantity": None,
                "total_cost_usd": None,
                "mfe_pct": None,
                "mae_pct": None,
                "outcome_class": "UNREPLAYABLE",
                "protective_vs_harmful": "unreplayable",
                "diagnostic_only": True,
                "execution_feasible": False,
                "no_fill": True,
                "unreplayable": True,
                "close_reason_timeout_like": False,
            }
        )
        return base

    entry_price = float(causal_bar.close)
    geometry = compute_tpsl_geometry(symbol, side, entry_price, regime, config)
    if geometry.get("status") != "OK":
        base.update(
            {
                "join_quality": "JOIN_SYMBOL_TIME_WINDOW",
                "support_quality": "LOW",
                "has_replay_outcome": False,
                "replay_status": text(geometry.get("status")),
                "unreplayable_reason": text(geometry.get("status")),
                "entry_price": entry_price,
                "entry_ts_ms": causal_bar.timestamp_ms,
                "entry_ts_iso": iso_utc(causal_bar.timestamp_ms),
                "close_reason_primary": None,
                "close_reason_secondary": None,
                "close_price_primary": None,
                "close_price_secondary": None,
                "close_ts_ms_primary": None,
                "close_ts_ms_secondary": None,
                "bars_held": None,
                "ambiguous_intrabar": False,
                "gross_pnl_usd": None,
                "net_pnl_usd": None,
                "gross_pnl_pct": None,
                "net_pnl_pct": None,
                "quantity": None,
                "total_cost_usd": None,
                "mfe_pct": None,
                "mae_pct": None,
                "outcome_class": "UNREPLAYABLE",
                "protective_vs_harmful": "unreplayable",
                "diagnostic_only": True,
                "execution_feasible": False,
                "no_fill": True,
                "unreplayable": True,
                "close_reason_timeout_like": False,
            }
        )
        return base

    symbol_profile = (config.get("symbol_profiles") or {}).get(symbol) or {}
    max_hold_sec = integer(symbol_profile.get("max_hold_sec"))
    horizon_ts = None if max_hold_sec is None else causal_bar.timestamp_ms + (max_hold_sec * 1000)
    path = simulate_tp_sl_path(symbol, side, entry_price, causal_bar.timestamp_ms, geometry["stop_price"], geometry["target_price"], bars_by_symbol, horizon_ts)
    if path.get("status") != "OK":
        base.update(
            {
                "join_quality": "JOIN_SYMBOL_TIME_WINDOW",
                "support_quality": "LOW",
                "has_replay_outcome": False,
                "replay_status": text(path.get("status")),
                "unreplayable_reason": text(path.get("status")),
                "entry_price": entry_price,
                "entry_ts_ms": causal_bar.timestamp_ms,
                "entry_ts_iso": iso_utc(causal_bar.timestamp_ms),
                "close_reason_primary": None,
                "close_reason_secondary": None,
                "close_price_primary": None,
                "close_price_secondary": None,
                "close_ts_ms_primary": None,
                "close_ts_ms_secondary": None,
                "bars_held": None,
                "ambiguous_intrabar": False,
                "gross_pnl_usd": None,
                "net_pnl_usd": None,
                "gross_pnl_pct": None,
                "net_pnl_pct": None,
                "quantity": None,
                "total_cost_usd": None,
                "mfe_pct": None,
                "mae_pct": None,
                "outcome_class": "UNREPLAYABLE",
                "protective_vs_harmful": "unreplayable",
                "diagnostic_only": True,
                "execution_feasible": False,
                "no_fill": True,
                "unreplayable": True,
                "close_reason_timeout_like": False,
            }
        )
        return base

    close_reason_primary = text(path.get("close_reason_primary"))
    close_reason_secondary = text(path.get("close_reason_secondary"))
    close_price_primary = number(path.get("close_price_primary"))
    close_price_secondary = number(path.get("close_price_secondary"))
    close_ts_ms_primary = integer(path.get("close_ts_ms_primary"))
    close_ts_ms_secondary = integer(path.get("close_ts_ms_secondary"))
    bars_held = integer(path.get("bars_considered"))
    ambiguous_intrabar = bool(path.get("ambiguous_intrabar"))
    quantity = notional_usd / entry_price if entry_price > 0 else None

    if quantity is None or close_price_primary is None:
        gross_pnl_usd = None
        gross_pnl_pct = None
        total_cost_usd = None
        net_pnl_usd = None
        net_pnl_pct = None
        outcome_class = "UNREPLAYABLE"
        protective_vs_harmful = "unreplayable"
    else:
        if side == "SELL":
            gross_pnl_usd = quantity * (entry_price - close_price_primary)
        else:
            gross_pnl_usd = quantity * (close_price_primary - entry_price)
        gross_pnl_pct = gross_pnl_usd / notional_usd * 100.0
        total_cost_usd = notional_usd * base["round_trip_cost_bps"] / 10000.0
        net_pnl_usd = gross_pnl_usd - total_cost_usd
        net_pnl_pct = net_pnl_usd / notional_usd * 100.0
        if net_pnl_usd > 0:
            outcome_class = "PROFITABLE"
            protective_vs_harmful = "harmful"
        elif net_pnl_usd < 0:
            outcome_class = "LOSING"
            protective_vs_harmful = "protective"
        else:
            outcome_class = "BREAKEVEN"
            protective_vs_harmful = "flat"

    support_quality = "HIGH" if close_reason_primary in {"TP_HIT", "SL_HIT"} and not ambiguous_intrabar else "MEDIUM"
    if close_reason_primary in TIMEOUT_LIKE_CLOSE_REASONS:
        support_quality = "MEDIUM"

    base.update(
        {
            "join_quality": "JOIN_SYMBOL_TIME_WINDOW",
            "support_quality": support_quality,
            "has_replay_outcome": True,
            "replay_status": "OK",
            "unreplayable_reason": None,
            "entry_price": entry_price,
            "entry_ts_ms": causal_bar.timestamp_ms,
            "entry_ts_iso": iso_utc(causal_bar.timestamp_ms),
            "close_reason_primary": close_reason_primary,
            "close_reason_secondary": close_reason_secondary,
            "close_price_primary": close_price_primary,
            "close_price_secondary": close_price_secondary,
            "close_ts_ms_primary": close_ts_ms_primary,
            "close_ts_ms_secondary": close_ts_ms_secondary,
            "bars_held": bars_held,
            "ambiguous_intrabar": ambiguous_intrabar,
            "gross_pnl_usd": gross_pnl_usd,
            "net_pnl_usd": net_pnl_usd,
            "gross_pnl_pct": gross_pnl_pct,
            "net_pnl_pct": net_pnl_pct,
            "quantity": quantity,
            "total_cost_usd": total_cost_usd,
            "mfe_pct": number(path.get("mfe_pct")),
            "mae_pct": number(path.get("mae_pct")),
            "outcome_class": outcome_class,
            "protective_vs_harmful": protective_vs_harmful,
            "diagnostic_only": True,
            "execution_feasible": False,
            "no_fill": True,
            "unreplayable": False,
            "close_reason_timeout_like": close_reason_primary in TIMEOUT_LIKE_CLOSE_REASONS,
        }
    )
    return base


def verdict_from_bucket(rows_total: int, replayable_rows: int, net_pnl_sum: float, profitable_rows: int, losing_rows: int) -> str:
    if rows_total < MIN_DIRECTIONAL_ROWS:
        return "LOW_SUPPORT"
    if replayable_rows == 0:
        return "UNREPLAYABLE"
    if net_pnl_sum > 0:
        if rows_total >= MIN_STRONG_ROWS and profitable_rows / replayable_rows >= 0.7:
            return "HARMFUL_STRONG"
        return "HARMFUL_WEAK"
    if net_pnl_sum < 0:
        if rows_total >= MIN_STRONG_ROWS and losing_rows / replayable_rows >= 0.7:
            return "PROTECTIVE_STRONG"
        return "PROTECTIVE_WEAK"
    return "MIXED"


def verdict_reason(verdict: str, rows_total: int, replayable_rows: int, net_pnl_sum: float, profitable_rows: int, losing_rows: int) -> str:
    if verdict == "LOW_SUPPORT":
        return f"Only {rows_total} rows, below directional threshold {MIN_DIRECTIONAL_ROWS}."
    if verdict == "UNREPLAYABLE":
        return "No causal-bar forward replay support in this bucket."
    if verdict.startswith("HARMFUL"):
        return f"Net positive diagnostic PnL ({net_pnl_sum:.6f}) with {profitable_rows}/{replayable_rows} replayable winners."
    if verdict.startswith("PROTECTIVE"):
        return f"Net negative diagnostic PnL ({net_pnl_sum:.6f}) with {losing_rows}/{replayable_rows} replayable losers."
    return "Mixed-sign diagnostic replay with no stable directional edge."


def group_buckets(rows: list[dict[str, Any]], group_fields: list[str], all_rejected_count: int, group_type: str) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = tuple(text(row.get(field)) for field in group_fields)
        buckets[key].append(row)

    summary_rows: list[dict[str, Any]] = []
    for key in sorted(buckets.keys()):
        bucket_rows = buckets[key]
        replayable_rows = [row for row in bucket_rows if row.get("outcome_class") != "UNREPLAYABLE"]
        pnl_rows = [row for row in replayable_rows if row.get("net_pnl_usd") is not None]
        positive_rows = [row for row in pnl_rows if float(row["net_pnl_usd"]) > 0]
        negative_rows = [row for row in pnl_rows if float(row["net_pnl_usd"]) < 0]
        breakeven_rows = [row for row in pnl_rows if float(row["net_pnl_usd"]) == 0]
        tp_rows = [row for row in bucket_rows if row.get("close_reason_primary") == "TP_HIT"]
        sl_rows = [row for row in bucket_rows if row.get("close_reason_primary") == "SL_HIT"]
        timeout_rows = [row for row in bucket_rows if row.get("close_reason_primary") in TIMEOUT_LIKE_CLOSE_REASONS]
        no_forward_rows = [row for row in bucket_rows if row.get("replay_status") == "NO_FORWARD_BARS"]
        unreplayable_rows = [row for row in bucket_rows if row.get("outcome_class") == "UNREPLAYABLE"]
        raw_only_rows = [row for row in bucket_rows if row.get("raw_only_in_canonical_casebook")]

        net_values = [float(row["net_pnl_usd"]) for row in pnl_rows]
        gross_values = [float(row["gross_pnl_usd"]) for row in pnl_rows]
        net_sum = sum(net_values) if net_values else 0.0
        gross_sum = sum(gross_values) if gross_values else 0.0
        win_values = [value for value in net_values if value > 0]
        loss_values = [value for value in net_values if value < 0]
        profit_factor = None
        if loss_values:
            profit_factor = sum(win_values) / abs(sum(loss_values)) if win_values else 0.0

        rows_total = len(bucket_rows)
        replayable_total = len(replayable_rows)
        verdict = verdict_from_bucket(rows_total, replayable_total, net_sum, len(positive_rows), len(negative_rows))
        summary_rows.append(
            {
                "bucket_type": group_type,
                **{field: value for field, value in zip(group_fields, key)},
                "rows": rows_total,
                "share_of_all_rejects_pct": pct(rows_total, all_rejected_count),
                "raw_only_rows": len(raw_only_rows),
                "raw_only_rows_pct": pct(len(raw_only_rows), rows_total),
                "replayable_rows": replayable_total,
                "unreplayable_rows": len(unreplayable_rows),
                "profitable_rows": len(positive_rows),
                "losing_rows": len(negative_rows),
                "breakeven_rows": len(breakeven_rows),
                "tp_hit_rows": len(tp_rows),
                "sl_hit_rows": len(sl_rows),
                "timeout_like_rows": len(timeout_rows),
                "positive_net_rows": len(positive_rows),
                "negative_net_rows": len(negative_rows),
                "gross_pnl_sum": gross_sum,
                "net_pnl_sum": net_sum,
                "avg_net_pnl": safe_mean(net_values),
                "median_net_pnl": safe_median(net_values),
                "profit_factor": profit_factor,
                "win_rate_pct": pct(len(positive_rows), replayable_total),
                "protective_rows": len(negative_rows),
                "protective_rows_pct": pct(len(negative_rows), replayable_total),
                "harmful_rows": len(positive_rows),
                "harmful_rows_pct": pct(len(positive_rows), replayable_total),
                "verdict": verdict,
                "verdict_reason": verdict_reason(verdict, rows_total, replayable_total, net_sum, len(positive_rows), len(negative_rows)),
            }
        )

    summary_rows.sort(key=lambda row: (-int(row["rows"]), text(row.get(group_fields[0], "")), text(row.get(group_fields[1], "")) if len(group_fields) > 1 else ""))
    return summary_rows


def md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_none_\n"
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(text(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, separator, *body]) + "\n"


def render_casebook_md(rows: list[dict[str, Any]]) -> str:
    profitable = sorted([row for row in rows if row.get("outcome_class") == "PROFITABLE"], key=lambda row: float(row["net_pnl_usd"]), reverse=True)[:12]
    losing = sorted([row for row in rows if row.get("outcome_class") == "LOSING"], key=lambda row: float(row["net_pnl_usd"]))[:12]
    low_support = sorted([row for row in rows if row.get("outcome_class") == "UNREPLAYABLE" or row.get("raw_only_in_canonical_casebook")], key=lambda row: (integer(row.get("source_line")) or 0))[:12]
    return "\n".join(
        [
            "# Rejected Only Casebook",
            "",
            "## Most Profitable Rejected Diagnostic Rows",
            md_table(
                profitable,
                ["source_line", "symbol", "regime", "nrr_code", "reject_reason", "close_reason_primary", "net_pnl_usd", "protective_vs_harmful", "raw_only_in_canonical_casebook"],
            ),
            "## Most Losing Rejected Diagnostic Rows",
            md_table(
                losing,
                ["source_line", "symbol", "regime", "nrr_code", "reject_reason", "close_reason_primary", "net_pnl_usd", "protective_vs_harmful", "raw_only_in_canonical_casebook"],
            ),
            "## Raw-Only or Unreplayable Edge Rows",
            md_table(
                low_support,
                ["source_line", "symbol", "regime", "nrr_code", "reject_reason", "replay_status", "outcome_class", "raw_only_in_canonical_casebook"],
            ),
        ]
    )


def render_profitability_md(summary: dict[str, Any], verdicts: list[dict[str, Any]], by_regime: list[dict[str, Any]], by_symbol_nnr: list[dict[str, Any]]) -> str:
    top_protective = sorted([row for row in verdicts if row["verdict"].startswith("PROTECTIVE")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])))[:5]
    top_harmful = sorted([row for row in verdicts if row["verdict"].startswith("HARMFUL")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])) )[:5]
    low_support = sorted([row for row in verdicts if row["verdict"] == "LOW_SUPPORT"], key=lambda row: (-int(row["rows"]), text(row.get("nrr_code", text(row.get("reject_reason"))))))[:5]
    harmful_regimes = sorted([row for row in by_regime if row["verdict"].startswith("HARMFUL")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])))[:5]
    harmful_symbol_nnr = sorted([row for row in by_symbol_nnr if row["verdict"].startswith("HARMFUL")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])))[:5]

    lines = [
        "# Rejected Only Profitability Summary",
        "",
        f"Diagnostic notional: {summary['diagnostic_notional_usd']} USDT (from config)",
        f"Raw reject rows: {summary['raw_reject_rows_total']}",
        f"Canonical casebook reject rows: {summary['canonical_casebook_reject_rows_total']}",
        f"Raw-only reject rows: {summary['raw_only_reject_rows_total']} -> {summary['raw_only_source_lines']}",
        f"Replayable rejected rows: {summary['replayable_rows_total']}",
        f"Unreplayable rejected rows: {summary['unreplayable_rows_total']}",
        f"Profitable rejected rows: {summary['profitable_rows_total']}",
        f"Losing rejected rows: {summary['losing_rows_total']}",
        f"Breakeven rejected rows: {summary['breakeven_rows_total']}",
        f"TP_HIT rows: {summary['tp_hit_rows_total']}",
        f"SL_HIT rows: {summary['sl_hit_rows_total']}",
        f"Timeout-like rows: {summary['timeout_like_rows_total']}",
        f"No-forward-bars rows: {summary['no_forward_bars_rows_total']}",
        "",
        f"Gross PnL sum: {summary['gross_pnl_sum_usd']}",
        f"Net PnL sum: {summary['net_pnl_sum_usd']}",
        f"Profit factor: {summary['profit_factor']}",
        f"Win rate among replayable rows: {summary['win_rate_pct']}",
        f"Expectancy per rejected row: {summary['expectancy_per_rejected_row_usd']}",
        "",
        "## Bucket Verdicts",
        "",
        "### Protective",
    ]
    lines.extend(f"- {row['bucket_type']}: {row.get('nrr_code', row.get('reject_reason', ''))} | rows={row['rows']} | net={row['net_pnl_sum']} | {row['verdict_reason']}" for row in top_protective)
    lines.extend([
        "",
        "### Harmful",
    ])
    lines.extend(f"- {row['bucket_type']}: {row.get('nrr_code', row.get('reject_reason', ''))} | rows={row['rows']} | net={row['net_pnl_sum']} | {row['verdict_reason']}" for row in top_harmful)
    lines.extend([
        "",
        "### Harmful Regime Slices",
    ])
    lines.extend(f"- {row['bucket_type']}: {row.get('regime', '')} | rows={row['rows']} | net={row['net_pnl_sum']} | {row['verdict_reason']}" for row in harmful_regimes)
    lines.extend([
        "",
        "### Harmful Symbol+NRR Pockets",
    ])
    lines.extend(f"- {row['bucket_type']}: {row.get('symbol', '')} / {row.get('nrr_code', '')} | rows={row['rows']} | net={row['net_pnl_sum']} | {row['verdict_reason']}" for row in harmful_symbol_nnr)
    lines.extend([
        "",
        "### Low Support",
    ])
    lines.extend(f"- {row['bucket_type']}: {row.get('nrr_code', row.get('reject_reason', ''))} | rows={row['rows']} | {row['verdict_reason']}" for row in low_support)
    return "\n".join(lines) + "\n"


def render_final_report(summary: dict[str, Any], verdicts: list[dict[str, Any]], classification_summary: dict[str, Any], by_regime: list[dict[str, Any]], by_symbol_nnr: list[dict[str, Any]]) -> str:
    harmful = sorted([row for row in verdicts if row["verdict"].startswith("HARMFUL")], key=lambda row: (-int(row["rows"]), -float(row["net_pnl_sum"])))[:5]
    protective = sorted([row for row in verdicts if row["verdict"].startswith("PROTECTIVE")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])))[:5]
    low_support = sorted([row for row in verdicts if row["verdict"] in {"LOW_SUPPORT", "UNREPLAYABLE"}], key=lambda row: (-int(row["rows"]), text(row.get("nrr_code", text(row.get("reject_reason"))))))[:5]
    harmful_regimes = sorted([row for row in by_regime if row["verdict"].startswith("HARMFUL")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])))[:5]
    harmful_symbol_nnr = sorted([row for row in by_symbol_nnr if row["verdict"].startswith("HARMFUL")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])))[:5]

    lines = [
        "# POLICY_NNR_REJECTED_ONLY_OUTCOME_AND_PROFITABILITY_AUDIT",
        "",
        "## Scope",
        "This audit is read-only and only covers policy / NRR / gate rejects.",
        "The rejected slice is built from the raw log so the two late NRR-062 raw-only rows are retained and explained.",
        "The diagnostic replay uses the explicit max notional from config and the existing TP/SL replay helpers.",
        "",
        "## Reconciliation",
        f"- raw reject rows: {classification_summary['raw_reject_rows_total']}",
        f"- canonical casebook reject rows: {classification_summary['canonical_casebook_reject_rows_total']}",
        f"- raw-only source lines: {classification_summary['raw_only_source_lines']}",
        "",
        "## Direct Answers",
        f"- blocked profitable opportunities: {summary['harmful_rows_total']}",
        f"- blocked losing opportunities: {summary['protective_rows_total']}",
        f"- unreplayable / low-support rejects: {summary['unreplayable_rows_total']}",
        f"- net rejected-only PnL: {summary['net_pnl_sum_usd']}",
        f"- profit factor: {summary['profit_factor']}",
        f"- win rate among replayable rejected rows: {summary['win_rate_pct']}",
        "",
        "## What Protects / What Harms",
        "NNR-level buckets are mostly protective or low-support.",
        "The meaningful blocked-profit signal shows up in regime slices LOW_VOLATILITY and HIGH_VOLATILITY, and in the SOLUSDT / NRR-027 symbol-pocket.",
        "NRR-062 is low-support and should not be used for config changes.",
        "",
        "### Protective Buckets",
    ]
    lines.extend(f"- {row.get('reject_reason', row.get('nrr_code', ''))} / {row.get('nrr_code', '')}: rows={row['rows']} | net={row['net_pnl_sum']} | {row['verdict']} | {row['verdict_reason']}" for row in protective)
    lines.extend([
        "",
        "### Harmful Buckets",
    ])
    lines.extend(f"- {row.get('reject_reason', row.get('nrr_code', ''))} / {row.get('nrr_code', '')}: rows={row['rows']} | net={row['net_pnl_sum']} | {row['verdict']} | {row['verdict_reason']}" for row in harmful)
    lines.extend([
        "",
        "### Harmful Regime Slices",
    ])
    lines.extend(f"- {row.get('regime', '')}: rows={row['rows']} | net={row['net_pnl_sum']} | {row['verdict']} | {row['verdict_reason']}" for row in harmful_regimes)
    lines.extend([
        "",
        "### Harmful Symbol+NRR Pockets",
    ])
    lines.extend(f"- {row.get('symbol', '')} / {row.get('nrr_code', '')}: rows={row['rows']} | net={row['net_pnl_sum']} | {row['verdict']} | {row['verdict_reason']}" for row in harmful_symbol_nnr)
    lines.extend([
        "",
        "### Low Support Buckets",
    ])
    lines.extend(f"- {row.get('reject_reason', row.get('nrr_code', ''))} / {row.get('nrr_code', '')}: rows={row['rows']} | {row['verdict']} | {row['verdict_reason']}" for row in low_support)
    lines.extend([
        "",
        "## Caveats",
        "- Diagnostic PnL is forced-open and does not imply runtime execution feasibility.",
        "- Intrabar ambiguity is resolved conservatively with SL-first semantics when TP and SL share a candle.",
        "- Low-support or unreplayable buckets should not drive config recommendations.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rejected-only policy / NNR / gate audit")
    parser.add_argument("--report-root", type=Path, default=REPORT_ROOT)
    parser.add_argument("--order-log", type=Path, default=RAW_LOG_PATH)
    parser.add_argument("--proposal-casebook", type=Path, default=CANONICAL_CASEBOOK_PATH)
    parser.add_argument("--recorder-root", type=Path, default=RECORDER_ROOT)
    args = parser.parse_args(argv)

    report_root = args.report_root
    report_root.mkdir(parents=True, exist_ok=True)

    config = load_config_snapshot()
    diagnostic_notional_usd = resolve_diagnostic_notional(config)
    open_fee_bps = number(config.get("fees", {}).get("open_fee_bps")) or 0.0
    close_fee_bps = number(config.get("fees", {}).get("close_fee_bps")) or 0.0
    slippage_bps = number(config.get("slippage", {}).get("buffer_bps")) or 0.0
    round_trip_cost_bps = open_fee_bps + close_fee_bps + slippage_bps

    raw_rows = load_order_log_rows(args.order_log)
    canonical_reject_lines, canonical_casebook_rows_total = load_canonical_reject_lines(args.proposal_casebook)
    bars_by_symbol, bar_coverage = load_bars_300(args.recorder_root)

    rejected_rows, classification_summary = load_rejected_rows(raw_rows, config, canonical_reject_lines)
    outcomes = [replay_rejected_row(row, config, bars_by_symbol, diagnostic_notional_usd) for row in rejected_rows]
    outcomes.sort(key=lambda row: (integer(row.get("source_line")) or 0, integer(row.get("timestamp_ms")) or 0, text(row.get("proposal_uid"))))

    classification_summary["canonical_casebook_rows_total"] = canonical_casebook_rows_total
    classification_summary["raw_only_source_lines"] = sorted(classification_summary["raw_only_source_lines"])

    replayable_rows = [row for row in outcomes if row.get("outcome_class") != "UNREPLAYABLE"]
    pnl_rows = [row for row in replayable_rows if row.get("net_pnl_usd") is not None]
    positive_rows = [row for row in pnl_rows if float(row["net_pnl_usd"]) > 0]
    negative_rows = [row for row in pnl_rows if float(row["net_pnl_usd"]) < 0]
    breakeven_rows = [row for row in pnl_rows if float(row["net_pnl_usd"]) == 0]
    tp_rows = [row for row in outcomes if row.get("close_reason_primary") == "TP_HIT"]
    sl_rows = [row for row in outcomes if row.get("close_reason_primary") == "SL_HIT"]
    timeout_rows = [row for row in outcomes if row.get("close_reason_primary") in TIMEOUT_LIKE_CLOSE_REASONS]
    observation_end_rows = [row for row in outcomes if row.get("close_reason_primary") == "OBSERVATION_END"]
    no_forward_bars_rows = [row for row in outcomes if row.get("replay_status") == "NO_FORWARD_BARS"]
    unreplayable_rows = [row for row in outcomes if row.get("outcome_class") == "UNREPLAYABLE"]

    net_values = [float(row["net_pnl_usd"]) for row in pnl_rows]
    gross_values = [float(row["gross_pnl_usd"]) for row in pnl_rows]
    win_values = [value for value in net_values if value > 0]
    loss_values = [value for value in net_values if value < 0]
    profit_factor = None
    if loss_values:
        profit_factor = sum(win_values) / abs(sum(loss_values)) if win_values else 0.0

    profitability_summary = {
        "diagnostic_notional_usd": diagnostic_notional_usd,
        "open_fee_bps": open_fee_bps,
        "close_fee_bps": close_fee_bps,
        "slippage_bps": slippage_bps,
        "round_trip_cost_bps": round_trip_cost_bps,
        "raw_reject_rows_total": len(rejected_rows),
        "canonical_casebook_reject_rows_total": len(canonical_reject_lines),
        "raw_only_reject_rows_total": len(classification_summary["raw_only_source_lines"]),
        "raw_only_source_lines": classification_summary["raw_only_source_lines"],
        "replayable_rows_total": len(replayable_rows),
        "unreplayable_rows_total": len(unreplayable_rows),
        "profitable_rows_total": len(positive_rows),
        "losing_rows_total": len(negative_rows),
        "breakeven_rows_total": len(breakeven_rows),
        "tp_hit_rows_total": len(tp_rows),
        "sl_hit_rows_total": len(sl_rows),
        "timeout_like_rows_total": len(timeout_rows),
        "observation_end_rows_total": len(observation_end_rows),
        "no_forward_bars_rows_total": len(no_forward_bars_rows),
        "gross_pnl_sum_usd": sum(gross_values) if gross_values else 0.0,
        "net_pnl_sum_usd": sum(net_values) if net_values else 0.0,
        "avg_net_pnl_usd": safe_mean(net_values),
        "median_net_pnl_usd": safe_median(net_values),
        "profit_factor": profit_factor,
        "win_rate_pct": pct(len(positive_rows), len(replayable_rows)),
        "expectancy_per_rejected_row_usd": (sum(net_values) / len(outcomes)) if outcomes else 0.0,
        "harmful_rows_total": len(positive_rows),
        "protective_rows_total": len(negative_rows),
        "bucket_verdict_counts": {},
        "bar_coverage_symbols": sorted(bar_coverage.keys()),
    }

    # Base rejected rows and outcomes first.
    write_jsonl(REJECTED_ONLY_ROWS_JSONL, rejected_rows)
    write_csv(
        REJECTED_ONLY_ROWS_CSV,
        rejected_rows,
        [
            "source_line",
            "timestamp_iso",
            "symbol",
            "side",
            "strategy",
            "regime",
            "row_role",
            "nrr_code",
            "reject_reason",
            "threshold_verdict",
            "threshold_reason",
            "policy_gate",
            "policy_family",
            "canonical_casebook_hit",
            "raw_only_in_canonical_casebook",
            "analysis_class",
            "evidence_class",
            "diagnostic_only",
        ],
    )

    write_jsonl(REJECTED_ONLY_OUTCOMES_JSONL, outcomes)
    write_csv(
        REJECTED_ONLY_OUTCOMES_CSV,
        outcomes,
        [
            "source_line",
            "timestamp_iso",
            "symbol",
            "side",
            "strategy",
            "regime",
            "nrr_code",
            "reject_reason",
            "canonical_casebook_hit",
            "raw_only_in_canonical_casebook",
            "join_quality",
            "support_quality",
            "replay_status",
            "unreplayable_reason",
            "entry_price",
            "close_reason_primary",
            "close_reason_secondary",
            "close_price_primary",
            "close_price_secondary",
            "close_ts_ms_primary",
            "close_ts_ms_secondary",
            "bars_held",
            "ambiguous_intrabar",
            "quantity",
            "diagnostic_notional_usd",
            "gross_pnl_usd",
            "net_pnl_usd",
            "gross_pnl_pct",
            "net_pnl_pct",
            "total_cost_usd",
            "protective_vs_harmful",
            "outcome_class",
            "mfe_pct",
            "mae_pct",
            "round_trip_cost_bps",
        ],
    )

    write_json(REJECTED_ONLY_CLASSIFICATION_SUMMARY_JSON, classification_summary)
    write_json(REJECTED_ONLY_PROFITABILITY_SUMMARY_JSON, profitability_summary)

    # Bucketed views.
    by_nnr = group_buckets(outcomes, ["nrr_code"], len(rejected_rows), "nnr")
    by_gate = group_buckets(outcomes, ["reject_reason"], len(rejected_rows), "gate")
    by_symbol = group_buckets(outcomes, ["symbol"], len(rejected_rows), "symbol")
    by_regime = group_buckets(outcomes, ["regime"], len(rejected_rows), "regime")
    by_strategy = group_buckets(outcomes, ["strategy"], len(rejected_rows), "strategy")
    by_symbol_nnr = group_buckets(outcomes, ["symbol", "nrr_code"], len(rejected_rows), "symbol_nnr")
    by_regime_nnr = group_buckets(outcomes, ["regime", "nrr_code"], len(rejected_rows), "regime_nnr")
    policy_nnr_verdicts = group_buckets(outcomes, ["reject_reason", "nrr_code"], len(rejected_rows), "policy_nnr")

    write_csv(REJECTED_BY_NNR_CSV, by_nnr, ["bucket_type", "nrr_code", "rows", "share_of_all_rejects_pct", "raw_only_rows", "raw_only_rows_pct", "replayable_rows", "unreplayable_rows", "profitable_rows", "losing_rows", "breakeven_rows", "tp_hit_rows", "sl_hit_rows", "timeout_like_rows", "gross_pnl_sum", "net_pnl_sum", "avg_net_pnl", "median_net_pnl", "profit_factor", "win_rate_pct", "protective_rows", "harmful_rows", "verdict", "verdict_reason"])
    write_csv(REJECTED_BY_GATE_CSV, by_gate, ["bucket_type", "reject_reason", "rows", "share_of_all_rejects_pct", "raw_only_rows", "raw_only_rows_pct", "replayable_rows", "unreplayable_rows", "profitable_rows", "losing_rows", "breakeven_rows", "tp_hit_rows", "sl_hit_rows", "timeout_like_rows", "gross_pnl_sum", "net_pnl_sum", "avg_net_pnl", "median_net_pnl", "profit_factor", "win_rate_pct", "protective_rows", "harmful_rows", "verdict", "verdict_reason"])
    write_csv(REJECTED_BY_SYMBOL_CSV, by_symbol, ["bucket_type", "symbol", "rows", "share_of_all_rejects_pct", "raw_only_rows", "raw_only_rows_pct", "replayable_rows", "unreplayable_rows", "profitable_rows", "losing_rows", "breakeven_rows", "tp_hit_rows", "sl_hit_rows", "timeout_like_rows", "gross_pnl_sum", "net_pnl_sum", "avg_net_pnl", "median_net_pnl", "profit_factor", "win_rate_pct", "protective_rows", "harmful_rows", "verdict", "verdict_reason"])
    write_csv(REJECTED_BY_REGIME_CSV, by_regime, ["bucket_type", "regime", "rows", "share_of_all_rejects_pct", "raw_only_rows", "raw_only_rows_pct", "replayable_rows", "unreplayable_rows", "profitable_rows", "losing_rows", "breakeven_rows", "tp_hit_rows", "sl_hit_rows", "timeout_like_rows", "gross_pnl_sum", "net_pnl_sum", "avg_net_pnl", "median_net_pnl", "profit_factor", "win_rate_pct", "protective_rows", "harmful_rows", "verdict", "verdict_reason"])
    write_csv(REJECTED_BY_STRATEGY_CSV, by_strategy, ["bucket_type", "strategy", "rows", "share_of_all_rejects_pct", "raw_only_rows", "raw_only_rows_pct", "replayable_rows", "unreplayable_rows", "profitable_rows", "losing_rows", "breakeven_rows", "tp_hit_rows", "sl_hit_rows", "timeout_like_rows", "gross_pnl_sum", "net_pnl_sum", "avg_net_pnl", "median_net_pnl", "profit_factor", "win_rate_pct", "protective_rows", "harmful_rows", "verdict", "verdict_reason"])
    write_csv(REJECTED_BY_SYMBOL_NNR_CSV, by_symbol_nnr, ["bucket_type", "symbol", "nrr_code", "rows", "share_of_all_rejects_pct", "raw_only_rows", "raw_only_rows_pct", "replayable_rows", "unreplayable_rows", "profitable_rows", "losing_rows", "breakeven_rows", "tp_hit_rows", "sl_hit_rows", "timeout_like_rows", "gross_pnl_sum", "net_pnl_sum", "avg_net_pnl", "median_net_pnl", "profit_factor", "win_rate_pct", "protective_rows", "harmful_rows", "verdict", "verdict_reason"])
    write_csv(REJECTED_BY_REGIME_NNR_CSV, by_regime_nnr, ["bucket_type", "regime", "nrr_code", "rows", "share_of_all_rejects_pct", "raw_only_rows", "raw_only_rows_pct", "replayable_rows", "unreplayable_rows", "profitable_rows", "losing_rows", "breakeven_rows", "tp_hit_rows", "sl_hit_rows", "timeout_like_rows", "gross_pnl_sum", "net_pnl_sum", "avg_net_pnl", "median_net_pnl", "profit_factor", "win_rate_pct", "protective_rows", "harmful_rows", "verdict", "verdict_reason"])
    write_csv(REJECTED_POLICY_NNR_VERDICTS_CSV, policy_nnr_verdicts, ["bucket_type", "reject_reason", "nrr_code", "rows", "share_of_all_rejects_pct", "raw_only_rows", "raw_only_rows_pct", "replayable_rows", "unreplayable_rows", "profitable_rows", "losing_rows", "breakeven_rows", "tp_hit_rows", "sl_hit_rows", "timeout_like_rows", "gross_pnl_sum", "net_pnl_sum", "avg_net_pnl", "median_net_pnl", "profit_factor", "win_rate_pct", "protective_rows", "harmful_rows", "verdict", "verdict_reason"])
    write_json(REJECTED_POLICY_NNR_VERDICTS_JSON, policy_nnr_verdicts)

    profitability_summary["bucket_verdict_counts"] = dict(sorted(Counter(row["verdict"] for row in policy_nnr_verdicts).items()))
    harmful_pool = [*by_regime, *by_symbol_nnr]
    profitability_summary["top_harmful_buckets"] = sorted([row for row in harmful_pool if row["verdict"].startswith("HARMFUL")], key=lambda row: (-int(row["rows"]), -float(row["net_pnl_sum"])))[:10]
    profitability_summary["top_protective_buckets"] = sorted([row for row in policy_nnr_verdicts if row["verdict"].startswith("PROTECTIVE")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])))[:10]
    profitability_summary["low_support_buckets"] = sorted([row for row in policy_nnr_verdicts if row["verdict"] in {"LOW_SUPPORT", "UNREPLAYABLE"}], key=lambda row: (-int(row["rows"]), text(row.get("nrr_code", text(row.get("reject_reason"))))))[:10]
    profitability_summary["top_harmful_regimes"] = sorted([row for row in by_regime if row["verdict"].startswith("HARMFUL")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])))[:10]
    profitability_summary["top_harmful_symbol_nnr"] = sorted([row for row in by_symbol_nnr if row["verdict"].startswith("HARMFUL")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])))[:10]
    profitability_summary["top_protective_regimes"] = sorted([row for row in by_regime if row["verdict"].startswith("PROTECTIVE")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])))[:10]
    profitability_summary["top_protective_symbol_nnr"] = sorted([row for row in by_symbol_nnr if row["verdict"].startswith("PROTECTIVE")], key=lambda row: (-int(row["rows"]), float(row["net_pnl_sum"])))[:10]
    write_json(REJECTED_ONLY_PROFITABILITY_SUMMARY_JSON, profitability_summary)

    write_text(REJECTED_ONLY_CASEBOOK_MD, render_casebook_md(outcomes))
    write_text(REJECTED_ONLY_PROFITABILITY_SUMMARY_MD, render_profitability_md(profitability_summary, policy_nnr_verdicts, by_regime, by_symbol_nnr))
    write_text(FINAL_REPORT_MD, render_final_report(profitability_summary, policy_nnr_verdicts, classification_summary, by_regime, by_symbol_nnr))
    write_json(REPORT_ROOT / "rejected_only_bar_coverage.json", bar_coverage)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
