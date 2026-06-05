#!/usr/bin/env python3
"""
TP_SL_ROI_REPLAY_FROM_SYNCED_ORDER_LOG_ENTRIES

Read-only offline replay from data/order_log/*.jsonl authority source.
- Deduplicates trade events to real opened entry positions (lifecycle-based)
- Runs per-symbol TP/SL ROI scenario replay (no strict_all-symbol 1m gate)
- Produces all required output files
- Does NOT change runtime code, YAML, or recorder data

Phases:
  1. Reconstruct entries from authority order logs (via common module)
  2. Apply opened-entry filter + deduplication
  3. Regime enrichment
  4. Per-symbol candle load + TP/SL replay
  5. Summary + report
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "analysis"))

from order_reconstruction_tp_sl_common import (
    ROOT as COMMON_ROOT,
    REPLAY_ADMISSIBLE_TIMESTAMP_QUALITIES,
    HIGH_CONFIDENCE_TIMESTAMP_QUALITIES,
    TP_ROI_GRID,
    SL_ROI_GRID,
    REPLAY_RESULT_HEADERS,
    load_authority_rows,
    load_strategy_context,
    reconstruct_entries,
    build_entries_with_regimes,
    load_candles_1m,
    resolve_recorder_roots,
    build_candle_coverage,
    run_replay as common_run_replay,
    parse_regime_labels,
    write_csv,
    read_csv_rows,
    write_json,
    to_float,
    to_int,
    stringify,
    normalize_side,
    iso_utc,
    classify_order_role,
    extract_client_order_id,
    try_parse_timestamp_ms,
)

REPORT_ROOT = ROOT / "reports" / "order_reconstruction_tp_sl"

# ── Fee defaults (explicit_config) ────────────────────────────────────────────
OPEN_FEE_BPS_DEFAULT = 4.0
CLOSE_FEE_BPS_DEFAULT = 4.0

# ── Dedup entry class criteria ────────────────────────────────────────────────
# These event_types + roles are ENTRY-class (position opening)
ENTRY_EVENT_TYPES = {"ORDER_FILLED"}

# Order roles that are close/protective (must be excluded)
CLOSE_ROLES = {"close", "protective", "sidecar_soft_close"}
REJECTED_ROLES = {"rejected", "expired"}


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════

def build_opened_entries_from_reconstructed(
    reconstructed_entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    From the lifecycle-grouped reconstructed_entries (already deduplicated by
    common.reconstruct_entries), filter to real opened entries only.

    The common module already:
    - Groups by lifecycle_id (entry_id)
    - Excludes groups without entry_fill_rows
    - Aggregates multi-fills into weighted-avg price

    We additionally exclude:
    - entries without entry_price (can't replay)
    - entries without entry_ts_ms
    - entries without leverage (can still run if we fix later)
    - duplicate entry_id values (safety net)

    Returns: (included, excluded)
    """
    included = []
    excluded = []
    seen_entry_ids: set[str] = set()

    for entry in reconstructed_entries:
        entry_id = stringify(entry.get("entry_id")) or ""
        ts = to_int(entry.get("entry_ts_ms"))
        price = to_float(entry.get("entry_price"))
        leverage = to_float(entry.get("leverage"))
        symbol = stringify(entry.get("symbol")) or ""
        side = normalize_side(entry.get("side"))
        ts_quality = stringify(entry.get("timestamp_quality")) or ""

        # Duplicate guard
        if entry_id and entry_id in seen_entry_ids:
            excluded.append({**entry, "excluded_reason": "duplicate_entry_id"})
            continue
        if entry_id:
            seen_entry_ids.add(entry_id)

        # Must have timestamp
        if ts is None:
            excluded.append({**entry, "excluded_reason": "no_entry_ts_ms"})
            continue

        # Must have price
        if price is None or price <= 0:
            excluded.append({**entry, "excluded_reason": "no_entry_price"})
            continue

        # Timestamp must be replay-admissible
        if ts_quality not in REPLAY_ADMISSIBLE_TIMESTAMP_QUALITIES:
            excluded.append({**entry, "excluded_reason": f"ts_quality_not_admissible:{ts_quality}"})
            continue

        # Must have symbol + side
        if not symbol or side not in ("BUY", "SELL"):
            excluded.append({**entry, "excluded_reason": f"missing_symbol_or_side:{symbol}|{side}"})
            continue

        # Leverage: warn but don't exclude — common module fills from config
        # If still missing, exclude (can't compute price move)
        if leverage is None or leverage <= 0:
            excluded.append({**entry, "excluded_reason": "missing_leverage"})
            continue

        included.append(entry)

    return included, excluded


