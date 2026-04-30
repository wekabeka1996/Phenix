#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


BASE = Path(__file__).resolve().parents[2]
LOGS = BASE / "logs"
REPORTS = BASE / "reports" / "forensics" / "r3_min_regime_confidence"
BAR_MS = 300_000
WINDOW_START_MS = 1776510000000
AURORA_SYMBOLS = {"BTCUSDT", "ETHUSDT", "DOGEUSDT", "XRPUSDT", "BNBUSDT"}
BASELINE_THRESHOLD = 0.42
TESTED_THRESHOLDS = [0.42, 0.37, 0.32, 0.27, 0.22]


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


def _breach_kind(row: dict[str, Any]) -> str | None:
    value = row.get("regime_confidence_breach_kind")
    if value in {"none", "missing", "below_min", "above_max"}:
        return value
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if isinstance(metadata, dict):
        meta_value = metadata.get("regime_confidence_breach_kind")
        if meta_value in {"none", "missing", "below_min", "above_max"}:
            return meta_value
    why = str(row.get("why") or "").lower()
    if "above max" in why:
        return "above_max"
    if "missing" in why:
        return "missing"
    if "< min=" in why:
        return "below_min"
    return None


def build_counterfactual_band_report(
    decisions: list[dict[str, Any]],
    *,
    lower: float,
    upper: float,
) -> dict[str, Any]:
    totals = Counter()
    by_symbol: dict[str, Counter[str]] = defaultdict(Counter)
    by_strategy: dict[str, Counter[str]] = defaultdict(Counter)
    by_regime: dict[str, Counter[str]] = defaultdict(Counter)

    for row in decisions:
        conf = _safe_float(row.get("regime_confidence_used"))
        if conf is None:
            continue
        symbol = str(row.get("symbol") or "")
        strategy = str(row.get("strategy_id") or "")
        regime = str(row.get("regime_used") or "")
        deny_reason = str(row.get("deny_reason") or "")
        verdict = str(row.get("threshold_verdict") or "")
        breach_kind = _breach_kind(row)

        totals["total_inspected"] += 1
        by_symbol[symbol]["total_inspected"] += 1
        by_strategy[strategy]["total_inspected"] += 1
        by_regime[regime]["total_inspected"] += 1

        if conf < lower:
            totals["below_min"] += 1
            by_symbol[symbol]["below_min"] += 1
            by_strategy[strategy]["below_min"] += 1
            by_regime[regime]["below_min"] += 1
        elif conf > upper:
            totals["above_max"] += 1
            by_symbol[symbol]["above_max"] += 1
            by_strategy[strategy]["above_max"] += 1
            by_regime[regime]["above_max"] += 1
        else:
            totals["inside_band"] += 1
            by_symbol[symbol]["inside_band"] += 1
            by_strategy[strategy]["inside_band"] += 1
            by_regime[regime]["inside_band"] += 1

        if deny_reason == "NRR-026":
            totals["currently_blocked_by_below_min"] += 1
            by_symbol[symbol]["currently_blocked_by_below_min"] += 1
            by_strategy[strategy]["currently_blocked_by_below_min"] += 1
            by_regime[regime]["currently_blocked_by_below_min"] += 1
            if lower <= conf <= upper:
                totals["current_nrr_026_within_band"] += 1
        elif deny_reason in {"NRR-027", "NRR-029", "NRR-030"} or (
            verdict == "BLOCK" and breach_kind not in {"below_min", "missing"}
        ):
            totals["currently_blocked_by_other_gate"] += 1
            by_symbol[symbol]["currently_blocked_by_other_gate"] += 1
            by_strategy[strategy]["currently_blocked_by_other_gate"] += 1
            by_regime[regime]["currently_blocked_by_other_gate"] += 1

        if conf > upper:
            if verdict == "ALLOW":
                totals["currently_allowed_but_would_above_max"] += 1
                by_symbol[symbol]["currently_allowed_but_would_above_max"] += 1
                by_strategy[strategy]["currently_allowed_but_would_above_max"] += 1
                by_regime[regime]["currently_allowed_but_would_above_max"] += 1
            elif deny_reason in {"NRR-027", "NRR-029", "NRR-030"} or (
                verdict == "BLOCK" and breach_kind not in {"below_min", "missing"}
            ):
                totals["currently_other_rejected_but_would_first_block_above_max"] += 1
                by_symbol[symbol]["currently_other_rejected_but_would_first_block_above_max"] += 1
                by_strategy[strategy]["currently_other_rejected_but_would_first_block_above_max"] += 1
                by_regime[regime]["currently_other_rejected_but_would_first_block_above_max"] += 1

    return {
        "band": {"lower": lower, "upper": upper},
        "totals": dict(totals),
        "by_symbol": {symbol: dict(counter) for symbol, counter in by_symbol.items()},
        "by_strategy": {strategy: dict(counter) for strategy, counter in by_strategy.items()},
        "by_regime": {regime: dict(counter) for regime, counter in by_regime.items()},
    }


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
                    }
                )
    for sym in list(series.keys()):
        series[sym].sort(key=lambda row: row["ts_ms"])
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


def _signed_qty(pos: dict[str, Any]) -> Decimal | None:
    for key in (
        "positionAmt",
        "net_position",
        "qty_signed",
        "signed_qty",
        "position_qty_signed",
        "qty",
    ):
        raw = pos.get(key)
        if raw in (None, "", "null", "None"):
            continue
        try:
            return Decimal(str(raw))
        except Exception:
            continue
    return None


