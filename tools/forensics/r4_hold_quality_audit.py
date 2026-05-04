#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parents[2]
RUNTIME_DIR = BASE / "reports" / "forensics" / "aurora_runtime"
LOGS = BASE / "logs"
REPORTS = BASE / "reports" / "forensics" / "r4_hold_quality"
BAR_MS = 300_000
MEANINGFUL_EDGE_PCT = 0.15
STALE_HOLD_MINUTES = 180.0
PROTECT_CHECKPOINT_PCT = 0.50
GIVEBACK_CAP_SHARE = 0.50


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    if value in (None, "", "None", "null"):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def _median(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _pct(num: int, den: int) -> float | None:
    if den == 0:
        return None
    return num / den


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _price_series() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _iter_jsonl(LOGS / "mean_reversion" / "bars_300s.jsonl"):
        sym = str(row.get("symbol") or "")
        ts = _safe_int(row.get("ts_ms") or row.get("ts") or row.get("bar_close_ts"))
        close = _safe_float(row.get("close"))
        high = _safe_float(row.get("high"))
        low = _safe_float(row.get("low"))
        if sym and ts is not None and close is not None:
            out[sym].append(
                {
                    "ts_ms": ts,
                    "close": close,
                    "high": high if high is not None else close,
                    "low": low if low is not None else close,
                }
            )
    for path in sorted((LOGS / "ta_features").glob("*.jsonl")):
        for row in _iter_jsonl(path):
            sym = str(row.get("symbol") or path.stem)
            ts = _safe_int(row.get("ts_ms") or row.get("ts") or row.get("bar_close_ts"))
            close = _safe_float(row.get("close"))
            if sym and ts is not None and close is not None:
                out[sym].append(
                    {
                        "ts_ms": ts,
                        "close": close,
                        "high": close,
                        "low": close,
                    }
                )
    for sym in list(out.keys()):
        uniq: dict[int, dict[str, Any]] = {}
        for row in out[sym]:
            ts = row["ts_ms"]
            prev = uniq.get(ts)
            if prev is None:
                uniq[ts] = row
            else:
                uniq[ts] = {
                    "ts_ms": ts,
                    "close": row.get("close") if row.get("close") is not None else prev.get("close"),
                    "high": max(prev.get("high") or prev.get("close"), row.get("high") or row.get("close")),
                    "low": min(prev.get("low") or prev.get("close"), row.get("low") or row.get("close")),
                }
        out[sym] = sorted(uniq.values(), key=lambda r: r["ts_ms"])
    return out


def _price_at(series: list[dict[str, Any]], ts_ms: int | None) -> float | None:
    if not series or ts_ms is None:
        return None
    lo, hi = 0, len(series) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if series[mid]["ts_ms"] <= ts_ms:
            lo = mid
        else:
            hi = mid - 1
    row = series[lo]
    return float(row["close"]) if row["ts_ms"] <= ts_ms else None


def _slice_bars(series: list[dict[str, Any]], entry_ts: int | None, exit_ts: int | None) -> list[dict[str, Any]]:
    if not series or entry_ts is None or exit_ts is None or exit_ts < entry_ts:
        return []
    rows = [row for row in series if entry_ts <= row["ts_ms"] <= exit_ts]
    return rows


def _pnl_pct(direction: str, entry_price: float | None, price: float | None) -> float | None:
    if entry_price in (None, 0.0) or price is None or not direction:
        return None
    if direction.upper() == "SHORT":
        return ((entry_price - price) / entry_price) * 100.0
    if direction.upper() == "LONG":
        return ((price - entry_price) / entry_price) * 100.0
    return None


def _pnl_abs_from_pct(trade: dict[str, Any], pct: float | None) -> float | None:
    if pct is None:
        return None
    entry_price = _safe_float(trade.get("entry_price"))
    qty = _safe_float(trade.get("filled_qty")) or _safe_float(trade.get("placed_qty"))
    if entry_price in (None, 0.0) or qty in (None, 0.0):
        return None
    return (pct / 100.0) * entry_price * qty


def _trade_id(row: dict[str, Any]) -> str:
    return str(row.get("trade_id") or row.get("close_rid") or row.get("parent_rid") or "")


@dataclass
class Segment:
    symbol: str
    start_ts_ms: int
    end_ts_ms: int
    regime_label: str
    confidence: float | None


def load_segments() -> dict[str, list[Segment]]:
    out: dict[str, list[Segment]] = defaultdict(list)
    with (RUNTIME_DIR / "regime_segments.csv").open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            symbol = str(row.get("symbol") or "")
            start_ts = _safe_int(row.get("regime_start_ts_ms"))
            end_ts = _safe_int(row.get("regime_end_ts_ms"))
            if not symbol or start_ts is None or end_ts is None:
                continue
            out[symbol].append(
                Segment(
                    symbol=symbol,
                    start_ts_ms=start_ts,
                    end_ts_ms=end_ts,
                    regime_label=str(row.get("regime_label") or ""),
                    confidence=_safe_float(row.get("confidence")),
                )
            )
    for rows in out.values():
        rows.sort(key=lambda row: row.start_ts_ms)
    return out


def _first_regime_change(segments: list[Segment], regime_at_entry: str, entry_ts: int | None, exit_ts: int | None) -> tuple[int | None, str | None, float | None]:
    if entry_ts is None or exit_ts is None:
        return None, None, None
    for seg in segments:
        if seg.start_ts_ms <= entry_ts:
            continue
        if seg.start_ts_ms > exit_ts:
            break
        if seg.regime_label != regime_at_entry:
            return seg.start_ts_ms, seg.regime_label, seg.confidence
    return None, None, None


def main() -> int:
    ap = argparse.ArgumentParser(description="R4 downstream hold-quality audit")
    ap.add_argument("--out-dir", default=str(REPORTS))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prices = _price_series()
    segments = load_segments()

    with (RUNTIME_DIR / "trades_master.csv").open("r", encoding="utf-8", newline="") as fh:
        trades = list(csv.DictReader(fh))

    master_rows: list[dict[str, Any]] = []
    counterfactual_rows: list[dict[str, Any]] = []
    casebook_buckets: dict[str, list[str]] = defaultdict(list)

    for trade in trades:
        trade_id = _trade_id(trade)
        symbol = str(trade.get("symbol") or "")
        direction = str(trade.get("direction") or "").upper()
        entry_ts = _safe_int(trade.get("entry_ts_ms"))
        exit_ts = _safe_int(trade.get("exit_ts_ms"))
        hold_minutes = ((_safe_int(trade.get("hold_ms")) or 0) / 60000.0) if trade.get("hold_ms") else None
        entry_price = _safe_float(trade.get("entry_price"))
        exit_price = _safe_float(trade.get("exit_price"))
        realized_pnl = _safe_float(trade.get("realized_pnl_abs"))
        realized_pnl_pct = _safe_float(trade.get("realized_pnl_pct"))
        mfe_pct_existing = _safe_float(trade.get("mfe_pct"))
        mae_pct_existing = _safe_float(trade.get("mae_pct"))
        regime_at_entry = str(trade.get("regime_at_entry") or "")
        regime_conf_at_entry = _safe_float(trade.get("regime_confidence_at_entry"))
        exit_reason = str(trade.get("exit_reason") or "")
        close_path_source = str(trade.get("close_path_source") or "")
        anomaly_flags = str(trade.get("anomaly_flags") or "")

        bars = _slice_bars(prices.get(symbol, []), entry_ts, exit_ts)
        ambiguity: list[str] = []
        if not bars:
            ambiguity.append("price_path_missing")
        if entry_price in (None, 0.0):
            ambiguity.append("entry_price_missing")
        if direction not in {"LONG", "SHORT"}:
            ambiguity.append("direction_missing")

        reported_regime_changed = str(trade.get("regime_changed_during_trade") or "").lower() == "true"
        first_regime_change_ts, regime_after_change, regime_conf_after_change = _first_regime_change(
            segments.get(symbol, []), regime_at_entry, entry_ts, exit_ts
        )
        regime_changed = reported_regime_changed
        if not regime_changed:
            first_regime_change_ts = None
            regime_after_change = None
            regime_conf_after_change = None

        mfe_price = None
        mae_price = None
        mfe_pct_proxy = mfe_pct_existing
        mae_pct_proxy = mae_pct_existing
        mfe_ts = None
        mae_ts = None
        first_positive_ts = None
        first_positive_pct = None

        if bars and entry_price not in (None, 0.0) and direction in {"LONG", "SHORT"}:
            if direction == "SHORT":
                mfe_row = min(bars, key=lambda row: row["low"])
                mae_row = max(bars, key=lambda row: row["high"])
                mfe_price = float(mfe_row["low"])
                mae_price = float(mae_row["high"])
            else:
                mfe_row = max(bars, key=lambda row: row["high"])
                mae_row = min(bars, key=lambda row: row["low"])
                mfe_price = float(mfe_row["high"])
                mae_price = float(mae_row["low"])
            mfe_ts = mfe_row["ts_ms"]
            mae_ts = mae_row["ts_ms"]
            mfe_pct_proxy = _pnl_pct(direction, entry_price, mfe_price)
            mae_pct_proxy = abs(_pnl_pct(direction, entry_price, mae_price) or 0.0)
            for row in bars:
                row_price = row["high"] if direction == "LONG" else row["low"]
                pct = _pnl_pct(direction, entry_price, row_price)
                if pct is not None and pct >= MEANINGFUL_EDGE_PCT:
                    first_positive_ts = row["ts_ms"]
                    first_positive_pct = pct
                    break

        time_to_mfe_minutes = ((mfe_ts - entry_ts) / 60000.0) if mfe_ts is not None and entry_ts is not None else None
        time_from_mfe_to_exit_minutes = ((exit_ts - mfe_ts) / 60000.0) if mfe_ts is not None and exit_ts is not None else None
        mfe_pnl_proxy = _pnl_abs_from_pct(trade, mfe_pct_proxy)
        mae_pnl_proxy = _pnl_abs_from_pct(trade, -mae_pct_proxy if mae_pct_proxy is not None else None)
        ever_positive_edge = bool(mfe_pct_proxy is not None and mfe_pct_proxy >= MEANINGFUL_EDGE_PCT)
        protectable_flag = ever_positive_edge and (mfe_pct_proxy or 0.0) >= max(MEANINGFUL_EDGE_PCT, PROTECT_CHECKPOINT_PCT)
        peak_giveback_abs = (mfe_pnl_proxy - realized_pnl) if mfe_pnl_proxy is not None and realized_pnl is not None else None
        peak_giveback_ratio = None
        if mfe_pnl_proxy not in (None, 0.0) and peak_giveback_abs is not None:
            peak_giveback_ratio = peak_giveback_abs / abs(mfe_pnl_proxy)

        stale_trade_flag = bool(
            hold_minutes is not None
            and hold_minutes >= STALE_HOLD_MINUTES
            and ((mfe_pct_proxy is None) or (mfe_pct_proxy < PROTECT_CHECKPOINT_PCT))
        )

        regime_change_pnl_pct = _pnl_pct(direction, entry_price, _price_at(prices.get(symbol, []), first_regime_change_ts)) if first_regime_change_ts else None
        regime_relevant = bool(
            regime_changed
            and first_regime_change_ts is not None
            and exit_ts is not None
            and (exit_ts - first_regime_change_ts) >= 2 * BAR_MS
            and regime_change_pnl_pct is not None
            and realized_pnl_pct is not None
            and (regime_change_pnl_pct - realized_pnl_pct) >= 0.20
        )

        exit_path_damaged = bool(
            exit_reason == "POSITION_CLOSED_DETECTED"
            or "unavailable" in str(trade.get("excursion_source") or "")
            or "[]" != anomaly_flags and anomaly_flags != ""
            or entry_price in (None, 0.0)
            or exit_price in (None, 0.0)
        )

        primary_bucket = "MIXED_OR_UNPROVEN"
        if exit_path_damaged and (realized_pnl or 0.0) <= 0:
            primary_bucket = "EXIT_PATH_DAMAGED"
        elif (realized_pnl or 0.0) < 0 and not ever_positive_edge:
            primary_bucket = "IMMEDIATE_FAILURE"
        elif regime_relevant and (realized_pnl or 0.0) <= 0:
            primary_bucket = "REGIME_DEGRADED_WHILE_OPEN"
        elif stale_trade_flag and (realized_pnl or 0.0) <= 0:
            primary_bucket = "STALE_DEAD_TRADE"
        elif ever_positive_edge and peak_giveback_ratio is not None and peak_giveback_ratio >= 0.50:
            primary_bucket = "EDGE_EARNED_THEN_GAVE_BACK"

        breakeven_after_edge = None
        protect_after_checkpoint = None
        dead_trade_timeout = None
        giveback_cap = None
        regime_degradation_exit = None
        notes: list[str] = []

        if ever_positive_edge and (realized_pnl or 0.0) < 0:
            breakeven_after_edge = 0.0
            notes.append("breakeven_after_edge")

        if protectable_flag and mfe_pnl_proxy is not None:
            protect_after_checkpoint = max(0.0, 0.25 * mfe_pnl_proxy)
            notes.append("checkpoint_protect")

        if hold_minutes is not None and hold_minutes > STALE_HOLD_MINUTES and entry_price not in (None, 0.0):
            timeout_ts = min((entry_ts or 0) + int(STALE_HOLD_MINUTES * 60000), exit_ts or 0)
            timeout_price = _price_at(prices.get(symbol, []), timeout_ts)
            timeout_pct = _pnl_pct(direction, entry_price, timeout_price)
            dead_trade_timeout = _pnl_abs_from_pct(trade, timeout_pct)
            notes.append("dead_trade_timeout")

        if ever_positive_edge and mfe_pnl_proxy is not None:
            giveback_cap = max(realized_pnl or 0.0, mfe_pnl_proxy * GIVEBACK_CAP_SHARE)
            notes.append("giveback_cap")

        if regime_relevant and first_regime_change_ts is not None and entry_price not in (None, 0.0):
            change_price = _price_at(prices.get(symbol, []), first_regime_change_ts)
            change_pct = _pnl_pct(direction, entry_price, change_price)
            regime_degradation_exit = _pnl_abs_from_pct(trade, change_pct)
            notes.append("regime_change_exit")

        proxies = [
            value for value in (
                breakeven_after_edge,
                protect_after_checkpoint,
                dead_trade_timeout,
                giveback_cap,
                regime_degradation_exit,
            )
            if value is not None
        ]
        best_bounded_proxy = max(proxies) if proxies else None
        improvement_vs_realized = (best_bounded_proxy - realized_pnl) if best_bounded_proxy is not None and realized_pnl is not None else None
        confidence_of_proxy = "LOW"
        if bars and entry_price not in (None, 0.0):
            confidence_of_proxy = "MEDIUM"
        if bars and first_regime_change_ts is not None and mfe_ts is not None:
            confidence_of_proxy = "HIGH"

        master_rows.append(
            {
                "trade_id": trade_id,
                "lifecycle_ref": str(trade.get("close_rid") or trade.get("parent_rid") or ""),
                "symbol": symbol,
                "strategy_id": str(trade.get("strategy_id") or ""),
                "side": direction,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "hold_minutes": hold_minutes,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "realized_pnl": realized_pnl,
                "realized_pnl_pct": realized_pnl_pct,
                "regime_at_entry": regime_at_entry,
                "regime_confidence_at_entry": regime_conf_at_entry,
                "regime_changed_while_open_flag": regime_changed,
                "first_regime_change_ts": first_regime_change_ts,
                "first_regime_change_label": regime_after_change,
                "first_regime_change_confidence": regime_conf_after_change,
                "mfe_price_proxy": mfe_price,
                "mfe_pnl_proxy": mfe_pnl_proxy,
                "mae_price_proxy": mae_price,
                "mae_pnl_proxy": mae_pnl_proxy,
                "time_to_mfe_minutes": time_to_mfe_minutes,
                "time_from_mfe_to_exit_minutes": time_from_mfe_to_exit_minutes,
                "first_meaningful_edge_ts": first_positive_ts,
                "first_meaningful_edge_pct": first_positive_pct,
                "peak_giveback_abs": peak_giveback_abs,
                "peak_giveback_ratio": peak_giveback_ratio,
                "ever_positive_edge_flag": ever_positive_edge,
                "protectable_flag": protectable_flag,
                "stale_trade_flag": stale_trade_flag,
                "primary_failure_bucket": primary_bucket,
                "ambiguity_flag": "|".join(ambiguity),
            }
        )

        if primary_bucket in {"EDGE_EARNED_THEN_GAVE_BACK", "STALE_DEAD_TRADE", "REGIME_DEGRADED_WHILE_OPEN"} and proxies:
            counterfactual_rows.append(
                {
                    "trade_id": trade_id,
                    "primary_failure_bucket": primary_bucket,
                    "realized_pnl": realized_pnl,
                    "breakeven_after_edge_pnl_proxy": breakeven_after_edge,
                    "protect_after_checkpoint_pnl_proxy": protect_after_checkpoint,
                    "dead_trade_timeout_pnl_proxy": dead_trade_timeout,
                    "giveback_cap_pnl_proxy": giveback_cap,
                    "regime_degradation_exit_pnl_proxy": regime_degradation_exit,
                    "best_bounded_proxy": best_bounded_proxy,
                    "improvement_vs_realized": improvement_vs_realized,
                    "confidence_of_proxy": confidence_of_proxy,
                    "notes": ",".join(notes),
                }
            )

        note = (
            f"- `{trade_id}` `{symbol}` `{direction or 'UNKNOWN'}` pnl=`{realized_pnl}` hold_min=`{hold_minutes}` "
            f"mfe=`{mfe_pnl_proxy}` giveback=`{peak_giveback_abs}` regime_change=`{regime_changed}` "
            f"exit=`{exit_reason}` ambiguity=`{'|'.join(ambiguity) or 'none'}`"
        )
        casebook_buckets[primary_bucket].append(note)

    with (out_dir / "hold_quality_master.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(master_rows[0].keys()) if master_rows else [])
        writer.writeheader()
        writer.writerows(master_rows)

    with (out_dir / "bounded_counterfactuals.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(counterfactual_rows[0].keys()) if counterfactual_rows else [])
        writer.writeheader()
        writer.writerows(counterfactual_rows)

    summary_rows: list[dict[str, Any]] = []
    group_defs: list[tuple[str, str, list[dict[str, Any]]]] = [
        ("overall", "ALL", master_rows),
    ]
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in master_rows:
        by_symbol[row["symbol"]].append(row)
        by_regime[row["regime_at_entry"]].append(row)
    for symbol, rows in sorted(by_symbol.items()):
        group_defs.append(("symbol", symbol, rows))
    for regime, rows in sorted(by_regime.items()):
        group_defs.append(("regime", regime, rows))

    for group_type, group_value, rows in group_defs:
        losers = [row for row in rows if (row["realized_pnl"] or 0.0) < 0]
        summary_rows.append(
            {
                "group_type": group_type,
                "group_value": group_value,
                "trade_count": len(rows),
                "loser_count": len(losers),
                "loser_with_positive_edge_count": sum(1 for row in losers if row["ever_positive_edge_flag"]),
                "avg_mfe_proxy": _mean([row["mfe_pnl_proxy"] for row in rows]),
                "avg_peak_giveback_ratio": _mean([row["peak_giveback_ratio"] for row in rows]),
                "avg_hold_minutes": _mean([row["hold_minutes"] for row in rows]),
                "pct_regime_changed_while_open": _pct(sum(1 for row in rows if row["regime_changed_while_open_flag"]), len(rows)),
                "pct_immediate_failure": _pct(sum(1 for row in rows if row["primary_failure_bucket"] == "IMMEDIATE_FAILURE"), len(rows)),
                "pct_edge_earned_then_gave_back": _pct(sum(1 for row in rows if row["primary_failure_bucket"] == "EDGE_EARNED_THEN_GAVE_BACK"), len(rows)),
                "pct_stale_dead_trade": _pct(sum(1 for row in rows if row["primary_failure_bucket"] == "STALE_DEAD_TRADE"), len(rows)),
                "pct_regime_degraded_while_open": _pct(sum(1 for row in rows if row["primary_failure_bucket"] == "REGIME_DEGRADED_WHILE_OPEN"), len(rows)),
                "pct_exit_path_damaged": _pct(sum(1 for row in rows if row["primary_failure_bucket"] == "EXIT_PATH_DAMAGED"), len(rows)),
                "net_realized_pnl": sum(row["realized_pnl"] or 0.0 for row in rows),
            }
        )

    with (out_dir / "hold_quality_summary.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()) if summary_rows else [])
        writer.writeheader()
        writer.writerows(summary_rows)

    bucket_order = [
        "IMMEDIATE_FAILURE",
        "EDGE_EARNED_THEN_GAVE_BACK",
        "STALE_DEAD_TRADE",
        "REGIME_DEGRADED_WHILE_OPEN",
        "EXIT_PATH_DAMAGED",
        "MIXED_OR_UNPROVEN",
    ]
    casebook_lines = ["# Hold Quality Casebook", ""]
    for bucket in bucket_order:
        casebook_lines.append(f"## {bucket}")
        for note in casebook_buckets.get(bucket, []):
            casebook_lines.append(note)
        casebook_lines.append("")
    (out_dir / "hold_quality_casebook.md").write_text("\n".join(casebook_lines), encoding="utf-8")

    bucket_counts = Counter(row["primary_failure_bucket"] for row in master_rows)
    losers = [row for row in master_rows if (row["realized_pnl"] or 0.0) < 0]
    edge_losers = [row for row in losers if row["ever_positive_edge_flag"]]
    protectable_loss_share = None
    if losers:
        total_loss_abs = abs(sum(row["realized_pnl"] or 0.0 for row in losers))
        edge_loss_abs = abs(sum(row["realized_pnl"] or 0.0 for row in edge_losers))
        protectable_loss_share = (edge_loss_abs / total_loss_abs) if total_loss_abs else None

    regime_changed_rows = [row for row in master_rows if row["regime_changed_while_open_flag"]]
    regime_changed_losers = [row for row in regime_changed_rows if (row["realized_pnl"] or 0.0) < 0]
    summary_overall = next((row for row in summary_rows if row["group_type"] == "overall"), None)
    best_proxy_total = sum((row["best_bounded_proxy"] or 0.0) - (row["realized_pnl"] or 0.0) for row in counterfactual_rows if row["improvement_vs_realized"] is not None)

    audit_lines = [
        "# R4 - Downstream Hold-Quality Audit",
        "",
        "## Problem Framing",
        "This package tests whether meaningful loss is being created after entry through weak holding, degradation handling, or exit behavior rather than primarily at entry selection time.",
        "",
        "## Facts",
        f"- Realized trades analyzed: `{len(master_rows)}`.",
        f"- Losing trades: `{len(losers)}`.",
        f"- Losing trades with positive edge proxy: `{len(edge_losers)}`.",
        f"- Failure-bucket distribution: `{dict(bucket_counts)}`.",
        f"- Regime changed while open on `{len(regime_changed_rows)}` trades; `{len(regime_changed_losers)}` of those were losers.",
        f"- Bounded counterfactual rows produced: `{len(counterfactual_rows)}`.",
        "",
        "## Inferences",
    ]
    if len(edge_losers) >= len(losers) / 3:
        audit_lines.append("- A material share of losses appear to be created after entry rather than at pure thesis inception.")
    else:
        audit_lines.append("- Immediate thesis failure remains significant, but it is not the only downstream loss contour.")
    if protectable_loss_share is not None:
        audit_lines.append(f"- Approximate gross-loss share from losers that once had positive edge: `{protectable_loss_share:.3%}`.")
    audit_lines.extend(
        [
            "",
            "## Assumptions",
            f"- Meaningful positive edge proxy is defined as MFE >= `{MEANINGFUL_EDGE_PCT:.2f}%`.",
            f"- Stale-trade timeout proxy uses a `{STALE_HOLD_MINUTES:.0f}` minute hold cap.",
            f"- Giveback-cap proxy preserves `{GIVEBACK_CAP_SHARE:.0%}` of peak favorable edge.",
            "- All excursion and counterfactual values are bar-based proxies, not guaranteed executable fills.",
            "",
            "## Unknowns",
            "- Some trades have incomplete lineage or missing price fields, especially `POSITION_CLOSED_DETECTED` rows.",
            "- The audit does not prove exact executable exit prices for the bounded counterfactuals.",
            "",
            "## Trade Failure-Bucket Distribution",
        ]
    )
    for bucket in bucket_order:
        audit_lines.append(f"- `{bucket}`: `{bucket_counts.get(bucket, 0)}`")
    audit_lines.extend(
        [
            "",
            "## Positive-Edge Surrender Analysis",
            f"- Losers with positive edge proxy: `{len(edge_losers)}/{len(losers)}`.",
            f"- Average peak giveback ratio: `{_mean([row['peak_giveback_ratio'] for row in edge_losers])}`.",
            f"- Median peak giveback ratio: `{_median([row['peak_giveback_ratio'] for row in edge_losers])}`.",
            "",
            "## Dead-Trade Analysis",
            f"- Trades flagged stale/dead: `{sum(1 for row in master_rows if row['stale_trade_flag'])}`.",
            f"- Average hold minutes overall: `{summary_overall['avg_hold_minutes'] if summary_overall else None}`.",
            f"- Long-hold bucket (`>{STALE_HOLD_MINUTES:.0f}m`) count: `{sum(1 for row in master_rows if (row['hold_minutes'] or 0.0) >= STALE_HOLD_MINUTES)}`.",
            "",
            "## Regime-Change-While-Open Analysis",
            f"- Regime change while open rate: `{summary_overall['pct_regime_changed_while_open'] if summary_overall else None}`.",
            f"- Trades classified `REGIME_DEGRADED_WHILE_OPEN`: `{bucket_counts.get('REGIME_DEGRADED_WHILE_OPEN', 0)}`.",
            "- Regime change appears relevant only when it happens with enough time remaining before exit and the trade is meaningfully worse by final close than at the change timestamp.",
            "",
            "## Exit-Path Damage Analysis",
            f"- Trades classified `EXIT_PATH_DAMAGED`: `{bucket_counts.get('EXIT_PATH_DAMAGED', 0)}`.",
            "- Exit-path damage is driven mainly by `POSITION_CLOSED_DETECTED`, missing price lineage, or unavailable excursion surfaces.",
            "",
            "## Bounded Lifecycle-Opportunity Verdict",
            f"- Aggregate improvement from best bounded proxies across covered trades: `{best_proxy_total}`.",
            "- This supports whether a future lifecycle package is worth testing, not a direct policy deployment claim.",
        ]
    )

    if bucket_counts.get("EDGE_EARNED_THEN_GAVE_BACK", 0) >= 4 or bucket_counts.get("STALE_DEAD_TRADE", 0) >= 4:
        next_package = "shadow hold/protect policy package"
    elif bucket_counts.get("REGIME_DEGRADED_WHILE_OPEN", 0) >= 4:
        next_package = "regime-degradation exit audit"
    elif bucket_counts.get("EXIT_PATH_DAMAGED", 0) >= 4:
        next_package = "execution close-path cleanup"
    else:
        next_package = "stale-trade timeout package"

    audit_lines.extend(
        [
            "",
            "## Recommendation",
            f"- Exact next package: `{next_package}`.",
        ]
    )
    (out_dir / "R4_HOLD_QUALITY_AUDIT.md").write_text("\n".join(audit_lines), encoding="utf-8")

    completion_lines = [
        "# R4 Completion Report",
        "",
        "## Proven",
        "- The package reconstructs per-trade hold quality, excursion proxies, regime-change timing, and bounded containment proxies for the realized trade set.",
        f"- `{len(edge_losers)}` losing trades had positive edge before closing red.",
        f"- `{bucket_counts.get('EDGE_EARNED_THEN_GAVE_BACK', 0)}` trades are primarily classified as edge-earned-then-gave-back.",
        f"- `{bucket_counts.get('STALE_DEAD_TRADE', 0)}` trades are primarily classified as stale/dead holds.",
        "",
        "## Unproven",
        "- Exact executable prices for any bounded containment proxy.",
        "- Whether a future lifecycle policy would preserve alpha after fees and live slippage.",
        "",
        "## Next Justified Package",
        f"- `{next_package}`",
        "",
        "## Still Not Justified",
        "- Entry-threshold retuning is not justified from this package alone.",
        "- Horizon changes are not justified.",
        "- Regime-detector rewrites are not justified.",
    ]
    (out_dir / "R4_COMPLETION_REPORT.md").write_text("\n".join(completion_lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "trades": len(master_rows),
                "losers": len(losers),
                "edge_losers": len(edge_losers),
                "bucket_counts": dict(bucket_counts),
                "next_package": next_package,
                "out_dir": str(out_dir),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