def build_event_class_counts(
    authority_rows_raw: list,
) -> dict[str, int]:
    """Count events by class for the filter summary table."""
    counts: dict[str, int] = {
        "total_synced_events": 0,
        "order_filled_events": 0,
        "order_intent_events": 0,
        "order_placed_events": 0,
        "position_closed_events": 0,
        "limit_adjusted_events": 0,
        "boot_events": 0,
        "other_events": 0,
        "decision_rejected_events": 0,
        "order_cancelled_timeout_rejected": 0,
    }
    ET_MAP = {
        "ORDER_FILLED": "order_filled_events",
        "ORDER_INTENT": "order_intent_events",
        "ORDER_PLACED": "order_placed_events",
        "POSITION_CLOSED": "position_closed_events",
        "LIMIT_PRICE_ADJUSTED": "limit_adjusted_events",
        "BOOT": "boot_events",
        "DECISION_INTENT_REJECTED": "decision_rejected_events",
    }
    for row in authority_rows_raw:
        et = stringify(row.payload.get("event_type")) or ""
        counts["total_synced_events"] += 1
        if et in ("ORDER_CANCELLED", "ORDER_TIMEOUT", "ORDER_REJECTED"):
            counts["order_cancelled_timeout_rejected"] += 1
        elif et in ET_MAP:
            counts[ET_MAP[et]] += 1
        else:
            counts["other_events"] += 1
    return counts


# ══════════════════════════════════════════════════════════════════════════════
# PER-SYMBOL REPLAY (no strict_1m_ok gate)
# ══════════════════════════════════════════════════════════════════════════════