def _directional_side(intent_side: str) -> str:
    value = str(intent_side).upper()
    if value in {"LONG", "BUY"}:
        return "BUY"
    if value in {"SHORT", "SELL"}:
        return "SELL"
    return value


def _favorable_move(side: str, start_price: float | None, future_price: float | None) -> bool | None:
    if start_price in (None, 0.0) or future_price is None:
        return None
    if side == "BUY":
        return future_price > start_price
    if side == "SELL":
        return future_price < start_price
    return None


def _directional_move_bps(side: str, start_price: float | None, future_price: float | None) -> float | None:
    if start_price in (None, 0.0) or future_price is None:
        return None
    if side == "BUY":
        return ((future_price - start_price) / start_price) * 10_000.0
    if side == "SELL":
        return ((start_price - future_price) / start_price) * 10_000.0
    return None


def _classify_quality(fav15: bool | None, fav60: bool | None, regime: str) -> str:
    if fav15 is True and fav60 is True:
        if regime == "TREND_DOWN":
            return "PROMISING_BUT_WEAK_REGIME"
        return "PROMISING"
    if fav15 is False and fav60 is False:
        return "DANGEROUS"
    if fav15 is True or fav60 is True:
        return "MIXED"
    return "UNKNOWN"


def _classify_timing(raw_price: float | None, event_price: float | None, segment: list[dict[str, Any]], side: str) -> str:
    if raw_price is None or event_price is None or not segment or side not in {"BUY", "SELL"}:
        return "UNKNOWN"
    highs = [float(row["high"]) for row in segment]
    lows = [float(row["low"]) for row in segment]
    local_best = max(highs) if side == "BUY" else min(lows)
    favorable_total = (local_best - raw_price) if side == "BUY" else (raw_price - local_best)
    favorable_done = (event_price - raw_price) if side == "BUY" else (raw_price - event_price)
    if favorable_total <= 0:
        return "UNKNOWN"
    ratio = favorable_done / favorable_total
    if ratio < 0:
        return "UNKNOWN"
    if ratio < 0.25:
        return "EARLY"
    if ratio <= 0.75:
        return "MID"
    if ratio <= 1.0:
        return "LATE"
    return "POST_EXHAUSTION"


@dataclass
class EpochRow:
    symbol: str
    stable_regime: str
    raw_regime: str
    raw_regime_start_ts: int | None
    stable_regime_start_ts: int | None
    stable_regime_end_ts: int | None
    stable_start_price: float | None
    raw_start_price: float | None


def load_bar_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prev_regime_by_symbol: dict[str, str] = {}
    for row in _iter_jsonl(LOGS / "shadow_critical_event_journal_v1.jsonl"):
        if row.get("event_name") != "EVT:REGIME_DETECTED":
            continue
        pf = row.get("payload_fragment") if isinstance(row.get("payload_fragment"), dict) else {}
        symbol = str(row.get("symbol") or pf.get("symbol") or "")
        regime = str(pf.get("regime") or "")
        ts = _safe_int(pf.get("ts_ms") or row.get("ts_ms"))
        if ts is None or ts < WINDOW_START_MS or symbol not in AURORA_SYMBOLS or not regime:
            continue
        prev_regime = prev_regime_by_symbol.get(symbol)
        rows.append(
            {
                "ts_ms": ts,
                "symbol": symbol,
                "regime": regime,
                "raw_regime": str(pf.get("raw_regime") or regime),
                "raw_confidence": _safe_float(pf.get("confidence")),
                "stable_confidence": _safe_float(pf.get("stable_confidence") or pf.get("confidence")),
                "structural_regime_ref": str(pf.get("structural_regime_ref") or ""),
                "changed": bool(pf.get("changed")) if pf.get("changed") is not None else prev_regime is None or prev_regime != regime,
            }
        )
        prev_regime_by_symbol[symbol] = regime
    rows.sort(key=lambda row: (str(row.get("symbol") or ""), _safe_int(row.get("ts_ms")) or 0))
    return rows


def build_epochs(bar_rows: list[dict[str, Any]], prices: dict[str, list[dict[str, Any]]]) -> list[EpochRow]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in bar_rows:
        by_symbol[str(row.get("symbol") or "")].append(row)
    epochs: list[EpochRow] = []
    for symbol, rows in by_symbol.items():
        rows.sort(key=lambda row: _safe_int(row.get("ts_ms")) or 0)
        starts: list[int] = []
        for i, row in enumerate(rows):
            if i == 0 or row.get("changed") is True:
                starts.append(i)
        for idx, start_i in enumerate(starts):
            row = rows[start_i]
            stable_regime = str(row.get("regime") or "")
            if not stable_regime:
                continue
            end_i = starts[idx + 1] - 1 if idx + 1 < len(starts) else len(rows) - 1
            stable_start_ts = _safe_int(row.get("ts_ms"))
            stable_end_ts = _safe_int(rows[end_i].get("ts_ms"))
            j = start_i
            while j > 0 and str(rows[j - 1].get("raw_regime") or "") == stable_regime:
                j -= 1
            raw_row = rows[j]
            raw_start_ts = _safe_int(raw_row.get("ts_ms"))
            price_series = prices.get(symbol, [])
            epochs.append(
                EpochRow(
                    symbol=symbol,
                    stable_regime=stable_regime,
                    raw_regime=str(raw_row.get("raw_regime") or ""),
                    raw_regime_start_ts=raw_start_ts,
                    stable_regime_start_ts=stable_start_ts,
                    stable_regime_end_ts=stable_end_ts,
                    stable_start_price=_price_at(price_series, stable_start_ts),
                    raw_start_price=_price_at(price_series, raw_start_ts),
                )
            )
    epochs.sort(key=lambda row: (row.symbol, row.stable_regime_start_ts or 0))
    return epochs


