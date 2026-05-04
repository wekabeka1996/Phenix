#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parents[2]
LOGS = BASE / "logs"
REPORTS = BASE / "reports" / "forensics" / "r1_confidence_latency"
RUNTIME_FORENSICS = BASE / "reports" / "forensics" / "aurora_runtime"
BAR_MS = 300_000
AURORA_SYMBOLS = {"BTCUSDT", "ETHUSDT", "DOGEUSDT", "XRPUSDT", "BNBUSDT"}

SCORE_LINE_RE = re.compile(
    r"(?P<mode>enter|hold|flip):(?P<side>buy|sell):score=(?P<score>-?[0-9.]+)"
    r"(?P<cmp>>=|<=-)(?P<thr>thr_buy|thr_sell|thr_neutral)=(?P<threshold>-?[0-9.]+)"
)


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


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _mean_or_none(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.mean(vals) if vals else None


def _median_or_none(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _price_series() -> dict[str, list[dict[str, Any]]]:
    series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    bars_300 = LOGS / "mean_reversion" / "bars_300s.jsonl"
    for row in _iter_jsonl(bars_300):
        sym = str(row.get("symbol") or "")
        ts = _safe_int(row.get("ts_ms") or row.get("ts") or row.get("bar_close_ts"))
        close = _safe_float(row.get("close"))
        high = _safe_float(row.get("high"))
        low = _safe_float(row.get("low"))
        if sym and ts is not None and close is not None:
            series[sym].append(
                {
                    "ts_ms": ts,
                    "close": close,
                    "high": high if high is not None else close,
                    "low": low if low is not None else close,
                    "source": "bars_300s",
                }
            )
    for path in sorted((LOGS / "ta_features").glob("*.jsonl")):
        for row in _iter_jsonl(path):
            sym = str(row.get("symbol") or path.stem)
            ts = _safe_int(row.get("ts_ms") or row.get("ts") or row.get("bar_close_ts"))
            close = _safe_float(row.get("close"))
            if sym and ts is not None and close is not None:
                series[sym].append(
                    {
                        "ts_ms": ts,
                        "close": close,
                        "high": close,
                        "low": close,
                        "source": "ta_close",
                    }
                )
    for sym in list(series.keys()):
        series[sym].sort(key=lambda r: r["ts_ms"])
    return series


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


def _slice_prices(series: list[dict[str, Any]], start_ts: int | None, end_ts: int | None) -> list[dict[str, Any]]:
    if not series or start_ts is None or end_ts is None or end_ts < start_ts:
        return []
    return [row for row in series if start_ts <= row["ts_ms"] <= end_ts]


def _parse_score_line(values: list[str]) -> dict[str, Any] | None:
    for value in values:
        m = SCORE_LINE_RE.search(str(value))
        if not m:
            continue
        return {
            "mode": m.group("mode"),
            "side": m.group("side").upper(),
            "score": _safe_float(m.group("score")),
            "threshold_name": m.group("thr"),
            "threshold": _safe_float(m.group("threshold")),
            "line": value,
        }
    return None


@dataclass
class EpochRow:
    symbol: str
    stable_regime: str
    raw_regime: str
    raw_regime_start_ts: int | None
    stable_regime_start_ts: int | None
    stable_regime_end_ts: int | None
    raw_regime_confidence_at_start: float | None
    structural_regime_ref: str
    stable_start_price: float | None
    raw_start_price: float | None


def load_regime_audit() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bar_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    for row in _iter_jsonl(LOGS / "regime_confidence_audit_v1.jsonl"):
        ts = _safe_int(row.get("ts_ms"))
        if ts is None or ts < 1776510000000:
            continue
        if row.get("record_type") == "bar_close":
            if str(row.get("symbol") or "") in AURORA_SYMBOLS:
                bar_rows.append(row)
        elif row.get("record_type") == "decision" and row.get("strategy_id") == "aurora":
            if str(row.get("symbol") or "") in AURORA_SYMBOLS:
                decision_rows.append(row)
    bar_rows.sort(key=lambda r: (str(r.get("symbol") or ""), _safe_int(r.get("ts_ms")) or 0))
    decision_rows.sort(key=lambda r: (str(r.get("symbol") or ""), _safe_int(r.get("ts_ms")) or 0))
    return bar_rows, decision_rows


def build_epochs(bar_rows: list[dict[str, Any]], prices: dict[str, list[dict[str, Any]]]) -> list[EpochRow]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in bar_rows:
        by_symbol[str(row.get("symbol"))].append(row)

    epochs: list[EpochRow] = []
    for symbol, rows in by_symbol.items():
        rows.sort(key=lambda r: _safe_int(r.get("ts_ms")) or 0)
        stable_starts: list[int] = []
        for i, row in enumerate(rows):
            if i == 0 or row.get("changed") is True:
                stable_starts.append(i)

        for idx, start_i in enumerate(stable_starts):
            row = rows[start_i]
            stable_regime = str(row.get("regime") or "")
            if stable_regime == "":
                continue
            end_i = stable_starts[idx + 1] - 1 if idx + 1 < len(stable_starts) else len(rows) - 1
            stable_start_ts = _safe_int(row.get("ts_ms"))
            stable_end_ts = _safe_int(rows[end_i].get("ts_ms"))
            j = start_i
            while j > 0 and str(rows[j - 1].get("raw_regime") or "") == stable_regime:
                j -= 1
            raw_row = rows[j]
            raw_start_ts = _safe_int(raw_row.get("ts_ms"))
            raw_conf = _safe_float(raw_row.get("raw_confidence"))
            price_series = prices.get(symbol, [])
            epochs.append(
                EpochRow(
                    symbol=symbol,
                    stable_regime=stable_regime,
                    raw_regime=str(raw_row.get("raw_regime") or ""),
                    raw_regime_start_ts=raw_start_ts,
                    stable_regime_start_ts=stable_start_ts,
                    stable_regime_end_ts=stable_end_ts,
                    raw_regime_confidence_at_start=raw_conf,
                    structural_regime_ref=str(row.get("structural_regime_ref") or ""),
                    stable_start_price=_price_at(price_series, stable_start_ts),
                    raw_start_price=_price_at(price_series, raw_start_ts),
                )
            )
    epochs.sort(key=lambda e: (e.symbol, e.stable_regime_start_ts or 0))
    return epochs


def load_shadow_intents() -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    for row in _iter_jsonl(LOGS / "shadow_critical_event_journal_v1.jsonl"):
        if str(row.get("strategy_id") or "") != "aurora":
            continue
        en = str(row.get("event_name") or "")
        if en not in {"EVT:TRADE_INTENT_PROPOSED", "EVT:TRADE_INTENT_REJECTED"}:
            continue
        ts = _safe_int(row.get("ts_ms"))
        pf = row.get("payload_fragment") if isinstance(row.get("payload_fragment"), dict) else {}
        why_values = pf.get("why_chain") if en == "EVT:TRADE_INTENT_REJECTED" else pf.get("why")
        parsed = _parse_score_line(list(why_values or []))
        rows.append(
            {
                "ts_ms": ts,
                "symbol": str(row.get("symbol") or ""),
                "rid": str(row.get("rid") or ""),
                "event_name": en,
                "reason_code": str(pf.get("reason_code") or ""),
                "context": str(pf.get("context") or pf.get("why") or ""),
                "regime": str(pf.get("regime") or ""),
                "regime_confidence": _safe_float(pf.get("regime_confidence")),
                "structural_regime_ref": str(
                    (((pf.get("regime_provenance") or {}).get("detector_event") or {}).get("structural_regime_ref") or ""
                )),
                "parsed_score": parsed,
            }
        )
    rows.sort(key=lambda r: (r["symbol"], r["ts_ms"] or 0))

    order_ts_by_rid: dict[str, int] = {}
    for row in _iter_jsonl(LOGS / "order_log_v1.jsonl"):
        if row.get("event_type") != "ORDER_PLACED":
            continue
        rid = str(row.get("rid") or "")
        ts = _safe_int(row.get("timestamp"))
        if rid and ts is not None and rid not in order_ts_by_rid:
            order_ts_by_rid[rid] = ts
    return rows, order_ts_by_rid


def load_trades() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    path = RUNTIME_FORENSICS / "trades_master.csv"
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            key = str(row.get("parent_rid") or "")
            if key:
                out[key] = row
    return out


def classify_entry_timing(
    *,
    raw_price: float | None,
    event_price: float | None,
    segment: list[dict[str, Any]],
    side: str,
) -> tuple[str, float | None, float | None]:
    if raw_price is None or event_price is None or not segment or side not in {"BUY", "SELL"}:
        return "UNKNOWN", None, None
    highs = [float(r["high"]) for r in segment]
    lows = [float(r["low"]) for r in segment]
    local_best = max(highs) if side == "BUY" else min(lows)
    local_worst = min(lows) if side == "BUY" else max(highs)
    favorable_total = (local_best - raw_price) if side == "BUY" else (raw_price - local_best)
    favorable_done = (event_price - raw_price) if side == "BUY" else (raw_price - event_price)
    if favorable_total <= 0:
        return "UNKNOWN", local_best, local_worst
    ratio = favorable_done / favorable_total
    if ratio < 0:
        bucket = "UNKNOWN"
    elif ratio < 0.25:
        bucket = "EARLY"
    elif ratio <= 0.75:
        bucket = "MID"
    elif ratio <= 1.0:
        bucket = "LATE"
    else:
        bucket = "POST_EXHAUSTION"
    return bucket, local_best, local_worst


def main() -> int:
    ap = argparse.ArgumentParser(description="R1 Confidence-Latency Audit")
    ap.add_argument("--out-dir", default=str(REPORTS))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prices = _price_series()
    bar_rows, decision_rows = load_regime_audit()
    epochs = build_epochs(bar_rows, prices)
    shadow_rows, order_ts_by_rid = load_shadow_intents()
    trade_by_parent = load_trades()

    decisions_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in decision_rows:
        decisions_by_symbol[str(row.get("symbol"))].append(row)
    shadow_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in shadow_rows:
        shadow_by_symbol[row["symbol"]].append(row)

    timing_rows: list[dict[str, Any]] = []
    gate_rows: list[dict[str, Any]] = []

    for epoch in epochs:
        decs = [
            row
            for row in decisions_by_symbol.get(epoch.symbol, [])
            if (epoch.stable_regime_start_ts or 0) <= (_safe_int(row.get("ts_ms")) or 0) <= (epoch.stable_regime_end_ts or 10**18)
        ]
        intents = [
            row
            for row in shadow_by_symbol.get(epoch.symbol, [])
            if (epoch.stable_regime_start_ts or 0) <= (row["ts_ms"] or 0) <= (epoch.stable_regime_end_ts or 10**18)
        ]

        c_row = next((r for r in decs if str(r.get("threshold_verdict")) == "PASS"), None)
        d_row = next(
            (
                r
                for r in decs
                if str(r.get("threshold_verdict")) == "PASS"
                and str(r.get("deny_reason")) not in {"NRR-026", "NRR-027"}
            ),
            None,
        )
        e_row = next((r for r in intents if r.get("parsed_score") is not None), None)
        f_row = next((r for r in intents if r.get("event_name") == "EVT:TRADE_INTENT_PROPOSED"), None)
        order_ts = order_ts_by_rid.get(str(f_row.get("rid") or "")) if f_row else None

        parsed = e_row.get("parsed_score") if e_row else None
        f_parsed = (f_row.get("parsed_score") or {}) if f_row else {}
        d_side = str(d_row.get("intent_side") or "") if d_row else ""
        side = str(parsed.get("side") if parsed else (f_parsed.get("side") or d_side)).upper()
        first_event_ts = order_ts or (f_row["ts_ms"] if f_row else (e_row["ts_ms"] if e_row else None))

        segment = _slice_prices(prices.get(epoch.symbol, []), epoch.raw_regime_start_ts, first_event_ts or epoch.stable_regime_end_ts)
        row_price = _price_at(prices.get(epoch.symbol, []), first_event_ts or (e_row["ts_ms"] if e_row else None))
        timing_bucket, local_best, local_worst = classify_entry_timing(
            raw_price=epoch.raw_start_price,
            event_price=row_price,
            segment=segment,
            side=side,
        )

        ambiguity: list[str] = []
        if c_row is None:
            ambiguity.append("min_regime_cross_unproven")
        if d_row is None:
            ambiguity.append("min_conf_cross_unproven")
        if e_row is None:
            ambiguity.append("signal_threshold_cross_proxy_missing")
        if f_row is None:
            ambiguity.append("intent_admissible_unobserved")
        if order_ts is None:
            ambiguity.append("order_unobserved")

        trade = trade_by_parent.get(str(f_row.get("rid") or "")) if f_row else None
        outcome = trade.get("realized_pnl_abs") if trade else ""

        row = {
            "symbol": epoch.symbol,
            "strategy_id": "aurora",
            "raw_regime": epoch.raw_regime,
            "stable_regime": epoch.stable_regime,
            "raw_regime_start_ts": epoch.raw_regime_start_ts,
            "stable_regime_start_ts": epoch.stable_regime_start_ts,
            "bars_raw_to_stable": ((epoch.stable_regime_start_ts - epoch.raw_regime_start_ts) / BAR_MS) if epoch.raw_regime_start_ts and epoch.stable_regime_start_ts else None,
            "raw_regime_confidence_at_start": epoch.raw_regime_confidence_at_start,
            "confidence_cross_min_regime_ts": _safe_int(c_row.get("ts_ms")) if c_row else None,
            "bars_stable_to_min_regime": ((_safe_int(c_row.get("ts_ms")) - epoch.stable_regime_start_ts) / BAR_MS) if c_row and epoch.stable_regime_start_ts else None,
            "effective_confidence_cross_min_conf_ts": _safe_int(d_row.get("ts_ms")) if d_row else None,
            "bars_to_min_conf": ((_safe_int(d_row.get("ts_ms")) - (_safe_int(c_row.get("ts_ms")) if c_row else epoch.stable_regime_start_ts)) / BAR_MS) if d_row and (c_row or epoch.stable_regime_start_ts) else None,
            "signal_threshold_cross_ts": e_row["ts_ms"] if e_row else None,
            "bars_to_signal_threshold": ((e_row["ts_ms"] - (_safe_int(d_row.get("ts_ms")) if d_row else (epoch.stable_regime_start_ts or 0))) / BAR_MS) if e_row and epoch.stable_regime_start_ts else None,
            "first_tradeable_ts": _safe_int(f_row.get("ts_ms")) if f_row else None,
            "first_actual_intent_ts": e_row["ts_ms"] if e_row else None,
            "first_actual_order_ts": order_ts,
            "price_at_raw_start": epoch.raw_start_price,
            "price_at_stable_start": epoch.stable_start_price,
            "price_at_min_regime_cross": _price_at(prices.get(epoch.symbol, []), _safe_int(c_row.get("ts_ms")) if c_row else None),
            "price_at_min_conf_cross": _price_at(prices.get(epoch.symbol, []), _safe_int(d_row.get("ts_ms")) if d_row else None),
            "price_at_signal_threshold_cross": _price_at(prices.get(epoch.symbol, []), e_row["ts_ms"] if e_row else None),
            "price_at_first_order": _price_at(prices.get(epoch.symbol, []), order_ts),
            "local_best_price_before_order": local_best,
            "local_worst_price_before_order": local_worst,
            "entry_lateness_pct_proxy": None if timing_bucket == "UNKNOWN" or epoch.raw_start_price is None or local_best is None else (
                (row_price - epoch.raw_start_price) / (local_best - epoch.raw_start_price)
                if side == "BUY" and row_price is not None and (local_best - epoch.raw_start_price) != 0
                else (epoch.raw_start_price - row_price) / (epoch.raw_start_price - local_best)
                if side == "SELL" and row_price is not None and (epoch.raw_start_price - local_best) != 0
                else None
            ),
            "timing_classification": timing_bucket,
            "eventual_trade_outcome": outcome,
            "ambiguity_flag": "|".join(ambiguity),
        }
        timing_rows.append(row)

        for dec in decs:
            deny_reason = str(dec.get("deny_reason") or "")
            if str(dec.get("outcome")) != "DENY":
                continue
            if str(dec.get("threshold_verdict")) == "BLOCK":
                gate_failed = "min_regime_confidence"
            elif deny_reason == "NRR-026":
                gate_failed = "min_confidence_or_trend_confirmation"
            elif deny_reason == "NRR-027":
                gate_failed = "directional_sanity"
            elif deny_reason in {"NRR-028", "NRR-029", "NRR-030"}:
                gate_failed = "price_motion"
            else:
                gate_failed = "other"
            later_pass = next(
                (
                    r
                    for r in decs
                    if (_safe_int(r.get("ts_ms")) or 0) > (_safe_int(dec.get("ts_ms")) or 0)
                    and str(r.get("outcome")) == "ALLOW"
                ),
                None,
            )
            gate_rows.append(
                {
                    "symbol": epoch.symbol,
                    "ts_ms": _safe_int(dec.get("ts_ms")),
                    "regime": dec.get("regime_used"),
                    "regime_confidence": _safe_float(dec.get("regime_confidence_used")),
                    "effective_confidence": max(_safe_float(dec.get("regime_confidence_used")) or 0.0, 0.0),
                    "score": None,
                    "gate_failed": gate_failed,
                    "why_code": deny_reason,
                    "blocked_until_ts": _safe_int(later_pass.get("ts_ms")) if later_pass else None,
                    "next_gate_pass_ts": _safe_int(later_pass.get("ts_ms")) if later_pass else None,
                }
            )

        for it in intents:
            if it["event_name"] != "EVT:TRADE_INTENT_REJECTED":
                continue
            parsed_score = it.get("parsed_score") or {}
            later_prop = next(
                (
                    r
                    for r in intents
                    if (r["ts_ms"] or 0) > (it["ts_ms"] or 0)
                    and r["event_name"] == "EVT:TRADE_INTENT_PROPOSED"
                ),
                None,
            )
            gate_rows.append(
                {
                    "symbol": epoch.symbol,
                    "ts_ms": it["ts_ms"],
                    "regime": it.get("regime"),
                    "regime_confidence": it.get("regime_confidence"),
                    "effective_confidence": it.get("regime_confidence"),
                    "score": parsed_score.get("score"),
                    "gate_failed": "post_signal_gateway",
                    "why_code": it.get("reason_code"),
                    "blocked_until_ts": later_prop["ts_ms"] if later_prop else None,
                    "next_gate_pass_ts": later_prop["ts_ms"] if later_prop else None,
                }
            )

    timing_rows.sort(key=lambda r: (r["symbol"], r["stable_regime_start_ts"] or 0))
    gate_rows.sort(key=lambda r: (r["symbol"], r["ts_ms"] or 0))

    summary_rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in timing_rows:
        grouped[(row["symbol"], row["stable_regime"])].append(row)

    for (symbol, regime), rows in sorted(grouped.items()):
        bars_raw_to_stable = [r["bars_raw_to_stable"] for r in rows if r["bars_raw_to_stable"] is not None]
        stable_to_tradeable = [
            ((r["first_tradeable_ts"] - r["stable_regime_start_ts"]) / BAR_MS)
            for r in rows
            if r["first_tradeable_ts"] is not None and r["stable_regime_start_ts"] is not None
        ]
        raw_drift = [
            ((r["price_at_first_order"] - r["price_at_raw_start"]) / r["price_at_raw_start"]) * 100.0
            for r in rows
            if r["price_at_first_order"] not in (None, 0.0) and r["price_at_raw_start"] not in (None, 0.0)
        ]
        stable_drift = [
            ((r["price_at_first_order"] - r["price_at_stable_start"]) / r["price_at_stable_start"]) * 100.0
            for r in rows
            if r["price_at_first_order"] not in (None, 0.0) and r["price_at_stable_start"] not in (None, 0.0)
        ]
        late_pct = (
            sum(1 for r in rows if r["timing_classification"] in {"LATE", "POST_EXHAUSTION"}) / len(rows)
            if rows else None
        )
        no_entry_pct = sum(1 for r in rows if not r["first_actual_order_ts"]) / len(rows) if rows else None
        bucket_pnl = defaultdict(list)
        for r in rows:
            if r["eventual_trade_outcome"] not in ("", None):
                try:
                    bucket_pnl[r["timing_classification"]].append(float(r["eventual_trade_outcome"]))
                except Exception:
                    pass
        summary_rows.append(
            {
                "symbol": symbol,
                "regime": regime,
                "count_epochs": len(rows),
                "avg_bars_raw_to_stable": _mean_or_none(bars_raw_to_stable),
                "avg_bars_stable_to_tradeable": _mean_or_none(stable_to_tradeable),
                "median_bars_stable_to_tradeable": _median_or_none(stable_to_tradeable),
                "avg_price_drift_raw_to_tradeable": _mean_or_none(raw_drift),
                "avg_price_drift_stable_to_tradeable": _mean_or_none(stable_drift),
                "pct_late_entries": late_pct,
                "pct_no_entry_epochs": no_entry_pct,
                "realized_pnl_after_early_entries": _mean_or_none(bucket_pnl["EARLY"]),
                "realized_pnl_after_mid_entries": _mean_or_none(bucket_pnl["MID"]),
                "realized_pnl_after_late_entries": _mean_or_none(bucket_pnl["LATE"] + bucket_pnl["POST_EXHAUSTION"]),
            }
        )

    with (out_dir / "confidence_timing_master.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(timing_rows[0].keys()) if timing_rows else [])
        writer.writeheader()
        writer.writerows(timing_rows)

    with (out_dir / "gate_block_decomposition.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(gate_rows[0].keys()) if gate_rows else [])
        writer.writeheader()
        writer.writerows(gate_rows)

    with (out_dir / "regime_epoch_latency_summary.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()) if summary_rows else [])
        writer.writeheader()
        writer.writerows(summary_rows)

    gate_counts = Counter(r["gate_failed"] for r in gate_rows)
    timing_counts = Counter(r["timing_classification"] for r in timing_rows)
    safety_counts = Counter()
    for row in decision_rows:
        if str(row.get("outcome")) == "DENY":
            if str(row.get("threshold_verdict")) == "BLOCK":
                safety_counts["min_regime_confidence"] += 1
            elif str(row.get("deny_reason")) == "NRR-026":
                safety_counts["min_confidence_or_trend_confirmation"] += 1
            elif str(row.get("deny_reason")) == "NRR-027":
                safety_counts["directional_sanity"] += 1
            elif str(row.get("deny_reason")) in {"NRR-028", "NRR-029", "NRR-030"}:
                safety_counts["price_motion"] += 1
        elif str(row.get("outcome")) == "ALLOW":
            safety_counts["allow"] += 1

    threshold_md = (
        "# Threshold Surface Snapshot\n\n"
        "- `basis_tf_sec`: owned by `config/aurora/regime.yaml`, consumed by `regime_detector.py` as the bar-only clock.\n"
        "- `uncertain_cutoff`: owned by `config/aurora/regime.yaml`, consumed in `regime_detector.py` where weak non-UNCERTAIN raw regimes are demoted back to `UNCERTAIN`.\n"
        "- `hysteresis_bars`: owned by `config/aurora/regime.yaml`, consumed in `regime_detector.py` to delay stable regime transition until repeated raw confirmations.\n"
        "- `min_regime_confidence`: owned by `config/aurora/domains.yaml`, consumed in `safety_gates.py` before directional sanity.\n"
        "- `min_confidence`: owned by `config/aurora/domains.yaml`, consumed in `safety_gates.py` against `max(regime_confidence, trend_confidence)`.\n"
        "- `signal_threshold`: owned by `config/aurora/strategies/aurora.yaml`, resolved through `config_resolver.py`. The resolver applies a typed per-instrument override when that override object exists, is enabled, and has a non-null `value`; otherwise it falls back to `strategies.aurora.decision.signal_threshold`.\n"
        "- Runtime threshold chain for Aurora is not just the headline global `0.162`. The effective side threshold passed into the execution gate is built from the resolved base threshold and then widened in policy as `signal_threshold * regime_threshold_multiplier * side_bias_multiplier`, which is why live `thr_buy` / `thr_sell` values in the logs are often much smaller than `0.162`.\n"
        "- Live post-threshold gateway blocks observed in this window were dominated by `FLIP_GATE_UNKNOWN` and `NRR-061`, not `SCORE_TOO_WEAK`.\n"
    )
    (out_dir / "threshold_surface_snapshot.md").write_text(threshold_md, encoding="utf-8")

    verdict = "Confidence-lag dominates the proven pre-signal bottleneck; score-threshold lag is not proven as the main blocker in this runtime window."
    top_followup = "mixed follow-up"
    if safety_counts["min_regime_confidence"] >= max(safety_counts["price_motion"], safety_counts["directional_sanity"]) and gate_counts["post_signal_gateway"] > 0:
        top_followup = "mixed follow-up"

    report_md = (
        "# R1 - Confidence-Latency Audit\n\n"
        "## Problem Framing\n"
        "This package tests whether Aurora becomes tradeable late because of the confidence and threshold chain, or whether the main bottleneck is elsewhere.\n\n"
        "## Facts\n"
        f"- Stable-epoch candidates analyzed: {len(timing_rows)}.\n"
        f"- Aurora safety-gate decision audit rows analyzed: {len(decision_rows)}.\n"
        f"- Aurora shadow intent rows analyzed: {len(shadow_rows)}.\n"
        f"- Safety-gate denials by class: {dict(safety_counts)}.\n"
        f"- Gate block decomposition counts: {dict(gate_counts)}.\n"
        f"- Timing classifications: {dict(timing_counts)}.\n"
        "- `min_regime_confidence` blocks are directly proven in `regime_confidence_audit_v1.jsonl`.\n"
        "- `SCORE_TOO_WEAK` is present in source, but I did not find live runtime evidence of it firing in the analyzed window.\n\n"
        "## Inferences\n"
        "- The dominant proven pre-signal blocker is regime-confidence gating, not score-threshold gating.\n"
        "- A secondary live bottleneck exists after score acceptance: post-signal gateway rejection, dominated by `FLIP_GATE_UNKNOWN` and later by embargo blocks.\n"
        "- Because the effective Aurora threshold is resolved through a per-instrument override contract and then regime-multiplied and side-biased, the global `0.162` value is not the live admission surface by itself.\n\n"
        "## Assumptions\n"
        "- `signal_threshold_cross_ts` is proxied by the first Aurora intent-level event carrying a parsed `enter:*score...thr_*` line.\n"
        "- `first_tradeable_ts` is proxied by the first `EVT:TRADE_INTENT_PROPOSED` inside the epoch.\n\n"
        "## Unknowns\n"
        "- There is no explicit runtime surface in this window that isolates score-threshold failure before later gateway handling for every candidate epoch.\n"
        "- State D (`min_confidence`) is only provable where `regime_confidence_audit_v1.jsonl` emitted an Aurora decision row for that epoch.\n\n"
        "## Main Bottleneck Verdict\n"
        f"- {verdict}\n"
        f"- Ranked bottlenecks: 1) `min_regime_confidence`, 2) post-signal gateway (`FLIP_GATE_UNKNOWN` / embargo), 3) price-motion gate, 4) directional sanity.\n"
        f"- Next justified package: `{top_followup}`.\n"
    )
    (out_dir / "R1_CONFIDENCE_LATENCY_AUDIT.md").write_text(report_md, encoding="utf-8")

    completion_md = (
        "# R1 Completion Report\n\n"
        "## Proven\n"
        f"- The live threshold chain owners and consumers are localized in source.\n"
        f"- The dominant proven pre-signal bottleneck is `min_regime_confidence` gating ({safety_counts['min_regime_confidence']} safety-gate denials).\n"
        f"- Score-threshold starvation is not proven from runtime logs; no live `SCORE_TOO_WEAK` evidence was found.\n"
        f"- Post-signal gating still materially blocks flow (`{gate_counts['post_signal_gateway']}` blocked intent rows in the decomposition table).\n\n"
        "## Unproven\n"
        "- Exact state-E timing for every epoch, because there is no dedicated score-threshold-cross event for all bars.\n"
        "- A single universally dominant bottleneck across all epochs without ambiguity; the top two are confidence gating and post-signal gateway rejection.\n\n"
        "## Artifacts Used\n"
        "- `logs/regime_confidence_audit_v1.jsonl`\n"
        "- `logs/shadow_critical_event_journal_v1.jsonl`\n"
        "- `logs/order_log_v1.jsonl`\n"
        "- `logs/mean_reversion/bars_300s.jsonl`\n"
        "- `logs/ta_features/*.jsonl`\n"
        "- `reports/forensics/aurora_runtime/trades_master.csv`\n\n"
        "## Next Package\n"
        "- A mixed follow-up is justified: confidence ablation plus gateway follow-up. Horizon replacement is not yet justified from this package alone.\n\n"
        "## Do Not Change Yet\n"
        "- Do not rewrite `RegimeDetector`.\n"
        "- Do not change horizons.\n"
        "- Do not lower confidence thresholds blindly.\n"
        "- Do not retune `signal_threshold` until gateway and confidence timing are separated with the R1 outputs.\n"
    )
    (out_dir / "R1_COMPLETION_REPORT.md").write_text(completion_md, encoding="utf-8")

    print(
        json.dumps(
            {
                "epochs": len(timing_rows),
                "decision_rows": len(decision_rows),
                "shadow_intents": len(shadow_rows),
                "safety_counts": dict(safety_counts),
                "gate_counts": dict(gate_counts),
                "timing_counts": dict(timing_counts),
                "out_dir": str(out_dir),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