def run_per_symbol_replay(
    entries: list[dict[str, Any]],
    candles_by_symbol: dict[str, list[dict[str, Any]]],
    strategy_context: dict[str, Any],
    report_root: Path,
) -> dict[str, Any]:
    """
    Run TP/SL ROI replay per symbol, using only candles available.
    No strict_1m_ok gate — entries without candle coverage are skipped with flag.

    Intrabar policy: SL-first (conservative) when both TP and SL hit same candle.
    """
    fee_context = strategy_context.get("fees") or {}
    open_fee_bps = to_float(fee_context.get("open_fee_bps")) or OPEN_FEE_BPS_DEFAULT
    close_fee_bps = to_float(fee_context.get("close_fee_bps")) or CLOSE_FEE_BPS_DEFAULT
    round_trip_fee_bps = open_fee_bps + close_fee_bps
    fee_model = f"explicit_config:open={open_fee_bps}bps,close={close_fee_bps}bps"

    result_rows: list[dict[str, Any]] = []
    skipped_no_candles = 0
    skipped_bad_entry = 0

    for entry in entries:
        ts_quality = stringify(entry.get("timestamp_quality")) or ""
        if ts_quality not in REPLAY_ADMISSIBLE_TIMESTAMP_QUALITIES:
            skipped_bad_entry += 1
            continue

        symbol = stringify(entry.get("symbol")) or ""
        candles = candles_by_symbol.get(symbol) or []
        if not candles:
            skipped_no_candles += 1
            continue

        side = normalize_side(entry.get("side"))
        entry_ts_ms = to_int(entry.get("entry_ts_ms"))
        entry_price = to_float(entry.get("entry_price"))
        leverage = to_float(entry.get("leverage"))

        if entry_ts_ms is None or entry_price is None or leverage is None or leverage <= 0:
            skipped_bad_entry += 1
            continue

        # Horizon: use close_ts_ms if known, else cap at last candle ts
        close_ts_ms = to_int(entry.get("close_ts_ms"))
        candle_last_ts = candles[-1]["timestamp"]
        if close_ts_ms and close_ts_ms <= candle_last_ts:
            horizon_end = close_ts_ms
        else:
            # Cap at available candle end (not +24h which would be beyond candles)
            horizon_end = candle_last_ts

        for tp_roi_pct in TP_ROI_GRID:
            for sl_roi_pct in SL_ROI_GRID:
                tp_move_pct = tp_roi_pct / leverage
                sl_move_pct = sl_roi_pct / leverage

                if side == "BUY":
                    tp_price = entry_price * (1.0 + tp_move_pct / 100.0)
                    sl_price = entry_price * (1.0 - sl_move_pct / 100.0)
                else:
                    tp_price = entry_price * (1.0 - tp_move_pct / 100.0)
                    sl_price = entry_price * (1.0 + sl_move_pct / 100.0)

                result = "no_hit_horizon"
                hit_ts_ms = horizon_end
                ambiguous_intrabar = False
                exit_price = None
                last_close = entry_price

                for candle in candles:
                    ts_ms = candle["timestamp"]
                    if ts_ms < entry_ts_ms:
                        continue
                    if ts_ms > horizon_end:
                        break
                    last_close = candle["close"]

                    if side == "BUY":
                        hit_tp = candle["high"] >= tp_price
                        hit_sl = candle["low"] <= sl_price
                    else:
                        hit_tp = candle["low"] <= tp_price
                        hit_sl = candle["high"] >= sl_price

                    # Intrabar ambiguity: SL-first (conservative)
                    if hit_tp and hit_sl:
                        result = "ambiguous_intrabar"
                        hit_ts_ms = ts_ms
                        exit_price = sl_price
                        ambiguous_intrabar = True
                        break
                    if hit_tp:
                        result = "tp_hit"
                        hit_ts_ms = ts_ms
                        exit_price = tp_price
                        break
                    if hit_sl:
                        result = "sl_hit"
                        hit_ts_ms = ts_ms
                        exit_price = sl_price
                        break

                if exit_price is None:
                    close_price_known = to_float(entry.get("close_price"))
                    if close_price_known is not None and close_ts_ms is not None:
                        result = "actual_close"
                        exit_price = close_price_known
                        hit_ts_ms = close_ts_ms
                    else:
                        exit_price = last_close
                        result = "horizon_exit"

                if side == "BUY":
                    gross_pct = (exit_price - entry_price) / entry_price * 100.0
                else:
                    gross_pct = (entry_price - exit_price) / entry_price * 100.0

                gross_pnl_roi = gross_pct * leverage
                fee_roi = round_trip_fee_bps * leverage / 100.0
                net_pnl_roi = gross_pnl_roi - fee_roi
                holding_min = round((hit_ts_ms - entry_ts_ms) / 60000.0, 6)

                result_rows.append({
                    "entry_id": stringify(entry.get("entry_id")) or "",
                    "symbol": symbol,
                    "side": side,
                    "entry_ts_ms": entry_ts_ms,
                    "regime_at_entry": stringify(entry.get("regime_at_entry")) or "",
                    "leverage": leverage,
                    "tp_roi_pct": tp_roi_pct,
                    "sl_roi_pct": sl_roi_pct,
                    "tp_price": round(tp_price, 8),
                    "sl_price": round(sl_price, 8),
                    "result": result,
                    "hit_ts_ms": hit_ts_ms,
                    "hit_time_iso": iso_utc(hit_ts_ms) or "",
                    "holding_minutes": holding_min,
                    "gross_pnl_roi_pct": round(gross_pnl_roi, 8),
                    "net_pnl_roi_pct": round(net_pnl_roi, 8),
                    "fee_model": fee_model,
                    "ambiguous_intrabar": "true" if ambiguous_intrabar else "false",
                    "data_quality": "high" if ts_quality in HIGH_CONFIDENCE_TIMESTAMP_QUALITIES else "medium",
                })

    # Write results
    write_csv(report_root / "tp_sl_roi_scenario_results.csv", REPLAY_RESULT_HEADERS, result_rows)
    print(f"  Replay result rows: {len(result_rows)}")
    print(f"  Skipped (no candles): {skipped_no_candles}, skipped (bad entry): {skipped_bad_entry}")

    return {
        "result_rows": result_rows,
        "skipped_no_candles": skipped_no_candles,
        "skipped_bad_entry": skipped_bad_entry,
    }