def load_decisions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _iter_jsonl(LOGS / "regime_confidence_audit_v1.jsonl"):
        if row.get("record_type") != "decision":
            continue
        if row.get("strategy_id") != "aurora":
            continue
        ts = _safe_int(row.get("ts_ms"))
        symbol = str(row.get("symbol") or "")
        conf = _safe_float(row.get("regime_confidence_used"))
        if ts is None or ts < WINDOW_START_MS or symbol not in AURORA_SYMBOLS or conf is None:
            continue
        row["regime_confidence_breach_kind"] = _breach_kind(row)
        rows.append(row)
    rows.sort(key=lambda row: (str(row.get("symbol") or ""), _safe_int(row.get("ts_ms")) or 0))
    if rows:
        return rows
    return load_shadow_decisions()


def _nearest_shadow_event(rows: list[dict[str, Any]], symbol: str, ts_ms: int, *, window_ms: int = 5_000) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_delta: int | None = None
    for row in rows:
        if str(row.get("symbol") or "") != symbol:
            continue
        row_ts = _safe_int(row.get("ts_ms"))
        if row_ts is None:
            continue
        delta = abs(row_ts - ts_ms)
        if delta > window_ms:
            continue
        if best is None or best_delta is None or delta < best_delta:
            best = row
            best_delta = delta
    return best


def load_shadow_decisions() -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    for row in _iter_jsonl(LOGS / "shadow_critical_event_journal_v1.jsonl"):
        if str(row.get("strategy_id") or "") != "aurora":
            continue
        en = str(row.get("event_name") or "")
        pf = row.get("payload_fragment") if isinstance(row.get("payload_fragment"), dict) else {}
        symbol = str(row.get("symbol") or pf.get("symbol") or "")
        ts = _safe_int(pf.get("ts_ms") or row.get("ts_ms"))
        if symbol not in AURORA_SYMBOLS or ts is None:
            continue
        if en == "EVT:QUADRATIC_DECISION_TRACE":
            traces.append(
                {
                    "ts_ms": ts,
                    "symbol": symbol,
                    "strategy_id": str(pf.get("strategy_id") or row.get("strategy_id") or "aurora"),
                    "intent_side": str(pf.get("side") or row.get("side") or ""),
                    "regime_used": str(pf.get("regime") or ""),
                    "regime_confidence_used": _safe_float(pf.get("regime_confidence")),
                    "threshold_verdict": "ALLOW",
                    "threshold_reason": "shadow_trace",
                    "deny_reason": "",
                    "why_short": "",
                    "outcome": "ALLOW",
                    "confidence_used_stage": "stable_confidence",
                    "regime_confidence_breach_kind": "none",
                }
            )
        elif en == "EVT:STRATEGY_DECISION_BLOCKED":
            blocks.append(
                {
                    "ts_ms": ts,
                    "symbol": symbol,
                    "strategy_id": str(pf.get("strategy_id") or row.get("strategy_id") or "aurora"),
                    "deny_reason": str(pf.get("reason_code") or ""),
                    "why_short": str(pf.get("why") or pf.get("context") or ""),
                    "context": str(pf.get("context") or ""),
                }
            )

    blocks.sort(key=lambda row: (str(row.get("symbol") or ""), _safe_int(row.get("ts_ms")) or 0))
    rows: list[dict[str, Any]] = []
    for trace in traces:
        symbol = str(trace.get("symbol") or "")
        ts_ms = _safe_int(trace.get("ts_ms")) or 0
        block = _nearest_shadow_event(blocks, symbol, ts_ms)
        deny_reason = str((block or {}).get("deny_reason") or "")
        threshold_verdict = "BLOCK" if deny_reason else "ALLOW"
        breach_kind = "none"
        if deny_reason == "NRR-026":
            breach_kind = "below_min"
        elif deny_reason == "NRR-063":
            breach_kind = "above_max"

        rows.append(
            {
                "record_type": "decision",
                "ts_ms": ts_ms,
                "symbol": symbol,
                "strategy_id": str(trace.get("strategy_id") or "aurora"),
                "intent_side": str(trace.get("intent_side") or ""),
                "regime_used": str(trace.get("regime_used") or ""),
                "regime_confidence_used": trace.get("regime_confidence_used"),
                "threshold_verdict": threshold_verdict,
                "threshold_reason": (block or {}).get("context") or "shadow_trace",
                "deny_reason": deny_reason,
                "why_short": (block or {}).get("why_short") or "",
                "outcome": "DENY" if threshold_verdict == "BLOCK" else "ALLOW",
                "confidence_used_stage": str(trace.get("confidence_used_stage") or "stable_confidence"),
                "regime_confidence_breach_kind": breach_kind,
            }
        )
    rows.sort(key=lambda row: (str(row.get("symbol") or ""), _safe_int(row.get("ts_ms")) or 0))
    return rows


