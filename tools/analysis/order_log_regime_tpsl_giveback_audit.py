#!/usr/bin/env python3
"""Regime / TP-SL / giveback attribution audit for logs/order_log_v1.jsonl.

This script is read-only. It uses the frozen counterfactual economic outputs,
joins replay timing from the replayed outcomes, reconstructs forward-bar MFE / MAE
from recorder bars, and writes narrow attribution artifacts for regime, TP / SL
geometry, giveback, and profit-protection counterfactuals.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_ROOT = ROOT / "tools" / "analysis"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

from order_log_counterfactual_replay_audit import (  # noqa: E402
    Bar,
    as_text,
    compute_tpsl_geometry,
    iso_utc,
    load_bars_300,
    pnl_from_prices,
    safe_float,
    safe_int,
)


REPORT_ROOT = ROOT / "reports" / "order_log_counterfactual_replay"
ECONOMIC_OUTCOMES_PATH = REPORT_ROOT / "economic_outcomes.jsonl"
REPLAYED_OUTCOMES_PATH = REPORT_ROOT / "replayed_outcomes.jsonl"
CONFIG_SNAPSHOT_PATH = REPORT_ROOT / "config_snapshot.json"
FIELD_COVERAGE_PATH = REPORT_ROOT / "economic_field_coverage.json"
RECORDER_ROOT = ROOT / "data" / "recorder"

BASELINE_OUTPUT_PATH = REPORT_ROOT / "regime_tpsl_giveback_baseline_reproduction.json"
REGIME_ATTRIBUTION_PATH = REPORT_ROOT / "regime_attribution.csv"
SYMBOL_REGIME_ATTRIBUTION_PATH = REPORT_ROOT / "symbol_regime_attribution.csv"
STRATEGY_REGIME_ATTRIBUTION_PATH = REPORT_ROOT / "strategy_regime_attribution.csv"
SYMBOL_STRATEGY_REGIME_ATTRIBUTION_PATH = REPORT_ROOT / "symbol_strategy_regime_attribution.csv"
TPSL_GEOMETRY_ATTRIBUTION_PATH = REPORT_ROOT / "tpsl_geometry_attribution.csv"
TPSL_CULPRIT_SUMMARY_PATH = REPORT_ROOT / "tpsl_culprit_summary.md"
LOSING_TRADE_MFE_GIVEBACK_AUDIT_CSV = REPORT_ROOT / "losing_trade_mfe_giveback_audit.csv"
LOSING_TRADE_MFE_GIVEBACK_AUDIT_JSON = REPORT_ROOT / "losing_trade_mfe_giveback_audit.json"
LOSING_TRADE_MFE_GIVEBACK_AUDIT_MD = REPORT_ROOT / "losing_trade_mfe_giveback_audit.md"
PROFIT_PROTECTION_COUNTERFACTUAL_CSV = REPORT_ROOT / "profit_protection_counterfactual.csv"
PROFIT_PROTECTION_COUNTERFACTUAL_MD = REPORT_ROOT / "profit_protection_counterfactual.md"
REGIME_TPSL_GIVEBACK_CASEBOOK_MD = REPORT_ROOT / "regime_tpsl_giveback_casebook.md"
FINAL_REPORT_MD = REPORT_ROOT / "ORDER_LOG_REGIME_TPSL_AND_GIVEBACK_ATTRIBUTION_AUDIT.md"

DEFAULT_ARM_PCTS = (0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.75, 1.00, 1.25, 1.50)
DEFAULT_GIVEBACK_TRIGGER_PCTS = (35.0, 50.0, 65.0, 80.0)
TIMEOUT_LIKE_CLOSE_REASONS = {"ENTRY_TIMEOUT_OR_STALE", "OBSERVATION_END"}

EXPECTED_BASELINE_KEYS = (
    "source_rows_total",
    "rows_with_pnl",
    "rows_without_pnl",
    "gross_pnl_sum_quote",
    "net_pnl_sum_quote",
    "profit_factor",
    "win_rate_net",
    "tp_rows",
    "sl_rows",
    "timeout_rows",
    "diagnostic_only_rows",
    "rows_with_entry_price",
    "rows_with_close_price",
    "rows_with_quantity",
    "rows_with_open_notional",
    "rows_with_leverage",
    "rows_with_fee_bps",
    "rows_with_slippage_bps",
    "rows_with_gross_pnl",
    "rows_with_net_pnl",
    "actual_qty_rows",
    "modeled_notional_rows",
    "close_reason_counts",
    "pnl_status_counts",
    "evidence_class_counts",
    "reject_economic_class_counts",
    "join_quality_counts",
    "support_quality_counts",
)


@dataclass(frozen=True)
class ReplayPathContext:
    proposal_uid: str
    symbol: str
    side: str
    strategy: str
    regime: str
    entry_price: float
    quantity: float
    open_notional_quote: float
    round_trip_cost_bps: float
    entry_ts_ms: int
    close_ts_ms: int
    start_idx: int
    end_idx: int
    stop_price: float
    target_price: float
    bars: list[Bar]
    ts_list: list[int]
    actual_gross_pnl_quote: float
    actual_net_pnl_quote: float
    actual_gross_return_pct: float
    actual_net_return_pct: float


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, (ReplayPathContext,)):
        return value.__dict__
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                payload = dict(payload)
                payload.setdefault("source_line", line_no)
                rows.append(payload)
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=_json_default) + "\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def flatten_for_csv(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: flatten_for_csv(row.get(field)) for field in fieldnames})


def text(value: Any) -> str:
    return as_text(value)


def number(value: Any) -> float | None:
    return safe_float(value)


def integer(value: Any) -> int | None:
    return safe_int(value)


def pct(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator) * 100.0


def safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def safe_median(values: list[float]) -> float | None:
    return median(values) if values else None


def fmt_num(value: Any, digits: int = 6) -> str:
    if value is None:
        return ""
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return text(value)
    if not math.isfinite(number_value):
        return text(value)
    return f"{number_value:.{digits}f}"


def md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_none_\n"
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(fmt_num(row.get(col), 6) if isinstance(row.get(col), (int, float)) else text(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, separator, *body]) + "\n"


def first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def choose_replay_row(rows: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not rows:
        return None

    def priority(row: dict[str, Any]) -> tuple[int, int, int, int]:
        return (
            1 if bool(row.get("diagnostic_only")) else 0,
            1 if integer(row.get("close_ts_ms")) is None else 0,
            1 if text(row.get("pnl_status")) != "OK" else 0,
            integer(row.get("source_line")) or 0,
        )

    return sorted(rows, key=priority)[0]


def index_rows_by_uid(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        uid = text(row.get("proposal_uid"))
        if uid:
            index[uid].append(row)
    return index


def build_field_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter()
    pnl_status_counts = Counter()
    evidence_class_counts = Counter()
    reject_class_counts = Counter()
    close_reason_counts = Counter()
    join_quality_counts = Counter()
    support_quality_counts = Counter()

    for row in rows:
        if row.get("entry_price") is not None:
            counts["entry_price_present"] += 1
        if row.get("close_price") is not None:
            counts["close_price_present"] += 1
        if row.get("quantity") is not None:
            counts["quantity_present"] += 1
        if row.get("open_notional_quote") is not None:
            counts["open_notional_present"] += 1
        if row.get("leverage") is not None:
            counts["leverage_present"] += 1
        if row.get("fee_bps") is not None:
            counts["fee_bps_present"] += 1
        if row.get("slippage_bps") is not None:
            counts["slippage_bps_present"] += 1
        if row.get("gross_pnl_quote") is not None:
            counts["gross_pnl_present"] += 1
        if row.get("net_pnl_quote") is not None:
            counts["net_pnl_present"] += 1
        if row.get("actual_qty_used"):
            counts["actual_qty_rows"] += 1
        if row.get("modeled_notional_used"):
            counts["modeled_notional_rows"] += 1
        if row.get("diagnostic_only"):
            counts["diagnostic_only_rows"] += 1
        if row.get("pnl_status"):
            pnl_status_counts[text(row.get("pnl_status"))] += 1
        if row.get("evidence_class"):
            evidence_class_counts[text(row.get("evidence_class"))] += 1
        if row.get("reject_economic_class"):
            reject_class_counts[text(row.get("reject_economic_class"))] += 1
        if row.get("close_reason"):
            close_reason_counts[text(row.get("close_reason"))] += 1
        if row.get("join_quality"):
            join_quality_counts[text(row.get("join_quality"))] += 1
        if row.get("support_quality"):
            support_quality_counts[text(row.get("support_quality"))] += 1

    pnl_rows = [row for row in rows if text(row.get("pnl_status")) == "OK"]
    gross_values = [number(row.get("gross_pnl_quote")) for row in pnl_rows if number(row.get("gross_pnl_quote")) is not None]
    net_values = [number(row.get("net_pnl_quote")) for row in pnl_rows if number(row.get("net_pnl_quote")) is not None]
    positive_net_values = [value for value in net_values if value > 0]
    negative_net_values = [value for value in net_values if value < 0]

    overall_summary = {
        "rows_total": len(rows),
        "rows_with_pnl": len(pnl_rows),
        "rows_without_pnl": len(rows) - len(pnl_rows),
        "gross_pnl_sum_quote": sum(gross_values) if gross_values else 0.0,
        "net_pnl_sum_quote": sum(net_values) if net_values else 0.0,
        "profit_factor": (sum(positive_net_values) / abs(sum(negative_net_values))) if negative_net_values else None,
        "win_rate_net": (len(positive_net_values) / len(pnl_rows)) if pnl_rows else None,
        "tp_rows": close_reason_counts["TP_HIT"],
        "sl_rows": close_reason_counts["SL_HIT"],
        "timeout_rows": close_reason_counts["ENTRY_TIMEOUT_OR_STALE"] + close_reason_counts["OBSERVATION_END"],
        "observation_end_rows": close_reason_counts["OBSERVATION_END"],
        "entry_timeout_rows": close_reason_counts["ENTRY_TIMEOUT_OR_STALE"],
        "diagnostic_only_rows": counts["diagnostic_only_rows"],
        "rows_with_entry_price": counts["entry_price_present"],
        "rows_with_close_price": counts["close_price_present"],
        "rows_with_quantity": counts["quantity_present"],
        "rows_with_open_notional": counts["open_notional_present"],
        "rows_with_leverage": counts["leverage_present"],
        "rows_with_fee_bps": counts["fee_bps_present"],
        "rows_with_slippage_bps": counts["slippage_bps_present"],
        "rows_with_gross_pnl": counts["gross_pnl_present"],
        "rows_with_net_pnl": counts["net_pnl_present"],
        "actual_qty_rows": counts["actual_qty_rows"],
        "modeled_notional_rows": counts["modeled_notional_rows"],
    }

    return {
        "source_rows_total": len(rows),
        "rows_with_pnl": len(pnl_rows),
        "rows_without_pnl": len(rows) - len(pnl_rows),
        "gross_pnl_sum_quote": overall_summary["gross_pnl_sum_quote"],
        "net_pnl_sum_quote": overall_summary["net_pnl_sum_quote"],
        "profit_factor": overall_summary["profit_factor"],
        "win_rate_net": overall_summary["win_rate_net"],
        "tp_rows": overall_summary["tp_rows"],
        "sl_rows": overall_summary["sl_rows"],
        "timeout_rows": overall_summary["timeout_rows"],
        "observation_end_rows": overall_summary["observation_end_rows"],
        "entry_timeout_rows": overall_summary["entry_timeout_rows"],
        "diagnostic_only_rows": counts["diagnostic_only_rows"],
        "rows_with_entry_price": counts["entry_price_present"],
        "rows_with_close_price": counts["close_price_present"],
        "rows_with_quantity": counts["quantity_present"],
        "rows_with_open_notional": counts["open_notional_present"],
        "rows_with_leverage": counts["leverage_present"],
        "rows_with_fee_bps": counts["fee_bps_present"],
        "rows_with_slippage_bps": counts["slippage_bps_present"],
        "rows_with_gross_pnl": counts["gross_pnl_present"],
        "rows_with_net_pnl": counts["net_pnl_present"],
        "actual_qty_rows": counts["actual_qty_rows"],
        "modeled_notional_rows": counts["modeled_notional_rows"],
        "pnl_status_counts": dict(sorted(pnl_status_counts.items())),
        "evidence_class_counts": dict(sorted(evidence_class_counts.items())),
        "reject_economic_class_counts": dict(sorted(reject_class_counts.items())),
        "close_reason_counts": dict(sorted(close_reason_counts.items())),
        "join_quality_counts": dict(sorted(join_quality_counts.items())),
        "support_quality_counts": dict(sorted(support_quality_counts.items())),
        "overall_summary": overall_summary,
    }


def compare_numbers(expected: Any, observed: Any, *, tol: float = 1e-9) -> bool:
    if expected is None or observed is None:
        return expected is None and observed is None
    try:
        return math.isclose(float(expected), float(observed), rel_tol=tol, abs_tol=tol)
    except (TypeError, ValueError):
        return expected == observed


def validate_baseline(observed: dict[str, Any], expected: dict[str, Any]) -> None:
    overall = expected.get("overall_summary") or {}
    observed_overall = observed.get("overall_summary") or {}
    for key in (
        "rows_total",
        "rows_with_pnl",
        "rows_without_pnl",
        "gross_pnl_sum_quote",
        "net_pnl_sum_quote",
        "profit_factor",
        "win_rate_net",
        "tp_rows",
        "sl_rows",
        "timeout_rows",
        "diagnostic_only_rows",
        "rows_with_entry_price",
        "rows_with_close_price",
        "rows_with_quantity",
        "rows_with_open_notional",
        "rows_with_leverage",
        "rows_with_fee_bps",
        "rows_with_slippage_bps",
        "rows_with_gross_pnl",
        "rows_with_net_pnl",
        "actual_qty_rows",
        "modeled_notional_rows",
    ):
        if key not in overall:
            continue
        if not compare_numbers(overall.get(key), observed_overall.get(key)):
            raise RuntimeError(f"Baseline mismatch for {key}: expected {overall.get(key)!r} observed {observed_overall.get(key)!r}")

    for key in (
        "pnl_status_counts",
        "evidence_class_counts",
        "reject_economic_class_counts",
        "close_reason_counts",
        "join_quality_counts",
        "support_quality_counts",
    ):
        if expected.get(key) is None:
            continue
        if dict(expected.get(key) or {}) != dict(observed.get(key) or {}):
            raise RuntimeError(f"Baseline mismatch for {key}: expected {expected.get(key)!r} observed {observed.get(key)!r}")


def bar_close_return_pct(side: str, entry_price: float, close_price: float) -> float:
    if entry_price <= 0 or close_price <= 0:
        return 0.0
    if side == "BUY":
        return ((close_price - entry_price) / entry_price) * 100.0
    return ((entry_price - close_price) / entry_price) * 100.0


def detect_tp_sl_hit(side: str, bar: Bar, stop_price: float, target_price: float) -> tuple[str | None, float | None, bool]:
    if side == "BUY":
        hit_stop = bar.low <= stop_price
        hit_tp = bar.high >= target_price
    else:
        hit_stop = bar.high >= stop_price
        hit_tp = bar.low <= target_price
    if hit_stop and hit_tp:
        return "SL_HIT", stop_price, True
    if hit_stop:
        return "SL_HIT", stop_price, False
    if hit_tp:
        return "TP_HIT", target_price, False
    return None, None, False


def simulate_tp_sl_path_indexed(
    side: str,
    entry_price: float,
    entry_ts_ms: int,
    stop_price: float,
    target_price: float,
    bars: list[Bar],
    ts_list: list[int],
    horizon_ts_ms: int | None = None,
) -> dict[str, Any]:
    if entry_price <= 0:
        return {"status": "INVALID_ENTRY_PRICE"}
    if not bars:
        return {"status": "NO_MARKET_DATA"}
    start_idx = bisect_right(ts_list, entry_ts_ms)
    end_idx = len(bars) if horizon_ts_ms is None else bisect_right(ts_list, horizon_ts_ms)
    if start_idx >= len(bars):
        return {"status": "NO_FORWARD_BARS"}

    mfe_pct = None
    mae_pct = None
    primary_reason = None
    primary_close_price = None
    primary_close_ts_ms = None
    primary_close_bar_idx = None
    secondary_reason = None
    secondary_close_price = None
    secondary_close_ts_ms = None
    secondary_close_bar_idx = None
    ambiguous = False

    for idx in range(start_idx, end_idx):
        bar = bars[idx]
        if side == "BUY":
            favorable = (bar.high - entry_price) / entry_price
            adverse = (bar.low - entry_price) / entry_price
        else:
            favorable = (entry_price - bar.low) / entry_price
            adverse = (entry_price - bar.high) / entry_price

        hit_reason, hit_price, hit_ambiguous = detect_tp_sl_hit(side, bar, stop_price, target_price)
        mfe_pct = favorable if mfe_pct is None else max(mfe_pct, favorable)
        mae_pct = adverse if mae_pct is None else min(mae_pct, adverse)

        if hit_reason is not None:
            ambiguous = ambiguous or hit_ambiguous
            primary_reason = hit_reason
            primary_close_price = hit_price
            primary_close_ts_ms = bar.timestamp_ms
            primary_close_bar_idx = idx
            secondary_reason = "TP_HIT" if hit_reason == "SL_HIT" and hit_ambiguous else hit_reason
            secondary_close_price = target_price if hit_ambiguous else hit_price
            secondary_close_ts_ms = bar.timestamp_ms
            secondary_close_bar_idx = idx
            break

    if primary_reason is None:
        last_idx = min(max(end_idx - 1, start_idx), len(bars) - 1)
        last_bar = bars[last_idx]
        primary_reason = "OBSERVATION_END"
        primary_close_price = last_bar.close
        primary_close_ts_ms = last_bar.timestamp_ms
        primary_close_bar_idx = last_idx
        secondary_reason = primary_reason
        secondary_close_price = primary_close_price
        secondary_close_ts_ms = primary_close_ts_ms
        secondary_close_bar_idx = primary_close_bar_idx

    return {
        "status": "OK",
        "mfe_pct": mfe_pct,
        "mae_pct": mae_pct,
        "close_reason_primary": primary_reason,
        "close_price_primary": primary_close_price,
        "close_ts_ms_primary": primary_close_ts_ms,
        "close_bar_idx_primary": primary_close_bar_idx,
        "close_reason_secondary": secondary_reason,
        "close_price_secondary": secondary_close_price,
        "close_ts_ms_secondary": secondary_close_ts_ms,
        "close_bar_idx_secondary": secondary_close_bar_idx,
        "ambiguous_intrabar": ambiguous,
        "bars_considered": max(0, end_idx - start_idx),
    }


def simulate_profit_protection_counterfactual_indexed(
    *,
    context: ReplayPathContext,
    arm_pct: float,
    giveback_trigger_pct: float,
) -> dict[str, Any]:
    side = context.side
    entry_price = context.entry_price
    bars = context.bars
    ts_list = context.ts_list
    stop_price = context.stop_price
    target_price = context.target_price
    start_idx = context.start_idx
    end_idx = context.end_idx

    if start_idx >= len(bars) or end_idx <= start_idx:
        return {"status": "NO_FORWARD_BARS"}

    peak_close_return_pct = 0.0
    armed = False

    for idx in range(start_idx, end_idx):
        bar = bars[idx]
        hit_reason, hit_price, _ = detect_tp_sl_hit(side, bar, stop_price, target_price)
        if hit_reason is not None:
            return {
                "status": "OK",
                "managed_exit": False,
                "exit_reason": hit_reason,
                "exit_price": hit_price,
                "exit_ts_ms": bar.timestamp_ms,
                "peak_close_return_pct": peak_close_return_pct,
                "giveback_pct": 0.0,
            }

        close_return_pct = bar_close_return_pct(side, entry_price, bar.close)
        peak_close_return_pct = max(peak_close_return_pct, close_return_pct)
        if peak_close_return_pct >= arm_pct:
            armed = True

        giveback_pct = 0.0
        if armed and peak_close_return_pct > 0.0:
            giveback_pct = max(0.0, ((peak_close_return_pct - close_return_pct) / peak_close_return_pct) * 100.0)
        if armed and giveback_pct >= giveback_trigger_pct:
            return {
                "status": "OK",
                "managed_exit": True,
                "exit_reason": "SIDECAR_PERCENT_GIVEBACK",
                "exit_price": bar.close,
                "exit_ts_ms": bar.timestamp_ms,
                "peak_close_return_pct": peak_close_return_pct,
                "giveback_pct": giveback_pct,
            }

    last_bar = bars[min(end_idx - 1, len(bars) - 1)]
    final_close_return_pct = bar_close_return_pct(side, entry_price, last_bar.close)
    giveback_pct = 0.0
    if peak_close_return_pct > 0.0:
        giveback_pct = max(0.0, ((peak_close_return_pct - final_close_return_pct) / peak_close_return_pct) * 100.0)

    return {
        "status": "OK",
        "managed_exit": False,
        "exit_reason": "HORIZON_END",
        "exit_price": last_bar.close,
        "exit_ts_ms": last_bar.timestamp_ms,
        "peak_close_return_pct": peak_close_return_pct,
        "giveback_pct": giveback_pct,
    }


def build_row_attribution(
    econ_row: dict[str, Any],
    replay_row: dict[str, Any] | None,
    config: dict[str, Any],
    bars_by_symbol: dict[str, list[Bar]],
    ts_by_symbol: dict[str, list[int]],
    bar_coverage: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], ReplayPathContext | None]:
    row = dict(econ_row)
    uid = text(row.get("proposal_uid"))

    if replay_row is not None:
        row.setdefault("replay_close_ts_ms", replay_row.get("close_ts_ms"))
        row.setdefault("replay_close_reason", replay_row.get("close_reason"))
        row.setdefault("replay_timestamp_ms", replay_row.get("timestamp_ms"))
        row.setdefault("replay_close_price", replay_row.get("close_price"))
        row.setdefault("replay_row_role", replay_row.get("row_role"))
        row.setdefault("replay_join_quality", replay_row.get("join_quality"))
        row.setdefault("replay_support_quality", replay_row.get("support_quality"))
        if row.get("close_ts_ms") is None:
            row["close_ts_ms"] = replay_row.get("close_ts_ms")
        if not row.get("close_reason"):
            row["close_reason"] = replay_row.get("close_reason")
        if row.get("close_price") is None:
            row["close_price"] = replay_row.get("close_price")
        if row.get("timestamp_ms") is None:
            row["timestamp_ms"] = replay_row.get("timestamp_ms")
        if row.get("entry_price") is None:
            row["entry_price"] = replay_row.get("entry_price")
        if row.get("quantity") is None:
            row["quantity"] = replay_row.get("quantity")
        if row.get("open_notional_quote") is None:
            row["open_notional_quote"] = replay_row.get("open_notional_quote")

    row["entry_ts_ms"] = integer(row.get("timestamp_ms")) or 0
    row["entry_ts_iso"] = iso_utc(row["entry_ts_ms"])
    row["close_ts_ms"] = integer(row.get("close_ts_ms"))
    row["close_ts_iso"] = iso_utc(row["close_ts_ms"])
    row["symbol"] = text(row.get("symbol")).upper()
    row["side"] = text(row.get("side")).upper()
    row["strategy"] = text(row.get("strategy") or row.get("strategy_id") or "aurora")
    row["close_reason_timeout_like"] = bool(row.get("close_reason_timeout_like") or text(row.get("close_reason")) in TIMEOUT_LIKE_CLOSE_REASONS)
    row["actual_close_reason"] = text(row.get("close_reason"))
    row["actual_gross_pnl_quote"] = number(row.get("gross_pnl_quote"))
    row["actual_net_pnl_quote"] = number(row.get("net_pnl_quote"))
    row["actual_gross_return_pct"] = number(row.get("gross_return_on_notional_pct"))
    row["actual_net_return_pct"] = number(row.get("net_return_on_notional_pct"))

    entry_price = number(row.get("entry_price"))
    quantity = number(row.get("quantity"))
    open_notional = number(row.get("open_notional_quote"))
    if open_notional is None and entry_price is not None and quantity is not None:
        open_notional = entry_price * quantity
    row["entry_price"] = entry_price
    row["quantity"] = quantity
    row["open_notional_quote"] = open_notional

    if row["actual_gross_return_pct"] is None and row["actual_gross_pnl_quote"] is not None and open_notional not in (None, 0):
        row["actual_gross_return_pct"] = (row["actual_gross_pnl_quote"] / open_notional) * 100.0
    if row["actual_net_return_pct"] is None and row["actual_net_pnl_quote"] is not None and open_notional not in (None, 0):
        row["actual_net_return_pct"] = (row["actual_net_pnl_quote"] / open_notional) * 100.0
    if row["actual_gross_pnl_quote"] is None and row["actual_gross_return_pct"] is not None and open_notional is not None:
        row["actual_gross_pnl_quote"] = open_notional * row["actual_gross_return_pct"] / 100.0
    if row["actual_net_pnl_quote"] is None and row["actual_net_return_pct"] is not None and open_notional is not None:
        row["actual_net_pnl_quote"] = open_notional * row["actual_net_return_pct"] / 100.0

    row["round_trip_cost_bps"] = number(row.get("round_trip_cost_bps")) or 0.0
    row["round_trip_cost_pct"] = row["round_trip_cost_bps"] / 100.0

    tpsl = compute_tpsl_geometry(row["symbol"], row["side"], entry_price or 0.0, text(row.get("regime")), config)
    row["tpsl_status"] = text(tpsl.get("status"))
    row["stop_price"] = number(tpsl.get("stop_price"))
    row["target_price"] = number(tpsl.get("target_price"))
    row["sl_pct_eff"] = number(tpsl.get("sl_pct_eff"))
    row["tp_pct_eff"] = number(tpsl.get("tp_pct_eff"))
    row["tp_rr_eff"] = number(tpsl.get("tp_rr_eff"))
    row["tpsl_min_dist_bps"] = number(tpsl.get("min_dist_bps"))
    row["tpsl_guardrail_notes"] = tpsl.get("guardrail_notes") or []
    row["tp_edge_bps"] = None if row["tp_pct_eff"] is None else row["tp_pct_eff"] * 100.0 - row["round_trip_cost_bps"]
    row["sl_edge_bps"] = None if row["sl_pct_eff"] is None else row["sl_pct_eff"] * 100.0 - row["round_trip_cost_bps"]
    row["tp_to_cost_ratio"] = None if row["tp_pct_eff"] is None or row["round_trip_cost_bps"] in (None, 0) else (row["tp_pct_eff"] * 100.0) / row["round_trip_cost_bps"]
    row["sl_to_cost_ratio"] = None if row["sl_pct_eff"] is None or row["round_trip_cost_bps"] in (None, 0) else (row["sl_pct_eff"] * 100.0) / row["round_trip_cost_bps"]

    bars = bars_by_symbol.get(row["symbol"]) or []
    ts_list = ts_by_symbol.get(row["symbol"]) or []
    coverage = bar_coverage.get(row["symbol"]) or {}
    coverage_start = integer(coverage.get("first_ts_ms"))
    coverage_end = integer(coverage.get("last_ts_ms"))

    path_status = "UNAVAILABLE"
    path_result: dict[str, Any] | None = None
    actual_path_result: dict[str, Any] | None = None
    path_clipped_start = False
    path_clipped_end = False
    start_idx = None
    end_idx = None

    if entry_price is None or entry_price <= 0:
        path_status = "MISSING_ENTRY_PRICE"
    elif quantity is None or quantity <= 0:
        path_status = "MISSING_QUANTITY"
    elif row["close_ts_ms"] is None:
        path_status = "MISSING_CLOSE_TS"
    elif not bars or not ts_list:
        path_status = "NO_MARKET_DATA"
    else:
        start_idx = bisect_right(ts_list, row["entry_ts_ms"])
        end_idx = bisect_right(ts_list, row["close_ts_ms"])
        if start_idx >= len(bars):
            path_status = "NO_FORWARD_BARS"
        else:
            dummy_stop = 0.0 if row["side"] == "BUY" else float("inf")
            dummy_target = float("inf") if row["side"] == "BUY" else 0.0
            path_result = simulate_tp_sl_path_indexed(
                row["side"],
                entry_price,
                row["entry_ts_ms"],
                dummy_stop,
                dummy_target,
                bars,
                ts_list,
                row["close_ts_ms"],
            )
            if path_result.get("status") != "OK":
                path_status = f"PATH_{path_result.get('status')}"
            else:
                path_clipped_start = coverage_start is not None and row["entry_ts_ms"] < coverage_start
                path_clipped_end = coverage_end is not None and row["close_ts_ms"] > coverage_end and text(path_result.get("close_reason_primary")) == "OBSERVATION_END"
                if path_clipped_start:
                    path_status = "PATH_COVERAGE_CLIPPED_START"
                elif path_clipped_end:
                    path_status = "PATH_COVERAGE_CLIPPED_END"
                else:
                    path_status = "OK"

            if row["tpsl_status"] == "OK":
                actual_path_result = simulate_tp_sl_path_indexed(
                    row["side"],
                    entry_price,
                    row["entry_ts_ms"],
                    row["stop_price"],
                    row["target_price"],
                    bars,
                    ts_list,
                    row["close_ts_ms"],
                )

    row["path_status"] = path_status
    row["path_clipped_start"] = path_clipped_start
    row["path_clipped_end"] = path_clipped_end
    row["path_start_idx"] = start_idx
    row["path_end_idx"] = end_idx

    if path_result is not None and path_result.get("status") == "OK":
        row["path_close_reason_primary"] = text(row.get("actual_close_reason")) or text(path_result.get("close_reason_primary"))
        row["path_close_price_primary"] = number(row.get("close_price")) if row.get("close_price") is not None else number(path_result.get("close_price_primary"))
        row["path_close_ts_ms_primary"] = row["close_ts_ms"]
        row["path_close_reason_secondary"] = row["path_close_reason_primary"]
        row["path_close_price_secondary"] = row["path_close_price_primary"]
        row["path_close_ts_ms_secondary"] = row["path_close_ts_ms_primary"]
        row["path_ambiguous_intrabar"] = bool(actual_path_result.get("ambiguous_intrabar")) if actual_path_result is not None else None
        row["path_bars_considered"] = integer(path_result.get("bars_considered"))
        row["mfe_gross_return_pct"] = number(path_result.get("mfe_pct")) * 100.0 if number(path_result.get("mfe_pct")) is not None else None
        row["mae_gross_return_pct"] = number(path_result.get("mae_pct")) * 100.0 if number(path_result.get("mae_pct")) is not None else None
        row["mfe_net_return_pct"] = None if row["mfe_gross_return_pct"] is None else row["mfe_gross_return_pct"] - row["round_trip_cost_pct"]
        row["realized_gross_return_pct"] = row["actual_gross_return_pct"]
        row["realized_net_return_pct"] = row["actual_net_return_pct"]
        row["mfe_gross_pnl_quote"] = None if open_notional is None or row["mfe_gross_return_pct"] is None else open_notional * row["mfe_gross_return_pct"] / 100.0
        row["mfe_net_pnl_quote"] = None if open_notional is None or row["mfe_net_return_pct"] is None else open_notional * row["mfe_net_return_pct"] / 100.0
        row["gross_giveback_quote"] = None if row["mfe_gross_pnl_quote"] is None or row["actual_gross_pnl_quote"] is None else max(0.0, row["mfe_gross_pnl_quote"] - row["actual_gross_pnl_quote"])
        row["net_giveback_quote"] = None if row["mfe_net_pnl_quote"] is None or row["actual_net_pnl_quote"] is None else max(0.0, row["mfe_net_pnl_quote"] - row["actual_net_pnl_quote"])
        row["gross_giveback_ratio_pct"] = None
        if row["mfe_gross_return_pct"] is not None and row["mfe_gross_return_pct"] > 0 and row["realized_gross_return_pct"] is not None:
            row["gross_giveback_ratio_pct"] = max(0.0, ((row["mfe_gross_return_pct"] - row["realized_gross_return_pct"]) / row["mfe_gross_return_pct"]) * 100.0)
        row["net_giveback_ratio_pct"] = None
        if row["mfe_net_return_pct"] is not None and row["mfe_net_return_pct"] > 0 and row["realized_net_return_pct"] is not None:
            row["net_giveback_ratio_pct"] = max(0.0, ((row["mfe_net_return_pct"] - row["realized_net_return_pct"]) / row["mfe_net_return_pct"]) * 100.0)
        row["profit_after_costs_available"] = bool(row["mfe_net_return_pct"] is not None and row["mfe_net_return_pct"] > 0)
        row["giveback_material"] = bool(row["profit_after_costs_available"] and row["actual_net_pnl_quote"] is not None and row["actual_net_pnl_quote"] < 0)
        row["geometry_issue_class"] = classify_geometry_issue(row)

        if path_status == "OK":
            context = ReplayPathContext(
                proposal_uid=uid,
                symbol=row["symbol"],
                side=row["side"],
                strategy=row["strategy"],
                regime=text(row.get("regime")),
                entry_price=entry_price,
                quantity=quantity or 0.0,
                open_notional_quote=open_notional or 0.0,
                round_trip_cost_bps=row["round_trip_cost_bps"],
                entry_ts_ms=row["entry_ts_ms"],
                close_ts_ms=row["close_ts_ms"],
                start_idx=start_idx or 0,
                end_idx=end_idx or 0,
                stop_price=row["stop_price"] or 0.0,
                target_price=row["target_price"] or 0.0,
                bars=bars,
                ts_list=ts_list,
                actual_gross_pnl_quote=row["actual_gross_pnl_quote"] or 0.0,
                actual_net_pnl_quote=row["actual_net_pnl_quote"] or 0.0,
                actual_gross_return_pct=row["actual_gross_return_pct"] or 0.0,
                actual_net_return_pct=row["actual_net_return_pct"] or 0.0,
            )
        else:
            context = None
    else:
        row["realized_gross_return_pct"] = row["actual_gross_return_pct"]
        row["realized_net_return_pct"] = row["actual_net_return_pct"]
        row["path_close_reason_primary"] = text(row.get("actual_close_reason"))
        row["path_close_price_primary"] = number(row.get("close_price"))
        row["path_close_ts_ms_primary"] = row["close_ts_ms"]
        row["path_close_reason_secondary"] = row["path_close_reason_primary"]
        row["path_close_price_secondary"] = row["path_close_price_primary"]
        row["path_close_ts_ms_secondary"] = row["path_close_ts_ms_primary"]
        row["path_ambiguous_intrabar"] = bool(actual_path_result.get("ambiguous_intrabar")) if actual_path_result is not None else None
        row["path_bars_considered"] = integer(path_result.get("bars_considered")) if path_result is not None else None
        row["mfe_gross_return_pct"] = number(path_result.get("mfe_pct")) * 100.0 if path_result is not None and number(path_result.get("mfe_pct")) is not None else None
        row["mae_gross_return_pct"] = number(path_result.get("mae_pct")) * 100.0 if path_result is not None and number(path_result.get("mae_pct")) is not None else None
        row["mfe_net_return_pct"] = None if row["mfe_gross_return_pct"] is None else row["mfe_gross_return_pct"] - row["round_trip_cost_pct"]
        row["mfe_gross_pnl_quote"] = None
        row["mfe_net_pnl_quote"] = None
        row["gross_giveback_quote"] = None
        row["net_giveback_quote"] = None
        row["gross_giveback_ratio_pct"] = None
        row["net_giveback_ratio_pct"] = None
        row["profit_after_costs_available"] = bool(row["mfe_net_return_pct"] is not None and row["mfe_net_return_pct"] > 0)
        row["giveback_material"] = bool(row["profit_after_costs_available"] and row["actual_net_pnl_quote"] is not None and row["actual_net_pnl_quote"] < 0)
        row["geometry_issue_class"] = classify_geometry_issue(row)
        context = None

    row["path_replayable"] = row["path_status"] == "OK"
    row["path_replayable_or_clipped"] = row["path_status"] in {"OK", "PATH_COVERAGE_CLIPPED_START", "PATH_COVERAGE_CLIPPED_END"}
    row["path_context_available"] = context is not None
    row["path_close_reason_match_actual"] = bool(
        text(row.get("path_close_reason_primary")) == text(row.get("actual_close_reason"))
    ) if row.get("path_close_reason_primary") is not None else None

    return row, context


def classify_geometry_issue(row: dict[str, Any]) -> str:
    if text(row.get("path_status")) != "OK":
        return text(row.get("path_status"))
    if text(row.get("tpsl_status")) != "OK":
        return f"TPSL_{text(row.get('tpsl_status'))}"
    tp_edge_bps = number(row.get("tp_edge_bps"))
    sl_edge_bps = number(row.get("sl_edge_bps"))
    if tp_edge_bps is not None and sl_edge_bps is not None and tp_edge_bps <= 0 and sl_edge_bps <= 0:
        return "TP_AND_SL_BELOW_COST"
    if tp_edge_bps is not None and tp_edge_bps <= 0:
        return "TP_BELOW_COST"
    if sl_edge_bps is not None and sl_edge_bps <= 0:
        return "SL_BELOW_COST"
    if bool(row.get("giveback_material")):
        return "MFE_GIVEBACK"
    if number(row.get("mfe_net_return_pct")) is not None and number(row.get("mfe_net_return_pct")) <= 0:
        return "NO_AFTER_COST_EDGE"
    if text(row.get("actual_close_reason")) == "TP_HIT":
        return "TP_HIT"
    if text(row.get("actual_close_reason")) == "SL_HIT":
        return "SL_HIT"
    if bool(row.get("close_reason_timeout_like")):
        return "TIMEOUT"
    return "OTHER"


def build_attribution_rows(
    economic_rows: list[dict[str, Any]],
    replay_rows: list[dict[str, Any]],
    config: dict[str, Any],
    bars_by_symbol: dict[str, list[Bar]],
    bar_coverage: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[ReplayPathContext]]:
    replay_index = index_rows_by_uid(replay_rows)
    ts_by_symbol = {symbol: [bar.timestamp_ms for bar in bars] for symbol, bars in bars_by_symbol.items()}

    attribution_rows: list[dict[str, Any]] = []
    contexts: list[ReplayPathContext] = []

    for econ_row in economic_rows:
        if text(econ_row.get("pnl_status")) != "OK":
            continue
        uid = text(econ_row.get("proposal_uid"))
        replay_row = choose_replay_row(replay_index.get(uid))
        row, context = build_row_attribution(econ_row, replay_row, config, bars_by_symbol, ts_by_symbol, bar_coverage)
        attribution_rows.append(row)
        if context is not None:
            contexts.append(context)

    return attribution_rows, contexts


def group_attribution_rows(rows: list[dict[str, Any]], group_fields: list[str], total_rows: int) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = tuple(text(row.get(field)) for field in group_fields)
        buckets[key].append(row)

    summary_rows: list[dict[str, Any]] = []
    for key, bucket_rows in buckets.items():
        pnl_rows = [row for row in bucket_rows if text(row.get("pnl_status")) == "OK"]
        path_rows = [row for row in pnl_rows if text(row.get("path_status")) == "OK"]
        net_values = [number(row.get("actual_net_pnl_quote")) for row in pnl_rows if number(row.get("actual_net_pnl_quote")) is not None]
        gross_values = [number(row.get("actual_gross_pnl_quote")) for row in pnl_rows if number(row.get("actual_gross_pnl_quote")) is not None]
        positive_net_values = [value for value in net_values if value > 0]
        negative_net_values = [value for value in net_values if value < 0]
        profit_factor = (sum(positive_net_values) / abs(sum(negative_net_values))) if negative_net_values else None
        tp_rows = [row for row in bucket_rows if text(row.get("actual_close_reason")) == "TP_HIT"]
        sl_rows = [row for row in bucket_rows if text(row.get("actual_close_reason")) == "SL_HIT"]
        timeout_rows = [row for row in bucket_rows if bool(row.get("close_reason_timeout_like"))]
        observation_end_rows = [row for row in bucket_rows if text(row.get("actual_close_reason")) == "OBSERVATION_END"]
        geometry_issue_rows = [row for row in bucket_rows if text(row.get("geometry_issue_class")) not in {"OTHER", "TP_HIT", "SL_HIT"}]
        giveback_material_rows = [row for row in path_rows if bool(row.get("giveback_material"))]
        positive_mfe_rows = [row for row in path_rows if bool(row.get("profit_after_costs_available"))]
        path_unreplayable_rows = len(pnl_rows) - len(path_rows)

        gain_ratios_gross = [number(row.get("gross_giveback_ratio_pct")) for row in path_rows if number(row.get("gross_giveback_ratio_pct")) is not None]
        gain_ratios_net = [number(row.get("net_giveback_ratio_pct")) for row in path_rows if number(row.get("net_giveback_ratio_pct")) is not None]
        mfe_values = [number(row.get("mfe_gross_return_pct")) for row in path_rows if number(row.get("mfe_gross_return_pct")) is not None]
        mae_values = [number(row.get("mae_gross_return_pct")) for row in path_rows if number(row.get("mae_gross_return_pct")) is not None]

        row = {
            "group_label": "|".join(key),
            **{field: value for field, value in zip(group_fields, key)},
            "rows_total": len(bucket_rows),
            "share_of_all_group_rows_pct": pct(len(bucket_rows), total_rows),
            "rows_with_pnl": len(pnl_rows),
            "path_ok_rows": len(path_rows),
            "path_unreplayable_rows": path_unreplayable_rows,
            "path_coverage_pct": pct(len(path_rows), len(pnl_rows)),
            "gross_pnl_sum_quote": sum(gross_values) if gross_values else 0.0,
            "net_pnl_sum_quote": sum(net_values) if net_values else 0.0,
            "avg_net_pnl_quote": safe_mean(net_values),
            "median_net_pnl_quote": safe_median(net_values),
            "profit_factor": profit_factor,
            "win_rate_net_pct": pct(len(positive_net_values), len(pnl_rows)),
            "positive_net_rows": len(positive_net_values),
            "negative_net_rows": len(negative_net_values),
            "tp_hit_rows": len(tp_rows),
            "sl_hit_rows": len(sl_rows),
            "timeout_like_rows": len(timeout_rows),
            "observation_end_rows": len(observation_end_rows),
            "geometry_issue_rows": len(geometry_issue_rows),
            "positive_mfe_after_costs_rows": len(positive_mfe_rows),
            "positive_mfe_after_costs_rate_pct": pct(len(positive_mfe_rows), len(path_rows)),
            "giveback_material_rows": len(giveback_material_rows),
            "giveback_material_rate_pct": pct(len(giveback_material_rows), len(path_rows)),
            "avg_mfe_gross_return_pct": safe_mean(mfe_values),
            "median_mfe_gross_return_pct": safe_median(mfe_values),
            "avg_mae_gross_return_pct": safe_mean(mae_values),
            "median_mae_gross_return_pct": safe_median(mae_values),
            "avg_gross_giveback_ratio_pct": safe_mean(gain_ratios_gross),
            "median_gross_giveback_ratio_pct": safe_median(gain_ratios_gross),
            "avg_net_giveback_ratio_pct": safe_mean(gain_ratios_net),
            "median_net_giveback_ratio_pct": safe_median(gain_ratios_net),
        }
        summary_rows.append(row)

    summary_rows.sort(key=lambda row: (number(row.get("net_pnl_sum_quote")) or 0.0, -(number(row.get("rows_with_pnl")) or 0.0), row.get("group_label") or ""))
    return summary_rows


def build_profit_protection_counterfactual(
    contexts: list[ReplayPathContext],
) -> list[dict[str, Any]]:
    scenario_rows: list[dict[str, Any]] = []
    baseline_net_pnl_sum = sum(context.actual_net_pnl_quote for context in contexts)
    baseline_rows = len(contexts)

    for arm_pct in DEFAULT_ARM_PCTS:
        for trigger_pct in DEFAULT_GIVEBACK_TRIGGER_PCTS:
            counterfactual_net_values: list[float] = []
            managed_exit_rows = 0
            improved_rows = 0
            worsened_rows = 0
            rescued_loss_rows = 0
            path_unreplayable_rows = 0

            for context in contexts:
                simulation = simulate_profit_protection_counterfactual_indexed(
                    context=context,
                    arm_pct=arm_pct,
                    giveback_trigger_pct=trigger_pct,
                )
                if simulation.get("status") != "OK":
                    path_unreplayable_rows += 1
                    continue

                exit_price = number(simulation.get("exit_price"))
                if exit_price is None:
                    path_unreplayable_rows += 1
                    continue

                gross_pnl_quote = pnl_from_prices(context.side, context.entry_price, exit_price, context.quantity)[1]
                if gross_pnl_quote is None:
                    path_unreplayable_rows += 1
                    continue

                net_pnl_quote = gross_pnl_quote - (context.open_notional_quote * context.round_trip_cost_bps / 10000.0)
                counterfactual_net_values.append(net_pnl_quote)
                managed_exit_rows += 1 if bool(simulation.get("managed_exit")) else 0
                if net_pnl_quote > context.actual_net_pnl_quote:
                    improved_rows += 1
                if net_pnl_quote < context.actual_net_pnl_quote:
                    worsened_rows += 1
                if context.actual_net_pnl_quote < 0 and net_pnl_quote > 0:
                    rescued_loss_rows += 1

            positive_net_values = [value for value in counterfactual_net_values if value > 0]
            negative_net_values = [value for value in counterfactual_net_values if value < 0]
            counterfactual_profit_factor = (sum(positive_net_values) / abs(sum(negative_net_values))) if negative_net_values else None

            scenario_rows.append(
                {
                    "scenario_id": f"arm_{arm_pct:.2f}_trigger_{trigger_pct:.0f}",
                    "arm_pct": arm_pct,
                    "giveback_trigger_pct": trigger_pct,
                    "rows_total": baseline_rows,
                    "rows_evaluated": len(counterfactual_net_values),
                    "rows_skipped_unreplayable": path_unreplayable_rows,
                    "managed_exit_rows": managed_exit_rows,
                    "managed_exit_rate_pct": pct(managed_exit_rows, len(counterfactual_net_values)),
                    "rescued_loss_rows": rescued_loss_rows,
                    "improved_rows": improved_rows,
                    "worsened_rows": worsened_rows,
                    "baseline_net_pnl_sum_quote": baseline_net_pnl_sum,
                    "counterfactual_net_pnl_sum_quote": sum(counterfactual_net_values) if counterfactual_net_values else 0.0,
                    "delta_net_pnl_sum_quote": (sum(counterfactual_net_values) if counterfactual_net_values else 0.0) - baseline_net_pnl_sum,
                    "counterfactual_profit_factor": counterfactual_profit_factor,
                    "counterfactual_win_rate_pct": pct(len(positive_net_values), len(counterfactual_net_values)),
                    "counterfactual_positive_rows": len(positive_net_values),
                    "counterfactual_negative_rows": len(negative_net_values),
                    "avg_counterfactual_net_pnl_quote": safe_mean(counterfactual_net_values),
                    "median_counterfactual_net_pnl_quote": safe_median(counterfactual_net_values),
                }
            )

    scenario_rows.sort(key=lambda row: (-(number(row.get("delta_net_pnl_sum_quote")) or 0.0), -(number(row.get("rescued_loss_rows")) or 0.0), row.get("scenario_id") or ""))
    return scenario_rows


def render_losing_trade_md(rows: list[dict[str, Any]]) -> str:
    top_losses = sorted(rows, key=lambda row: number(row.get("actual_net_pnl_quote")) or 0.0)[:12]
    top_giveback = sorted(
        [row for row in rows if row.get("path_replayable")],
        key=lambda row: number(row.get("net_giveback_ratio_pct")) or 0.0,
        reverse=True,
    )[:12]
    path_unreplayable = sorted([row for row in rows if not row.get("path_replayable")], key=lambda row: number(row.get("actual_net_pnl_quote")) or 0.0)[:12]
    return "\n".join(
        [
            "# Losing Trade MFE / Giveback Audit",
            "",
            "## Largest Losses",
            md_table(
                top_losses,
                [
                    "source_line",
                    "symbol",
                    "regime",
                    "side",
                    "actual_close_reason",
                    "actual_net_pnl_quote",
                    "mfe_gross_return_pct",
                    "mfe_net_return_pct",
                    "net_giveback_ratio_pct",
                    "geometry_issue_class",
                ],
            ),
            "## Largest Giveback Ratios",
            md_table(
                top_giveback,
                [
                    "source_line",
                    "symbol",
                    "regime",
                    "side",
                    "actual_close_reason",
                    "actual_net_pnl_quote",
                    "mfe_gross_return_pct",
                    "mfe_net_return_pct",
                    "net_giveback_ratio_pct",
                    "geometry_issue_class",
                ],
            ),
            "## Path-Unreplayable Losses",
            md_table(
                path_unreplayable,
                [
                    "source_line",
                    "symbol",
                    "regime",
                    "side",
                    "actual_close_reason",
                    "actual_net_pnl_quote",
                    "path_status",
                    "tpsl_status",
                ],
            ),
        ]
    )


def render_casebook_md(rows: list[dict[str, Any]], scenarios: list[dict[str, Any]]) -> str:
    top_by_giveback = sorted([row for row in rows if row.get("path_replayable")], key=lambda row: number(row.get("net_giveback_ratio_pct")) or 0.0, reverse=True)[:10]
    top_losses = sorted(rows, key=lambda row: number(row.get("actual_net_pnl_quote")) or 0.0)[:10]
    top_geometry = sorted([row for row in rows if text(row.get("geometry_issue_class")) not in {"OTHER", "TP_HIT", "SL_HIT"}], key=lambda row: number(row.get("actual_net_pnl_quote")) or 0.0)[:10]
    best_scenario = scenarios[0] if scenarios else None
    return "\n".join(
        [
            "# Regime / TP-SL / Giveback Casebook",
            "",
            f"Best profit-protection scenario: {best_scenario.get('scenario_id')}" if best_scenario else "Best profit-protection scenario: _none_",
            f"Delta net PnL quote: {fmt_num(best_scenario.get('delta_net_pnl_sum_quote'), 6)}" if best_scenario else "Delta net PnL quote: _none_",
            "",
            "## Biggest Losses",
            md_table(
                top_losses,
                [
                    "source_line",
                    "symbol",
                    "regime",
                    "side",
                    "actual_close_reason",
                    "actual_net_pnl_quote",
                    "path_status",
                    "geometry_issue_class",
                ],
            ),
            "## Highest Giveback Rows",
            md_table(
                top_by_giveback,
                [
                    "source_line",
                    "symbol",
                    "regime",
                    "side",
                    "actual_close_reason",
                    "actual_net_pnl_quote",
                    "mfe_gross_return_pct",
                    "mfe_net_return_pct",
                    "net_giveback_ratio_pct",
                    "geometry_issue_class",
                ],
            ),
            "## Geometry Edge Cases",
            md_table(
                top_geometry,
                [
                    "source_line",
                    "symbol",
                    "regime",
                    "side",
                    "actual_close_reason",
                    "actual_net_pnl_quote",
                    "tpsl_status",
                    "tp_edge_bps",
                    "sl_edge_bps",
                    "geometry_issue_class",
                ],
            ),
        ]
    )


def render_culprit_summary_md(baseline: dict[str, Any], regime_rows: list[dict[str, Any]], symbol_regime_rows: list[dict[str, Any]], losing_rows: list[dict[str, Any]]) -> str:
    top_regimes = sorted(regime_rows, key=lambda row: number(row.get("net_pnl_sum_quote")) or 0.0)[:5]
    top_symbol_regimes = sorted(symbol_regime_rows, key=lambda row: number(row.get("net_pnl_sum_quote")) or 0.0)[:5]
    top_giveback_rows = sorted([row for row in losing_rows if row.get("path_replayable")], key=lambda row: number(row.get("net_giveback_ratio_pct")) or 0.0, reverse=True)[:5]
    geometry_issue_counts = Counter(text(row.get("geometry_issue_class")) for row in losing_rows)
    geometry_issue_rows = [{"geometry_issue_class": key, "rows": value} for key, value in geometry_issue_counts.most_common(8)]

    return "\n".join(
        [
            "# TP / SL / Giveback Culprit Summary",
            "",
            "## Baseline",
            f"- rows with pnl: {baseline['rows_with_pnl']}",
            f"- net pnl sum quote: {fmt_num(baseline['net_pnl_sum_quote'], 6)}",
            f"- profit factor: {fmt_num(baseline['profit_factor'], 6)}",
            f"- win rate net: {fmt_num(baseline['win_rate_net'], 6)}",
            "",
            "## Regime Pockets",
            md_table(
                top_regimes,
                [
                    "regime",
                    "rows_with_pnl",
                    "path_ok_rows",
                    "net_pnl_sum_quote",
                    "win_rate_net_pct",
                    "giveback_material_rows",
                    "median_net_giveback_ratio_pct",
                ],
            ),
            "## Symbol / Regime Pockets",
            md_table(
                top_symbol_regimes,
                [
                    "symbol",
                    "regime",
                    "rows_with_pnl",
                    "path_ok_rows",
                    "net_pnl_sum_quote",
                    "win_rate_net_pct",
                    "giveback_material_rows",
                    "median_net_giveback_ratio_pct",
                ],
            ),
            "## Biggest Giveback Rows",
            md_table(
                top_giveback_rows,
                [
                    "source_line",
                    "symbol",
                    "regime",
                    "side",
                    "actual_close_reason",
                    "actual_net_pnl_quote",
                    "mfe_gross_return_pct",
                    "mfe_net_return_pct",
                    "net_giveback_ratio_pct",
                ],
            ),
            "## Geometry Issue Counts",
            md_table(
                geometry_issue_rows,
                ["geometry_issue_class", "rows"],
            ),
        ]
    )


def render_profit_protection_md(rows: list[dict[str, Any]]) -> str:
    top_rows = rows[:8]
    best = top_rows[0] if top_rows else None
    top_rescues = sorted(rows, key=lambda row: (number(row.get("rescued_loss_rows")) or 0.0, number(row.get("delta_net_pnl_sum_quote")) or 0.0), reverse=True)[:8]
    return "\n".join(
        [
            "# Profit Protection Counterfactual",
            "",
            f"Best scenario: {best.get('scenario_id')}" if best else "Best scenario: _none_",
            f"Best delta net PnL quote: {fmt_num(best.get('delta_net_pnl_sum_quote'), 6)}" if best else "Best delta net PnL quote: _none_",
            "",
            "## Best by Net Delta",
            md_table(
                top_rows,
                [
                    "scenario_id",
                    "arm_pct",
                    "giveback_trigger_pct",
                    "rows_evaluated",
                    "managed_exit_rows",
                    "rescued_loss_rows",
                    "delta_net_pnl_sum_quote",
                    "counterfactual_win_rate_pct",
                ],
            ),
            "## Best by Rescued Losses",
            md_table(
                top_rescues,
                [
                    "scenario_id",
                    "arm_pct",
                    "giveback_trigger_pct",
                    "rows_evaluated",
                    "managed_exit_rows",
                    "rescued_loss_rows",
                    "delta_net_pnl_sum_quote",
                    "counterfactual_win_rate_pct",
                ],
            ),
        ]
    )


def render_final_report(
    baseline: dict[str, Any],
    regime_rows: list[dict[str, Any]],
    symbol_regime_rows: list[dict[str, Any]],
    strategy_regime_rows: list[dict[str, Any]],
    symbol_strategy_regime_rows: list[dict[str, Any]],
    losing_rows: list[dict[str, Any]],
    scenario_rows: list[dict[str, Any]],
    context_rows: list[ReplayPathContext],
    bar_coverage: dict[str, dict[str, Any]],
) -> str:
    best_scenario = scenario_rows[0] if scenario_rows else None
    top_regime = regime_rows[0] if regime_rows else None
    top_symbol_regime = symbol_regime_rows[0] if symbol_regime_rows else None
    top_geometry_issue = max((row for row in losing_rows if row.get("geometry_issue_class") not in {"OTHER", "TP_HIT", "SL_HIT"}), key=lambda row: abs(number(row.get("actual_net_pnl_quote")) or 0.0), default=None)
    path_ok_rows = [row for row in losing_rows if row.get("path_replayable")]
    giveback_rows = [row for row in path_ok_rows if bool(row.get("giveback_material"))]
    top_coverage_symbol = max(bar_coverage.values(), key=lambda item: integer(item.get("valid_rows")) or 0, default=None)

    lines = [
        "# ORDER_LOG_REGIME_TPSL_AND_GIVEBACK_ATTRIBUTION_AUDIT",
        "",
        "## Scope",
        "This audit is read-only. It consumes the frozen economic outcomes, replayed timing, and recorder bars, then reconstructs forward MFE / MAE / giveback without rerunning normalization.",
        "",
        "## Baseline",
        f"- source rows with pnl: {baseline['rows_with_pnl']}",
        f"- gross pnl sum quote: {fmt_num(baseline['gross_pnl_sum_quote'], 6)}",
        f"- net pnl sum quote: {fmt_num(baseline['net_pnl_sum_quote'], 6)}",
        f"- profit factor: {fmt_num(baseline['profit_factor'], 6)}",
        f"- win rate net: {fmt_num(baseline['win_rate_net'], 6)}",
        f"- tp rows: {baseline['tp_rows']}",
        f"- sl rows: {baseline['sl_rows']}",
        f"- timeout rows: {baseline['timeout_rows']}",
        "",
        "## Main Readout",
        f"- path replayable rows: {len(context_rows)}",
        f"- losing rows with path replay: {len(path_ok_rows)}",
        f"- losing rows with positive after-cost MFE: {sum(1 for row in path_ok_rows if bool(row.get('profit_after_costs_available')))}",
        f"- losing rows with giveback: {len(giveback_rows)}",
        f"- recorder symbols covered: {', '.join(sorted(bar_coverage.keys()))}",
        f"- top coverage symbol: {top_coverage_symbol.get('symbol') if top_coverage_symbol else ''}",
        "",
        "## Most Harmful Regime",
        f"- {top_regime.get('regime') if top_regime else ''}: net={fmt_num(top_regime.get('net_pnl_sum_quote') if top_regime else None, 6)} rows={top_regime.get('rows_with_pnl') if top_regime else ''} giveback={top_regime.get('giveback_material_rows') if top_regime else ''}",
        "",
        "## Most Harmful Symbol / Regime",
        f"- {top_symbol_regime.get('symbol') if top_symbol_regime else ''} / {top_symbol_regime.get('regime') if top_symbol_regime else ''}: net={fmt_num(top_symbol_regime.get('net_pnl_sum_quote') if top_symbol_regime else None, 6)} rows={top_symbol_regime.get('rows_with_pnl') if top_symbol_regime else ''} giveback={top_symbol_regime.get('giveback_material_rows') if top_symbol_regime else ''}",
        "",
        "## TP / SL Geometry",
        f"- top geometry issue row: {top_geometry_issue.get('source_line') if top_geometry_issue else ''} {top_geometry_issue.get('symbol') if top_geometry_issue else ''} {top_geometry_issue.get('geometry_issue_class') if top_geometry_issue else ''}",
        f"- geometry issue rows on losing slice: {sum(1 for row in losing_rows if text(row.get('geometry_issue_class')) not in {'OTHER', 'TP_HIT', 'SL_HIT'})}",
        "",
        "## Profit Protection Counterfactual",
        f"- best scenario: {best_scenario.get('scenario_id') if best_scenario else ''}",
        f"- best delta net pnl quote: {fmt_num(best_scenario.get('delta_net_pnl_sum_quote') if best_scenario else None, 6)}",
        f"- rescued loss rows: {best_scenario.get('rescued_loss_rows') if best_scenario else ''}",
        "",
        "## Notes",
        "- Same-bar TP / SL ambiguity is resolved conservatively with SL-first semantics.",
        "- Profit-protection scenarios use gross-return arm / giveback thresholds and then measure net PnL after the frozen round-trip cost.",
        "- Rows with missing close timestamp or incomplete recorder coverage are marked path-unreplayable and excluded from giveback math.",
    ]
    return "\n".join(lines) + "\n"


def validate_required_files() -> None:
    for path in (ECONOMIC_OUTCOMES_PATH, REPLAYED_OUTCOMES_PATH, CONFIG_SNAPSHOT_PATH, FIELD_COVERAGE_PATH):
        if not path.exists():
            raise RuntimeError(f"Missing required artifact: {path}")


def main() -> int:
    validate_required_files()
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)

    config = read_json(CONFIG_SNAPSHOT_PATH)
    expected_coverage = read_json(FIELD_COVERAGE_PATH)
    economic_rows = read_jsonl(ECONOMIC_OUTCOMES_PATH)
    replayed_rows = read_jsonl(REPLAYED_OUTCOMES_PATH)
    bars_by_symbol, bar_coverage = load_bars_300(RECORDER_ROOT)

    observed_coverage = build_field_coverage(economic_rows)
    validate_baseline(observed_coverage, expected_coverage)

    write_json(
        BASELINE_OUTPUT_PATH,
        {
            "schema_version": "order_log_regime_tpsl_giveback_baseline_reproduction_v1",
            "source_files": {
                "economic_outcomes": ECONOMIC_OUTCOMES_PATH.as_posix(),
                "replayed_outcomes": REPLAYED_OUTCOMES_PATH.as_posix(),
                "config_snapshot": CONFIG_SNAPSHOT_PATH.as_posix(),
                "economic_field_coverage": FIELD_COVERAGE_PATH.as_posix(),
                "recorder_root": RECORDER_ROOT.as_posix(),
            },
            "reference_field_coverage": expected_coverage,
            "observed_field_coverage": observed_coverage,
            "baseline_match": True,
        },
    )

    attribution_rows, contexts = build_attribution_rows(economic_rows, replayed_rows, config, bars_by_symbol, bar_coverage)
    total_rows = len(attribution_rows)
    regime_rows = group_attribution_rows(attribution_rows, ["regime"], total_rows)
    symbol_regime_rows = group_attribution_rows(attribution_rows, ["symbol", "regime"], total_rows)
    strategy_regime_rows = group_attribution_rows(attribution_rows, ["strategy", "regime"], total_rows)
    symbol_strategy_regime_rows = group_attribution_rows(attribution_rows, ["symbol", "strategy", "regime"], total_rows)

    losing_rows = [row for row in attribution_rows if (number(row.get("actual_net_pnl_quote")) or 0.0) < 0]
    losing_rows.sort(key=lambda row: (number(row.get("net_giveback_ratio_pct")) or 0.0, number(row.get("actual_net_pnl_quote")) or 0.0), reverse=True)

    scenario_rows = build_profit_protection_counterfactual(contexts)

    write_csv(
        REGIME_ATTRIBUTION_PATH,
        regime_rows,
        [
            "regime",
            "rows_total",
            "share_of_all_group_rows_pct",
            "rows_with_pnl",
            "path_ok_rows",
            "path_unreplayable_rows",
            "path_coverage_pct",
            "gross_pnl_sum_quote",
            "net_pnl_sum_quote",
            "avg_net_pnl_quote",
            "median_net_pnl_quote",
            "profit_factor",
            "win_rate_net_pct",
            "positive_net_rows",
            "negative_net_rows",
            "tp_hit_rows",
            "sl_hit_rows",
            "timeout_like_rows",
            "observation_end_rows",
            "geometry_issue_rows",
            "positive_mfe_after_costs_rows",
            "positive_mfe_after_costs_rate_pct",
            "giveback_material_rows",
            "giveback_material_rate_pct",
            "avg_mfe_gross_return_pct",
            "median_mfe_gross_return_pct",
            "avg_mae_gross_return_pct",
            "median_mae_gross_return_pct",
            "avg_gross_giveback_ratio_pct",
            "median_gross_giveback_ratio_pct",
            "avg_net_giveback_ratio_pct",
            "median_net_giveback_ratio_pct",
        ],
    )
    write_csv(
        SYMBOL_REGIME_ATTRIBUTION_PATH,
        symbol_regime_rows,
        [
            "symbol",
            "regime",
            "rows_total",
            "share_of_all_group_rows_pct",
            "rows_with_pnl",
            "path_ok_rows",
            "path_unreplayable_rows",
            "path_coverage_pct",
            "gross_pnl_sum_quote",
            "net_pnl_sum_quote",
            "avg_net_pnl_quote",
            "median_net_pnl_quote",
            "profit_factor",
            "win_rate_net_pct",
            "positive_net_rows",
            "negative_net_rows",
            "tp_hit_rows",
            "sl_hit_rows",
            "timeout_like_rows",
            "observation_end_rows",
            "geometry_issue_rows",
            "positive_mfe_after_costs_rows",
            "positive_mfe_after_costs_rate_pct",
            "giveback_material_rows",
            "giveback_material_rate_pct",
            "avg_mfe_gross_return_pct",
            "median_mfe_gross_return_pct",
            "avg_mae_gross_return_pct",
            "median_mae_gross_return_pct",
            "avg_gross_giveback_ratio_pct",
            "median_gross_giveback_ratio_pct",
            "avg_net_giveback_ratio_pct",
            "median_net_giveback_ratio_pct",
        ],
    )
    write_csv(
        STRATEGY_REGIME_ATTRIBUTION_PATH,
        strategy_regime_rows,
        [
            "strategy",
            "regime",
            "rows_total",
            "share_of_all_group_rows_pct",
            "rows_with_pnl",
            "path_ok_rows",
            "path_unreplayable_rows",
            "path_coverage_pct",
            "gross_pnl_sum_quote",
            "net_pnl_sum_quote",
            "avg_net_pnl_quote",
            "median_net_pnl_quote",
            "profit_factor",
            "win_rate_net_pct",
            "positive_net_rows",
            "negative_net_rows",
            "tp_hit_rows",
            "sl_hit_rows",
            "timeout_like_rows",
            "observation_end_rows",
            "geometry_issue_rows",
            "positive_mfe_after_costs_rows",
            "positive_mfe_after_costs_rate_pct",
            "giveback_material_rows",
            "giveback_material_rate_pct",
            "avg_mfe_gross_return_pct",
            "median_mfe_gross_return_pct",
            "avg_mae_gross_return_pct",
            "median_mae_gross_return_pct",
            "avg_gross_giveback_ratio_pct",
            "median_gross_giveback_ratio_pct",
            "avg_net_giveback_ratio_pct",
            "median_net_giveback_ratio_pct",
        ],
    )
    write_csv(
        SYMBOL_STRATEGY_REGIME_ATTRIBUTION_PATH,
        symbol_strategy_regime_rows,
        [
            "symbol",
            "strategy",
            "regime",
            "rows_total",
            "share_of_all_group_rows_pct",
            "rows_with_pnl",
            "path_ok_rows",
            "path_unreplayable_rows",
            "path_coverage_pct",
            "gross_pnl_sum_quote",
            "net_pnl_sum_quote",
            "avg_net_pnl_quote",
            "median_net_pnl_quote",
            "profit_factor",
            "win_rate_net_pct",
            "positive_net_rows",
            "negative_net_rows",
            "tp_hit_rows",
            "sl_hit_rows",
            "timeout_like_rows",
            "observation_end_rows",
            "geometry_issue_rows",
            "positive_mfe_after_costs_rows",
            "positive_mfe_after_costs_rate_pct",
            "giveback_material_rows",
            "giveback_material_rate_pct",
            "avg_mfe_gross_return_pct",
            "median_mfe_gross_return_pct",
            "avg_mae_gross_return_pct",
            "median_mae_gross_return_pct",
            "avg_gross_giveback_ratio_pct",
            "median_gross_giveback_ratio_pct",
            "avg_net_giveback_ratio_pct",
            "median_net_giveback_ratio_pct",
        ],
    )

    tpsl_rows = sorted(
        attribution_rows,
        key=lambda row: (number(row.get("actual_net_pnl_quote")) or 0.0, number(row.get("net_giveback_ratio_pct")) or 0.0),
    )
    write_csv(
        TPSL_GEOMETRY_ATTRIBUTION_PATH,
        tpsl_rows,
        [
            "proposal_uid",
            "source_line",
            "entry_ts_iso",
            "close_ts_iso",
            "symbol",
            "side",
            "strategy",
            "regime",
            "actual_close_reason",
            "close_reason_timeout_like",
            "pnl_status",
            "actual_gross_pnl_quote",
            "actual_net_pnl_quote",
            "actual_gross_return_pct",
            "actual_net_return_pct",
            "path_status",
            "path_close_reason_primary",
            "path_close_price_primary",
            "path_close_ts_ms_primary",
            "path_close_reason_secondary",
            "path_close_price_secondary",
            "path_close_ts_ms_secondary",
            "path_ambiguous_intrabar",
            "path_bars_considered",
            "mfe_gross_return_pct",
            "mae_gross_return_pct",
            "mfe_net_return_pct",
            "realized_gross_return_pct",
            "realized_net_return_pct",
            "mfe_gross_pnl_quote",
            "mfe_net_pnl_quote",
            "gross_giveback_quote",
            "net_giveback_quote",
            "gross_giveback_ratio_pct",
            "net_giveback_ratio_pct",
            "profit_after_costs_available",
            "giveback_material",
            "geometry_issue_class",
            "tpsl_status",
            "stop_price",
            "target_price",
            "sl_pct_eff",
            "tp_pct_eff",
            "tp_rr_eff",
            "tpsl_min_dist_bps",
            "tp_edge_bps",
            "sl_edge_bps",
            "tp_to_cost_ratio",
            "sl_to_cost_ratio",
            "tpsl_guardrail_notes",
            "path_clipped_start",
            "path_clipped_end",
            "path_replayable",
            "path_replayable_or_clipped",
            "path_context_available",
            "path_close_reason_match_actual",
        ],
    )

    write_json(LOSING_TRADE_MFE_GIVEBACK_AUDIT_JSON, losing_rows)
    write_csv(
        LOSING_TRADE_MFE_GIVEBACK_AUDIT_CSV,
        losing_rows,
        [
            "proposal_uid",
            "source_line",
            "entry_ts_iso",
            "close_ts_iso",
            "symbol",
            "side",
            "strategy",
            "regime",
            "actual_close_reason",
            "actual_net_pnl_quote",
            "actual_gross_pnl_quote",
            "actual_gross_return_pct",
            "actual_net_return_pct",
            "path_status",
            "path_close_reason_primary",
            "path_bars_considered",
            "mfe_gross_return_pct",
            "mfe_net_return_pct",
            "gross_giveback_quote",
            "net_giveback_quote",
            "gross_giveback_ratio_pct",
            "net_giveback_ratio_pct",
            "profit_after_costs_available",
            "giveback_material",
            "geometry_issue_class",
            "tpsl_status",
            "tp_edge_bps",
            "sl_edge_bps",
            "tp_pct_eff",
            "sl_pct_eff",
        ],
    )

    write_csv(
        PROFIT_PROTECTION_COUNTERFACTUAL_CSV,
        scenario_rows,
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
            "avg_counterfactual_net_pnl_quote",
            "median_counterfactual_net_pnl_quote",
        ],
    )

    write_text(TPSL_CULPRIT_SUMMARY_PATH, render_culprit_summary_md(observed_coverage["overall_summary"], regime_rows, symbol_regime_rows, losing_rows))
    write_text(LOSING_TRADE_MFE_GIVEBACK_AUDIT_MD, render_losing_trade_md(losing_rows))
    write_text(PROFIT_PROTECTION_COUNTERFACTUAL_MD, render_profit_protection_md(scenario_rows))
    write_text(REGIME_TPSL_GIVEBACK_CASEBOOK_MD, render_casebook_md(losing_rows, scenario_rows))
    write_text(
        FINAL_REPORT_MD,
        render_final_report(
            observed_coverage["overall_summary"],
            regime_rows,
            symbol_regime_rows,
            strategy_regime_rows,
            symbol_strategy_regime_rows,
            losing_rows,
            scenario_rows,
            contexts,
            bar_coverage,
        ),
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "baseline_report": BASELINE_OUTPUT_PATH.as_posix(),
                "report": FINAL_REPORT_MD.as_posix(),
                "rows_with_pnl": observed_coverage["rows_with_pnl"],
                "path_replayable_rows": len(contexts),
                "losing_rows": len(losing_rows),
                "best_scenario": scenario_rows[0]["scenario_id"] if scenario_rows else None,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=_json_default,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())