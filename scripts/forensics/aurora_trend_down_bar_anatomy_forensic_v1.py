#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
DATE_TAG = "2026_05_04"

DATASET_CSV = REPORTS / "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_dataset.csv"
TRADES_CSV = REPORTS / "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_trades.csv"
V2_JSON = REPORTS / "AURORA_TREND_DOWN_BEHAVIOR_SEARCH_V2_2026_05_04.json"

OUT_MD = REPORTS / f"AURORA_TREND_DOWN_BAR_ANATOMY_FORENSIC_V1_{DATE_TAG}.md"
OUT_JSON = REPORTS / \
    f"AURORA_TREND_DOWN_BAR_ANATOMY_FORENSIC_V1_{DATE_TAG}.json"
OUT_DATASET_CSV = REPORTS / \
    f"AURORA_TREND_DOWN_BAR_ANATOMY_DATASET_{DATE_TAG}.csv"
OUT_SEGMENT_CSV = REPORTS / f"AURORA_TREND_DOWN_SEGMENT_ANATOMY_{DATE_TAG}.csv"
OUT_PATTERN_CSV = REPORTS / \
    f"AURORA_TREND_DOWN_BAR_PATTERN_RESULTS_{DATE_TAG}.csv"
OUT_TPSL_CSV = REPORTS / \
    f"AURORA_TREND_DOWN_BAR_PATTERN_TPSL_RESULTS_{DATE_TAG}.csv"

PRIMARY_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
CONTROL_REGIMES = [
    "TREND_UP",
    "MEAN_REVERSION",
    "HIGH_VOLATILITY",
    "LOW_VOLATILITY",
    "UNCERTAIN",
]
TD = "TREND_DOWN"

FWD_H = [1, 3, 6, 12, 18, 36]
MAX_SIM_BARS = 40

TP_GRID = [15.0, 20.0, 25.0, 30.0, 36.8, 45.0, 55.0, 70.0]
SL_GRID = [25.0, 35.0, 45.0, 55.2, 65.0, 75.0, 90.0, 110.0]
TO_GRID = [3, 6, 9, 12, 14, 18, 24, 36]
COSTS_BPS = [4, 6, 8, 10]

AGE_BUCKETS = [
    ("age_1", lambda s: s == 1),
    ("age_2_3", lambda s: (s >= 2) & (s <= 3)),
    ("age_4_6", lambda s: (s >= 4) & (s <= 6)),
    ("age_7_12", lambda s: (s >= 7) & (s <= 12)),
    ("age_13_24", lambda s: (s >= 13) & (s <= 24)),
    ("age_gt_24", lambda s: s > 24),
]


@dataclass
class CandidateDef:
    name: str
    description: str


def _safe_div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.full_like(a, np.nan, dtype=float)
    mask = np.isfinite(b) & (np.abs(b) > 1e-12)
    out[mask] = a[mask] / b[mask]
    return out


def _fmt(v: Any, nd: int = 4) -> str:
    if v is None:
        return "null"
    if isinstance(v, (float, np.floating)):
        if not np.isfinite(float(v)):
            return "null"
        return f"{float(v):.{nd}f}"
    return str(v)


def _rows_to_md(rows: List[Dict[str, Any]], cols: List[str], max_rows: int = 25) -> str:
    if not rows:
        return "(empty)"
    rows = rows[:max_rows]
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines = [head, sep]
    for r in rows:
        lines.append("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |")
    return "\n".join(lines)


def load_inputs() -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    df = pd.read_csv(DATASET_CSV)
    tr = pd.read_csv(TRADES_CSV)
    v2 = {}
    if V2_JSON.exists():
        v2 = json.loads(V2_JSON.read_text(encoding="utf-8"))

    df = df[df["symbol"].isin(PRIMARY_SYMBOLS)].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)

    if "entry_timestamp" in tr.columns:
        tr["entry_timestamp"] = pd.to_datetime(
            tr["entry_timestamp"], utc=True, errors="coerce")
    tr = tr[tr["symbol"].isin(PRIMARY_SYMBOLS)].copy()

    return df, tr, v2


def _future_extreme(arr: np.ndarray, h: int, mode: str) -> np.ndarray:
    n = len(arr)
    out = np.full(n, np.nan, dtype=float)
    if n <= h:
        return out
    windows = sliding_window_view(arr[1:], h)
    if mode == "max":
        x = np.nanmax(windows, axis=1)
    else:
        x = np.nanmin(windows, axis=1)
    out[: n - h] = x
    return out


def add_bar_features(df: pd.DataFrame) -> pd.DataFrame:
    out_all: List[pd.DataFrame] = []

    for sym, g in df.groupby("symbol", sort=False):
        s = g.copy().reset_index(drop=True)

        o = s["open"].astype(float).values
        h = s["high"].astype(float).values
        l = s["low"].astype(float).values
        c = s["close"].astype(float).values
        v = s["volume"].astype(float).values
        n = len(s)

        prev_c = np.full(n, np.nan)
        prev_c[1:] = c[:-1]

        bar_range = h - l
        body_abs = np.abs(c - o)
        signed_body = c - o

        s["bar_range_pct"] = _safe_div(bar_range, o) * 100.0
        s["bar_range_bps"] = s["bar_range_pct"] * 100.0

        s["body_pct"] = _safe_div(body_abs, o) * 100.0
        s["body_bps"] = s["body_pct"] * 100.0

        s["signed_body_pct"] = _safe_div(signed_body, o) * 100.0
        s["signed_body_bps"] = s["signed_body_pct"] * 100.0

        s["close_to_close_pct"] = _safe_div(c - prev_c, prev_c) * 100.0
        s["close_to_close_bps"] = s["close_to_close_pct"] * 100.0

        green = c >= o
        up_w = np.where(green, h - c, h - o)
        lo_w = np.where(green, o - l, c - l)
        s["upper_wick_bps"] = _safe_div(up_w, o) * 10000.0
        s["lower_wick_bps"] = _safe_div(lo_w, o) * 10000.0

        denom = bar_range.copy()
        denom[denom <= 1e-12] = np.nan
        s["body_to_range_ratio"] = body_abs / denom
        s["close_position_in_bar"] = (c - l) / denom
        s["open_position_in_bar"] = (o - l) / denom

        s["gap_from_prev_close_bps"] = _safe_div(o - prev_c, prev_c) * 10000.0

        rng_bps = s["bar_range_bps"].astype(float)
        vol = pd.Series(v)
        rng = pd.Series(rng_bps.values)
        s["volume_zscore_rolling"] = (
            vol - vol.rolling(48, min_periods=20).mean()) / vol.rolling(48, min_periods=20).std(ddof=0)
        s["range_zscore_rolling"] = (
            rng - rng.rolling(48, min_periods=20).mean()) / rng.rolling(48, min_periods=20).std(ddof=0)

        tr1 = h - l
        tr2 = np.abs(h - prev_c)
        tr3 = np.abs(l - prev_c)
        true_range = np.nanmax(np.vstack([tr1, tr2, tr3]), axis=0)
        atr14 = pd.Series(true_range).rolling(14, min_periods=5).mean().values
        s["atr_bps"] = _safe_div(atr14, c) * 10000.0

        # Local context features for bucketing and candidates
        hi10 = pd.Series(h).rolling(10, min_periods=3).max().values
        lo10 = pd.Series(l).rolling(10, min_periods=3).min().values
        rng10 = hi10 - lo10
        rng10[rng10 <= 1e-12] = np.nan
        s["hi10"] = hi10
        s["lo10"] = lo10
        s["pos_in_rng10"] = (c - lo10) / rng10

        ret3 = np.full(n, np.nan)
        ret6 = np.full(n, np.nan)
        if n > 3:
            ret3[3:] = (c[3:] - c[:-3]) / c[:-3] * 10000.0
        if n > 6:
            ret6[6:] = (c[6:] - c[:-6]) / c[:-6] * 10000.0
        s["prior_3_bar_return_bps"] = ret3
        s["prior_6_bar_return_bps"] = ret6

        # Forward short returns and adverse excursion from current close
        for hh in FWD_H:
            f_short = np.full(n, np.nan)
            if n > hh:
                f_short[: n - hh] = (c[: n - hh] - c[hh:]) / \
                    c[: n - hh] * 10000.0
            s[f"future_{hh}_bar_short_bps"] = f_short

            max_hi = _future_extreme(h, hh, mode="max")
            min_lo = _future_extreme(l, hh, mode="min")
            s[f"future_{hh}_bar_max_adverse_bps"] = _safe_div(
                max_hi - c, c) * 10000.0
            s[f"future_{hh}_bar_max_favorable_bps"] = _safe_div(
                c - min_lo, c) * 10000.0

        out_all.append(s)

    out = pd.concat(out_all, ignore_index=True)
    return out