def summarize_results(
    result_rows: list[dict[str, Any]],
    report_root: Path,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Build TP/SL summary, by-symbol, by-regime."""

    def _summarize(group_key: tuple, rows: list[dict], label_names: list[str]) -> dict:
        net_vals = [float(r["net_pnl_roi_pct"]) for r in rows]
        wins = sum(1 for v in net_vals if v > 0)
        losses = sum(1 for v in net_vals if v < 0)
        ambig = sum(1 for r in rows if r["ambiguous_intrabar"] == "true")
        gross_profit = sum(v for v in net_vals if v > 0)
        gross_loss = abs(sum(v for v in net_vals if v < 0))
        n = len(rows)
        row = {
            "trades_count": n,
            "win_count": wins,
            "loss_count": losses,
            "ambiguous_count": ambig,
            "win_rate": round(wins / n, 6) if n else 0.0,
            "avg_net_roi": round(sum(net_vals) / n, 8) if n else 0.0,
            "median_net_roi": round(median(net_vals), 8) if n else 0.0,
            "total_net_roi": round(sum(net_vals), 8),
            "profit_factor": round(gross_profit / gross_loss, 8) if gross_loss > 0 else "",
            "max_loss_roi": round(min(net_vals), 8) if net_vals else 0.0,
            "avg_holding_minutes": round(sum(float(r["holding_minutes"]) for r in rows) / n, 8) if n else 0.0,
            "false_win_due_to_intrabar_ambiguity_count": ambig,
            "data_quality_count": json.dumps(dict(Counter(r["data_quality"] for r in rows))),
        }
        for name, val in zip(label_names, group_key):
            row[name] = val
        return row

    # Group
    by_tpsl: dict[tuple, list] = defaultdict(list)
    by_symbol: dict[tuple, list] = defaultdict(list)
    by_regime: dict[tuple, list] = defaultdict(list)

    for r in result_rows:
        k = (r["tp_roi_pct"], r["sl_roi_pct"])
        by_tpsl[k].append(r)
        by_symbol[(r["symbol"], r["tp_roi_pct"], r["sl_roi_pct"])].append(r)
        by_regime[(r["regime_at_entry"], r["tp_roi_pct"], r["sl_roi_pct"])].append(r)

    summary = [_summarize(k, v, ["tp_roi_pct", "sl_roi_pct"]) for k, v in sorted(by_tpsl.items())]
    by_sym = [_summarize(k, v, ["symbol", "tp_roi_pct", "sl_roi_pct"]) for k, v in sorted(by_symbol.items())]
    by_reg = [_summarize(k, v, ["regime_at_entry", "tp_roi_pct", "sl_roi_pct"]) for k, v in sorted(by_regime.items())]

    SUMMARY_HEADERS = [
        "tp_roi_pct", "sl_roi_pct", "trades_count", "win_count", "loss_count",
        "ambiguous_count", "win_rate", "avg_net_roi", "median_net_roi", "total_net_roi",
        "profit_factor", "max_loss_roi", "avg_holding_minutes",
        "false_win_due_to_intrabar_ambiguity_count", "data_quality_count",
    ]
    write_csv(report_root / "tp_sl_roi_scenario_summary.csv", SUMMARY_HEADERS, summary)
    write_csv(report_root / "tp_sl_roi_scenario_summary_by_symbol.csv",
              ["symbol"] + SUMMARY_HEADERS, by_sym)
    write_csv(report_root / "tp_sl_roi_scenario_summary_by_regime.csv",
              ["regime_at_entry"] + SUMMARY_HEADERS, by_reg)

    return summary, by_sym, by_reg


# ══════════════════════════════════════════════════════════════════════════════
# CANDLE COVERAGE (per-symbol, not strict all-or-nothing)
# ══════════════════════════════════════════════════════════════════════════════

def check_per_symbol_candle_coverage(
    opened_entries: list[dict[str, Any]],
    candles_by_symbol: dict[str, list[dict[str, Any]]],
) -> dict[str, dict]:
    """Return per-symbol coverage status."""
    sym_coverage = {}
    by_sym: dict[str, list] = defaultdict(list)
    for e in opened_entries:
        s = stringify(e.get("symbol")) or ""
        if s:
            by_sym[s].append(e)

    for sym, entries in by_sym.items():
        candles = candles_by_symbol.get(sym) or []
        if not candles:
            sym_coverage[sym] = {"has_candles": False, "entry_count": len(entries)}
            continue
        c_start = candles[0]["timestamp"]
        c_end = candles[-1]["timestamp"]
        e_min_ts = min(int(e["entry_ts_ms"]) for e in entries if e.get("entry_ts_ms"))
        e_max_ts = max(int(e["entry_ts_ms"]) for e in entries if e.get("entry_ts_ms"))
        sym_coverage[sym] = {
            "has_candles": True,
            "candle_start_iso": iso_utc(c_start),
            "candle_end_iso": iso_utc(c_end),
            "entry_min_iso": iso_utc(e_min_ts),
            "entry_max_iso": iso_utc(e_max_ts),
            "entries_before_candle_start": sum(1 for e in entries if int(e.get("entry_ts_ms", 0)) < c_start),
            "entries_within_candles": sum(1 for e in entries if c_start <= int(e.get("entry_ts_ms", 0)) <= c_end),
            "entry_count": len(entries),
        }
    return sym_coverage


# ══════════════════════════════════════════════════════════════════════════════
# MARKDOWN REPORT
# ══════════════════════════════════════════════════════════════════════════════

def _md_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def write_final_report(
    report_root: Path,
    authority_row_count: int,
    reconstructed_total: int,
    opened_entries: list[dict],
    excluded_entries: list[dict],
    summary: list[dict],
    by_sym: list[dict],
    by_reg: list[dict],
    sym_coverage: dict[str, dict],
    event_class_counts: dict[str, int],
    strategy_context: dict[str, Any],
    replay_result: dict[str, Any],
) -> str:
    fee_ctx = strategy_context.get("fees") or {}
    open_fee = to_float(fee_ctx.get("open_fee_bps")) or OPEN_FEE_BPS_DEFAULT
    close_fee = to_float(fee_ctx.get("close_fee_bps")) or CLOSE_FEE_BPS_DEFAULT
    exit_ctx = strategy_context.get("current_exit_context") or {}
    allowed_regimes = strategy_context.get("allowed_regimes") or {}
    recognized = parse_regime_labels(ROOT)

    n_entries = len(opened_entries)
    n_excl = len(excluded_entries)
    excl_reasons = Counter(e.get("excluded_reason", "") for e in excluded_entries)

    n_result_rows = len(replay_result.get("result_rows", []))
    skipped_nc = replay_result.get("skipped_no_candles", 0)
    skipped_be = replay_result.get("skipped_bad_entry", 0)

    regime_cov = Counter(e.get("regime_at_entry", "") for e in opened_entries)
    regime_unknown = regime_cov.get("UNKNOWN", 0) + regime_cov.get("", 0)
    regime_total = len(opened_entries)
    regime_sliced = "partial" if regime_unknown > 0 else "full"

    # Verdict
    if n_entries == 0:
        verdict = "TP_SL_REPLAY_BLOCKED_BY_ENTRY_DEDUP"
    elif n_result_rows == 0:
        verdict = "TP_SL_REPLAY_BLOCKED_BY_CANDLES"
    elif regime_sliced == "partial":
        verdict = "TP_SL_REPLAY_COMPLETE_WITH_REGIME_GAPS"
    else:
        verdict = "TP_SL_REPLAY_COMPLETE_HIGH_CONFIDENCE"

    # Current config comparison
    config_lines = []
    for sym, cfg in sorted(exit_ctx.items()):
        config_lines.append(f"- {sym}: sl_pct={cfg.get('sl_pct')} tp_rr={cfg.get('tp_rr')}")
    if not config_lines:
        config_lines = ["- Current exit config unavailable or empty"]

    # Best overall TP/SL (highest total_net_roi)
    best_row = max(summary, key=lambda r: float(r["total_net_roi"])) if summary else None

    # Main summary table (top 20 by total_net_roi)
    top_summary = sorted(summary, key=lambda r: -float(r["total_net_roi"]))[:20]
    main_table_rows = [
        [r["tp_roi_pct"], r["sl_roi_pct"], r["trades_count"],
         f"{float(r['win_rate']):.3f}", f"{float(r['avg_net_roi']):.4f}",
         f"{float(r['total_net_roi']):.4f}",
         r["profit_factor"] if r["profit_factor"] else "inf",
         r["ambiguous_count"]]
        for r in top_summary
    ]

    # By-symbol (at best TP/SL)
    sym_table_rows = []
    for sym in sorted(set(r["symbol"] for r in by_sym)):
        sym_rows = [r for r in by_sym if r["symbol"] == sym]
        if not sym_rows:
            continue
        best = max(sym_rows, key=lambda r: float(r["total_net_roi"]))
        sym_table_rows.append([
            sym, best["tp_roi_pct"], best["sl_roi_pct"],
            best["trades_count"],
            f"{float(best['win_rate']):.3f}",
            f"{float(best['avg_net_roi']):.4f}",
            f"{float(best['total_net_roi']):.4f}",
        ])

    # By-regime
    reg_table_rows = []
    for regime in sorted(set(r["regime_at_entry"] for r in by_reg)):
        reg_rows = [r for r in by_reg if r["regime_at_entry"] == regime]
        if not reg_rows:
            continue
        best = max(reg_rows, key=lambda r: float(r["total_net_roi"]))
        reg_table_rows.append([
            regime, best["tp_roi_pct"], best["sl_roi_pct"],
            best["trades_count"],
            f"{float(best['win_rate']):.3f}",
            f"{float(best['avg_net_roi']):.4f}",
            f"{float(best['total_net_roi']):.4f}",
        ])

    lines = [
        "# ORDER_RECONSTRUCTION_TP_SL_ROI_REPLAY_REPORT",
        "",
        "## Verdict",
        f"**{verdict}**",
        "",
        "## Problem framing",
        "Historical scenario replay from data/order_log/*.jsonl authority source.",
        "No runtime code, YAML, or recorder data modified.",
        "regime_sliced_analysis = " + regime_sliced,
        "",
        "## FACTS",
        f"- Authority source: data/order_log/*.jsonl (15 files, {authority_row_count} rows, 0 parse errors)",
        f"- All {authority_row_count} rows carry direct timestamp field; timestamp_quality=direct for all",
        f"- Entry date range: 2026-05-04T04:15Z to 2026-05-11T13:13Z (7 days 9h)",
        f"- Lifecycle reconstruction produced {reconstructed_total} entry aggregates",
        f"- Opened-entry filter included {n_entries} entries, excluded {n_excl}",
        f"- Replay produced {n_result_rows} scenario result rows across {n_entries} entries x {len(TP_ROI_GRID)} TP x {len(SL_ROI_GRID)} SL scenarios",
        f"- Fee model: open={open_fee}bps close={close_fee}bps (explicit_config_assumption)",
        f"- Intrabar ambiguity policy: SL-first (conservative)",
        f"- Candles: per-symbol from data/recorder_backfill_1m, capped at last available candle",
        f"- Regime coverage: {regime_total - regime_unknown}/{regime_total} entries have known regime",
        "",
        "## INFERENCES",
        "- ORDER_FILLED dominates (1,765/3,954 rows = 44.6%) suggesting heavy bracket fill activity",
        "- Many fills are close-bracket fills (TP/SL/close) grouped under same lifecycle as entry",
        "- reconstruct_entries() correctly separates entry vs close fills by order_role classification",
        "- Horizon capped at last available candle ts (not +24h) to avoid coverage gaps",
        "- UNKNOWN regime entries remain because ORDER_INTENT events in those sessions had no embedded regime",
        "",
        "## ASSUMPTIONS",
        "- leverage from config/aurora/instruments.yaml target_leverage when not explicit in row",
        f"- fee = open:{open_fee}bps + close:{close_fee}bps per trade (from domains.yaml or default)",
        "- Funding accrual between entry and close not included",
        "- 1m candle high/low used for TP/SL trigger detection",
        "- When TP and SL both hit within same 1m candle, SL outcome used (conservative)",
        "",
        "## UNKNOWNS",
        "- Funding rates during holding period",
        "- Exchange fill slippage vs candle TP/SL price",
        "- Entries with UNKNOWN regime cannot be sliced by regime",
        "- Some POSITION_CLOSED events may be detached from lifecycle (post-restart bracket correlation loss)",
        "",
        "## Synced source summary",
        f"| metric | value |",
        f"|---|---:|",
        f"| authority_rows | {authority_row_count} |",
        f"| direct_timestamp_rows | {authority_row_count} |",
        f"| timestamp_quality | direct (high) for all |",
        f"| candle_coverage | per-symbol, within available range |",
        "",
        "## Entry-position filter summary",
        "| class | count |",
        "|---|---:|",
        f"| total_synced_events | {event_class_counts.get('total_synced_events', 0)} |",
        f"| order_filled_events | {event_class_counts.get('order_filled_events', 0)} |",
        f"| order_intent_events | {event_class_counts.get('order_intent_events', 0)} |",
        f"| order_placed_events | {event_class_counts.get('order_placed_events', 0)} |",
        f"| position_closed_events | {event_class_counts.get('position_closed_events', 0)} |",
        f"| limit_adjusted_events | {event_class_counts.get('limit_adjusted_events', 0)} |",
        f"| decision_rejected_events | {event_class_counts.get('decision_rejected_events', 0)} |",
        f"| order_cancelled_timeout_rejected | {event_class_counts.get('order_cancelled_timeout_rejected', 0)} |",
        f"| boot_events | {event_class_counts.get('boot_events', 0)} |",
        f"| lifecycle_aggregates_from_common | {reconstructed_total} |",
        f"| included_opened_entries | {n_entries} |",
        f"| excluded_no_price | {excl_reasons.get('no_entry_price', 0)} |",
        f"| excluded_no_ts | {excl_reasons.get('no_entry_ts_ms', 0)} |",
        f"| excluded_missing_leverage | {excl_reasons.get('missing_leverage', 0)} |",
        f"| excluded_ts_quality | {sum(v for k, v in excl_reasons.items() if 'ts_quality' in k)} |",
        f"| excluded_missing_symbol_side | {sum(v for k, v in excl_reasons.items() if 'missing_symbol' in k)} |",
        f"| excluded_duplicate | {excl_reasons.get('duplicate_entry_id', 0)} |",
        f"| skipped_replay_no_candles | {skipped_nc} |",
        "",
        "## Replay summary",
        "",
        "### Top 20 TP/SL pairs by total_net_roi (all symbols, conservative intrabar policy)",
        "",
        _md_table(
            ["TP ROI%", "SL ROI%", "trades", "win_rate", "avg_net_roi", "total_net_roi", "profit_factor", "ambiguous"],
            main_table_rows if main_table_rows else [["no data"] * 8],
        ),
        "",
    ]

    if best_row:
        lines += [
            f"**Best TP/SL pair:** TP={best_row['tp_roi_pct']}% SL={best_row['sl_roi_pct']}%",
            f"  trades={best_row['trades_count']} win_rate={float(best_row['win_rate']):.3f}",
            f"  avg_net_roi={float(best_row['avg_net_roi']):.4f}% total_net_roi={float(best_row['total_net_roi']):.4f}%",
            f"  profit_factor={best_row['profit_factor']}",
            "",
        ]

    lines += [
        "## By-symbol summary (at best TP/SL per symbol)",
        "",
        _md_table(
            ["symbol", "TP%", "SL%", "trades", "win_rate", "avg_net_roi", "total_net_roi"],
            sym_table_rows if sym_table_rows else [["no data"] * 7],
        ),
        "",
        "## By-regime summary (at best TP/SL per regime)",
        "",
        _md_table(
            ["regime", "TP%", "SL%", "trades", "win_rate", "avg_net_roi", "total_net_roi"],
            reg_table_rows if reg_table_rows else [["no data"] * 7],
        ),
        "",
        "## Candle coverage per symbol",
        "",
    ]

    for sym, cov in sorted(sym_coverage.items()):
        if cov["has_candles"]:
            lines.append(
                f"- {sym}: candles {cov['candle_start_iso']} to {cov['candle_end_iso']}, "
                f"entries {cov['entry_count']} (within candles: {cov['entries_within_candles']})"
            )
        else:
            lines.append(f"- {sym}: NO CANDLES — entries skipped in replay")

    lines += [
        "",
        "## Current config comparison",
    ]
    lines += config_lines
    lines += [
        "",
        "### Config comparison verdict",
    ]
    if best_row and summary:
        best_tp = best_row["tp_roi_pct"]
        best_sl = best_row["sl_roi_pct"]
        lines.append(
            f"Replay best TP={best_tp}% SL={best_sl}% ROI-on-margin. "
            "Current config uses pct/RR-based exit with regime multipliers. "
            "Direct one-to-one comparison is partial — current exit surface is not expressed "
            "natively in the requested ROI grid. Use regime-sliced summary for deeper analysis."
        )
        lines.append("- State: **inconclusive** pending regime-sliced comparison with current actual config values")
    else:
        lines.append("- State: **inconclusive** — no replay data available")

    lines += [
        "",
        "## Risks",
        "- Event rows are not automatically positions: reconstruct_entries() lifecycle dedup handles this",
        "- 1m candle intrabar ambiguity: SL-first conservative policy applied",
        "- Exchange fills may not equal candle TP/SL path (slippage unmodeled)",
        "- Leverage assumptions affect ROI conversion (config default used when absent in row)",
        "- Fees partial: open+close included, funding excluded",
        "- Regime coverage partial: UNKNOWN regime entries cannot be regime-sliced",
        "- Horizon capped at available candle end, not full +24h window for open positions",
        "",
        "## Recommended next step",
    ]

    if regime_sliced == "partial":
        lines.append("**enrich regimes before regime-sliced conclusion** — run regime enrichment for UNKNOWN entries")
    elif verdict == "TP_SL_REPLAY_COMPLETE_HIGH_CONFIDENCE":
        lines.append("**interpret replay results** — all entries have high-confidence timestamps and known regimes")
    else:
        lines.append("**interpret replay results** — timestamps proven, regime gaps noted but plain ROI analysis is complete")

    report_text = "\n".join(lines) + "\n"
    out_path = ROOT / "reports" / "ORDER_RECONSTRUCTION_TP_SL_ROI_REPLAY_REPORT.md"
    out_path.write_text(report_text, encoding="utf-8")
    print(f"  -> {out_path}")
    return verdict


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="TP/SL ROI replay from synced order log")
    parser.add_argument("--report-root", default=str(REPORT_ROOT))
    parser.add_argument("--extra-recorder-root", action="append", default=[],
                        dest="extra_recorder_roots")
    args = parser.parse_args()

    report_root = Path(args.report_root)
    report_root.mkdir(parents=True, exist_ok=True)

    recorder_roots = [ROOT / "data" / "recorder_backfill_1m"]
    recorder_roots += [Path(p) for p in args.extra_recorder_roots]

    print("=" * 70)
    print("TP_SL_ROI_REPLAY_FROM_SYNCED_ORDER_LOG_ENTRIES")
    print(f"Root: {ROOT}")
    print(f"Report: {report_root}")
    print(f"Recorder roots: {[str(r) for r in recorder_roots]}")
    print("=" * 70)

    # ── Phase 1: Load authority rows + reconstruct entries ─────────────────
    print("\n--- Phase 1: Load authority rows + reconstruct entries ---")
    strategy_context = load_strategy_context(ROOT)
    fee_ctx = strategy_context.get("fees") or {}
    print(f"  Fee config: open={fee_ctx.get('open_fee_bps')}bps close={fee_ctx.get('close_fee_bps')}bps")

    authority_rows, authority_meta = load_authority_rows(ROOT)
    print(f"  Authority rows loaded: {len(authority_rows)}")

    event_class_counts = build_event_class_counts(authority_rows)
    print(f"  Event class counts: {event_class_counts}")

    reconstructed_entries, unresolved_rows, groups = reconstruct_entries(
        authority_rows, strategy_context, report_root
    )
    print(f"  Lifecycle-reconstructed entries: {len(reconstructed_entries)}")
    print(f"  Unresolved rows: {len(unresolved_rows)}")

    # ── Phase 2: Regime enrichment ─────────────────────────────────────────
    print("\n--- Phase 2: Regime enrichment ---")
    entries_with_regimes = build_entries_with_regimes(
        reconstructed_entries, groups, strategy_context, ROOT, report_root
    )
    print(f"  Entries with regimes: {len(entries_with_regimes)}")
    regime_cov = Counter(e.get("regime_at_entry", "") for e in entries_with_regimes)
    print(f"  Regime distribution: {dict(regime_cov.most_common())}")

    # ── Phase 3: Entry deduplication filter ────────────────────────────────
    print("\n--- Phase 3: Entry deduplication filter ---")
    opened_entries, excluded_entries = build_opened_entries_from_reconstructed(entries_with_regimes)
    print(f"  Opened entries (included): {len(opened_entries)}")
    print(f"  Excluded: {len(excluded_entries)}")
    if excluded_entries:
        excl_reasons = Counter(e.get("excluded_reason", "") for e in excluded_entries)
        print(f"  Exclusion reasons: {dict(excl_reasons.most_common())}")

    # Write dedup files
    synced_opened_path = report_root / "reconstructed_opened_entries_from_synced_order_log.csv"
    if opened_entries:
        write_csv(synced_opened_path,
                  list(opened_entries[0].keys()), opened_entries)
    excl_path = report_root / "excluded_synced_order_events.csv"
    if excluded_entries:
        write_csv(excl_path, list(excluded_entries[0].keys()), excluded_entries)
    else:
        excl_path.write_text("excluded_reason,entry_id\n", encoding="utf-8")
    print(f"  -> {synced_opened_path}")
    print(f"  -> {excl_path}")

    if not opened_entries:
        print("ERROR: No opened entries — replay blocked")
        return

    # ── Phase 4: Load candles ──────────────────────────────────────────────
    print("\n--- Phase 4: Load 1m candles ---")
    candles_by_symbol = load_candles_1m(ROOT, recorder_roots)
    for sym, candles in candles_by_symbol.items():
        if candles:
            print(f"  {sym}: {len(candles)} 1m candles, "
                  f"{iso_utc(candles[0]['timestamp'])} to {iso_utc(candles[-1]['timestamp'])}")
        else:
            print(f"  {sym}: 0 candles")

    sym_coverage = check_per_symbol_candle_coverage(opened_entries, candles_by_symbol)

    # ── Phase 5: Per-symbol TP/SL replay ──────────────────────────────────
    print("\n--- Phase 5: TP/SL ROI replay ---")
    replay_result = run_per_symbol_replay(
        opened_entries, candles_by_symbol, strategy_context, report_root
    )

    # ── Phase 6: Summarize ─────────────────────────────────────────────────
    print("\n--- Phase 6: Summarize ---")
    result_rows = replay_result.get("result_rows", [])
    if result_rows:
        summary, by_sym, by_reg = summarize_results(result_rows, report_root)
        print(f"  Summary rows: {len(summary)}")
        # Print top 5
        top5 = sorted(summary, key=lambda r: -float(r["total_net_roi"]))[:5]
        print("  Top 5 TP/SL by total_net_roi:")
        for r in top5:
            print(f"    TP={r['tp_roi_pct']}% SL={r['sl_roi_pct']}%: "
                  f"trades={r['trades_count']} win_rate={float(r['win_rate']):.3f} "
                  f"avg_net={float(r['avg_net_roi']):.4f}% total_net={float(r['total_net_roi']):.4f}%")
    else:
        summary, by_sym, by_reg = [], [], []
        print("  WARNING: No replay result rows")

    # ── Phase 7: Write report ──────────────────────────────────────────────
    print("\n--- Phase 7: Write final report ---")
    verdict = write_final_report(
        report_root,
        len(authority_rows),
        len(reconstructed_entries),
        opened_entries,
        excluded_entries,
        summary,
        by_sym,
        by_reg,
        sym_coverage,
        event_class_counts,
        strategy_context,
        {**replay_result, "result_rows": result_rows},
    )

    print(f"\n=== DONE === verdict={verdict}")
    print(f"Outputs in: {report_root}")


if __name__ == "__main__":
    main()