def load_shadow() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    proposals: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    for row in _iter_jsonl(LOGS / "shadow_critical_event_journal_v1.jsonl"):
        if str(row.get("strategy_id") or "") != "aurora":
            continue
        symbol = str(row.get("symbol") or "")
        if symbol not in AURORA_SYMBOLS:
            continue
        en = str(row.get("event_name") or "")
        if en == "EVT:TRADE_INTENT_PROPOSED":
            proposals.append(row)
        elif en == "EVT:TRADE_INTENT_REJECTED":
            rejects.append(row)
    proposals.sort(key=lambda row: _safe_int(row.get("ts_ms")) or 0)
    rejects.sort(key=lambda row: _safe_int(row.get("ts_ms")) or 0)
    return proposals, rejects


def load_order_rows() -> list[dict[str, Any]]:
    rows = [row for row in _iter_jsonl(LOGS / "order_log_v1.jsonl")]
    rows.sort(key=lambda row: _safe_int(row.get("timestamp")) or 0)
    return rows


def load_exposure_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _iter_jsonl(LOGS / "shadow_critical_event_journal_v1.jsonl"):
        if row.get("event_name") != "EVT:EXPOSURE_SUMMARY_UPDATED":
            continue
        ts = _safe_int(row.get("ts_ms"))
        pf = row.get("payload_fragment") if isinstance(row.get("payload_fragment"), dict) else {}
        portfolio_state = pf.get("portfolio_state") if isinstance(pf.get("portfolio_state"), dict) else {}
        if ts is None:
            continue
        rows.append({"ts_ms": ts, "portfolio_state": portfolio_state})
    rows.sort(key=lambda row: row["ts_ms"])
    return rows


def _latest_exposure(rows: list[dict[str, Any]], ts_ms: int) -> dict[str, Any] | None:
    if not rows:
        return None
    idxs = [row["ts_ms"] for row in rows]
    i = bisect_right(idxs, ts_ms) - 1
    if i < 0:
        return None
    return rows[i]


def _next_proposal(proposals: list[dict[str, Any]], symbol: str, side: str, ts_ms: int) -> dict[str, Any] | None:
    for row in proposals:
        row_ts = _safe_int(row.get("ts_ms"))
        if row_ts is None or row_ts <= ts_ms:
            continue
        if str(row.get("symbol") or "") != symbol:
            continue
        if _directional_side(str(row.get("side") or "")) != side:
            continue
        return row
    return None


def _next_order(order_rows: list[dict[str, Any]], symbol: str, side: str, ts_ms: int) -> dict[str, Any] | None:
    for row in order_rows:
        row_ts = _safe_int(row.get("timestamp"))
        if row_ts is None or row_ts <= ts_ms:
            continue
        if row.get("event_type") != "ORDER_PLACED":
            continue
        if str(row.get("symbol") or "") != symbol:
            continue
        if _directional_side(str(row.get("side") or "")) != side:
            continue
        return row
    return None


def _assign_epoch(epoch_rows: list[EpochRow], symbol: str, regime: str, ts_ms: int) -> EpochRow | None:
    for epoch in epoch_rows:
        if epoch.symbol != symbol:
            continue
        if epoch.stable_regime != regime:
            continue
        if epoch.stable_regime_start_ts is None or epoch.stable_regime_end_ts is None:
            continue
        if epoch.stable_regime_start_ts <= ts_ms <= epoch.stable_regime_end_ts:
            return epoch
    return None