def regime_compare(df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    regimes = [TD] + CONTROL_REGIMES

    for sym in PRIMARY_SYMBOLS:
        s = df[df["symbol"] == sym].copy()
        for reg in regimes:
            g = s[s["regime"] == reg]
            if g.empty:
                continue

            red = (g["close"] < g["open"]).mean() * 100.0
            green = (g["close"] >= g["open"]).mean() * 100.0

            rows.append(
                {
                    "symbol": sym,
                    "regime": reg,
                    "bars": int(len(g)),
                    "avg_bar_range_bps": float(g["bar_range_bps"].mean()),
                    "median_bar_range_bps": float(g["bar_range_bps"].median()),
                    "p75_bar_range_bps": float(g["bar_range_bps"].quantile(0.75)),
                    "p90_bar_range_bps": float(g["bar_range_bps"].quantile(0.90)),
                    "p95_bar_range_bps": float(g["bar_range_bps"].quantile(0.95)),
                    "avg_signed_body_bps": float(g["signed_body_bps"].mean()),
                    "median_signed_body_bps": float(g["signed_body_bps"].median()),
                    "red_share_pct": float(red),
                    "green_share_pct": float(green),
                    "avg_body_to_range_ratio": float(g["body_to_range_ratio"].mean()),
                    "avg_close_position_in_bar": float(g["close_position_in_bar"].mean()),
                    "volume_zscore_avg": float(g["volume_zscore_rolling"].mean()),
                    "atr_bps_avg": float(g["atr_bps"].mean()),
                }
            )

    return pd.DataFrame(rows)


def _age_bucket(age: pd.Series) -> pd.Series:
    out = pd.Series(index=age.index, dtype="object")
    for label, fn in AGE_BUCKETS:
        out.loc[fn(age)] = label
    out = out.fillna("age_unknown")
    return out


def lifecycle_timing(df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    td = df[df["regime"] == TD].copy()
    td["age_bucket"] = _age_bucket(td["regime_age_bars"].astype(float))

    for sym in PRIMARY_SYMBOLS:
        s = td[td["symbol"] == sym]
        for bucket, g in s.groupby("age_bucket", sort=False):
            if g.empty:
                continue
            rows.append(
                {
                    "symbol": sym,
                    "age_bucket": bucket,
                    "bars": int(len(g)),
                    "avg_close_to_close_bps": float(g["close_to_close_bps"].mean()),
                    "next_1_bar_short_bps": float(g["future_1_bar_short_bps"].mean()),
                    "next_3_bar_short_bps": float(g["future_3_bar_short_bps"].mean()),
                    "next_6_bar_short_bps": float(g["future_6_bar_short_bps"].mean()),
                    "next_12_bar_short_bps": float(g["future_12_bar_short_bps"].mean()),
                    "red_share_pct": float((g["close"] < g["open"]).mean() * 100.0),
                    "avg_range_bps": float(g["bar_range_bps"].mean()),
                    "avg_body_to_range_ratio": float(g["body_to_range_ratio"].mean()),
                    "avg_close_position_in_bar": float(g["close_position_in_bar"].mean()),
                }
            )

    return pd.DataFrame(rows)


def segment_anatomy(df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    for sym in PRIMARY_SYMBOLS:
        s = df[df["symbol"] == sym].copy().reset_index(drop=True)
        is_td = (s["regime"] == TD).values
        if not is_td.any():
            continue

        seg_id = 0
        i = 0
        while i < len(s):
            if not is_td[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(s) and is_td[j + 1]:
                j += 1

            seg = s.iloc[i: j + 1].copy()
            sp = float(seg.iloc[0]["close"])
            ep = float(seg.iloc[-1]["close"])
            seg_ret = (ep - sp) / sp * 10000.0

            min_lo = float(seg["low"].min())
            max_hi = float(seg["high"].max())
            max_fav_dn = (sp - min_lo) / sp * 10000.0
            max_adv_up = (max_hi - sp) / sp * 10000.0

            n = len(seg)
            p3 = min(2, n - 1)
            p6 = min(5, n - 1)
            first3 = (float(seg.iloc[p3]["close"]) - sp) / sp * 10000.0
            first6 = (float(seg.iloc[p6]["close"]) - sp) / sp * 10000.0

            l3_idx = max(0, n - 3)
            l6_idx = max(0, n - 6)
            base_l3 = float(seg.iloc[l3_idx]["close"])
            base_l6 = float(seg.iloc[l6_idx]["close"])
            last3 = (ep - base_l3) / base_l3 * 10000.0
            last6 = (ep - base_l6) / base_l6 * 10000.0

            rows.append(
                {
                    "segment_id": f"{sym}_td_{seg_id:05d}",
                    "symbol": sym,
                    "start_ts": seg.iloc[0]["timestamp"],
                    "end_ts": seg.iloc[-1]["timestamp"],
                    "bars_count": int(n),
                    "start_price": sp,
                    "end_price": ep,
                    "segment_return_pct": seg_ret / 100.0,
                    "segment_return_bps": seg_ret,
                    "max_favorable_down_move_bps": max_fav_dn,
                    "max_adverse_up_move_bps": max_adv_up,
                    "first_3_bars_return_bps": first3,
                    "first_6_bars_return_bps": first6,
                    "last_3_bars_return_bps": last3,
                    "last_6_bars_return_bps": last6,
                    "avg_bar_range_bps": float(seg["bar_range_bps"].mean()),
                    "avg_body_bps": float(seg["body_bps"].mean()),
                    "red_share": float((seg["close"] < seg["open"]).mean()),
                    "close_near_low_share": float((seg["close_position_in_bar"] <= 0.25).mean()),
                    "confidence_start": float(seg.iloc[0]["regime_confidence"]),
                    "confidence_max": float(seg["regime_confidence"].max()),
                    "confidence_end": float(seg.iloc[-1]["regime_confidence"]),
                }
            )

            seg_id += 1
            i = j + 1

    return pd.DataFrame(rows)


def classify_patterns(td: pd.DataFrame) -> pd.DataFrame:
    s = td.copy()

    red = s["signed_body_bps"] < 0
    green = s["signed_body_bps"] > 0
    close_low = s["close_position_in_bar"] <= 0.25

    # Dynamic thresholds per symbol for volatility/chop separation.
    p75_range = s.groupby("symbol")["bar_range_bps"].transform(
        lambda x: x.quantile(0.75))
    med_range = s.groupby("symbol")["bar_range_bps"].transform(
        lambda x: x.quantile(0.50))

    lower_share = _safe_div(s["lower_wick_bps"].values,
                            s["bar_range_bps"].values)
    upper_share = _safe_div(s["upper_wick_bps"].values,
                            s["bar_range_bps"].values)
    wick_share = lower_share + upper_share

    prev_green_pullback = (s["signed_body_bps"].shift(1) > 0) & (
        s["close_position_in_bar"].shift(1) >= 0.50)

    s["PATTERN_RED_BREAKDOWN"] = red & (
        s["signed_body_bps"] < -20.0) & close_low
    s["PATTERN_RED_EXHAUSTION_WICK"] = red & (
        lower_share >= 0.40) & (s["close_position_in_bar"] > 0.40)
    s["PATTERN_GREEN_PULLBACK"] = green & (s["close_position_in_bar"] >= 0.50)
    s["PATTERN_INSIDE_NOISE"] = (s["body_bps"] <= 10.0) & (
        s["bar_range_bps"] <= med_range) & (s["body_to_range_ratio"] <= 0.35)
    s["PATTERN_HIGH_VOL_CHOP"] = (s["bar_range_bps"] >= p75_range) & (
        s["body_to_range_ratio"] <= 0.30) & (wick_share >= 0.60)
    s["PATTERN_CONTINUATION_AFTER_PULLBACK"] = prev_green_pullback & red & (
        s["close"] < s["close"].shift(1))

    s["wick_share_total"] = wick_share
    s["upper_wick_share"] = upper_share
    s["lower_wick_share"] = lower_share

    return s


def forward_bucket_study(td: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    s = td.copy()

    conf_bins = [0.0, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 1.01]
    conf_labels = ["<0.20", "0.20-0.30", "0.30-0.40",
                   "0.40-0.50", "0.50-0.60", "0.60-0.70", "0.70+"]
    s["bucket_conf"] = pd.cut(
        s["regime_confidence"], bins=conf_bins, labels=conf_labels, include_lowest=True)
    s["bucket_age"] = _age_bucket(s["regime_age_bars"].astype(float))
    s["bucket_range_pos"] = pd.cut(s["pos_in_rng10"], bins=[
                                   0.0, 0.25, 0.5, 0.75, 1.01], labels=["0-0.25", "0.25-0.50", "0.50-0.75", "0.75+"])
    s["bucket_signed_body"] = pd.cut(s["signed_body_bps"], bins=[-1e9, -40, -20, -10, 0, 10, 20, 1e9], labels=[
                                     "<-40", "-40..-20", "-20..-10", "-10..0", "0..10", "10..20", ">20"])
    s["bucket_close_pos"] = pd.cut(s["close_position_in_bar"], bins=[
                                   0.0, 0.25, 0.5, 0.75, 1.01], labels=["0-0.25", "0.25-0.50", "0.50-0.75", "0.75+"])
    s["bucket_prior3"] = pd.cut(s["prior_3_bar_return_bps"], bins=[-1e9, -80, -40, -20, 0, 20,
                                40, 1e9], labels=["<-80", "-80..-40", "-40..-20", "-20..0", "0..20", "20..40", ">40"])
    s["bucket_prior6"] = pd.cut(s["prior_6_bar_return_bps"], bins=[-1e9, -120, -60, -30, 0, 30,
                                60, 1e9], labels=["<-120", "-120..-60", "-60..-30", "-30..0", "0..30", "30..60", ">60"])

    def agg(df0: pd.DataFrame, bucket_col: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for (sym, b), g in df0.groupby(["symbol", bucket_col], dropna=True):
            if len(g) < 30:
                continue
            rows.append(
                {
                    "symbol": sym,
                    "bucket_type": bucket_col,
                    "bucket": str(b),
                    "count": int(len(g)),
                    "f1": float(g["future_1_bar_short_bps"].mean()),
                    "f3": float(g["future_3_bar_short_bps"].mean()),
                    "f6": float(g["future_6_bar_short_bps"].mean()),
                    "f12": float(g["future_12_bar_short_bps"].mean()),
                    "f18": float(g["future_18_bar_short_bps"].mean()),
                    "f36": float(g["future_36_bar_short_bps"].mean()),
                    "adv6": float(g["future_6_bar_max_adverse_bps"].mean()),
                    "adv12": float(g["future_12_bar_max_adverse_bps"].mean()),
                    "adv18": float(g["future_18_bar_max_adverse_bps"].mean()),
                    "adv36": float(g["future_36_bar_max_adverse_bps"].mean()),
                }
            )
        rows.sort(key=lambda x: x["f6"], reverse=True)
        return rows

    return {
        "bucket_conf": agg(s, "bucket_conf"),
        "bucket_age": agg(s, "bucket_age"),
        "bucket_range_pos": agg(s, "bucket_range_pos"),
        "bucket_signed_body": agg(s, "bucket_signed_body"),
        "bucket_close_pos": agg(s, "bucket_close_pos"),
        "bucket_prior3": agg(s, "bucket_prior3"),
        "bucket_prior6": agg(s, "bucket_prior6"),
    }


def pattern_forward_stats(td: pd.DataFrame) -> pd.DataFrame:
    pattern_cols = [
        "PATTERN_RED_BREAKDOWN",
        "PATTERN_RED_EXHAUSTION_WICK",
        "PATTERN_GREEN_PULLBACK",
        "PATTERN_INSIDE_NOISE",
        "PATTERN_HIGH_VOL_CHOP",
        "PATTERN_CONTINUATION_AFTER_PULLBACK",
    ]
    rows: List[Dict[str, Any]] = []

    for sym in PRIMARY_SYMBOLS:
        s = td[td["symbol"] == sym]
        for p in pattern_cols:
            g = s[s[p]].copy()
            if g.empty:
                continue
            rows.append(
                {
                    "result_type": "taxonomy_forward",
                    "symbol": sym,
                    "name": p,
                    "count": int(len(g)),
                    "future_1_short_bps": float(g["future_1_bar_short_bps"].mean()),
                    "future_3_short_bps": float(g["future_3_bar_short_bps"].mean()),
                    "future_6_short_bps": float(g["future_6_bar_short_bps"].mean()),
                    "future_12_short_bps": float(g["future_12_bar_short_bps"].mean()),
                    "future_18_short_bps": float(g["future_18_bar_short_bps"].mean()),
                    "future_36_short_bps": float(g["future_36_bar_short_bps"].mean()),
                    "adverse_6_bps": float(g["future_6_bar_max_adverse_bps"].mean()),
                    "adverse_12_bps": float(g["future_12_bar_max_adverse_bps"].mean()),
                    "adverse_36_bps": float(g["future_36_bar_max_adverse_bps"].mean()),
                    "red_share_pct": float((g["close"] < g["open"]).mean() * 100.0),
                    "close_near_low_share": float((g["close_position_in_bar"] <= 0.25).mean()),
                }
            )

    return pd.DataFrame(rows)


def define_candidates(td: pd.DataFrame) -> Tuple[pd.DataFrame, List[CandidateDef]]:
    s = td.copy()

    prev_close = s.groupby("symbol")["close"].shift(1)
    prev_green_pullback = (s.groupby("symbol")["signed_body_bps"].shift(1) > 0) & (
        s.groupby("symbol")["close_position_in_bar"].shift(1) >= 0.50
    )

    prev_lo10 = s.groupby("symbol")["lo10"].shift(1)

    s["BD1_SHORT_AFTER_GREEN_PULLBACK_IN_TD"] = (
        (s["regime"] == TD)
        & (s["signed_body_bps"] > 0)
        & (s["close_position_in_bar"] >= 0.50)
    )

    s["BD2_SHORT_AFTER_PULLBACK_THEN_RED_CONFIRMATION"] = (
        (s["regime"] == TD)
        & prev_green_pullback
        & (s["signed_body_bps"] < 0)
        & (s["close"] < prev_close)
    )

    s["BD3_SHORT_ON_BREAKDOWN_CLOSE_NEAR_LOW"] = (
        (s["regime"] == TD)
        & (s["close"] < prev_lo10)
        & (s["close_position_in_bar"] <= 0.25)
    )

    for th in [10, 20, 30, 40]:
        s[f"BD4_SHORT_ONLY_AFTER_SMALL_RED_NOT_BIG_RED_{th}"] = (
            (s["regime"] == TD)
            & (s["signed_body_bps"] < 0)
            & (s["signed_body_bps"] >= -float(th))
        )

    s["BD5_SHORT_WHEN_FORWARD_BAR_STRUCTURE_CONFIRMED"] = (
        (s["regime"] == TD)
        & (s["prior_3_bar_return_bps"] < 0)
        & (s["close_position_in_bar"] > 0.25)
    )

    defs = [
        CandidateDef("BD1_SHORT_AFTER_GREEN_PULLBACK_IN_TD",
                     "TD active, green pullback, close in upper half."),
        CandidateDef("BD2_SHORT_AFTER_PULLBACK_THEN_RED_CONFIRMATION",
                     "Prev bar green pullback, now red confirmation."),
        CandidateDef("BD3_SHORT_ON_BREAKDOWN_CLOSE_NEAR_LOW",
                     "Break previous 10-bar low and close near low."),
        CandidateDef("BD4_SHORT_ONLY_AFTER_SMALL_RED_NOT_BIG_RED_10",
                     "Small red bar only, avoid chase under -10bps."),
        CandidateDef("BD4_SHORT_ONLY_AFTER_SMALL_RED_NOT_BIG_RED_20",
                     "Small red bar only, avoid chase under -20bps."),
        CandidateDef("BD4_SHORT_ONLY_AFTER_SMALL_RED_NOT_BIG_RED_30",
                     "Small red bar only, avoid chase under -30bps."),
        CandidateDef("BD4_SHORT_ONLY_AFTER_SMALL_RED_NOT_BIG_RED_40",
                     "Small red bar only, avoid chase under -40bps."),
        CandidateDef("BD5_SHORT_WHEN_FORWARD_BAR_STRUCTURE_CONFIRMED",
                     "Last 3 bars negative, close not at local low."),
    ]
    return s, defs


def build_entry_matrices(sym_df: pd.DataFrame, signal_mask: np.ndarray) -> Dict[str, np.ndarray]:
    s = sym_df.reset_index(drop=True)

    entry_idx = np.where(signal_mask)[0] + 1
    entry_idx = entry_idx[entry_idx < len(s)]
    if len(entry_idx) == 0:
        return {
            "entry_idx": np.array([], dtype=int),
            "ep": np.array([], dtype=float),
            "high_m": np.zeros((0, MAX_SIM_BARS), dtype=float),
            "low_m": np.zeros((0, MAX_SIM_BARS), dtype=float),
            "close_m": np.zeros((0, MAX_SIM_BARS), dtype=float),
            "is_td_m": np.zeros((0, MAX_SIM_BARS), dtype=bool),
            "last_valid": np.array([], dtype=int),
        }

    hi = s["high"].values
    lo = s["low"].values
    cl = s["close"].values
    op = s["open"].values
    reg = s["regime"].values
    total = len(s)

    n = len(entry_idx)
    high_m = np.full((n, MAX_SIM_BARS), np.nan)
    low_m = np.full((n, MAX_SIM_BARS), np.nan)
    close_m = np.full((n, MAX_SIM_BARS), np.nan)
    is_td_m = np.zeros((n, MAX_SIM_BARS), dtype=bool)

    for k, e in enumerate(entry_idx):
        for j in range(MAX_SIM_BARS):
            fi = e + j
            if fi >= total:
                break
            high_m[k, j] = hi[fi]
            low_m[k, j] = lo[fi]
            close_m[k, j] = cl[fi]
            is_td_m[k, j] = reg[fi] == TD

    lv = np.zeros(n, dtype=np.int32)
    for k in range(n):
        ok = ~np.isnan(close_m[k])
        if ok.any():
            lv[k] = int(np.where(ok)[0].max())

    ep = op[entry_idx]
    return {
        "entry_idx": entry_idx,
        "ep": ep,
        "high_m": high_m,
        "low_m": low_m,
        "close_m": close_m,
        "is_td_m": is_td_m,
        "last_valid": lv,
    }


def simulate_short_batch(
    ep: np.ndarray,
    high_m: np.ndarray,
    low_m: np.ndarray,
    close_m: np.ndarray,
    is_td_m: np.ndarray,
    tp_bps: float,
    sl_bps: float,
    timeout: int,
    exit_on_rc: bool,
    last_valid: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = len(ep)
    t = min(timeout, MAX_SIM_BARS)
    if n == 0:
        return np.array([], dtype=object), np.array([], dtype=float), np.array([], dtype=int)

    tp_p = ep * (1 - tp_bps / 10000.0)
    sl_p = ep * (1 + sl_bps / 10000.0)

    tp_hit = low_m[:, :t] <= tp_p[:, None]
    sl_hit = high_m[:, :t] >= sl_p[:, None]
    rc_hit = (~is_td_m[:, :t]) if exit_on_rc else np.zeros((n, t), dtype=bool)

    pri = np.zeros((n, t), dtype=np.int8)
    pri[rc_hit] = 1
    pri[tp_hit] = 2
    pri[sl_hit] = 3

    any_exit = pri > 0
    has_exit = any_exit.any(axis=1)
    first_j = np.where(has_exit, np.argmax(any_exit, axis=1), t - 1)

    ix = np.arange(n)
    fj = np.minimum(first_j, t - 1)

    sl_win = sl_hit[ix, fj] & has_exit
    tp_win = tp_hit[ix, fj] & has_exit & ~sl_win
    rc_win = rc_hit[ix, fj] & has_exit & ~sl_win & ~tp_win
    to_win = ~has_exit

    reasons = np.full(n, "TIMEOUT", dtype=object)
    reasons[sl_win] = "SL"
    reasons[tp_win] = "TP"
    reasons[rc_win] = "REGIME_CHANGE"

    exit_p = np.full(n, np.nan)
    exit_p[sl_win] = sl_p[sl_win]
    exit_p[tp_win] = tp_p[tp_win]
    if rc_win.any():
        exit_p[rc_win] = close_m[ix[rc_win], fj[rc_win]]

    if to_win.any():
        cols = np.minimum(last_valid, t - 1)
        to_idx = np.where(to_win)[0]
        cidx = cols[to_idx]
        px = close_m[to_idx, cidx]
        px[np.isnan(px)] = ep[to_idx][np.isnan(px)]
        exit_p[to_win] = px

    exit_p = np.where(np.isnan(exit_p), ep, exit_p)
    pnl = (ep - exit_p) / ep
    bars = fj + 1
    bars[to_win] = t
    return reasons, pnl, bars


def candidate_forward_eval(sym_df: pd.DataFrame, candidate_col: str) -> Dict[str, Any]:
    m = build_entry_matrices(
        sym_df, sym_df[candidate_col].fillna(False).values.astype(bool))
    ep = m["ep"]
    close_m = m["close_m"]
    high_m = m["high_m"]

    out: Dict[str, Any] = {"count": int(len(ep))}
    if len(ep) == 0:
        for hh in FWD_H:
            out[f"f{hh}_short_bps"] = np.nan
            out[f"adv{hh}_bps"] = np.nan
        return out

    for hh in FWD_H:
        col = hh - 1
        if col >= close_m.shape[1]:
            out[f"f{hh}_short_bps"] = np.nan
            out[f"adv{hh}_bps"] = np.nan
            continue

        exit_c = close_m[:, col]
        val = (ep - exit_c) / ep * 10000.0
        out[f"f{hh}_short_bps"] = float(np.nanmean(val))

        sub_hi = high_m[:, :hh]
        adv = (np.nanmax(sub_hi, axis=1) - ep) / ep * 10000.0
        out[f"adv{hh}_bps"] = float(np.nanmean(adv))

    return out


def candidate_tpsl_grid(sym_df: pd.DataFrame, candidate_col: str, symbol: str) -> pd.DataFrame:
    m = build_entry_matrices(
        sym_df, sym_df[candidate_col].fillna(False).values.astype(bool))
    ep = m["ep"]
    if len(ep) == 0:
        return pd.DataFrame()

    rows: List[Dict[str, Any]] = []

    for tp in TP_GRID:
        for sl in SL_GRID:
            for to in TO_GRID:
                for erc in (False, True):
                    reasons, pnl, bars = simulate_short_batch(
                        ep,
                        m["high_m"],
                        m["low_m"],
                        m["close_m"],
                        m["is_td_m"],
                        tp,
                        sl,
                        to,
                        erc,
                        m["last_valid"],
                    )
                    if len(pnl) == 0:
                        continue
                    gross = float(np.sum(pnl) * 100.0)
                    row = {
                        "symbol": symbol,
                        "candidate": candidate_col,
                        "count": int(len(pnl)),
                        "tp_bps": float(tp),
                        "sl_bps": float(sl),
                        "timeout": int(to),
                        "exit_on_rc": bool(erc),
                        "gross_pnl_pct": gross,
                        "net_4bps": float(np.sum((pnl - 4 / 10000.0) * 100.0)),
                        "net_6bps": float(np.sum((pnl - 6 / 10000.0) * 100.0)),
                        "net_8bps": float(np.sum((pnl - 8 / 10000.0) * 100.0)),
                        "net_10bps": float(np.sum((pnl - 10 / 10000.0) * 100.0)),
                        "win_rate_pct": float((pnl > 0).mean() * 100.0),
                        "avg_bars": float(np.mean(bars)),
                        "tp_count": int((reasons == "TP").sum()),
                        "sl_count": int((reasons == "SL").sum()),
                        "timeout_count": int((reasons == "TIMEOUT").sum()),
                        "rc_count": int((reasons == "REGIME_CHANGE").sum()),
                    }
                    rows.append(row)

    return pd.DataFrame(rows)


def risk_off_analysis(td: pd.DataFrame, pattern_stats: pd.DataFrame, candidate_eval: pd.DataFrame) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    # Long-ban relevance: if long returns after TD bars are negative, ban remains justified.
    td_long = td.copy()
    td_long["future_6_long_bps"] = -td_long["future_6_bar_short_bps"]
    td_long["future_12_long_bps"] = -td_long["future_12_bar_short_bps"]

    by_sym = td_long.groupby("symbol").agg(
        bars=("future_6_long_bps", "count"),
        avg_future_6_long_bps=("future_6_long_bps", "mean"),
        avg_future_12_long_bps=("future_12_long_bps", "mean"),
    ).reset_index()
    out["long_during_td_baseline"] = by_sym.to_dict(orient="records")

    # Pattern-based long block / allow
    risk_rows: List[Dict[str, Any]] = []
    for _, r in pattern_stats.iterrows():
        p = str(r["name"])
        f6_short = float(r["future_6_short_bps"])
        f6_long = -f6_short
        recommendation = "BLOCK_LONG"
        if p == "PATTERN_RED_EXHAUSTION_WICK" and f6_long > 0:
            recommendation = "ALLOW_LONG_AFTER_EXHAUSTION"
        risk_rows.append(
            {
                "pattern": p,
                "symbol": str(r["symbol"]),
                "future_6_long_bps": f6_long,
                "future_6_short_bps": f6_short,
                "recommendation": recommendation,
            }
        )
    out["pattern_risk_off"] = risk_rows

    # If all short candidates are net negative at baseline, keep short disabled unless proven by strict filter.
    c = candidate_eval.copy()
    c["edge_positive_f6"] = c["f6_short_bps"] > 0
    out["candidate_edge_positive_share"] = float(
        c["edge_positive_f6"].mean()) if len(c) else 0.0

    return out


def select_top_candidates(candidate_eval: pd.DataFrame, min_count: int = 50, top_n: int = 5) -> List[str]:
    c = candidate_eval[candidate_eval["count"] >= min_count].copy()
    if c.empty:
        c = candidate_eval.copy()
    c = c.sort_values(["f6_short_bps", "count"], ascending=[False, False])
    names = c["candidate"].drop_duplicates().head(top_n).tolist()
    return [str(x) for x in names]


def build_verdict(
    top_grid: pd.DataFrame,
    candidate_eval: pd.DataFrame,
    risk_off: Dict[str, Any],
) -> str:
    if not top_grid.empty:
        ok = top_grid[top_grid["net_6bps"] > 0]
        if not ok.empty:
            return "SHORT_PATTERN_CANDIDATE_FOUND"

    if risk_off.get("candidate_edge_positive_share", 0.0) <= 0.30:
        return "ONLY_RISK_OFF_CONFIRMED"

    if candidate_eval["f6_short_bps"].max(skipna=True) <= 0:
        return "BAR_ANATOMY_INSUFFICIENT_EDGE"

    return "NEEDS_MORE_FEATURES"


def run() -> None:
    started = datetime.now(timezone.utc)
    print("Loading input data ...")
    df, trades, v2 = load_inputs()

    print("Computing bar anatomy features ...")
    feat = add_bar_features(df)

    # Keep only columns needed in anatomy dataset output to keep file practical.
    dataset_cols = [
        "timestamp",
        "symbol",
        "regime",
        "regime_confidence",
        "regime_age_bars",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "bar_range_pct",
        "bar_range_bps",
        "body_pct",
        "body_bps",
        "signed_body_pct",
        "signed_body_bps",
        "close_to_close_pct",
        "close_to_close_bps",
        "upper_wick_bps",
        "lower_wick_bps",
        "body_to_range_ratio",
        "close_position_in_bar",
        "open_position_in_bar",
        "gap_from_prev_close_bps",
        "volume_zscore_rolling",
        "range_zscore_rolling",
        "atr_bps",
        "pos_in_rng10",
        "prior_3_bar_return_bps",
        "prior_6_bar_return_bps",
    ] + [f"future_{h}_bar_short_bps" for h in FWD_H] + [f"future_{h}_bar_max_adverse_bps" for h in FWD_H]

    anatomy_dataset = feat[dataset_cols].copy()

    print("Phase 2: TREND_DOWN vs control regimes ...")
    regime_cmp = regime_compare(feat)

    print("Phase 3: continuous TREND_DOWN segment anatomy ...")
    seg = segment_anatomy(feat)

    print("Phase 4: regime lifecycle timing by age buckets ...")
    life = lifecycle_timing(feat)

    td = feat[feat["regime"] == TD].copy().reset_index(drop=True)

    print("Phase 5: forward return bucket study ...")
    bucket_study = forward_bucket_study(td)

    print("Phase 6: bar pattern taxonomy ...")
    td_pat = classify_patterns(td)
    pat_stats = pattern_forward_stats(td_pat)

    print("Phase 7: behavior candidates from anatomy ...")
    td_cand, cand_defs = define_candidates(td_pat)

    cand_rows: List[Dict[str, Any]] = []
    for sym in PRIMARY_SYMBOLS:
        sym_df = td_cand[td_cand["symbol"] ==
                         sym].copy().reset_index(drop=True)
        for cd in cand_defs:
            m = candidate_forward_eval(sym_df, cd.name)
            cand_rows.append(
                {
                    "result_type": "candidate_forward",
                    "symbol": sym,
                    "candidate": cd.name,
                    "description": cd.description,
                    **m,
                }
            )
    cand_eval = pd.DataFrame(cand_rows)

    print("Phase 8: TP/SL/timeout replay for top candidates ...")
    top_candidates = select_top_candidates(cand_eval, min_count=50, top_n=5)

    tpsl_rows: List[pd.DataFrame] = []
    for sym in PRIMARY_SYMBOLS:
        sym_df = td_cand[td_cand["symbol"] ==
                         sym].copy().reset_index(drop=True)
        for cname in top_candidates:
            if cname not in sym_df.columns:
                continue
            part = candidate_tpsl_grid(sym_df, cname, sym)
            if not part.empty:
                tpsl_rows.append(part)

    tpsl = pd.concat(
        tpsl_rows, ignore_index=True) if tpsl_rows else pd.DataFrame()

    print("Phase 9: risk-off behavior from bar anatomy ...")
    risk_off = risk_off_analysis(td_cand, pat_stats, cand_eval)

    # Consolidated pattern results CSV
    pattern_csv = pd.concat(
        [
            pat_stats,
            cand_eval,
        ],
        ignore_index=True,
        sort=False,
    )

    # Best candidates from TP/SL
    top_grid = pd.DataFrame()
    if not tpsl.empty:
        top_grid = tpsl[tpsl["count"] >= 30].sort_values(
            "net_6bps", ascending=False).head(20).copy()

    verdict = build_verdict(top_grid, cand_eval, risk_off)

    # Q/A extraction
    qa = {
        "phase2": {
            "q1_trend_down_more_red": None,
            "q2_large_range": None,
            "q3_close_near_lows": None,
            "q4_directional_or_wicky": None,
            "q5_volatility_vs_direction": None,
        },
        "phase3": {
            "q1_fall_during_segment": None,
            "q2_early_middle_late": None,
            "q3_label_late": None,
            "q4_reverse_before_change": None,
            "q5_profitable_vs_losing_diff": None,
        },
        "phase4": {
            "q1_early_better_for_shorts": None,
            "q2_late_reversal_prone": None,
            "q3_best_age_bucket": None,
            "q4_pullback_needed": None,
        },
        "phase5": {
            "q1_best_bar_types": None,
            "q2_too_much_adverse": None,
            "q3_entry_style": None,
            "q4_predictive_horizons": None,
        },
        "phase6": {
            "q1_good_short_patterns": None,
            "q2_avoid_patterns": None,
            "q3_wait_pullback_then_confirm": None,
            "q4_red_breakdown_chase": None,
        },
    }

    td_cmp = regime_cmp[regime_cmp["regime"] == TD].copy()
    non_td_cmp = regime_cmp[regime_cmp["regime"].isin(CONTROL_REGIMES)].copy()

    if not td_cmp.empty and not non_td_cmp.empty:
        qa["phase2"]["q1_trend_down_more_red"] = bool(
            td_cmp["red_share_pct"].mean() > non_td_cmp["red_share_pct"].mean())
        qa["phase2"]["q2_large_range"] = bool(
            td_cmp["avg_bar_range_bps"].mean() > non_td_cmp["avg_bar_range_bps"].mean())
        qa["phase2"]["q3_close_near_lows"] = bool(
            td_cmp["avg_close_position_in_bar"].mean() < 0.45)
        qa["phase2"]["q4_directional_or_wicky"] = "directional" if td_cmp["avg_body_to_range_ratio"].mean(
        ) >= 0.42 else "wick_heavy"
        qa["phase2"]["q5_volatility_vs_direction"] = "volatility_plus_direction" if td_cmp["avg_signed_body_bps"].mean(
        ) < 0 else "mostly_volatility"

    if not seg.empty:
        qa["phase3"]["q1_fall_during_segment"] = bool(
            seg["segment_return_bps"].median() < 0)
        qa["phase3"]["q2_early_middle_late"] = "early" if seg["first_6_bars_return_bps"].median(
        ) < seg["last_6_bars_return_bps"].median() else "late"
        qa["phase3"]["q3_label_late"] = bool(seg["first_3_bars_return_bps"].median(
        ) > seg["segment_return_bps"].median() * 0.25)
        qa["phase3"]["q4_reverse_before_change"] = bool(
            seg["last_3_bars_return_bps"].median() > 0)

    if not life.empty:
        best_age = life.sort_values(
            "next_6_bar_short_bps", ascending=False).head(1)
        qa["phase4"]["q3_best_age_bucket"] = best_age[[
            "symbol", "age_bucket", "next_6_bar_short_bps"]].to_dict(orient="records")
        early = life[life["age_bucket"].isin(
            ["age_1", "age_2_3", "age_4_6"])]["next_6_bar_short_bps"].mean()
        late = life[life["age_bucket"].isin(
            ["age_13_24", "age_gt_24"])]["next_6_bar_short_bps"].mean()
        qa["phase4"]["q1_early_better_for_shorts"] = bool(early > late)
        qa["phase4"]["q2_late_reversal_prone"] = bool(late < 0)

    if not cand_eval.empty:
        best_c = cand_eval.sort_values("f6_short_bps", ascending=False).head(5)
        worst_c = cand_eval.sort_values("adv6_bps", ascending=False).head(5)
        qa["phase5"]["q1_best_bar_types"] = best_c[["symbol", "candidate",
                                                    "f6_short_bps", "count"]].to_dict(orient="records")
        qa["phase5"]["q2_too_much_adverse"] = worst_c[[
            "symbol", "candidate", "adv6_bps", "count"]].to_dict(orient="records")
        qa["phase5"]["q3_entry_style"] = "green_pullback_or_confirm" if any(
            "BD1" in x or "BD2" in x for x in best_c["candidate"].tolist()) else "breakdown_or_other"
        qa["phase5"]["q4_predictive_horizons"] = {
            "avg_f1": float(cand_eval["f1_short_bps"].mean()),
            "avg_f3": float(cand_eval["f3_short_bps"].mean()),
            "avg_f6": float(cand_eval["f6_short_bps"].mean()),
            "avg_f12": float(cand_eval["f12_short_bps"].mean()),
            "avg_f18": float(cand_eval["f18_short_bps"].mean()),
            "avg_f36": float(cand_eval["f36_short_bps"].mean()),
        }

    if not pat_stats.empty:
        good_p = pat_stats.sort_values(
            "future_6_short_bps", ascending=False).head(3)
        bad_p = pat_stats.sort_values(
            "future_6_short_bps", ascending=True).head(3)
        qa["phase6"]["q1_good_short_patterns"] = good_p[["symbol", "name",
                                                         "future_6_short_bps", "count"]].to_dict(orient="records")
        qa["phase6"]["q2_avoid_patterns"] = bad_p[["symbol", "name",
                                                   "future_6_short_bps", "count"]].to_dict(orient="records")
        q_wait = good_p["name"].str.contains(
            "CONTINUATION_AFTER_PULLBACK").any()
        qa["phase6"]["q3_wait_pullback_then_confirm"] = bool(q_wait)
        rb = pat_stats[pat_stats["name"] == "PATTERN_RED_BREAKDOWN"]
        if not rb.empty:
            qa["phase6"]["q4_red_breakdown_chase"] = bool(
                float(rb["future_6_short_bps"].mean()) <= 0)

    # Facts/inferences/assumptions/unknowns
    facts: List[str] = []
    inferences: List[str] = []
    assumptions: List[str] = [
        "Segment first_3/first_6 returns are measured from segment start close to close at bar index min(2, n-1) / min(5, n-1).",
        "Segment last_3/last_6 returns are measured from close at start of last-3/last-6 window to segment end close.",
        "Forward predictive metrics from Phase 5 use close_t baseline (not next-bar open entry).",
        "Entry replay for candidate behavior uses next-bar open as required.",
        "No lookahead is used in candidate signal conditions; only current and prior bars are used.",
    ]
    unknowns: List[str] = []

    facts.append(f"Input bars analyzed: {len(feat):,} (BTCUSDT+ETHUSDT, 5m).")
    facts.append(f"TREND_DOWN bars analyzed: {len(td):,}.")
    facts.append(
        f"Behavior candidates tested in Phase 7: {cand_eval['candidate'].nunique() if not cand_eval.empty else 0}.")
    facts.append(
        f"Top candidates promoted to TP/SL grid (Phase 8): {len(top_candidates)}.")
    facts.append(f"TP/SL rows generated: {len(tpsl):,}.")

    if not top_grid.empty:
        best = top_grid.iloc[0].to_dict()
        facts.append(
            "Best TP/SL row by net_6bps: "
            f"{best['symbol']} {best['candidate']} tp={best['tp_bps']} sl={best['sl_bps']} to={best['timeout']} "
            f"exit_on_rc={best['exit_on_rc']} net6={best['net_6bps']:.4f}."
        )

    if verdict == "ONLY_RISK_OFF_CONFIRMED":
        inferences.append(
            "Short edge is not robust after realistic cost assumptions across tested anatomy-derived candidates.")
        inferences.append(
            "TREND_DOWN remains operationally useful as risk-off / long-ban context.")
    elif verdict == "SHORT_PATTERN_CANDIDATE_FOUND":
        inferences.append(
            "At least one anatomy-derived candidate shows positive net_6bps in TP/SL replay.")
    else:
        inferences.append(
            "Bar anatomy provides useful segmentation but does not yet provide a stable tradable short edge.")

    if tpsl.empty:
        unknowns.append(
            "No TP/SL rows produced (likely too few valid next-bar entries for selected candidates).")
    if cand_eval.empty:
        unknowns.append("No candidate forward evaluation rows generated.")

    # Prior recap
    prior_recap = {
        "v2_verdict": v2.get("verdict"),
        "v2_top_combined_best": v2.get("top_combined_best"),
        "v2_acceptance_gate": v2.get("acceptance_gate"),
    }

    # Build JSON payload
    payload: Dict[str, Any] = {
        "report_id": "AURORA_TREND_DOWN_BAR_ANATOMY_FORENSIC_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "symbols": PRIMARY_SYMBOLS,
        "timeframe": "300s",
        "facts": facts,
        "inferences": inferences,
        "assumptions": assumptions,
        "unknowns": unknowns,
        "prior_trend_down_recap": prior_recap,
        "phase2_regime_compare": regime_cmp.to_dict(orient="records"),
        "phase3_segment_summary": {
            "rows": int(len(seg)),
            "median_segment_return_bps": float(seg["segment_return_bps"].median()) if len(seg) else None,
            "median_first_6_bars_return_bps": float(seg["first_6_bars_return_bps"].median()) if len(seg) else None,
            "median_last_6_bars_return_bps": float(seg["last_6_bars_return_bps"].median()) if len(seg) else None,
        },
        "phase4_lifecycle": life.to_dict(orient="records"),
        "phase5_bucket_study_top": {k: v[:12] for k, v in bucket_study.items()},
        "phase6_pattern_taxonomy": pat_stats.to_dict(orient="records"),
        "phase7_candidate_forward": cand_eval.to_dict(orient="records"),
        "phase8_tpsl_top20": top_grid.to_dict(orient="records") if not top_grid.empty else [],
        "phase9_risk_off": risk_off,
        "critical_questions": qa,
        "rejected_patterns": (
            top_grid[top_grid["net_6bps"] <= 0][["symbol", "candidate", "tp_bps", "sl_bps",
                                                 "timeout", "exit_on_rc", "net_6bps"]].head(50).to_dict(orient="records")
            if not top_grid.empty
            else []
        ),
        "acceptance_gate": {
            "trend_down_bar_anatomy_computed": True,
            "segment_anatomy_computed": len(seg) > 0,
            "forward_return_by_bar_type_computed": len(pat_stats) > 0,
            "bar_patterns_tested": len(pat_stats) > 0,
            "at_least_5_behavior_candidates_tested": int(cand_eval["candidate"].nunique()) >= 5 if not cand_eval.empty else False,
            "tpsl_timeout_tested_for_top_patterns": len(tpsl) > 0,
            "explicit_verdict": verdict,
        },
    }

    # Save CSV artifacts
    anatomy_dataset.to_csv(OUT_DATASET_CSV, index=False)
    seg.to_csv(OUT_SEGMENT_CSV, index=False)
    pattern_csv.to_csv(OUT_PATTERN_CSV, index=False)
    tpsl.to_csv(OUT_TPSL_CSV, index=False)

    # Save JSON
    OUT_JSON.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Build MD
    best_any = top_grid.head(1).to_dict(
        orient="records") if not top_grid.empty else []
    reg_rows = regime_cmp.sort_values(
        ["symbol", "regime"]).to_dict(orient="records")
    life_rows = life.sort_values(
        ["symbol", "age_bucket"]).to_dict(orient="records")
    pat_rows = pat_stats.sort_values(["symbol", "future_6_short_bps"], ascending=[
                                     True, False]).to_dict(orient="records")
    cand_rows_md = cand_eval.sort_values(["symbol", "f6_short_bps"], ascending=[
                                         True, False]).to_dict(orient="records")
    top_rows_md = top_grid.to_dict(
        orient="records") if not top_grid.empty else []

    md_lines: List[str] = []
    md_lines.append("# AURORA_TREND_DOWN_BAR_ANATOMY_FORENSIC_V1")
    md_lines.append("")
    md_lines.append("## Verdict")
    md_lines.append("")
    md_lines.append(verdict)
    md_lines.append("")

    md_lines.append("## FACTS")
    md_lines.append("")
    for x in facts:
        md_lines.append(f"- {x}")
    md_lines.append("")

    md_lines.append("## INFERENCES")
    md_lines.append("")
    for x in inferences:
        md_lines.append(f"- {x}")
    md_lines.append("")

    md_lines.append("## ASSUMPTIONS")
    md_lines.append("")
    for x in assumptions:
        md_lines.append(f"- {x}")
    md_lines.append("")

    md_lines.append("## UNKNOWNS")
    md_lines.append("")
    if unknowns:
        for x in unknowns:
            md_lines.append(f"- {x}")
    else:
        md_lines.append(
            "- No material unknowns beyond finite sample and model risk.")
    md_lines.append("")

    md_lines.append("## Prior TREND_DOWN recap")
    md_lines.append("")
    md_lines.append(f"- V2 verdict: {v2.get('verdict')}")
    md_lines.append(f"- V2 top combined best: {v2.get('top_combined_best')}")
    md_lines.append("")

    md_lines.append("## TREND_DOWN vs other regimes")
    md_lines.append("")
    md_lines.append(_rows_to_md(reg_rows, [
        "symbol", "regime", "bars", "avg_bar_range_bps", "median_bar_range_bps", "avg_signed_body_bps",
        "red_share_pct", "green_share_pct", "avg_body_to_range_ratio", "avg_close_position_in_bar", "atr_bps_avg",
    ], max_rows=30))
    md_lines.append("")

    md_lines.append("## Bar anatomy summary")
    md_lines.append("")
    md_lines.append(
        "- Dataset artifact includes full per-bar anatomy and forward/adverse fields.")
    md_lines.append(f"- Bars in anatomy dataset: {len(anatomy_dataset):,}")
    md_lines.append(f"- TREND_DOWN bars: {len(td):,}")
    md_lines.append("")

    md_lines.append("## Segment anatomy")
    md_lines.append("")
    md_lines.append(_rows_to_md(seg.sort_values(["symbol", "bars_count"], ascending=[True, False]).to_dict(orient="records"), [
        "segment_id", "symbol", "bars_count", "segment_return_bps", "first_6_bars_return_bps", "last_6_bars_return_bps",
        "max_favorable_down_move_bps", "max_adverse_up_move_bps", "red_share", "close_near_low_share",
    ], max_rows=20))
    md_lines.append("")

    md_lines.append("## Regime lifecycle timing")
    md_lines.append("")
    md_lines.append(_rows_to_md(life_rows, [
        "symbol", "age_bucket", "bars", "avg_close_to_close_bps", "next_1_bar_short_bps", "next_3_bar_short_bps",
        "next_6_bar_short_bps", "next_12_bar_short_bps", "red_share_pct", "avg_range_bps",
    ], max_rows=30))
    md_lines.append("")

    md_lines.append("## Forward return study")
    md_lines.append("")
    for key in ["bucket_conf", "bucket_age", "bucket_range_pos", "bucket_signed_body", "bucket_close_pos", "bucket_prior3", "bucket_prior6"]:
        md_lines.append(f"### {key}")
        md_lines.append("")
        md_lines.append(_rows_to_md(bucket_study.get(key, []), [
            "symbol", "bucket", "count", "f1", "f3", "f6", "f12", "f18", "f36", "adv6", "adv12", "adv36",
        ], max_rows=12))
        md_lines.append("")

    md_lines.append("## Bar pattern taxonomy")
    md_lines.append("")
    md_lines.append(_rows_to_md(pat_rows, [
        "symbol", "name", "count", "future_1_short_bps", "future_3_short_bps", "future_6_short_bps", "future_12_short_bps",
        "adverse_6_bps", "adverse_12_bps", "red_share_pct", "close_near_low_share",
    ], max_rows=30))
    md_lines.append("")

    md_lines.append("## Pattern candidate replay")
    md_lines.append("")
    md_lines.append(_rows_to_md(cand_rows_md, [
        "symbol", "candidate", "count", "f1_short_bps", "f3_short_bps", "f6_short_bps", "f12_short_bps", "f18_short_bps", "f36_short_bps", "adv6_bps",
    ], max_rows=40))
    md_lines.append("")

    md_lines.append("## TP/SL/timeout for pattern candidates")
    md_lines.append("")
    md_lines.append(_rows_to_md(top_rows_md, [
        "symbol", "candidate", "count", "tp_bps", "sl_bps", "timeout", "exit_on_rc", "gross_pnl_pct", "net_6bps", "win_rate_pct", "avg_bars",
    ], max_rows=30))
    md_lines.append("")

    md_lines.append("## Risk-off behavior analysis")
    md_lines.append("")
    md_lines.append("### Long during TREND_DOWN baseline")
    md_lines.append("")
    md_lines.append(_rows_to_md(risk_off.get("long_during_td_baseline", []), [
        "symbol", "bars", "avg_future_6_long_bps", "avg_future_12_long_bps",
    ], max_rows=10))
    md_lines.append("")
    md_lines.append("### Pattern-level long policy")
    md_lines.append("")
    md_lines.append(_rows_to_md(risk_off.get("pattern_risk_off", []), [
        "symbol", "pattern", "future_6_long_bps", "future_6_short_bps", "recommendation",
    ], max_rows=30))
    md_lines.append("")

    md_lines.append("## BTC vs ETH split")
    md_lines.append("")
    md_lines.append(
        "- All calculations and candidate tests are split by symbol and reported with symbol field.")
    md_lines.append("")

    md_lines.append("## Best candidate if any")
    md_lines.append("")
    if best_any:
        md_lines.append(_rows_to_md(best_any, [
            "symbol", "candidate", "count", "tp_bps", "sl_bps", "timeout", "exit_on_rc", "gross_pnl_pct", "net_6bps",
        ], max_rows=1))
    else:
        md_lines.append("No TP/SL candidate rows available.")
    md_lines.append("")

    md_lines.append("## Rejected patterns")
    md_lines.append("")
    rej = payload.get("rejected_patterns", [])
    md_lines.append(_rows_to_md(rej, [
        "symbol", "candidate", "tp_bps", "sl_bps", "timeout", "exit_on_rc", "net_6bps",
    ], max_rows=50))
    md_lines.append("")

    md_lines.append("## Final recommendation")
    md_lines.append("")
    if verdict == "SHORT_PATTERN_CANDIDATE_FOUND":
        md_lines.append(
            "- Short pattern candidate exists in replay. Keep as research candidate; do not mutate runtime in this task.")
    elif verdict == "ONLY_RISK_OFF_CONFIRMED":
        md_lines.append(
            "- Keep TREND_DOWN as risk-off / long-ban context. Do not force short entries without stronger confirmation.")
        md_lines.append(
            "- If future work continues, prioritize pullback+confirmation anatomy over raw breakdown chase.")
    elif verdict == "BAR_ANATOMY_INSUFFICIENT_EDGE":
        md_lines.append(
            "- Bar anatomy alone is insufficient for stable short edge under tested costs.")
    else:
        md_lines.append(
            "- Expand features (microstructure, cross-symbol context, session context) before next candidate cycle.")
    md_lines.append("")

    md_lines.append("## Acceptance gate")
    md_lines.append("")
    gate = payload["acceptance_gate"]
    for k, v in gate.items():
        md_lines.append(f"- {k}: {v}")
    md_lines.append("")

    OUT_MD.write_text("\n".join(md_lines), encoding="utf-8")

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"Wrote {OUT_DATASET_CSV.name} ({len(anatomy_dataset):,} rows)")
    print(f"Wrote {OUT_SEGMENT_CSV.name} ({len(seg):,} rows)")
    print(f"Wrote {OUT_PATTERN_CSV.name} ({len(pattern_csv):,} rows)")
    print(f"Wrote {OUT_TPSL_CSV.name} ({len(tpsl):,} rows)")
    print(f"Wrote {OUT_JSON.name}")
    print(f"Wrote {OUT_MD.name}")
    print(f"Verdict: {verdict}")
    print(f"Elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    run()
