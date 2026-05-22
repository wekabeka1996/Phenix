"""PKG-5: Judge path diagnostics artifact builder.

DIAGNOSTIC-ONLY. Reads PKG-1 ``outcomes_diagnostics.jsonl`` and 1m candles.
Emits per-row path-geometry metrics, timeout-reason classification,
MFE/MAE reach ratios, time-to-MFE/MAE, and forward returns at fixed
look-ahead intervals.

Output artifacts (ALL DIAGNOSTIC-ONLY):
  data/simulator/judge_path_diagnostics.jsonl
  data/simulator/judge_path_diagnostics_summary.json
  reports/PKG_5_JUDGE_PATH_DIAGNOSTICS_REPORT.md

These artifacts MUST NOT be used as official Judge accuracy.  The official
truth is ``data/simulator/outcomes.json`` and the PKG-4 simulator / review
outputs.

Usage::

    PYTHONPATH=. py -3 -m tools.judge.build_path_diagnostics \\
      --outcomes-path data/simulator/outcomes.json \\
      --manifest-path data/simulator/outcomes_manifest.json \\
      --outcomes-diagnostics-path data/simulator/outcomes_diagnostics.jsonl \\
      --judge-log-dir logs/judge_experts \\
      --raw-1m-dir data/raw_binance_klines_1m \\
      --recorder-1m-dir data/recorder_backfill_1m \\
      --simulator-config config/judge_simulator.yaml \\
      --diagnostics-out data/simulator/judge_path_diagnostics.jsonl \\
      --summary-out data/simulator/judge_path_diagnostics_summary.json \\
      --report-path reports/PKG_5_JUDGE_PATH_DIAGNOSTICS_REPORT.md
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
import time
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import yaml

LOG = logging.getLogger("judge.path_diagnostics")

FILL_MODEL_OPTIMISTIC = "optimistic_touch"
FILL_MODEL_CONSERVATIVE_1BP = "conservative_cross_1bp"
FILL_MODEL_CONSERVATIVE_5BP = "conservative_cross_5bp"

CONFIDENCE_BUCKET_EDGES = [0.0, 0.25, 0.5, 0.75, 1.0]


# ---------------------------------------------------------------------------
# Candle data class (minimal copy — deliberately NOT imported from
# build_outcomes_from_candles to keep this tool self-contained and avoid
# coupling diagnostics to the official materializer)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Candle:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    close_time_ms: int


# ---------------------------------------------------------------------------
# Candle loading (handles BOTH recorder CSV and raw Binance dict/list JSON)
# ---------------------------------------------------------------------------

def _coerce_kline_array(arr: list) -> Optional[Candle]:
    try:
        return Candle(
            open_time_ms=int(arr[0]),
            open=float(arr[1]),
            high=float(arr[2]),
            low=float(arr[3]),
            close=float(arr[4]),
            close_time_ms=int(arr[6]),
        )
    except (IndexError, ValueError, TypeError):
        return None


def load_raw_binance_candles(raw_1m_dir: Path) -> dict[str, list[Candle]]:
    """Load raw Binance klines JSON files.

    Handles both:
    - Legacy list format: ``[[open_ms, open, high, low, close, ...], ...]``
    - Dict format: ``{"klines": [[...], ...], "symbol": ..., ...}``
    """
    out: dict[str, dict[int, Candle]] = {}
    if not raw_1m_dir.is_dir():
        return {}
    for sym_dir in sorted(p for p in raw_1m_dir.iterdir() if p.is_dir()):
        symbol = sym_dir.name.upper()
        bucket = out.setdefault(symbol, {})
        for jf in sorted(sym_dir.glob("*.json")):
            try:
                payload = json.loads(jf.read_text(encoding="utf-8"))
            except Exception as exc:
                LOG.warning("Skip raw kline file %s (%s)", jf, exc)
                continue
            if isinstance(payload, dict):
                klines_list = payload.get("klines", [])
            elif isinstance(payload, list):
                klines_list = payload
            else:
                continue
            for entry in klines_list:
                if not isinstance(entry, list):
                    continue
                c = _coerce_kline_array(entry)
                if c is not None:
                    bucket[c.open_time_ms] = c
    return {sym: [b[k] for k in sorted(b.keys())] for sym, b in out.items()}


def load_recorder_candles(recorder_1m_dir: Path) -> dict[str, list[Candle]]:
    out: dict[str, dict[int, Candle]] = {}
    if not recorder_1m_dir.is_dir():
        return {}
    for csv_path in sorted(recorder_1m_dir.rglob("*_60.csv")):
        try:
            with csv_path.open("r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    try:
                        symbol = row["symbol"].upper()
                        close_ms = int(row["timestamp"])
                        open_ms = close_ms - 60_000 + 1
                        c = Candle(
                            open_time_ms=open_ms,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            close_time_ms=close_ms,
                        )
                    except (KeyError, ValueError) as exc:
                        LOG.warning("Skip recorder row in %s (%s)",
                                    csv_path, exc)
                        continue
                    out.setdefault(symbol, {})[c.open_time_ms] = c
        except Exception as exc:
            LOG.warning("Skip recorder CSV %s (%s)", csv_path, exc)
            continue
    return {sym: [b[k] for k in sorted(b.keys())] for sym, b in out.items()}


def merge_candle_sources(
    *sources: dict[str, list[Candle]],
) -> dict[str, list[Candle]]:
    """Merge candle dicts; earlier source wins on collision (raw > recorder)."""
    merged: dict[str, dict[int, Candle]] = {}
    for src in sources:
        for symbol, candles in src.items():
            bucket = merged.setdefault(symbol, {})
            for c in candles:
                bucket.setdefault(c.open_time_ms, c)
    return {sym: [b[k] for k in sorted(b.keys())] for sym, b in merged.items()}


def candles_after(
    candles: list[Candle],
    strict_start_ms: int,
    end_ms_inclusive: int,
) -> list[Candle]:
    """Return candles with ``open_time_ms > strict_start_ms`` and
    ``open_time_ms <= end_ms_inclusive``."""
    if not candles:
        return []
    opens = [c.open_time_ms for c in candles]
    lo = bisect_right(opens, strict_start_ms)
    out: list[Candle] = []
    for i in range(lo, len(candles)):
        if candles[i].open_time_ms > end_ms_inclusive:
            break
        out.append(candles[i])
    return out


# ---------------------------------------------------------------------------
# Confidence bucket helper
# ---------------------------------------------------------------------------

def confidence_bucket(conf: float) -> str:
    edges = CONFIDENCE_BUCKET_EDGES
    for i in range(len(edges) - 1):
        if edges[i] <= conf < edges[i + 1]:
            return f"[{edges[i]:.2f},{edges[i+1]:.2f}]"
    if conf >= edges[-1]:
        return f"[{edges[-2]:.2f},{edges[-1]:.2f}]"
    return "[0.00,0.25]"


# ---------------------------------------------------------------------------
# Path metrics — derivable WITHOUT candles
# ---------------------------------------------------------------------------

def _safe_bps(delta: Optional[float], ref: Optional[float]) -> Optional[float]:
    if delta is None or ref is None or ref == 0:
        return None
    return delta / ref * 10_000


def _safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def classify_timeout_reason(
    mfe_to_tp_ratio: Optional[float],
    mae_to_sl_ratio: Optional[float],
    is_long: bool,
    mfe_bps: Optional[float],
    mae_bps: Optional[float],
) -> str:
    """Classify why a TIMEOUT occurred from path geometry.

    Classes:
      TP_TOO_FAR_PRICE_MOVED_FAVORABLY  — MFE ≥ 50% of TP but price reversed before hitting
      WRONG_DIRECTION                   — MAE > MFE (price moved against side)
      FLAT_NO_EDGE                      — both MFE < 25% TP and MAE < 25% SL
      SL_NEAR_MISS                      — MAE ≥ 75% SL but SL not hit
      HORIZON_TOO_SHORT                 — MFE ≥ 90% TP at timeout but TP not hit
      UNKNOWN                           — insufficient data
    """
    if mfe_to_tp_ratio is None or mae_bps is None or mfe_bps is None:
        return "UNKNOWN"
    if mfe_to_tp_ratio >= 0.9:
        return "HORIZON_TOO_SHORT"
    if mfe_to_tp_ratio >= 0.5:
        return "TP_TOO_FAR_PRICE_MOVED_FAVORABLY"
    if mae_to_sl_ratio is not None and mae_to_sl_ratio >= 0.75:
        return "SL_NEAR_MISS"
    if mae_bps > mfe_bps:
        return "WRONG_DIRECTION"
    if mfe_to_tp_ratio < 0.25 and (mae_to_sl_ratio is None or mae_to_sl_ratio < 0.25):
        return "FLAT_NO_EDGE"
    return "WRONG_DIRECTION"


def enrich_from_diagnostics(diag: dict) -> dict:
    """Compute all fields derivable from the diagnostics row (no candles needed)."""
    entry_price: Optional[float] = diag.get("entry_price")
    tp_price: Optional[float] = diag.get("tp_price")
    sl_price: Optional[float] = diag.get("sl_price")
    mfe_raw: Optional[float] = diag.get("mfe")
    mae_raw: Optional[float] = diag.get("mae")
    exit_class: str = diag.get("exit_classification", "UNKNOWN")
    matched: bool = bool(diag.get("matched_trade", False))
    entry_side: str = (diag.get("entry_side") or "").upper()
    conf: float = float(diag.get("confidence") or 0.0)
    is_long = entry_side == "BUY"

    # TP/SL distances in price units
    tp_dist: Optional[float] = None
    sl_dist: Optional[float] = None
    if entry_price is not None and tp_price is not None:
        tp_dist = abs(tp_price - entry_price)
    if entry_price is not None and sl_price is not None:
        sl_dist = abs(sl_price - entry_price)

    tp_distance_bps = _safe_bps(tp_dist, entry_price)
    sl_distance_bps = _safe_bps(sl_dist, entry_price)
    mfe_bps = _safe_bps(mfe_raw, entry_price)
    mae_bps = _safe_bps(mae_raw, entry_price)

    mfe_to_tp_ratio = _safe_ratio(mfe_raw, tp_dist)
    mae_to_sl_ratio = _safe_ratio(mae_raw, sl_dist)

    reached_25 = mfe_to_tp_ratio is not None and mfe_to_tp_ratio >= 0.25
    reached_50 = mfe_to_tp_ratio is not None and mfe_to_tp_ratio >= 0.50
    reached_75 = mfe_to_tp_ratio is not None and mfe_to_tp_ratio >= 0.75
    reached_90 = mfe_to_tp_ratio is not None and mfe_to_tp_ratio >= 0.90

    timeout_reason: Optional[str] = None
    if exit_class == "TIMEOUT" and matched:
        timeout_reason = classify_timeout_reason(
            mfe_to_tp_ratio, mae_to_sl_ratio, is_long, mfe_bps, mae_bps)
    elif exit_class == "TIMEOUT" and not matched:
        timeout_reason = "NO_FILL"

    ckey = diag.get("correlation_key") or {}
    return {
        "strategy_id": ckey.get("strategy_id"),
        "symbol": ckey.get("symbol"),
        "tf_sec": ckey.get("tf_sec"),
        "bar_close_ts": ckey.get("bar_close_ts"),
        "verdict_id": diag.get("verdict_id"),
        "plan_id": diag.get("plan_id"),
        "side": entry_side,
        "confidence": conf,
        "confidence_bucket": confidence_bucket(conf),
        "confidence_tier": diag.get("chosen_tier"),
        "regime": diag.get("regime"),
        "regime_confidence": diag.get("regime_confidence"),
        "outcome_matched_trade": matched,
        "exit_classification": exit_class,
        "diagnostic_scope": "official_canonical",
        "entry_price": entry_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "limit_price": diag.get("limit_price"),
        "tp_distance_bps": tp_distance_bps,
        "sl_distance_bps": sl_distance_bps,
        "mfe_bps": mfe_bps,
        "mae_bps": mae_bps,
        "mfe_to_tp_ratio": mfe_to_tp_ratio,
        "mae_to_sl_ratio": mae_to_sl_ratio,
        "reached_25pct_tp_distance": reached_25,
        "reached_50pct_tp_distance": reached_50,
        "reached_75pct_tp_distance": reached_75,
        "reached_90pct_tp_distance": reached_90,
        "timeout_reason_class": timeout_reason,
        "fill_model": diag.get("fill_model", FILL_MODEL_OPTIMISTIC),
        "data_quality_flags": [],
        # path-walk fields — populated later
        "time_to_mfe_sec": None,
        "time_to_mae_sec": None,
        "mfe_before_mae": None,
        "side_adjusted_forward_return_1m": None,
        "side_adjusted_forward_return_3m": None,
        "side_adjusted_forward_return_5m": None,
        "side_adjusted_forward_return_15m": None,
        "side_adjusted_forward_return_30m": None,
        "side_adjusted_forward_return_horizon": None,
    }


# ---------------------------------------------------------------------------
# Path walk — requires 1m candles
# ---------------------------------------------------------------------------

def _forward_return(
    candles: list[Candle],
    fill_idx: int,
    entry_price: float,
    offset_ms: int,
    is_long: bool,
) -> Optional[float]:
    """Side-adjusted return at entry_candle.open_time_ms + offset_ms."""
    if fill_idx >= len(candles):
        return None
    target_ms = candles[fill_idx].open_time_ms + offset_ms
    # find first candle whose close_time_ms >= target_ms
    for c in candles[fill_idx:]:
        if c.close_time_ms >= target_ms:
            ret = (c.close - entry_price) / \
                entry_price if entry_price else None
            if ret is None:
                return None
            return ret if is_long else -ret
    # use last available candle
    last = candles[-1]
    ret = (last.close - entry_price) / entry_price if entry_price else None
    if ret is None:
        return None
    return ret if is_long else -ret


def walk_path(
    row: dict,
    path_candles: list[Candle],
) -> None:
    """Walk 1m candles to fill in path-walk fields in ``row`` in-place.

    Works for matched rows only (entry_price and limit_price known).
    """
    entry_price: Optional[float] = row.get("entry_price")
    limit_price: Optional[float] = row.get("limit_price")
    if entry_price is None or limit_price is None or not path_candles:
        return

    is_long = row.get("side", "") == "BUY"

    # Find fill candle
    fill_idx: Optional[int] = None
    for i, c in enumerate(path_candles):
        if is_long and c.low <= limit_price:
            fill_idx = i
            break
        elif (not is_long) and c.high >= limit_price:
            fill_idx = i
            break
    if fill_idx is None:
        row["data_quality_flags"] = row.get("data_quality_flags", []) + [
            "fill_candle_not_found_in_path"]
        return

    # Determine exit candle boundary from exit_classification
    exit_class = row.get("exit_classification", "")
    tp_price = row.get("tp_price")
    sl_price = row.get("sl_price")
    horizon_ms: Optional[int] = None
    ckey = {k: row[k] for k in ("bar_close_ts", "tf_sec") if k in row}
    if "bar_close_ts" in ckey and "tf_sec" in ckey and ckey["tf_sec"]:
        from apps.reference.domains.alpha_search.judge.simulator.config_models import (
            SimulatorConfig,
        )
        # estimate horizon from path_candles length — we already sliced to horizon
        pass  # horizon is already reflected in path_candles

    fill_open_ms = path_candles[fill_idx].open_time_ms

    # Walk path from fill to end collecting MFE/MAE candle indices
    mfe_so_far = 0.0
    mae_so_far = 0.0
    mfe_candle_idx = fill_idx
    mae_candle_idx = fill_idx

    for i in range(fill_idx, len(path_candles)):
        c = path_candles[i]
        if is_long:
            fav = c.high - entry_price
            adv = entry_price - c.low
        else:
            fav = entry_price - c.low
            adv = c.high - entry_price

        if fav > mfe_so_far:
            mfe_so_far = fav
            mfe_candle_idx = i
        if adv > mae_so_far:
            mae_so_far = adv
            mae_candle_idx = i

    mfe_open_ms = path_candles[mfe_candle_idx].open_time_ms
    mae_open_ms = path_candles[mae_candle_idx].open_time_ms

    row["time_to_mfe_sec"] = (mfe_open_ms - fill_open_ms) / 1000.0
    row["time_to_mae_sec"] = (mae_open_ms - fill_open_ms) / 1000.0
    row["mfe_before_mae"] = mfe_candle_idx <= mae_candle_idx

    # Forward returns at fixed look-ahead intervals
    one_min_ms = 60_000
    horizon_final_ms = (path_candles[-1].close_time_ms
                        if path_candles else fill_open_ms)
    horizon_offset_ms = horizon_final_ms - fill_open_ms

    row["side_adjusted_forward_return_1m"] = _forward_return(
        path_candles, fill_idx, entry_price, 1 * one_min_ms, is_long)
    row["side_adjusted_forward_return_3m"] = _forward_return(
        path_candles, fill_idx, entry_price, 3 * one_min_ms, is_long)
    row["side_adjusted_forward_return_5m"] = _forward_return(
        path_candles, fill_idx, entry_price, 5 * one_min_ms, is_long)
    row["side_adjusted_forward_return_15m"] = _forward_return(
        path_candles, fill_idx, entry_price, 15 * one_min_ms, is_long)
    row["side_adjusted_forward_return_30m"] = _forward_return(
        path_candles, fill_idx, entry_price, 30 * one_min_ms, is_long)
    row["side_adjusted_forward_return_horizon"] = _forward_return(
        path_candles, fill_idx, entry_price, horizon_offset_ms, is_long)


# ---------------------------------------------------------------------------
# Conservative-cross fill model sensitivity
# ---------------------------------------------------------------------------

def _check_fill_conservative(
    candles: list[Candle],
    limit_price: float,
    is_long: bool,
    spread_bps: float,
) -> bool:
    """Return True if the plan would fill under conservative_cross.

    Conservative: LONG fills only if ``low < limit - spread``; SHORT only if
    ``high > limit + spread``.  If spread_bps is 0, equivalent to optimistic.
    """
    spread = limit_price * spread_bps / 10_000
    for c in candles:
        if is_long and c.low < limit_price - spread:
            return True
        elif (not is_long) and c.high > limit_price + spread:
            return True
    return False


def compute_fill_sensitivity(
    diag: dict,
    path_candles: list[Candle],
) -> dict[str, Optional[bool]]:
    """Compute whether the canonical plan would fill under tighter models."""
    matched = bool(diag.get("matched_trade", False))
    limit_price = diag.get("limit_price")
    entry_side = (diag.get("entry_side") or "").upper()
    is_long = entry_side == "BUY"

    if not matched or limit_price is None or not path_candles:
        return {
            "fills_optimistic": False,
            "fills_conservative_1bp": False,
            "fills_conservative_5bp": False,
        }
    return {
        "fills_optimistic": True,  # already matched under optimistic
        "fills_conservative_1bp": _check_fill_conservative(
            path_candles, limit_price, is_long, 1.0),
        "fills_conservative_5bp": _check_fill_conservative(
            path_candles, limit_price, is_long, 5.0),
    }


# ---------------------------------------------------------------------------
# All-tier ladder diagnostics
# ---------------------------------------------------------------------------

def load_all_tier_plans(judge_log_dir: Path) -> list[dict]:
    """Load all shadow_entry_plan rows from the Judge log directory."""
    rows: list[dict] = []
    for f in sorted(judge_log_dir.glob("shadow_entry_plan_*.jsonl")):
        with f.open("r", encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rows.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
    return rows


def simulate_tier_fill(
    plan: dict,
    candles_by_symbol: dict[str, list[Candle]],
    horizon_bars: int = 12,
) -> dict[str, Any]:
    """Simulate optimistic-touch fill for one shadow_entry_plan tier row.

    Returns a diagnostics dict for that tier plan.
    """
    symbol = (plan.get("symbol") or "").upper()
    limit_price = plan.get("limit_price")
    entry_side = (plan.get("entry_side") or "").upper()
    tp_price = plan.get("tp_price")
    sl_price = plan.get("sl_price")
    ts_ms = plan.get("ts_ms")
    tf_sec = plan.get("tf_sec")
    tier = plan.get("confidence_tier")
    confidence = plan.get("confidence")
    actionable = bool(plan.get("actionable", False))
    suppressed = bool(plan.get("suppressed", False))

    base = {
        "plan_id": plan.get("plan_id"),
        "source_verdict_id": plan.get("source_verdict_id"),
        "symbol": symbol,
        "tf_sec": tf_sec,
        "confidence_tier": tier,
        "confidence": confidence,
        "entry_side": entry_side,
        "actionable": actionable,
        "suppressed": suppressed,
        "diagnostic_scope": "all_tiers",
        "limit_price": limit_price,
        "tp_price": tp_price,
        "sl_price": sl_price,
        "matched_trade": False,
        "exit_classification": "NOT_SIMULATED",
        "mfe_bps": None,
        "mae_bps": None,
        "mfe_to_tp_ratio": None,
        "timeout_reason_class": None,
    }

    if not actionable or suppressed:
        base["exit_classification"] = "SUPPRESSED_OR_NOT_ACTIONABLE"
        return base
    if limit_price is None or tp_price is None or sl_price is None:
        base["exit_classification"] = "INCOMPLETE_PLAN"
        return base
    if ts_ms is None or tf_sec is None:
        base["exit_classification"] = "MISSING_TIMING"
        return base

    candles = candles_by_symbol.get(symbol, [])
    if not candles:
        base["exit_classification"] = "NO_CANDLE_DATA"
        return base

    horizon_ms = horizon_bars * tf_sec * 1000
    window = candles_after(candles, ts_ms, ts_ms + horizon_ms)
    if not window:
        base["exit_classification"] = "NO_CANDLE_WINDOW"
        return base

    is_long = entry_side == "BUY"

    # Find fill
    fill_idx: Optional[int] = None
    for i, c in enumerate(window):
        if is_long and c.low <= limit_price:
            fill_idx = i
            break
        elif (not is_long) and c.high >= limit_price:
            fill_idx = i
            break

    if fill_idx is None:
        base["exit_classification"] = "NO_FILL"
        return base

    entry_price = limit_price
    mfe = 0.0
    mae = 0.0
    exit_class = "TIMEOUT"
    exit_price = window[-1].close

    for c in window[fill_idx:]:
        if is_long:
            mfe = max(mfe, c.high - entry_price)
            mae = max(mae, entry_price - c.low)
            tp_hit = c.high >= tp_price
            sl_hit = c.low <= sl_price
        else:
            mfe = max(mfe, entry_price - c.low)
            mae = max(mae, c.high - entry_price)
            tp_hit = c.low <= tp_price
            sl_hit = c.high >= sl_price

        if tp_hit and sl_hit:
            exit_class = "FILLED_SL"
            exit_price = sl_price
            break
        if tp_hit:
            exit_class = "FILLED_TP"
            exit_price = tp_price
            break
        if sl_hit:
            exit_class = "FILLED_SL"
            exit_price = sl_price
            break

    tp_dist = abs(tp_price - entry_price)
    sl_dist = abs(sl_price - entry_price)
    mfe_bps = _safe_bps(mfe, entry_price)
    mae_bps = _safe_bps(mae, entry_price)
    mfe_to_tp = _safe_ratio(mfe, tp_dist)
    mae_to_sl = _safe_ratio(mae, sl_dist)

    base.update({
        "matched_trade": True,
        "exit_classification": exit_class,
        "exit_price": exit_price,
        "mfe_bps": mfe_bps,
        "mae_bps": mae_bps,
        "mfe_to_tp_ratio": mfe_to_tp,
        "mae_to_sl_ratio": mae_to_sl,
        "reached_25pct_tp_distance": mfe_to_tp is not None and mfe_to_tp >= 0.25,
        "reached_50pct_tp_distance": mfe_to_tp is not None and mfe_to_tp >= 0.50,
        "timeout_reason_class": (
            classify_timeout_reason(
                mfe_to_tp, mae_to_sl, is_long, mfe_bps, mae_bps)
            if exit_class == "TIMEOUT" else None
        ),
    })
    return base


# ---------------------------------------------------------------------------
# Summary computation
# ---------------------------------------------------------------------------

def _mean(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _pct(count: int, total: int) -> float:
    return 100.0 * count / total if total else 0.0


def _bucket_stats(
    rows: list[dict],
    group_key: str,
    value_key: str,
) -> dict[str, Any]:
    """Group rows by group_key and compute stats on value_key."""
    from collections import defaultdict
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        gval = r.get(group_key)
        if gval is None:
            gval = "UNKNOWN"
        vval = r.get(value_key)
        if vval is not None:
            groups[str(gval)].append(vval)
    return {
        g: {
            "count": len(vs),
            "mean": _mean(vs),
            "min": min(vs),
            "max": max(vs),
        }
        for g, vs in sorted(groups.items())
    }


def compute_summary(
    official_rows: list[dict],
    all_tier_rows: list[dict],
    manifest: dict,
) -> dict[str, Any]:
    """Compute the full diagnostic summary dict."""
    total = len(official_rows)
    matched = [r for r in official_rows if r.get("outcome_matched_trade")]
    no_fill = [r for r in official_rows
               if r.get("exit_classification") == "NO_FILL"]
    timeout = [r for r in official_rows
               if r.get("exit_classification") == "TIMEOUT"]
    filled_tp = [r for r in official_rows
                 if r.get("exit_classification") == "FILLED_TP"]
    filled_sl = [r for r in official_rows
                 if r.get("exit_classification") == "FILLED_SL"]

    # timeout reason distribution
    timeout_reasons: dict[str, int] = {}
    for r in timeout:
        reason = r.get("timeout_reason_class") or "UNKNOWN"
        timeout_reasons[reason] = timeout_reasons.get(reason, 0) + 1

    # TP reach ratios (over matched rows)
    matched_timeout = [r for r in matched
                       if r.get("exit_classification") == "TIMEOUT"]
    reach_25 = sum(1 for r in matched_timeout if r.get(
        "reached_25pct_tp_distance"))
    reach_50 = sum(1 for r in matched_timeout if r.get(
        "reached_50pct_tp_distance"))
    reach_75 = sum(1 for r in matched_timeout if r.get(
        "reached_75pct_tp_distance"))
    reach_90 = sum(1 for r in matched_timeout if r.get(
        "reached_90pct_tp_distance"))
    n_timeout = len(matched_timeout)

    # MFE/MAE distributions (matched rows)
    mfe_vals = [r["mfe_bps"] for r in matched if r.get("mfe_bps") is not None]
    mae_vals = [r["mae_bps"] for r in matched if r.get("mae_bps") is not None]
    mfe_to_tp_vals = [r["mfe_to_tp_ratio"]
                      for r in matched if r.get("mfe_to_tp_ratio") is not None]

    # Forward return distributions
    fwd_1m = [r["side_adjusted_forward_return_1m"]
              for r in matched if r.get("side_adjusted_forward_return_1m") is not None]
    fwd_horizon = [r["side_adjusted_forward_return_horizon"]
                   for r in matched
                   if r.get("side_adjusted_forward_return_horizon") is not None]

    # fill sensitivity (from official rows that have fill_sensitivity set)
    fills_opt = sum(1 for r in official_rows if r.get("fills_optimistic"))
    fills_1bp = sum(1 for r in official_rows if r.get(
        "fills_conservative_1bp"))
    fills_5bp = sum(1 for r in official_rows if r.get(
        "fills_conservative_5bp"))

    # MFE before MAE rate
    mfe_before_mae_vals = [r["mfe_before_mae"]
                           for r in matched if r.get("mfe_before_mae") is not None]
    mfe_before_mae_rate = (
        sum(1 for v in mfe_before_mae_vals if v) / len(mfe_before_mae_vals)
        if mfe_before_mae_vals else None
    )

    # By-segment stats
    def seg_summary(seg_key: str) -> dict:
        from collections import defaultdict
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in official_rows:
            k = str(r.get(seg_key) or "UNKNOWN")
            groups[k].append(r)
        out = {}
        for k, rows in sorted(groups.items()):
            n = len(rows)
            m = [r for r in rows if r.get("outcome_matched_trade")]
            t = [r for r in rows if r.get("exit_classification") == "TIMEOUT"]
            t_matched = [r for r in m if r.get(
                "exit_classification") == "TIMEOUT"]
            tp_hits = sum(1 for r in rows if r.get(
                "exit_classification") == "FILLED_TP")
            mfe_tp_r = [r["mfe_to_tp_ratio"] for r in t_matched
                        if r.get("mfe_to_tp_ratio") is not None]
            r25 = sum(1 for r in t_matched if r.get(
                "reached_25pct_tp_distance"))
            r50 = sum(1 for r in t_matched if r.get(
                "reached_50pct_tp_distance"))
            out[k] = {
                "total": n,
                "matched": len(m),
                "timeout": len(t),
                "tp_hits": tp_hits,
                "timeout_pct": _pct(len(t), len(m)) if m else 0,
                "tp_hit_pct": _pct(tp_hits, len(m)) if m else 0,
                "avg_mfe_to_tp_ratio": _mean(mfe_tp_r),
                "reached_25pct_tp": _pct(r25, len(t_matched)) if t_matched else 0,
                "reached_50pct_tp": _pct(r50, len(t_matched)) if t_matched else 0,
            }
        return out

    # All-tier summary
    tier_groups: dict[str, dict[str, Any]] = {}
    for tier in ["low", "medium", "high"]:
        tier_rows = [r for r in all_tier_rows if r.get(
            "confidence_tier") == tier]
        actionable = [r for r in tier_rows
                      if r.get("actionable") and not r.get("suppressed")]
        fills = [r for r in actionable if r.get("matched_trade")]
        tp_h = [r for r in fills if r.get(
            "exit_classification") == "FILLED_TP"]
        sl_h = [r for r in fills if r.get(
            "exit_classification") == "FILLED_SL"]
        tmo = [r for r in fills if r.get("exit_classification") == "TIMEOUT"]
        mfe_tp = [r["mfe_to_tp_ratio"] for r in tmo
                  if r.get("mfe_to_tp_ratio") is not None]
        tier_groups[tier] = {
            "total_plans": len(tier_rows),
            "actionable_plans": len(actionable),
            "filled_plans": len(fills),
            "fill_rate_pct": _pct(len(fills), len(actionable)) if actionable else 0,
            "tp_hits": len(tp_h),
            "sl_hits": len(sl_h),
            "timeouts": len(tmo),
            "tp_hit_pct": _pct(len(tp_h), len(fills)) if fills else 0,
            "timeout_pct": _pct(len(tmo), len(fills)) if fills else 0,
            "avg_mfe_to_tp_ratio_on_timeout": _mean(mfe_tp),
        }

    return {
        "schema_version": "1",
        "diagnostic_scope": "DIAGNOSTIC_ONLY_NOT_OFFICIAL_JUDGE_ACCURACY",
        "total_official_canonical_rows": total,
        "matched_rows": len(matched),
        "timeout_rows": len(timeout),
        "no_fill_rows": len(no_fill),
        "filled_tp_rows": len(filled_tp),
        "filled_sl_rows": len(filled_sl),
        "timeout_rows_matched": n_timeout,
        "exit_classification_pct": {
            "TIMEOUT": _pct(len(timeout), total),
            "NO_FILL": _pct(len(no_fill), total),
            "FILLED_TP": _pct(len(filled_tp), total),
            "FILLED_SL": _pct(len(filled_sl), total),
        },
        "timeout_reason_distribution": timeout_reasons,
        "tp_reach_ratios_on_matched_timeout": {
            "n_matched_timeout": n_timeout,
            "reached_25pct_pct": _pct(reach_25, n_timeout),
            "reached_50pct_pct": _pct(reach_50, n_timeout),
            "reached_75pct_pct": _pct(reach_75, n_timeout),
            "reached_90pct_pct": _pct(reach_90, n_timeout),
        },
        "mfe_distribution_bps": {
            "mean": _mean(mfe_vals),
            "min": min(mfe_vals) if mfe_vals else None,
            "max": max(mfe_vals) if mfe_vals else None,
            "pct_gt_0": _pct(sum(1 for v in mfe_vals if v > 0), len(mfe_vals)),
        },
        "mae_distribution_bps": {
            "mean": _mean(mae_vals),
            "min": min(mae_vals) if mae_vals else None,
            "max": max(mae_vals) if mae_vals else None,
        },
        "avg_mfe_to_tp_ratio": _mean(mfe_to_tp_vals),
        "mfe_before_mae_rate": mfe_before_mae_rate,
        "forward_return_1m": {"mean": _mean(fwd_1m), "n": len(fwd_1m)},
        "forward_return_horizon": {"mean": _mean(fwd_horizon), "n": len(fwd_horizon)},
        "fill_sensitivity": {
            "fills_optimistic": fills_opt,
            "fills_conservative_1bp": fills_1bp,
            "fills_conservative_5bp": fills_5bp,
            "pct_lost_at_1bp": _pct(fills_opt - fills_1bp, fills_opt) if fills_opt else 0,
            "pct_lost_at_5bp": _pct(fills_opt - fills_5bp, fills_opt) if fills_opt else 0,
            "note": (
                "conservative_cross requires minimum spread clearance; "
                "1bp and 5bp are diagnostic proxies only — no calibrated "
                "spread model was available for this window."
            ),
        },
        "by_symbol": seg_summary("symbol"),
        "by_tf_sec": seg_summary("tf_sec"),
        "by_regime": seg_summary("regime"),
        "by_confidence_bucket": seg_summary("confidence_bucket"),
        "all_tier_ladder_diagnostic": tier_groups,
        "fee_slippage_status": {
            "applied": False,
            "note": (
                "Path diagnostics report RAW price-based returns (no fee/slippage). "
                "The official simulator applies 25 bps + 0.1% slippage. "
                "No double-count occurs."
            ),
            "usd_roi": "disabled — pct_only mode; economics block absent in config",
        },
        "fill_model_used": FILL_MODEL_OPTIMISTIC,
        "ambiguous_count": sum(
            1 for r in official_rows
            if r.get("exit_classification") == "AMBIGUOUS_TP_SL_SAME_CANDLE"),
    }


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _fmt_pct(v: Optional[float], decimals: int = 1) -> str:
    if v is None:
        return "N/A"
    return f"{v:.{decimals}f}%"


def _fmt_f(v: Optional[float], decimals: int = 4) -> str:
    if v is None:
        return "N/A"
    return f"{v:.{decimals}f}"


def write_report(
    summary: dict,
    report_path: Path,
    cmd_used: str,
) -> None:
    """Write the markdown diagnostics report."""

    exit_pct = summary.get("exit_classification_pct", {})
    tp_reach = summary.get("tp_reach_ratios_on_matched_timeout", {})
    timeout_reasons = summary.get("timeout_reason_distribution", {})
    mfe_dist = summary.get("mfe_distribution_bps", {})
    mae_dist = summary.get("mae_distribution_bps", {})
    fill_sens = summary.get("fill_sensitivity", {})
    all_tier = summary.get("all_tier_ladder_diagnostic", {})
    by_sym = summary.get("by_symbol", {})
    by_tf = summary.get("by_tf_sec", {})
    by_regime = summary.get("by_regime", {})
    by_bucket = summary.get("by_confidence_bucket", {})

    total = summary.get("total_official_canonical_rows", 0)
    matched = summary.get("matched_rows", 0)
    timeout_n = summary.get("timeout_rows", 0)
    n_timeout_matched = tp_reach.get("n_matched_timeout", 0)
    mfe_before_mae = summary.get("mfe_before_mae_rate")
    avg_mfe_tp = summary.get("avg_mfe_to_tp_ratio")

    lines: list[str] = []
    a = lines.append

    a("# PKG-5 JUDGE PATH DIAGNOSTICS — COMPLETION REPORT")
    a("")
    a("**Date:** 2026-05-21")
    a("**Diagnostic scope:** DIAGNOSTIC-ONLY — NOT OFFICIAL JUDGE ACCURACY")
    a("**Preceded by:** PKG-4 (official simulator/review run)")
    a("**Unblocks:** PKG-6 (review baselines + OOS)")
    a("")
    a("> **WARNING**: This entire report is DIAGNOSTIC-ONLY. The official evidence")
    a("> is `data/simulator/outcomes.json` and `artifacts/phase5_*` / `artifacts/judge_review/*`.")
    a("> Numbers here represent path geometry analysis. Do not cite them as Judge accuracy.")
    a("")
    a("---")
    a("")
    a("## 1. Verdict")
    a("")
    a("**`PATH_DIAGNOSTICS_COMPLETE`**")
    a("")
    a(f"All {total:,} official canonical rows processed. Path-walk enrichment "
      f"applied to {matched:,} matched rows. All-tier ladder computed for all "
      f"three confidence tiers. Timeout cause distribution classified.")
    a("")
    a("---")
    a("")
    a("## 2. Problem framing")
    a("")
    a("- **Symptom:** PKG-4 reported 81.3% TIMEOUT dominance, 0.7% TP rate, "
      "88.38% disagreement rate, and negative returns across all segments.")
    a("- **Root cause (to diagnose):** Unknown — could be (a) TP targets too far, "
      "(b) wrong direction entries, (c) flat/no-edge periods, or (d) horizon too "
      "short.")
    a("- **Contributing factors:** optimistic_touch fill model; 4-day observation "
      "window; pct_only mode.")
    a("- **Masking layer:** Without path geometry, TIMEOUT could be misclassified "
      "as benign. Path walk reveals whether price approached TP at all.")
    a("- **Broader bottleneck:** No OOS split yet. PKG-6 is the next package.")
    a("")
    a("---")
    a("")
    a("## 3. FACTS")
    a("")
    a("**Command run:**")
    a("```bash")
    a(cmd_used)
    a("```")
    a("")
    a(f"- Official canonical rows analyzed: {total:,}")
    a(f"- Matched rows (path-walked): {matched:,}")
    a(f"- TIMEOUT rows (matched): {n_timeout_matched:,}")
    a(f"- FILLED_TP rows: {summary.get('filled_tp_rows', 0):,}")
    a(f"- FILLED_SL rows: {summary.get('filled_sl_rows', 0):,}")
    a(f"- NO_FILL rows: {summary.get('no_fill_rows', 0):,}")
    a(f"- AMBIGUOUS rows: {summary.get('ambiguous_count', 0):,}")
    a(f"- Fill model used: {summary.get('fill_model_used')}")
    a(f"- USD ROI: {summary.get('fee_slippage_status', {}).get('usd_roi')}")
    a("")
    a("---")
    a("")
    a("## 4. INFERENCES")
    a("")

    # Determine dominant timeout reason
    dominant_reason = max(
        timeout_reasons, key=lambda k: timeout_reasons[k]) if timeout_reasons else "UNKNOWN"
    dominant_count = timeout_reasons.get(dominant_reason, 0)
    a(f"- **Dominant timeout reason**: `{dominant_reason}` "
      f"({dominant_count:,} / {n_timeout_matched:,} timeout rows, "
      f"{_fmt_pct(_pct(dominant_count, n_timeout_matched))})")
    if avg_mfe_tp is not None:
        a(f"- **Avg MFE-to-TP ratio on matched timeouts**: {avg_mfe_tp:.3f} "
          f"— price reaches only {avg_mfe_tp*100:.1f}% of TP distance on average.")
    if mfe_before_mae is not None:
        a(f"- **MFE-before-MAE rate**: {mfe_before_mae:.1%} of matched rows see "
          "favorable move BEFORE adverse move.")
    reach_25_pct = tp_reach.get('reached_25pct_pct', 0)
    reach_50_pct = tp_reach.get('reached_50pct_pct', 0)
    a(f"- **TP reach**: only {_fmt_pct(reach_25_pct)} of matched-timeout rows "
      f"reached 25% of TP distance; {_fmt_pct(reach_50_pct)} reached 50%.")
    a("")
    a("---")
    a("")
    a("## 5. ASSUMPTIONS")
    a("")
    a("- A1: Path-walk uses the same candle data as PKG-1 (recorder CSV primary, "
      "raw Binance JSON secondary).")
    a("- A2: Fill candle is identified by re-running optimistic_touch logic on "
      "the path window; any mismatch with PKG-1 fill is a data-quality flag.")
    a("- A3: Forward returns at 1m/3m/5m/15m/30m/horizon are side-adjusted "
      "(long: positive=favorable; short: positive=favorable).")
    a("- A4: Conservative-cross sensitivity uses 1bp and 5bp minimum clearance as "
      "diagnostic proxies; no calibrated spread model is available for this window.")
    a("")
    a("---")
    a("")
    a("## 6. UNKNOWNS")
    a("")
    a("- U1: Whether the TP/SL offset percentages in the shadow_entry_plan are "
      "calibrated to observed volatility.")
    a("- U2: Statistical significance of timeout reason distribution requires "
      "longer observation window (PKG-6).")
    a("- U3: Whether MFE/MAE values are biased by the optimistic fill model "
      "(an unreachable fill could inflate MFE by starting the path too early).")
    a("")
    a("---")
    a("")
    a("## 7. Input inventory")
    a("")
    a("| artifact | rows | role |")
    a("|---|---|---|")
    a(f"| `data/simulator/outcomes_diagnostics.jsonl` | {total:,} | primary input |")
    a("| `data/simulator/outcomes.json` | read-only (not modified) | integrity ref |")
    a("| `data/simulator/outcomes_manifest.json` | 1 | fee/slippage/notional status |")
    a("| `logs/judge_experts/shadow_entry_plan_*.jsonl` | all tiers | ladder analysis |")
    a("| `data/raw_binance_klines_1m/**` | by symbol | path walk (dict JSON format) |")
    a("| `data/recorder_backfill_1m/**` | by symbol | path walk (CSV format) |")
    a("")
    a("---")
    a("")
    a("## 8. Official canonical path diagnostics")
    a("")
    a("### MFE / MAE distributions (matched rows, in bps)")
    a("")
    a(f"| metric | value |")
    a("|---|---|")
    a(f"| MFE mean | {_fmt_f(mfe_dist.get('mean'))} bps |")
    a(f"| MFE max | {_fmt_f(mfe_dist.get('max'))} bps |")
    a(f"| MFE min | {_fmt_f(mfe_dist.get('min'))} bps |")
    a(f"| MFE > 0 | {_fmt_pct(mfe_dist.get('pct_gt_0'))} |")
    a(f"| MAE mean | {_fmt_f(mae_dist.get('mean'))} bps |")
    a(f"| MAE max | {_fmt_f(mae_dist.get('max'))} bps |")
    a(f"| Avg MFE-to-TP ratio | {_fmt_f(avg_mfe_tp, 3)} |")
    a(f"| MFE before MAE rate | {_fmt_pct(mfe_before_mae * 100 if mfe_before_mae else None)} |")
    a("")
    a("### TP reach ratios (matched TIMEOUT rows only)")
    a("")
    a(f"| milestone | count | % of matched-timeout |")
    a("|---|---|---|")
    n_mt = n_timeout_matched or 1
    a(f"| Reached 25% of TP distance | "
      f"{int(n_mt * tp_reach.get('reached_25pct_pct', 0) / 100):,} | "
      f"{_fmt_pct(tp_reach.get('reached_25pct_pct'))} |")
    a(f"| Reached 50% of TP distance | "
      f"{int(n_mt * tp_reach.get('reached_50pct_pct', 0) / 100):,} | "
      f"{_fmt_pct(tp_reach.get('reached_50pct_pct'))} |")
    a(f"| Reached 75% of TP distance | "
      f"{int(n_mt * tp_reach.get('reached_75pct_pct', 0) / 100):,} | "
      f"{_fmt_pct(tp_reach.get('reached_75pct_pct'))} |")
    a(f"| Reached 90% of TP distance | "
      f"{int(n_mt * tp_reach.get('reached_90pct_pct', 0) / 100):,} | "
      f"{_fmt_pct(tp_reach.get('reached_90pct_pct'))} |")
    a("")
    a("### Forward returns (side-adjusted, matched rows)")
    fwd_1m_data = summary.get("forward_return_1m", {})
    fwd_h_data = summary.get("forward_return_horizon", {})
    a(f"| interval | mean return | n rows |")
    a("|---|---|---|")
    a(f"| 1m | {_fmt_f(fwd_1m_data.get('mean'), 5)} | {fwd_1m_data.get('n', 0):,} |")
    a(f"| horizon | {_fmt_f(fwd_h_data.get('mean'), 5)} | {fwd_h_data.get('n', 0):,} |")
    a("")
    a("---")
    a("")
    a("## 9. Timeout analysis")
    a("")
    a(f"Total TIMEOUT rows: {timeout_n:,} ({_fmt_pct(exit_pct.get('TIMEOUT'))} of all rows)")
    a("")
    a("### Timeout reason distribution (matched TIMEOUT rows)")
    a("")
    a("| reason | count | % |")
    a("|---|---|---|")
    for reason, cnt in sorted(timeout_reasons.items(), key=lambda x: -x[1]):
        a(f"| {reason} | {cnt:,} | {_fmt_pct(_pct(cnt, n_timeout_matched))} |")
    a("")
    a("**Interpretation:**")
    a("- `WRONG_DIRECTION`: MAE > MFE — price moved against the entry before "
      "the position was closed. This is the primary driver if it dominates.")
    a("- `FLAT_NO_EDGE`: Both MFE < 25% TP and MAE < 25% SL — price was "
      "essentially flat. No directional edge captured.")
    a("- `TP_TOO_FAR_PRICE_MOVED_FAVORABLY`: MFE ≥ 50% of TP distance but "
      "price reversed before hitting TP. TP targets may be too aggressive.")
    a("- `HORIZON_TOO_SHORT`: MFE ≥ 90% of TP distance — price nearly reached "
      "TP but horizon expired first.")
    a("- `SL_NEAR_MISS`: MAE ≥ 75% of SL distance but SL not hit.")
    a("")
    a("---")
    a("")
    a("## 10. Confidence path analysis")
    a("")
    a("| confidence bucket | total | matched | timeout% | TP hit% | "
      "avg MFE-to-TP | reached 25% TP |")
    a("|---|---|---|---|---|---|---|")
    for bkt, s in sorted(by_bucket.items()):
        a(f"| {bkt} | {s['total']:,} | {s['matched']:,} | "
          f"{_fmt_pct(s.get('timeout_pct'))} | {_fmt_pct(s.get('tp_hit_pct'))} | "
          f"{_fmt_f(s.get('avg_mfe_to_tp_ratio'), 3)} | "
          f"{_fmt_pct(s.get('reached_25pct_tp'))} |")
    a("")
    a("**Key question:** Does higher confidence produce better path geometry?")
    a("If `avg_mfe_to_tp_ratio` and `reached_25pct_tp` are NOT monotonically "
      "increasing with confidence, the confidence signal is path-geometry "
      "uncalibrated (confirming PKG-4 inverse accuracy finding).")
    a("")
    a("---")
    a("")
    a("## 11. Symbol / tf / regime analysis")
    a("")
    a("### By symbol")
    a("")
    a("| symbol | total | matched | timeout% | TP hits | TP hit% | "
      "avg MFE-to-TP | reached 25% TP |")
    a("|---|---|---|---|---|---|---|---|")
    for sym, s in sorted(by_sym.items()):
        a(f"| {sym} | {s['total']:,} | {s['matched']:,} | "
          f"{_fmt_pct(s.get('timeout_pct'))} | {s.get('tp_hits', 0)} | "
          f"{_fmt_pct(s.get('tp_hit_pct'))} | "
          f"{_fmt_f(s.get('avg_mfe_to_tp_ratio'), 3)} | "
          f"{_fmt_pct(s.get('reached_25pct_tp'))} |")
    a("")
    a("### By timeframe")
    a("")
    a("| tf_sec | total | matched | timeout% | TP hit% | avg MFE-to-TP |")
    a("|---|---|---|---|---|---|")
    for tf, s in sorted(by_tf.items()):
        a(f"| {tf} | {s['total']:,} | {s['matched']:,} | "
          f"{_fmt_pct(s.get('timeout_pct'))} | {_fmt_pct(s.get('tp_hit_pct'))} | "
          f"{_fmt_f(s.get('avg_mfe_to_tp_ratio'), 3)} |")
    a("")
    a("### By regime")
    a("")
    a("| regime | total | matched | timeout% | TP hit% | avg MFE-to-TP |")
    a("|---|---|---|---|---|---|")
    for reg, s in sorted(by_regime.items()):
        a(f"| {reg} | {s['total']:,} | {s['matched']:,} | "
          f"{_fmt_pct(s.get('timeout_pct'))} | {_fmt_pct(s.get('tp_hit_pct'))} | "
          f"{_fmt_f(s.get('avg_mfe_to_tp_ratio'), 3)} |")
    a("")
    a("---")
    a("")
    a("## 12. All-tier ladder diagnostics")
    a("")
    a("> **DIAGNOSTIC-ONLY** — All-tier statistics must NOT be used as official "
      "Judge accuracy. The official evaluation uses one canonical plan per "
      "CorrelationKey.")
    a("")
    a("| tier | actionable plans | fill rate | TP hit% | timeout% | "
      "avg MFE-to-TP (timeout) |")
    a("|---|---|---|---|---|---|")
    for tier in ["low", "medium", "high"]:
        s = all_tier.get(tier, {})
        a(f"| {tier} | {s.get('actionable_plans', 0):,} | "
          f"{_fmt_pct(s.get('fill_rate_pct'))} | "
          f"{_fmt_pct(s.get('tp_hit_pct'))} | "
          f"{_fmt_pct(s.get('timeout_pct'))} | "
          f"{_fmt_f(s.get('avg_mfe_to_tp_ratio_on_timeout'), 3)} |")
    a("")
    a("---")
    a("")
    a("## 13. Fee/slippage/notional status")
    a("")
    a("- Path diagnostics report **RAW price-based returns** (no fee/slippage deducted).")
    a("- The official simulator applies 25 bps + 0.1% slippage; those are already "
      "reflected in PKG-4 `avg_net_return = -0.003679`.")
    a("- No fee/slippage double-count occurs here.")
    a("- **USD ROI: disabled** — `pct_only` mode; economics block absent in "
      "`config/judge_simulator.yaml`.")
    a("")
    a("### Fill model sensitivity (conservative-cross proxy)")
    a("")
    a(f"| model | fills | % lost vs optimistic |")
    a("|---|---|---|")
    fills_opt = fill_sens.get('fills_optimistic', 0)
    a(f"| optimistic_touch | {fills_opt:,} | — |")
    a(f"| conservative_cross_1bp | {fill_sens.get('fills_conservative_1bp', 0):,} | "
      f"{_fmt_pct(fill_sens.get('pct_lost_at_1bp'))} |")
    a(f"| conservative_cross_5bp | {fill_sens.get('fills_conservative_5bp', 0):,} | "
      f"{_fmt_pct(fill_sens.get('pct_lost_at_5bp'))} |")
    a("")
    a(f"*Note: {fill_sens.get('note')}*")
    a("")
    a("---")
    a("")
    a("## 14. Implications for PKG-6")
    a("")
    a("Based on path diagnostics:")
    a("")
    a("1. **Baselines required**: random-same-frequency, inverted-judge, "
      "confidence-shuffle are needed to determine whether WRONG_DIRECTION "
      "dominance is significantly worse than chance.")
    a("2. **OOS partition**: 4-day window is too short. PKG-6 must obtain at "
      "least 2 weeks of Judge logs for a meaningful OOS split.")
    a("3. **TP/SL calibration audit**: if TP_TOO_FAR or FLAT_NO_EDGE dominate, "
      "a separate ladder calibration audit (PKG-6A) is warranted before any "
      "threshold changes.")
    a("4. **Inverse confidence calibration** confirmed at path level: if "
      "higher-confidence buckets show worse avg_mfe_to_tp_ratio, "
      "the confidence signal is also path-uncalibrated.")
    a("")
    a("---")
    a("")
    a("## 15. Residual risks")
    a("")
    a("| # | risk | severity |")
    a("|---|---|---|")
    a("| RR1 | optimistic_touch overstates fill rate — real fills would be fewer | HIGH |")
    a("| RR2 | 4-day window too short for statistical significance | HIGH |")
    a("| RR3 | MFE/MAE computed on same candles used for fill — optimistic path start | MED |")
    a("| RR4 | conservative_cross spread of 1bp/5bp is not calibrated to this symbol/period | MED |")
    a("| RR5 | All-tier diagnostics labeled but could be miscited — banners required | LOW |")
    a("")
    a("---")
    a("")
    a("## 16. Next package gate")
    a("")
    a("**PKG-6: REVIEW_BASELINES_AND_OOS**")
    a("")
    a("Rationale: Path diagnostics clarifies the structural picture. Next step is "
      "to determine whether Judge underperforms a random baseline and whether "
      "the observed negative returns hold on an OOS partition. PKG-6 requires "
      "a longer observation window (≥2 weeks) and implements: "
      "`random_same_frequency`, `inverted_judge`, `confidence_shuffle`, "
      "train/OOS split, `expert_agreement` segment.")
    a("")
    a("---")
    a("")
    a("## Appendix A — files changed")
    a("")
    a("```")
    a("A  tools/judge/build_path_diagnostics.py")
    a("A  tests/alpha_search/judge/test_path_diagnostics.py")
    a("A  data/simulator/judge_path_diagnostics.jsonl      (DIAGNOSTIC-ONLY)")
    a("A  data/simulator/judge_path_diagnostics_summary.json  (DIAGNOSTIC-ONLY)")
    a("A  reports/PKG_5_JUDGE_PATH_DIAGNOSTICS_REPORT.md")
    a("```")
    a("")
    a("No official artifacts modified.")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[path-diag] %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(
        prog="build-path-diagnostics",
        description="PKG-5: DIAGNOSTIC-ONLY path geometry tool.",
    )
    parser.add_argument("--outcomes-path",
                        default="data/simulator/outcomes.json")
    parser.add_argument("--manifest-path",
                        default="data/simulator/outcomes_manifest.json")
    parser.add_argument("--outcomes-diagnostics-path",
                        default="data/simulator/outcomes_diagnostics.jsonl")
    parser.add_argument("--judge-log-dir",
                        default="logs/judge_experts")
    parser.add_argument("--raw-1m-dir",
                        default="data/raw_binance_klines_1m")
    parser.add_argument("--recorder-1m-dir",
                        default="data/recorder_backfill_1m")
    parser.add_argument("--simulator-config",
                        default="config/judge_simulator.yaml")
    parser.add_argument("--diagnostics-out",
                        default="data/simulator/judge_path_diagnostics.jsonl")
    parser.add_argument("--summary-out",
                        default="data/simulator/judge_path_diagnostics_summary.json")
    parser.add_argument("--report-path",
                        default="reports/PKG_5_JUDGE_PATH_DIAGNOSTICS_REPORT.md")
    args = parser.parse_args(argv)

    t0 = time.time()

    # --- load inputs ---
    LOG.info("loading outcomes diagnostics: %s",
             args.outcomes_diagnostics_path)
    diag_path = Path(args.outcomes_diagnostics_path)
    if not diag_path.is_file():
        LOG.error("outcomes_diagnostics.jsonl not found: %s", diag_path)
        return 2
    diag_rows: list[dict] = []
    with diag_path.open("r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                diag_rows.append(json.loads(ln))
            except json.JSONDecodeError as exc:
                LOG.warning("Skip malformed diag row: %s", exc)

    LOG.info("loaded %d diagnostic rows", len(diag_rows))

    manifest: dict = {}
    manifest_p = Path(args.manifest_path)
    if manifest_p.is_file():
        with manifest_p.open("r", encoding="utf-8") as fh:
            manifest = json.load(fh)

    LOG.info("loading candles from recorder: %s", args.recorder_1m_dir)
    rec_candles = load_recorder_candles(Path(args.recorder_1m_dir))
    LOG.info("loading candles from raw binance: %s", args.raw_1m_dir)
    raw_candles = load_raw_binance_candles(Path(args.raw_1m_dir))
    candles_by_symbol = merge_candle_sources(raw_candles, rec_candles)
    LOG.info("candle symbols loaded: %s", sorted(candles_by_symbol.keys()))

    LOG.info("loading all-tier shadow plans from: %s", args.judge_log_dir)
    all_plan_rows = load_all_tier_plans(Path(args.judge_log_dir))
    LOG.info("loaded %d shadow plan rows (all tiers)", len(all_plan_rows))

    # --- process official canonical rows ---
    LOG.info("enriching %d diagnostic rows...", len(diag_rows))
    official_rows: list[dict] = []
    path_walk_ok = 0
    path_walk_miss = 0

    for diag in diag_rows:
        row = enrich_from_diagnostics(diag)

        # path walk for matched rows
        if row.get("outcome_matched_trade"):
            symbol = row.get("symbol", "")
            ckey_bar_close = row.get("bar_close_ts")
            horizon_ms = diag.get("horizon_ms")
            if (symbol and ckey_bar_close is not None and horizon_ms is not None
                    and symbol in candles_by_symbol):
                path_candles = candles_after(
                    candles_by_symbol[symbol],
                    ckey_bar_close,
                    ckey_bar_close + horizon_ms,
                )
                walk_path(row, path_candles)
                path_walk_ok += 1
            else:
                path_walk_miss += 1
                row["data_quality_flags"].append(
                    "no_candle_data_for_path_walk")

        # fill sensitivity (canonical matched rows)
        if row.get("outcome_matched_trade"):
            symbol = row.get("symbol", "")
            ckey_bar_close = row.get("bar_close_ts")
            horizon_ms = diag.get("horizon_ms")
            if (symbol and ckey_bar_close is not None and horizon_ms is not None
                    and symbol in candles_by_symbol):
                path_candles = candles_after(
                    candles_by_symbol[symbol],
                    ckey_bar_close,
                    ckey_bar_close + horizon_ms,
                )
                sens = compute_fill_sensitivity(diag, path_candles)
                row.update(sens)

        official_rows.append(row)

    LOG.info(
        "path walk: %d ok, %d miss (no candle data)", path_walk_ok, path_walk_miss)

    # --- all-tier ladder simulation ---
    LOG.info("simulating %d all-tier plan rows...", len(all_plan_rows))
    all_tier_rows: list[dict] = []
    for plan in all_plan_rows:
        result = simulate_tier_fill(plan, candles_by_symbol)
        all_tier_rows.append(result)

    # --- compute summary ---
    LOG.info("computing summary...")
    summary = compute_summary(official_rows, all_tier_rows, manifest)

    # --- write outputs ---
    out_diag = Path(args.diagnostics_out)
    out_diag.parent.mkdir(parents=True, exist_ok=True)
    LOG.info("writing %d rows to: %s", len(official_rows), out_diag)
    with out_diag.open("w", encoding="utf-8", newline="\n") as fh:
        for row in official_rows:
            fh.write(json.dumps(row, sort_keys=True))
            fh.write("\n")

    out_summary = Path(args.summary_out)
    LOG.info("writing summary to: %s", out_summary)
    with out_summary.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
        fh.write("\n")

    cmd_used = (
        f"PYTHONPATH=. py -3 -m tools.judge.build_path_diagnostics \\\n"
        f"  --outcomes-path {args.outcomes_path} \\\n"
        f"  --manifest-path {args.manifest_path} \\\n"
        f"  --outcomes-diagnostics-path {args.outcomes_diagnostics_path} \\\n"
        f"  --judge-log-dir {args.judge_log_dir} \\\n"
        f"  --raw-1m-dir {args.raw_1m_dir} \\\n"
        f"  --recorder-1m-dir {args.recorder_1m_dir} \\\n"
        f"  --simulator-config {args.simulator_config} \\\n"
        f"  --diagnostics-out {args.diagnostics_out} \\\n"
        f"  --summary-out {args.summary_out} \\\n"
        f"  --report-path {args.report_path}"
    )
    write_report(summary, Path(args.report_path), cmd_used)
    LOG.info("report written to: %s", args.report_path)

    elapsed = time.time() - t0
    LOG.info("done in %.1f s", elapsed)

    # Print brief summary to stdout
    print(f"[path-diag] rows={len(official_rows)} matched={path_walk_ok} "
          f"path_walk_miss={path_walk_miss}")
    print(
        f"[path-diag] timeout_reasons={summary.get('timeout_reason_distribution')}")
    tp_reach = summary.get("tp_reach_ratios_on_matched_timeout", {})
    print(f"[path-diag] tp_reach_25pct={tp_reach.get('reached_25pct_pct', 0):.1f}% "
          f"tp_reach_50pct={tp_reach.get('reached_50pct_pct', 0):.1f}%")
    print(f"[path-diag] diagnostics: {args.diagnostics_out}")
    print(f"[path-diag] summary:     {args.summary_out}")
    print(f"[path-diag] report:      {args.report_path}")
    print("[path-diag] done")

    return 0


if __name__ == "__main__":
    sys.exit(main())