def _resolve_epoch_at_ts(epoch_rows: list[EpochRow], symbol: str, ts_ms: int) -> EpochRow | None:
    for epoch in epoch_rows:
        if epoch.symbol != symbol:
            continue
        if epoch.stable_regime_start_ts is None or epoch.stable_regime_end_ts is None:
            continue
        if epoch.stable_regime_start_ts <= ts_ms <= epoch.stable_regime_end_ts:
            return epoch
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="R3 min_regime_confidence ablation")
    ap.add_argument("--out-dir", default=str(REPORTS))
    ap.add_argument("--band-lower", type=float, default=0.20)
    ap.add_argument("--band-upper", type=float, default=0.35)
    ap.add_argument("--regime", default=None, help="Optional regime filter for the counterfactual band report")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prices = _price_series()
    bar_rows = load_bar_rows()
    epochs = build_epochs(bar_rows, prices)
    decisions = load_decisions()
    for row in decisions:
        if str(row.get("regime_used") or ""):
            continue
        ts_ms = _safe_int(row.get("ts_ms"))
        symbol = str(row.get("symbol") or "")
        if ts_ms is None or not symbol:
            continue
        epoch = _resolve_epoch_at_ts(epochs, symbol, ts_ms)
        if epoch is not None:
            row["regime_used"] = epoch.stable_regime
    proposals, _rejects = load_shadow()
    order_rows = load_order_rows()
    exposure_rows = load_exposure_rows()
    regime_filter = str(args.regime).strip().upper() if args.regime is not None else ""
    if regime_filter:
        decisions = [
            row for row in decisions
            if str(row.get("regime_used") or "").strip().upper() == regime_filter
        ]
    band_report = build_counterfactual_band_report(
        decisions,
        lower=float(args.band_lower),
        upper=float(args.band_upper),
    )

    baseline_rows = [
        row for row in decisions
        if str(row.get("threshold_verdict")) == "BLOCK"
        and str(row.get("deny_reason")) == "NRR-026"
        and (_safe_float(row.get("regime_confidence_used")) or 0.0) < BASELINE_THRESHOLD
    ]

    epoch_by_threshold: dict[float, list[dict[str, Any]]] = {}
    newly_admitted_rows: list[dict[str, Any]] = []

    for threshold in TESTED_THRESHOLDS:
        threshold_epoch_rows: list[dict[str, Any]] = []
        passing_rows = [row for row in decisions if (_safe_float(row.get("regime_confidence_used")) or -1.0) >= threshold]

        by_epoch_key: dict[tuple[str, int], dict[str, Any]] = {}
        for row in passing_rows:
            ts_ms = _safe_int(row.get("ts_ms")) or 0
            symbol = str(row.get("symbol") or "")
            regime = str(row.get("regime_used") or "")
            epoch = _assign_epoch(epochs, symbol, regime, ts_ms)
            if epoch is None:
                continue
            key = (symbol, epoch.stable_regime_start_ts or ts_ms)
            current = by_epoch_key.get(key)
            if current is None or (_safe_int(current.get("ts_ms")) or 10**18) > ts_ms:
                by_epoch_key[key] = row
        for row in by_epoch_key.values():
            ts_ms = _safe_int(row.get("ts_ms")) or 0
            symbol = str(row.get("symbol") or "")
            regime = str(row.get("regime_used") or "")
            epoch = _assign_epoch(epochs, symbol, regime, ts_ms)
            side = _directional_side(str(row.get("intent_side") or ""))
            price_now = _price_at(prices.get(symbol, []), ts_ms)
            segment = _slice_prices(prices.get(symbol, []), epoch.raw_regime_start_ts if epoch else None, ts_ms)
            threshold_epoch_rows.append(
                {
                    "symbol": symbol,
                    "regime": regime,
                    "threshold": threshold,
                    "stable_regime_start_ts": epoch.stable_regime_start_ts if epoch else None,
                    "admissible_ts": ts_ms,
                    "bars_stable_to_admissible": ((ts_ms - (epoch.stable_regime_start_ts or ts_ms)) / BAR_MS) if epoch and epoch.stable_regime_start_ts is not None else None,
                    "price_drift_stable_to_admissible": (((price_now - epoch.stable_start_price) / epoch.stable_start_price) * 100.0) if epoch and price_now not in (None, 0.0) and epoch.stable_start_price not in (None, 0.0) else None,
                    "timing_classification": _classify_timing(epoch.raw_start_price if epoch else None, price_now, segment, side),
                }
            )
        epoch_by_threshold[threshold] = threshold_epoch_rows

        if threshold == BASELINE_THRESHOLD:
            continue

        for row in baseline_rows:
            conf = _safe_float(row.get("regime_confidence_used")) or 0.0
            if conf < threshold:
                continue
            ts_ms = _safe_int(row.get("ts_ms")) or 0
            symbol = str(row.get("symbol") or "")
            regime = str(row.get("regime_used") or "")
            intent_side = _directional_side(str(row.get("intent_side") or ""))
            epoch = _assign_epoch(epochs, symbol, regime, ts_ms)
            exposure_row = _latest_exposure(exposure_rows, ts_ms)
            portfolio_state = exposure_row.get("portfolio_state") if exposure_row else {}
            positions = portfolio_state.get("positions") if isinstance(portfolio_state, dict) else []
            curr_pos = next((p for p in positions if isinstance(p, dict) and p.get("symbol") == symbol), None)
            qty_signed = _signed_qty(curr_pos) if curr_pos else Decimal("0")
            same_side_flag = False
            if qty_signed is not None:
                if qty_signed > 0 and intent_side == "BUY":
                    same_side_flag = True
                if qty_signed < 0 and intent_side == "SELL":
                    same_side_flag = True

            price_now = _price_at(prices.get(symbol, []), ts_ms)
            price_5 = _price_at(prices.get(symbol, []), ts_ms + 5 * 60_000)
            price_15 = _price_at(prices.get(symbol, []), ts_ms + 15 * 60_000)
            price_60 = _price_at(prices.get(symbol, []), ts_ms + 60 * 60_000)
            fav5 = _favorable_move(intent_side, price_now, price_5)
            fav15 = _favorable_move(intent_side, price_now, price_15)
            fav60 = _favorable_move(intent_side, price_now, price_60)

            baseline_prop = _next_proposal(proposals, symbol, intent_side, ts_ms)
            baseline_order = _next_order(order_rows, symbol, intent_side, ts_ms)
            baseline_later_entry_ts = _safe_int(baseline_prop.get("ts_ms")) if baseline_prop else (_safe_int(baseline_order.get("timestamp")) if baseline_order else None)
            baseline_later_entry_price = _price_at(prices.get(symbol, []), baseline_later_entry_ts) if baseline_later_entry_ts else None

            newly_admitted_rows.append(
                {
                    "symbol": symbol,
                    "strategy_id": "aurora",
                    "regime": regime,
                    "tested_threshold": threshold,
                    "baseline_blocked_flag": True,
                    "newly_admitted_flag": True,
                    "stable_regime_start_ts": epoch.stable_regime_start_ts if epoch else None,
                    "admissible_ts": ts_ms,
                    "intended_side": intent_side,
                    "regime_confidence": conf,
                    "effective_confidence": conf,
                    "score": None,
                    "price_at_admissible": price_now,
                    "price_5m_after": price_5,
                    "price_15m_after": price_15,
                    "price_60m_after": price_60,
                    "favorable_direction_5m": fav5,
                    "favorable_direction_15m": fav15,
                    "favorable_direction_60m": fav60,
                    "baseline_later_entry_ts": baseline_later_entry_ts,
                    "baseline_later_entry_price": baseline_later_entry_price,
                    "earlier_than_baseline_flag": baseline_later_entry_ts is not None and baseline_later_entry_ts > ts_ms,
                    "quality_proxy_bucket": _classify_quality(fav15, fav60, regime),
                    "same_side_under_strict_flag": same_side_flag,
                    "ambiguity_flag": "" if epoch is not None else "epoch_unassigned",
                }
            )

    newly_admitted_rows.sort(key=lambda row: (row["tested_threshold"], row["symbol"], row["admissible_ts"] or 0))

    with (out_dir / "newly_admitted_candidates.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(newly_admitted_rows[0].keys()) if newly_admitted_rows else [])
        writer.writeheader()
        writer.writerows(newly_admitted_rows)

    matrix_rows: list[dict[str, Any]] = []
    grouped_matrix: dict[tuple[float, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in newly_admitted_rows:
        grouped_matrix[(row["tested_threshold"], row["symbol"], row["regime"])].append(row)
    for (threshold, symbol, regime), rows in sorted(grouped_matrix.items()):
        fav15 = [row["favorable_direction_15m"] for row in rows if row["favorable_direction_15m"] is not None]
        fav60 = [row["favorable_direction_60m"] for row in rows if row["favorable_direction_60m"] is not None]
        same_side = sum(1 for row in rows if row["same_side_under_strict_flag"])
        matrix_rows.append(
            {
                "tested_threshold": threshold,
                "symbol": symbol,
                "regime": regime,
                "newly_admitted_count": len(rows),
                "favorable_15m_rate": _pct(sum(1 for v in fav15 if v), len(fav15)),
                "favorable_60m_rate": _pct(sum(1 for v in fav60 if v), len(fav60)),
                "noise_risk_proxy": "HIGH" if (regime == "TREND_DOWN" and len(rows) >= 3) or (fav15 and _pct(sum(1 for v in fav15 if v), len(fav15)) < 0.4) else "MEDIUM" if regime == "TREND_DOWN" else "LOW",
                "concentration_warnings": "same_side_strict" if same_side == len(rows) else "",
            }
        )
    with (out_dir / "symbol_regime_ablation_matrix.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(matrix_rows[0].keys()) if matrix_rows else [])
        writer.writeheader()
        writer.writerows(matrix_rows)

    baseline_admissible_count = sum(1 for row in decisions if (_safe_float(row.get("regime_confidence_used")) or -1.0) >= BASELINE_THRESHOLD)
    baseline_epoch_rows = epoch_by_threshold[BASELINE_THRESHOLD]
    summary_rows: list[dict[str, Any]] = []
    for threshold in TESTED_THRESHOLDS:
        epoch_rows = epoch_by_threshold[threshold]
        threshold_new_rows = [row for row in newly_admitted_rows if row["tested_threshold"] == threshold]
        denied_count = sum(1 for row in decisions if (_safe_float(row.get("regime_confidence_used")) or -1.0) < threshold)
        admissible_count = sum(1 for row in decisions if (_safe_float(row.get("regime_confidence_used")) or -1.0) >= threshold)
        fav5 = [row["favorable_direction_5m"] for row in threshold_new_rows if row["favorable_direction_5m"] is not None]
        fav15 = [row["favorable_direction_15m"] for row in threshold_new_rows if row["favorable_direction_15m"] is not None]
        fav60 = [row["favorable_direction_60m"] for row in threshold_new_rows if row["favorable_direction_60m"] is not None]
        classifications = Counter(row["timing_classification"] for row in epoch_rows)
        trend_down_conc = _pct(sum(1 for row in threshold_new_rows if row["regime"] == "TREND_DOWN"), len(threshold_new_rows))
        mean_reversion_conc = _pct(sum(1 for row in threshold_new_rows if row["regime"] == "MEAN_REVERSION"), len(threshold_new_rows))

        favorable_15_rate = _pct(sum(1 for v in fav15 if v), len(fav15))
        favorable_60_rate = _pct(sum(1 for v in fav60 if v), len(fav60))
        likely_noise_risk = "BASELINE"
        if threshold != BASELINE_THRESHOLD:
            if len(threshold_new_rows) < 10:
                likely_noise_risk = "LOW_SAMPLE"
            elif (favorable_15_rate or 0.0) < 0.45 or (trend_down_conc or 0.0) > 0.5:
                likely_noise_risk = "HIGH"
            elif (favorable_60_rate or 0.0) >= 0.5 and (mean_reversion_conc or 0.0) >= 0.3:
                likely_noise_risk = "MODERATE"
            else:
                likely_noise_risk = "MEDIUM"
        confidence_of_estimate = "LOW"
        if len(threshold_new_rows) >= 30:
            confidence_of_estimate = "MEDIUM"
        if len(threshold_new_rows) >= 60:
            confidence_of_estimate = "HIGH"
        if threshold == BASELINE_THRESHOLD:
            confidence_of_estimate = "REFERENCE"

        summary_rows.append(
            {
                "tested_min_regime_confidence": threshold,
                "candidate_count": len(decisions),
                "denied_count": denied_count,
                "admissible_count": admissible_count,
                "delta_vs_baseline_admissible": admissible_count - baseline_admissible_count,
                "newly_admitted_count": len(threshold_new_rows),
                "otherwise_valid_fresh_entry_candidates": sum(1 for row in threshold_new_rows if not row["same_side_under_strict_flag"]),
                "avg_bars_stable_to_admissible": _mean([row["bars_stable_to_admissible"] for row in epoch_rows]),
                "median_bars_stable_to_admissible": _median([row["bars_stable_to_admissible"] for row in epoch_rows]),
                "avg_price_drift_to_admissible": _mean([row["price_drift_stable_to_admissible"] for row in epoch_rows]),
                "early_count": classifications.get("EARLY", 0),
                "mid_count": classifications.get("MID", 0),
                "late_count": classifications.get("LATE", 0) + classifications.get("POST_EXHAUSTION", 0),
                "unknown_count": classifications.get("UNKNOWN", 0),
                "favorable_5m_rate": _pct(sum(1 for v in fav5 if v), len(fav5)),
                "favorable_15m_rate": favorable_15_rate,
                "favorable_60m_rate": favorable_60_rate,
                "concentration_in_trend_down": trend_down_conc,
                "concentration_in_mean_reversion": mean_reversion_conc,
                "likely_noise_risk": likely_noise_risk,
                "confidence_of_estimate": confidence_of_estimate,
            }
        )
    with (out_dir / "regime_conf_ablation_summary.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()) if summary_rows else [])
        writer.writeheader()
        writer.writerows(summary_rows)

    best_row = None
    for row in summary_rows:
        if row["tested_min_regime_confidence"] == BASELINE_THRESHOLD:
            continue
        if row["likely_noise_risk"] == "HIGH":
            continue
        if (row["favorable_15m_rate"] or 0.0) < 0.5:
            continue
        if best_row is None or row["newly_admitted_count"] > best_row["newly_admitted_count"]:
            best_row = row

    recommendation_lines = [
        "# R3 Threshold Recommendation",
        "",
        "## Facts",
        f"- Baseline `min_regime_confidence` is `{BASELINE_THRESHOLD}` from `config/aurora/domains.yaml` and is consumed by `apps/reference/domains/decision_making/safety_gates.py` gate 1.",
        f"- Tested values: `{', '.join(f'{v:.2f}' for v in TESTED_THRESHOLDS)}`.",
        "",
        "## Recommendation",
    ]
    if best_row is None:
        recommendation_lines.append("- No tested lower value shows a convincing quality-preserving improvement from proxy evidence alone.")
        recommendation_lines.append("- Baseline strictness is not disproven by this package.")
    else:
        recommendation_lines.append(
            f"- Best bounded candidate range is around `{best_row['tested_min_regime_confidence']:.2f}`."
        )
        recommendation_lines.append(
            f"- Reason: it adds `{best_row['newly_admitted_count']}` newly admitted candidates with `favorable_15m_rate={best_row['favorable_15m_rate']}` and `favorable_60m_rate={best_row['favorable_60m_rate']}` while avoiding the highest noise-risk bucket."
        )
        recommendation_lines.append("- This is a shadow-calibration candidate only, not a deployment recommendation.")
    recommendation_lines.extend(
        [
            "",
            "## Unproven",
            "- Short-horizon favorable motion is not full trade profitability proof.",
            "- This package does not prove production-safe execution quality after admission increases.",
            "",
            "## Next",
            "- If a lower range looks promising, the next justified package is shadow calibration of `min_regime_confidence` only.",
            "- `min_confidence`, `signal_threshold`, horizons, and detector logic are still not justified targets from this package alone.",
        ]
    )
    (out_dir / "R3_threshold_recommendation.md").write_text("\n".join(recommendation_lines) + "\n", encoding="utf-8")

    summary_lookup = {row["tested_min_regime_confidence"]: row for row in summary_rows}
    md_lines = [
        "# R3 - min_regime_confidence Confidence Ablation",
        "",
        "## Problem Framing",
        "This package tests only one hypothesis: whether the current `min_regime_confidence` value suppresses economically valid opportunities before they become actionable.",
        "",
        "## Facts",
        f"- Baseline config value is `0.42` in `config/aurora/domains.yaml`.",
        "- Gate owner and consumer path is `domains.decision_making.directional_sanity.min_regime_confidence` -> `apps/reference/domains/decision_making/safety_gates.py` gate 1.",
        f"- Live decision rows analyzed: `{len(decisions)}`.",
        f"- Baseline gate-1 blocked rows analyzed: `{len(baseline_rows)}`.",
        f"- Tested values: `{', '.join(f'{v:.2f}' for v in TESTED_THRESHOLDS)}`.",
        "",
        "## Inferences",
    ]
    if best_row is None:
        md_lines.append("- No tested lower value produced a strong enough proxy improvement to justify a preferred lower range from this package alone.")
    else:
        md_lines.append(
            f"- Lowering to `{best_row['tested_min_regime_confidence']:.2f}` appears to be the best bounded trade-off in this sweep, but only as a shadow-test candidate."
        )
    md_lines.extend(
        [
            "- Admission volume alone is not economic proof; quality proxies must stay attached to every ablation point.",
            "",
            "## Assumptions",
            "- Newly admitted candidates are defined as baseline gate-1 blocks whose `regime_confidence_used` would pass the lower tested threshold.",
            "- Quality uses 5m/15m/60m directional price proxies from available bar-close data.",
            "- `baseline_later_entry_ts` is proxied by the next same-symbol same-direction proposed intent or placed order in the baseline logs.",
            "",
            "## Unknowns",
            "- This package does not prove full realized trade PnL for newly admitted candidates.",
            "- It does not prove downstream execution, hold, or exit quality after admission increases.",
            "",
            "## Baseline Threshold Chain Context",
            "- `min_regime_confidence` is the first explicit confidence gate.",
            "- `min_confidence`, score thresholding, flip semantics, and horizons were held fixed by design.",
            "",
            "## Tested Values",
        ]
    )
    for row in summary_rows:
        md_lines.append(
            f"- `{row['tested_min_regime_confidence']:.2f}`: newly_admitted=`{row['newly_admitted_count']}`, favorable_15m=`{row['favorable_15m_rate']}`, favorable_60m=`{row['favorable_60m_rate']}`, noise_risk=`{row['likely_noise_risk']}`"
        )
    md_lines.extend(
        [
            "",
            "## Admission-Volume Impact",
            f"- Baseline admissible count: `{summary_lookup[BASELINE_THRESHOLD]['admissible_count']}`.",
        ]
    )
    for row in summary_rows:
        if row["tested_min_regime_confidence"] == BASELINE_THRESHOLD:
            continue
        md_lines.append(
            f"- `{row['tested_min_regime_confidence']:.2f}` adds `{row['delta_vs_baseline_admissible']}` gate-1-admissible decision rows and `{row['newly_admitted_count']}` newly admitted baseline-blocked candidates."
        )
    md_lines.extend(["", "## Timing Impact"])
    for row in summary_rows:
        md_lines.append(
            f"- `{row['tested_min_regime_confidence']:.2f}`: avg_bars=`{row['avg_bars_stable_to_admissible']}`, median_bars=`{row['median_bars_stable_to_admissible']}`, early/mid/late/unknown=`{row['early_count']}/{row['mid_count']}/{row['late_count']}/{row['unknown_count']}`"
        )
    md_lines.extend(["", "## Quality-Proxy Impact"])
    for row in summary_rows:
        if row["tested_min_regime_confidence"] == BASELINE_THRESHOLD:
            continue
        md_lines.append(
            f"- `{row['tested_min_regime_confidence']:.2f}`: favorable_5m=`{row['favorable_5m_rate']}`, favorable_15m=`{row['favorable_15m_rate']}`, favorable_60m=`{row['favorable_60m_rate']}`, TREND_DOWN_concentration=`{row['concentration_in_trend_down']}`, MEAN_REVERSION_concentration=`{row['concentration_in_mean_reversion']}`"
        )
        md_lines.extend(
        [
            "",
            "## Counterfactual Band Report",
            f"- Proposed band: `{band_report['band']['lower']:.2f}-{band_report['band']['upper']:.2f}`",
            f"- Total inspected: `{band_report['totals'].get('total_inspected', 0)}`",
            f"- Below min: `{band_report['totals'].get('below_min', 0)}`",
            f"- Inside band: `{band_report['totals'].get('inside_band', 0)}`",
            f"- Above max: `{band_report['totals'].get('above_max', 0)}`",
            f"- Current NRR-026 rows inside band: `{band_report['totals'].get('current_nrr_026_within_band', 0)}`",
            f"- Currently allowed but would above max: `{band_report['totals'].get('currently_allowed_but_would_above_max', 0)}`",
            f"- Currently other-rejected but would first-block above max: `{band_report['totals'].get('currently_other_rejected_but_would_first_block_above_max', 0)}`",
            "",
        ]
    )
    md_lines.extend(
        [
            "",
            "## Risk Of Over-Admission",
            "- Over-admission risk is flagged when newly admitted flow concentrates in historically weak regime buckets such as `TREND_DOWN` or when favorable-direction rates fall below roughly coin-flip quality.",
            "- Same-side strict-position add-on cases are tracked separately and do not count as fresh-entry opportunity evidence.",
            "",
            "## Verdict",
        ]
    )
    if best_row is None:
        md_lines.append("- Baseline strictness is not disproven. No tested lower threshold provides a convincing improvement from this bounded proxy evidence.")
    else:
        md_lines.append(
            f"- There is bounded evidence of under-admission at baseline, and the best next shadow-test range is around `{best_row['tested_min_regime_confidence']:.2f}`."
        )
        md_lines.append("- This is not a production recommendation.")
    (out_dir / "R3_MIN_REGIME_CONFIDENCE_ABLATION.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    completion_lines = [
        "# R3 Completion Report",
        "",
        "## Proven",
        f"- Lowering `min_regime_confidence` increases gate-1 admissible flow relative to the `{BASELINE_THRESHOLD}` baseline.",
        "- The package quantifies timing and short-horizon quality proxies for newly admitted candidates while keeping all other variables fixed.",
        "",
        "## Unproven",
        "- Full realized trade profitability of newly admitted candidates.",
        "- Production-safe deployment of any lower threshold.",
        "",
        "## Next Package",
    ]
    if best_row is None:
        completion_lines.append("- No lower range is strong enough yet; the next justified package is a downstream hold-quality package, not a threshold deployment step.")
    else:
        completion_lines.append("- The next justified package is shadow calibration of `min_regime_confidence` only.")
    completion_lines.extend(
        [
            "",
            "## Still Not Justified",
            "- `min_confidence` ablation is not justified from this package alone.",
            "- `signal_threshold` changes are not justified.",
            "- Horizon changes are not justified.",
            "- Regime-detector rewrites are not justified.",
        ]
    )
    (out_dir / "R3_COMPLETION_REPORT.md").write_text("\n".join(completion_lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "baseline_rows": len(baseline_rows),
                "decisions": len(decisions),
                "tested_thresholds": TESTED_THRESHOLDS,
                "best_threshold": None if best_row is None else best_row["tested_min_regime_confidence"],
                "counterfactual_band_report": band_report,
                "regime_filter": regime_filter or None,
                "out_dir": str(out_dir),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
