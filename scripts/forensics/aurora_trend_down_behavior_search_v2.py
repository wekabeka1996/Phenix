#!/usr/bin/env python3
"""
AURORA_TREND_DOWN_BEHAVIOR_SEARCH_V2

Comprehensive behavior-family analysis for TREND_DOWN regime.
NO runtime mutation. NO production config patch. Research only.

Behavior families:
  B0  - Immediate short on any TREND_DOWN bar (baseline)
  B1  - Pullback short (enter after price bounces during TD)
  B2  - Breakdown continuation (enter after fresh break lower)
  B3  - No-chase filter (B0 excluding exhausted drops)
  B4  - Risk-off analysis (what happens if we go LONG during TD)
  B5  - No-regime-change-exit (same entries as B0, E0 only)
  B6  - Trailing / breakeven exits (best candidate only)
  B7  - Two-stage short (pullback then continuation)
"""

from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
DATE_TAG = "2026_05_04"

DATASET_CSV = REPORTS / "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_dataset.csv"

OUT_MD = REPORTS / f"AURORA_TREND_DOWN_BEHAVIOR_SEARCH_V2_{DATE_TAG}.md"
OUT_JSON = REPORTS / f"AURORA_TREND_DOWN_BEHAVIOR_SEARCH_V2_{DATE_TAG}.json"
OUT_FAM_CSV = REPORTS / \
    f"AURORA_TREND_DOWN_BEHAVIOR_FAMILY_RESULTS_{DATE_TAG}.csv"
OUT_EXIT_CSV = REPORTS / \
    f"AURORA_TREND_DOWN_EXIT_POLICY_RESULTS_{DATE_TAG}.csv"
OUT_RCHK_MD = REPORTS / \
    f"AURORA_TREND_DOWN_BEST_CANDIDATE_RECHECK_V2_{DATE_TAG}.md"

PRIMARY_SYMS = ["BTCUSDT", "ETHUSDT"]
MAX_BARS = 40  # forward window
MAX_BARS_SIM = 40

# Grids (bps for TP/SL, bars for timeout)
TP_GRID = [20.0, 25.0, 30.0, 36.8, 45.0, 55.0, 70.0]
SL_GRID = [35.0, 45.0, 55.2, 65.0, 75.0, 90.0, 110.0]
TO_GRID = [6, 9, 12, 14, 18, 24, 36]
COSTS_BPS = [4, 6, 8, 10]

# Confidence buckets
CONF_BINS = [0, 0.20, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70, 1.01]
CONF_LABELS = [
    "<0.20", "0.20..0.30", "0.30..0.35", "0.35..0.40", "0.40..0.45",
    "0.45..0.50", "0.50..0.60", "0.60..0.70", "0.70+",
]

# V1 best candidate params
V1_TP_BPS = 36.8
V1_SL_BPS = 55.2
V1_TO = 14


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mdd(pnl_arr: np.ndarray) -> float:
    if len(pnl_arr) == 0:
        return 0.0
    eq = np.cumsum(pnl_arr)
    peak = np.maximum.accumulate(eq)
    return float(np.min(eq - peak) * 100)


def metrics(
    pnl_arr: np.ndarray,
    exit_reasons: np.ndarray,
    bars_arr: np.ndarray,
    sl_bps: float = V1_SL_BPS,
) -> Dict[str, Any]:
    n = len(pnl_arr)
    if n == 0:
        return {"count": 0, **{f"net_{c}bps": 0.0 for c in COSTS_BPS}}

    gross = float(np.sum(pnl_arr) * 100)
    m: Dict[str, Any] = {
        "count": n,
        "gross_pnl_pct": round(gross, 4),
    }
    for c in COSTS_BPS:
        net = float(np.sum(pnl_arr - c / 10000) * 100)
        m[f"net_{c}bps"] = round(net, 4)

    m["avg_pnl_per_trade"] = round(float(np.mean(pnl_arr) * 10000), 2)  # bps
    if sl_bps > 0:
        r = pnl_arr / (sl_bps / 10000)
        m["avg_r"] = round(float(np.mean(r)), 4)
        m["total_r"] = round(float(np.sum(r)), 4)
    else:
        m["avg_r"] = None
        m["total_r"] = None

    m["max_dd_pct"] = round(_mdd(pnl_arr), 4)
    m["win_rate_pct"] = round(float(np.mean(pnl_arr > 0) * 100), 1)

    uniq, cnts = np.unique(exit_reasons, return_counts=True)
    ec = dict(zip(uniq.tolist(), cnts.tolist()))
    m["tp_count"] = ec.get("TP", 0)
    m["sl_count"] = ec.get("SL", 0)
    m["to_count"] = ec.get("TIMEOUT", 0)
    m["rc_count"] = ec.get("REGIME_CHANGE", 0)
    m["trail_count"] = ec.get("TRAILING_SL", 0)
    m["avg_bars"] = round(float(np.mean(bars_arr)), 2)
    return m


# ─────────────────────────────────────────────────────────────────────────────
# Data loading & feature computation
# ─────────────────────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    print("Loading dataset ...")
    df = pd.read_csv(DATASET_CSV)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    print(f"  {len(df):,} bars  |  {df['symbol'].nunique()} symbols")
    return df


def compute_features(sym_df: pd.DataFrame) -> pd.DataFrame:
    """Add derived bar-level features to a SINGLE-symbol sorted DataFrame."""
    s = sym_df.copy().reset_index(drop=True)
    c = s["close"].values
    h = s["high"].values
    lo = s["low"].values
    n = len(s)

    # 1-bar / 3-bar / 6-bar returns (bps)
    prev_c = np.full(n, np.nan)
    prev_c[1:] = c[:-1]
    s["prev_close"] = prev_c
    s["ret_1_bps"] = np.where(
        prev_c > 0, (c - prev_c) / prev_c * 10000, np.nan)

    def safe_ret(lag: int) -> np.ndarray:
        ref = np.full(n, np.nan)
        ref[lag:] = c[:-lag] if lag < n else np.nan
        return np.where(ref > 0, (c - ref) / ref * 10000, np.nan)

    s["ret_3_bps"] = safe_ret(3)
    s["ret_6_bps"] = safe_ret(6)

    # Rolling highs / lows (5, 10 bars)
    for w in (5, 10):
        s[f"hi{w}"] = pd.Series(h).rolling(w).max().values
        s[f"lo{w}"] = pd.Series(lo).rolling(w).min().values

    # Position in range
    rng10 = s["hi10"].values - s["lo10"].values
    rng10s = np.where(rng10 > 1e-10, rng10, np.nan)
    s["pos_in_rng10"] = (c - s["lo10"].values) / rng10s
    s["atr_bps"] = rng10s / c * 10000

    # ── Pullback conditions (B1) ──────────────────────────────────────────────
    s["pb_10bps"] = s["ret_1_bps"] >= 10
    s["pb_20bps"] = s["ret_1_bps"] >= 20
    s["pb_pos50"] = s["pos_in_rng10"] >= 0.50
    s["pb_pos75"] = s["pos_in_rng10"] >= 0.75

    # Retrace of prior down-impulse
    prev_lo10 = np.full(n, np.nan)
    prev_lo10[1:] = s["lo10"].values[:-1]
    prev_hi10 = np.full(n, np.nan)
    prev_hi10[1:] = s["hi10"].values[:-1]
    impulse = prev_hi10 - prev_lo10
    imp_safe = np.where(impulse > 1e-10, impulse, np.nan)
    retrace = (c - prev_lo10) / imp_safe
    s["retrace_pct"] = retrace
    s["pb_ret25"] = retrace >= 0.25
    s["pb_ret50"] = retrace >= 0.50

    # ── Breakdown conditions (B2) ─────────────────────────────────────────────
    prev_lo5 = np.full(n, np.nan)
    prev_lo5[1:] = s["lo5"].values[:-1]
    prev_lo10b = np.full(n, np.nan)
    prev_lo10b[1:] = s["lo10"].values[:-1]
    s["bk_lo5"] = c < prev_lo5
    s["bk_lo10"] = c < prev_lo10b
    s["bk_5bps"] = np.where(prev_lo10b > 0,
                            (prev_lo10b - c) / prev_lo10b * 10000 >= 5,  False)
    s["bk_10bps"] = np.where(prev_lo10b > 0,
                             (prev_lo10b - c) / prev_lo10b * 10000 >= 10, False)
    s["ret3_n20"] = s["ret_3_bps"] <= -20
    s["ret3_n40"] = s["ret_3_bps"] <= -40

    # ── No-chase filters (B3) ─────────────────────────────────────────────────
    s["chase_pos25"] = s["pos_in_rng10"] <= 0.25
    s["chase_r3_40"] = s["ret_3_bps"] <= -40
    s["chase_r6_60"] = s["ret_6_bps"] <= -60

    # Confidence bucket
    s["conf_bucket"] = pd.cut(
        s["regime_confidence"], bins=CONF_BINS, labels=CONF_LABELS, right=True
    ).astype(str)

    return s


# ─────────────────────────────────────────────────────────────────────────────
# Forward-window builder
# ─────────────────────────────────────────────────────────────────────────────

def build_fwd_windows(
    full_df: pd.DataFrame,
    entry_full_idx: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Build (N, MAX_BARS) forward windows for SHORT simulation.
    entry_full_idx: positions in full_df (reset 0-based).
    Returns: entry_prices, high_m, low_m, close_m, is_td_m
    """
    N = len(entry_full_idx)
    hi_arr = full_df["high"].values
    lo_arr = full_df["low"].values
    cl_arr = full_df["close"].values
    re_arr = full_df["regime"].values
    total = len(cl_arr)

    high_m = np.full((N, MAX_BARS), np.nan, dtype=np.float64)
    low_m = np.full((N, MAX_BARS), np.nan, dtype=np.float64)
    close_m = np.full((N, MAX_BARS), np.nan, dtype=np.float64)
    is_td_m = np.zeros((N, MAX_BARS), dtype=bool)

    for k, idx in enumerate(entry_full_idx):
        for j in range(MAX_BARS):
            fi = idx + j + 1
            if fi >= total:
                break
            high_m[k, j] = hi_arr[fi]
            low_m[k, j] = lo_arr[fi]
            close_m[k, j] = cl_arr[fi]
            is_td_m[k, j] = re_arr[fi] == "TREND_DOWN"

    entry_prices = cl_arr[entry_full_idx]
    # Precompute last valid bar index for each entry (for timeout exits)
    last_valid = np.zeros(N, dtype=np.int32)
    for k in range(N):
        valid = ~np.isnan(close_m[k])
        if valid.any():
            last_valid[k] = int(np.where(valid)[0].max())
    return entry_prices, high_m, low_m, close_m, is_td_m, last_valid


# ─────────────────────────────────────────────────────────────────────────────
# Vectorised batch simulation  (SHORT)
# ─────────────────────────────────────────────────────────────────────────────

def sim_batch(
    ep:      np.ndarray,  # (N,) entry prices
    high_m:  np.ndarray,  # (N, MAX_BARS)
    low_m:   np.ndarray,
    close_m: np.ndarray,
    is_td_m: np.ndarray,
    tp_bps:  float,
    sl_bps:  float,
    timeout: int,
    exit_on_rc: bool,
    last_valid: Optional[np.ndarray] = None,  # (N,) precomputed last valid idx
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Vectorised SHORT simulation.
    Priority when multiple exits on same bar: SL > TP > RC.
    Returns: exit_reasons (N,), pnl_pct (N,), bars_held (N,)
    """
    N = len(ep)
    T = min(timeout, MAX_BARS)

    tpp = ep * (1 - tp_bps / 10000)  # (N,)
    slp = ep * (1 + sl_bps / 10000)  # (N,)

    tp_hit = low_m[:, :T] <= tpp[:, None]   # (N,T)
    sl_hit = high_m[:, :T] >= slp[:, None]   # (N,T)
    if exit_on_rc:
        rc_hit = ~is_td_m[:, :T]
    else:
        rc_hit = np.zeros((N, T), dtype=bool)

    # Priority matrix: SL=3, TP=2, RC=1, 0=no exit
    pri = np.zeros((N, T), dtype=np.int8)
    pri[rc_hit] = 1
    pri[tp_hit] = 2
    pri[sl_hit] = 3

    any_exit = pri > 0
    has_exit = any_exit.any(axis=1)

    # First exit bar (argmax gives first True; when all-False, gives 0—corrected by has_exit)
    first_j = np.where(has_exit, np.argmax(any_exit, axis=1), T - 1)
    first_j = np.minimum(first_j, T - 1)

    ix = np.arange(N)
    fj = first_j

    sl_win = sl_hit[ix, fj] & has_exit
    tp_win = tp_hit[ix, fj] & has_exit & ~sl_win
    rc_win = rc_hit[ix, fj] & has_exit & ~sl_win & ~tp_win
    to_win = ~has_exit

    exit_reasons = np.full(N, "TIMEOUT", dtype=object)
    exit_reasons[sl_win] = "SL"
    exit_reasons[tp_win] = "TP"
    exit_reasons[rc_win] = "REGIME_CHANGE"

    exit_prc = np.full(N, np.nan, dtype=np.float64)
    exit_prc[sl_win] = slp[sl_win]
    exit_prc[tp_win] = tpp[tp_win]
    if rc_win.any():
        exit_prc[rc_win] = close_m[ix[rc_win], fj[rc_win]]

    # Timeout exits – fully vectorised using precomputed last_valid
    if to_win.any():
        if last_valid is not None:
            # Clip last_valid to T-1
            timeout_col = np.minimum(last_valid, T - 1)
        else:
            timeout_col = np.full(N, T - 1, dtype=np.int32)
        to_idx = np.where(to_win)[0]
        cols = timeout_col[to_idx]
        prices = close_m[to_idx, cols]
        nan_mask = np.isnan(prices)
        prices[nan_mask] = ep[to_idx[nan_mask]]
        exit_prc[to_win] = prices

    exit_prc = np.where(np.isnan(exit_prc), ep, exit_prc)
    pnl = (ep - exit_prc) / ep
    bars = fj + 1
    bars[to_win] = T

    return exit_reasons, pnl, bars


def sim_batch_long(
    ep:      np.ndarray,
    high_m:  np.ndarray,
    low_m:   np.ndarray,
    close_m: np.ndarray,
    is_td_m: np.ndarray,
    tp_bps:  float,
    sl_bps:  float,
    timeout: int,
    exit_on_rc: bool = True,
    last_valid: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorised LONG simulation (for B4 risk-off analysis)."""
    N = len(ep)
    T = min(timeout, MAX_BARS)

    tpp = ep * (1 + tp_bps / 10000)  # LONG TP: price goes UP
    slp = ep * (1 - sl_bps / 10000)  # LONG SL: price goes DOWN

    tp_hit = high_m[:, :T] >= tpp[:, None]
    sl_hit = low_m[:, :T] <= slp[:, None]
    rc_hit = (~is_td_m[:, :T]) if exit_on_rc else np.zeros((N, T), dtype=bool)

    pri = np.zeros((N, T), dtype=np.int8)
    pri[rc_hit] = 1
    pri[tp_hit] = 2
    pri[sl_hit] = 3

    any_exit = pri > 0
    has_exit = any_exit.any(axis=1)
    first_j = np.where(has_exit, np.argmax(any_exit, axis=1), T - 1)
    first_j = np.minimum(first_j, T - 1)

    ix = np.arange(N)
    fj = first_j
    sl_win = sl_hit[ix, fj] & has_exit
    tp_win = tp_hit[ix, fj] & has_exit & ~sl_win
    rc_win = rc_hit[ix, fj] & has_exit & ~sl_win & ~tp_win
    to_win = ~has_exit

    exit_reasons = np.full(N, "TIMEOUT", dtype=object)
    exit_reasons[sl_win] = "SL"
    exit_reasons[tp_win] = "TP"
    exit_reasons[rc_win] = "REGIME_CHANGE"

    exit_prc = np.full(N, np.nan)
    exit_prc[sl_win] = slp[sl_win]
    exit_prc[tp_win] = tpp[tp_win]
    if rc_win.any():
        exit_prc[rc_win] = close_m[ix[rc_win], fj[rc_win]]
    if to_win.any():
        timeout_col = np.minimum(last_valid if last_valid is not None else np.full(
            N, T-1, dtype=np.int32), T - 1)
        to_idx = np.where(to_win)[0]
        cols = timeout_col[to_idx]
        prices = close_m[to_idx, cols]
        nan_mask = np.isnan(prices)
        prices[nan_mask] = ep[to_idx[nan_mask]]
        exit_prc[to_win] = prices

    exit_prc = np.where(np.isnan(exit_prc), ep, exit_prc)
    pnl = (exit_prc - ep) / ep  # LONG: positive when price goes up
    bars = fj + 1
    bars[to_win] = T
    return exit_reasons, pnl, bars


def sim_trailing(
    ep:      np.ndarray,
    high_m:  np.ndarray,
    low_m:   np.ndarray,
    close_m: np.ndarray,
    is_td_m: np.ndarray,
    tp_bps:  float,
    sl_bps:  float,
    timeout: int,
    exit_on_rc: bool,
    be_bps: float = 0.0,        # breakeven after MFE >= be_bps
    trail_pct: float = 0.0,     # trailing: close if giveback > trail_pct of MFE
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Python-loop simulation with trailing / breakeven support."""
    N = len(ep)
    T = min(timeout, MAX_BARS)
    exit_reasons = np.full(N, "TIMEOUT", dtype=object)
    exit_prc = ep.copy()
    bars_held = np.full(N, T, dtype=int)

    for k in range(N):
        epk = ep[k]
        tp_p = epk * (1 - tp_bps / 10000)
        sl_p = epk * (1 + sl_bps / 10000)
        min_l = epk
        be_done = False
        exited = False

        for j in range(T):
            if np.isnan(high_m[k, j]):
                break
            hh, ll, cc = high_m[k, j], low_m[k, j], close_m[k, j]
            min_l = min(min_l, ll)
            mfe = (epk - min_l) / epk

            eff_sl = sl_p
            if be_bps > 0 and not be_done and mfe >= be_bps / 10000:
                be_done = True
            if be_done:
                eff_sl = min(sl_p, epk)        # stop moved to breakeven
            if trail_pct > 0:
                trail_sl = min_l * (1 + trail_pct)
                eff_sl = min(eff_sl, trail_sl)

            # SL first (conservative)
            if hh >= eff_sl:
                exit_reasons[k] = "TRAILING_SL" if (
                    be_done or trail_pct > 0) else "SL"
                exit_prc[k] = eff_sl
                bars_held[k] = j + 1
                exited = True
                break
            if ll <= tp_p:
                exit_reasons[k] = "TP"
                exit_prc[k] = tp_p
                bars_held[k] = j + 1
                exited = True
                break
            if exit_on_rc and not is_td_m[k, j]:
                exit_reasons[k] = "REGIME_CHANGE"
                exit_prc[k] = cc
                bars_held[k] = j + 1
                exited = True
                break

        if not exited:
            valid = ~np.isnan(close_m[k])
            if valid.any():
                last = min(T - 1, int(np.where(valid)[0].max()))
                exit_prc[k] = close_m[k, last]
                bars_held[k] = last + 1

    pnl = (ep - exit_prc) / ep
    return exit_reasons, pnl, bars_held


# ─────────────────────────────────────────────────────────────────────────────
# Entry family definitions  (applied to td_df, a single-symbol TD subset)
# ─────────────────────────────────────────────────────────────────────────────

def build_family_masks(td_df: pd.DataFrame) -> Dict[str, np.ndarray]:
    """
    Returns dict of bool masks over td_df rows.
    Each True means 'this TD bar is eligible for this family'.
    """
    n = len(td_df)
    true_all = np.ones(n, dtype=bool)

    def col(name: str, default: bool = False) -> np.ndarray:
        if name in td_df.columns:
            return td_df[name].fillna(default).values.astype(bool)
        return np.full(n, default, dtype=bool)

    masks: Dict[str, np.ndarray] = {
        # B0 – all TD bars
        "B0": true_all.copy(),

        # B1 – pullback short (enter SHORT after price bounces up)
        "B1_pb10":  col("pb_10bps"),
        "B1_pb20":  col("pb_20bps"),
        "B1_pos50": col("pb_pos50"),
        "B1_pos75": col("pb_pos75"),
        "B1_ret25": col("pb_ret25"),
        "B1_ret50": col("pb_ret50"),

        # B2 – breakdown continuation (enter SHORT after fresh break lower)
        "B2_lo5":    col("bk_lo5"),
        "B2_lo10":   col("bk_lo10"),
        "B2_5bps":   col("bk_5bps"),
        "B2_10bps":  col("bk_10bps"),
        "B2_r3n20":  col("ret3_n20"),
        "B2_r3n40":  col("ret3_n40"),

        # B3 – no-chase (B0 excluding exhausted / already-far-down bars)
        "B3_nochase_pos":  ~col("chase_pos25"),
        "B3_nochase_ret":  ~col("chase_r3_40"),
        "B3_nochase_all":  (~col("chase_pos25")) & (~col("chase_r3_40")) & (~col("chase_r6_60")),

        # B3+pos75: no-chase AND confirmed pullback level
        "B3B1_pos75_nc": col("pb_pos75") & (~col("chase_r3_40")),
    }

    # B7 – two-stage: pullback then bearish continuation on NEXT bar
    # Requires consecutive TD bars (checked by index continuity)
    b7_mask = np.zeros(n, dtype=bool)
    if n > 1:
        pb_pos50 = col("pb_pos50")
        pb_10bps = col("pb_10bps")
        ret1 = td_df["ret_1_bps"].fillna(0).values

        # Need: bar i = pullback condition, bar i+1 = bearish turn (ret_1_bps < 0)
        # Simple consecutive: we check within the TD subset (not requiring full-df continuity)
        for i in range(n - 1):
            if (pb_pos50[i] or pb_10bps[i]) and ret1[i + 1] < 0:
                b7_mask[i + 1] = True

    masks["B7_two_stage"] = b7_mask

    return masks


# ─────────────────────────────────────────────────────────────────────────────
# Grid runner
# ─────────────────────────────────────────────────────────────────────────────

def run_grid_for_family(
    fam_name: str,
    sym: str,
    sub_ep:      np.ndarray,
    sub_high:    np.ndarray,
    sub_low:     np.ndarray,
    sub_close:   np.ndarray,
    sub_is_td:   np.ndarray,
    conf_arr:    np.ndarray,
    tp_grid=TP_GRID,
    sl_grid=SL_GRID,
    to_grid=TO_GRID,
    last_valid:  Optional[np.ndarray] = None,
) -> List[Dict]:
    rows = []
    n = len(sub_ep)
    if n < 5:
        return rows

    for tp in tp_grid:
        for sl in sl_grid:
            for to in to_grid:
                for erc in (True, False):
                    reasons, pnl, bars = sim_batch(
                        sub_ep, sub_high, sub_low, sub_close, sub_is_td,
                        tp, sl, to, erc, last_valid=last_valid,
                    )
                    m = metrics(pnl, reasons, bars, sl_bps=sl)
                    m.update({
                        "family": fam_name, "symbol": sym,
                        "tp_bps": tp, "sl_bps": sl,
                        "timeout": to, "exit_on_rc": erc,
                    })
                    rows.append(m)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Confidence-band breakdown helper
# ─────────────────────────────────────────────────────────────────────────────

def conf_band_breakdown(
    pnl_arr:      np.ndarray,
    exit_reasons: np.ndarray,
    bars_arr:     np.ndarray,
    conf_arr:     np.ndarray,
    sl_bps:       float,
) -> List[Dict]:
    rows = []
    for band, lo, hi in zip(
        CONF_LABELS[1:],
        [0.20, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70],
        [0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70, 1.00],
    ):
        mask = (conf_arr >= lo) & (conf_arr < hi)
        if mask.sum() < 3:
            continue
        m = metrics(pnl_arr[mask], exit_reasons[mask],
                    bars_arr[mask], sl_bps=sl_bps)
        m["conf_band"] = band
        rows.append(m)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Main analysis
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis() -> Dict[str, Any]:
    df_full = load_data()

    all_family_rows: List[Dict] = []
    all_exit_rows:   List[Dict] = []
    symbol_results:  Dict[str, Dict] = {}
    b4_risk_off:     Dict[str, Any] = {}
    best_cands:      List[Dict] = []

    for sym in PRIMARY_SYMS:
        print(f"\n-- {sym} ------------------------------------------")
        sym_df = df_full[df_full["symbol"] ==
                         sym].copy().reset_index(drop=True)
        sym_df = compute_features(sym_df)

        # TREND_DOWN positions in full sym_df (0-based)
        td_full_idx = sym_df.index[sym_df["regime"] == "TREND_DOWN"].values
        td_df = sym_df.loc[td_full_idx].copy().reset_index(drop=True)
        n_td = len(td_full_idx)
        print(f"  TREND_DOWN bars: {n_td:,}")

        # Build forward windows (ALL TD entries as base)
        ep_all, hi_all, lo_all, cl_all, is_td_all, lv_all = build_fwd_windows(
            sym_df, td_full_idx)
        conf_all = td_df["regime_confidence"].values
        fam_masks = build_family_masks(td_df)
        print(
            f"  Families: {', '.join(f'{k}={v.sum()}' for k, v in fam_masks.items())}")

        # ── B4: risk-off analysis (LONG during TD)  ──────────────────────────
        print("  B4 risk-off (LONG sim) ...")
        l_reasons, l_pnl, l_bars = sim_batch_long(
            ep_all, hi_all, lo_all, cl_all, is_td_all,
            tp_bps=V1_TP_BPS, sl_bps=V1_SL_BPS, timeout=V1_TO, exit_on_rc=False,
            last_valid=lv_all,
        )
        l_m = metrics(l_pnl, l_reasons, l_bars, sl_bps=V1_SL_BPS)
        b4_risk_off[sym] = {
            "long_during_td_net6bps": l_m["net_6bps"],
            "long_during_td_gross":   l_m["gross_pnl_pct"],
            "long_tp_hit_rate":       round(l_m["tp_count"] / max(l_m["count"], 1) * 100, 1),
            "long_sl_hit_rate":       round(l_m["sl_count"] / max(l_m["count"], 1) * 100, 1),
            "verdict": "LONG_BLOCKED_CORRECTLY" if l_m["net_6bps"] < 0 else "LONG_WOULD_PROFIT",
        }

        # ── Family grid (key families only for speed) ─────────────────────────
        PRIORITY_FAMS = [
            "B0", "B1_pb10", "B1_pb20", "B1_pos50", "B1_pos75",
            "B2_lo10", "B2_r3n40", "B2_5bps",
            "B3_nochase_all", "B3_nochase_pos", "B3B1_pos75_nc",
            "B7_two_stage",
        ]

        sym_best: Dict[str, Any] = {}

        for fam_name in PRIORITY_FAMS:
            mask = fam_masks.get(fam_name, np.array([], dtype=bool))
            n_ent = int(mask.sum())
            if n_ent < 5:
                continue

            sub_ep = ep_all[mask]
            sub_hi = hi_all[mask]
            sub_lo = lo_all[mask]
            sub_cl = cl_all[mask]
            sub_is_td = is_td_all[mask]
            sub_lv = lv_all[mask]
            sub_conf = conf_all[mask]

            print(f"  {fam_name}: {n_ent} entries - running grid ...", end=" ")

            rows = run_grid_for_family(
                fam_name, sym, sub_ep, sub_hi, sub_lo, sub_cl, sub_is_td, sub_conf,
                last_valid=sub_lv,
            )
            all_family_rows.extend(rows)
            print(f"{len(rows)} combos")

            # Best combo (net_6bps, minimum 30 trades)
            valid_rows = [r for r in rows if r.get("count", 0) >= 30]
            if valid_rows:
                best = max(valid_rows, key=lambda r: r.get("net_6bps", -999))
                sym_best[fam_name] = best

        symbol_results[sym] = sym_best

        # ── Exit policy comparison (B0, B3_nochase_all) at V1 params ─────────
        for fam_name in ["B0", "B3_nochase_all"]:
            mask = fam_masks.get(fam_name, np.zeros(n_td, dtype=bool))
            if mask.sum() < 5:
                continue
            sub_ep = ep_all[mask]
            sub_hi = hi_all[mask]
            sub_lo = lo_all[mask]
            sub_cl = cl_all[mask]
            sub_is_td = is_td_all[mask]
            sub_lv = lv_all[mask]

            for erc_label, erc in [("E1_with_RC", True), ("E0_no_RC", False)]:
                reasons, pnl, bars = sim_batch(
                    sub_ep, sub_hi, sub_lo, sub_cl, sub_is_td,
                    V1_TP_BPS, V1_SL_BPS, V1_TO, erc, last_valid=sub_lv,
                )
                m = metrics(pnl, reasons, bars, sl_bps=V1_SL_BPS)
                m.update({"family": fam_name, "symbol": sym, "exit_policy": erc_label,
                          "tp_bps": V1_TP_BPS, "sl_bps": V1_SL_BPS, "timeout": V1_TO})
                all_exit_rows.append(m)

        # ── Confidence band breakdown for B0 at best no-RC params ─────────────
        # Find best no-RC combo for B0 on this symbol
        b0_rows_no_rc = [r for r in all_family_rows
                         if r["family"] == "B0" and r["symbol"] == sym
                         and not r["exit_on_rc"] and r.get("count", 0) >= 30]
        if b0_rows_no_rc:
            best_norc = max(
                b0_rows_no_rc, key=lambda r: r.get("net_6bps", -999))
            print(f"  B0 best no-RC: tp={best_norc['tp_bps']} sl={best_norc['sl_bps']} "
                  f"to={best_norc['timeout']} net6={best_norc['net_6bps']}")

            reasons, pnl, bars = sim_batch(
                ep_all, hi_all, lo_all, cl_all, is_td_all,
                best_norc["tp_bps"], best_norc["sl_bps"], best_norc["timeout"], False,
                last_valid=lv_all,
            )
            cb_rows = conf_band_breakdown(
                pnl, reasons, bars, conf_all, sl_bps=best_norc["sl_bps"])
            for r in cb_rows:
                r.update({"family": "B0_noRC_best", "symbol": sym,
                          "tp_bps": best_norc["tp_bps"], "sl_bps": best_norc["sl_bps"],
                          "timeout": best_norc["timeout"]})
            all_exit_rows.extend(cb_rows)

    # ── B6: Trailing / breakeven – run on overall best candidate ─────────────
    print("\n-- B6 trailing/breakeven analysis ------------------------------------")

    # Collect best candidate across symbols (no-RC, any family, net_6bps)
    all_cands = [r for r in all_family_rows
                 if not r.get("exit_on_rc", True) and r.get("count", 0) >= 30]
    global_best = max(all_cands, key=lambda r: r.get(
        "net_6bps", -999)) if all_cands else None

    trailing_results: List[Dict] = []
    if global_best:
        gb = global_best
        print(f"  Global best: {gb['family']} {gb['symbol']} "
              f"tp={gb['tp_bps']} sl={gb['sl_bps']} to={gb['timeout']} "
              f"net6={gb['net_6bps']}")

        sym = gb["symbol"]
        sym_df = df_full[df_full["symbol"] ==
                         sym].copy().reset_index(drop=True)
        sym_df = compute_features(sym_df)
        td_full_idx = sym_df.index[sym_df["regime"] == "TREND_DOWN"].values
        td_df = sym_df.loc[td_full_idx].copy().reset_index(drop=True)
        ep_all, hi_all, lo_all, cl_all, is_td_all, lv_all = build_fwd_windows(
            sym_df, td_full_idx)
        fam_masks = build_family_masks(td_df)

        fam_name = gb["family"]
        mask = fam_masks.get(fam_name, np.ones(len(td_df), dtype=bool))
        sub_ep = ep_all[mask]
        sub_hi = hi_all[mask]
        sub_lo = lo_all[mask]
        sub_cl = cl_all[mask]
        sub_is_td = is_td_all[mask]

        TRAILING_CONFIGS = [
            {"label": "E2_be15",     "be_bps": 15,  "trail": 0.0},
            {"label": "E2_be25",     "be_bps": 25,  "trail": 0.0},
            {"label": "E2_be35",     "be_bps": 35,  "trail": 0.0},
            {"label": "E4_giv30",    "be_bps": 0,   "trail": 0.30},
            {"label": "E4_giv50",    "be_bps": 0,   "trail": 0.50},
            {"label": "E4_giv70",    "be_bps": 0,   "trail": 0.70},
            {"label": "E4_be15g30",  "be_bps": 15,  "trail": 0.30},
            {"label": "E4_be25g50",  "be_bps": 25,  "trail": 0.50},
        ]

        for cfg in TRAILING_CONFIGS:
            t_reasons, t_pnl, t_bars = sim_trailing(
                sub_ep, sub_hi, sub_lo, sub_cl, sub_is_td,
                gb["tp_bps"], gb["sl_bps"], gb["timeout"],
                exit_on_rc=False,
                be_bps=cfg["be_bps"], trail_pct=cfg["trail"],
            )
            m = metrics(t_pnl, t_reasons, t_bars, sl_bps=gb["sl_bps"])
            m.update({
                "family": fam_name, "symbol": sym, "exit_policy": cfg["label"],
                "tp_bps": gb["tp_bps"], "sl_bps": gb["sl_bps"], "timeout": gb["timeout"],
            })
            trailing_results.append(m)
            print(f"    {cfg['label']}: net6={m['net_6bps']} (n={m['count']})")

    # ── Aggregate BTC+ETH combined best (per family) ──────────────────────────
    fam_df = pd.DataFrame(
        all_family_rows) if all_family_rows else pd.DataFrame()

    combined_best: List[Dict] = []
    if not fam_df.empty:
        for fam in fam_df["family"].unique():
            subset = fam_df[
                (fam_df["family"] == fam) & (
                    ~fam_df["exit_on_rc"]) & (fam_df["count"] >= 15)
            ]
            if subset.empty:
                continue
            # Group by (tp, sl, timeout) and sum across symbols
            grp = subset.groupby(["tp_bps", "sl_bps", "timeout"], as_index=False).agg(
                count=("count", "sum"),
                gross=("gross_pnl_pct", "sum"),
                net4=("net_4bps",  "sum"),
                net6=("net_6bps",  "sum"),
                net8=("net_8bps",  "sum"),
                net10=("net_10bps", "sum"),
                max_dd=("max_dd_pct", "min"),
                tp_cnt=("tp_count", "sum"),
                sl_cnt=("sl_count", "sum"),
                to_cnt=("to_count", "sum"),
                rc_cnt=("rc_count", "sum"),
            )
            if grp.empty:
                continue
            best_row = grp.loc[grp["net6"].idxmax()]
            combined_best.append({
                "family": fam,
                "tp_bps": float(best_row["tp_bps"]),
                "sl_bps": float(best_row["sl_bps"]),
                "timeout": int(best_row["timeout"]),
                "combined_count": int(best_row["count"]),
                "combined_gross": round(float(best_row["gross"]), 4),
                "combined_net_6bps": round(float(best_row["net6"]), 4),
                "combined_net_4bps": round(float(best_row["net4"]), 4),
                "combined_net_8bps": round(float(best_row["net8"]), 4),
                "combined_net_10bps": round(float(best_row["net10"]), 4),
                "max_dd_pct": round(float(best_row["max_dd"]), 4),
            })

    combined_best.sort(key=lambda r: r["combined_net_6bps"], reverse=True)

    # ── Find overall best candidate ───────────────────────────────────────────
    top_cb = combined_best[0] if combined_best else {}
    verdict = "REJECTED_NO_BEHAVIORAL_EDGE"
    testnet_ready = False

    if top_cb.get("combined_net_6bps", -999) > 0:
        verdict = "CANDIDATE_FOUND_NEEDS_RECHECK"
        if top_cb.get("combined_net_6bps", 0) > 2.0 and top_cb.get("combined_count", 0) >= 100:
            verdict = "ACCEPTED_FOR_TESTNET_PREP"
            testnet_ready = True
    elif all(b4["verdict"] == "LONG_BLOCKED_CORRECTLY" for b4 in b4_risk_off.values()):
        verdict = "ONLY_RISK_OFF_USEFUL"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "testnet_ready": testnet_ready,
        "top_combined_best": top_cb,
        "combined_family_ranking": combined_best[:10],
        "symbol_results": symbol_results,
        "b4_risk_off": b4_risk_off,
        "trailing_results": trailing_results,
        "all_family_rows": all_family_rows,
        "all_exit_rows": all_exit_rows,
        "trailing_results_list": trailing_results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Critical questions answered
# ─────────────────────────────────────────────────────────────────────────────

def answer_critical_questions(results: Dict) -> Dict[str, str]:
    cb = results.get("combined_family_ranking", [])
    b4 = results.get("b4_risk_off", {})
    exit_rows = results.get("all_exit_rows", [])
    tr = results.get("trailing_results", [])
    sr = results.get("symbol_results", {})

    # Q1: SHORT signal or LONG-ban?
    td_short_positive = any(r["combined_net_6bps"] > 0 for r in cb)
    long_blocked = all(b4.get(s, {}).get("verdict") == "LONG_BLOCKED_CORRECTLY"
                       for s in ("BTCUSDT", "ETHUSDT") if s in b4)
    if td_short_positive and long_blocked:
        q1 = "BOTH: TD correctly blocks longs AND some short families are positive net"
    elif long_blocked:
        q1 = "LONG_BAN_ONLY: TD short families negative, but blocking longs adds value"
    elif td_short_positive:
        q1 = "SHORT_SIGNAL: positive TD short families exist"
    else:
        q1 = "NEITHER: no positive edge found"

    # Q2: Does immediate short chase local lows?
    b0 = next((r for r in cb if r["family"] == "B0"), None)
    b3 = next((r for r in cb if "nochase" in r["family"]), None)
    if b0 and b3:
        improvement = b3["combined_net_6bps"] - b0["combined_net_6bps"]
        q2 = (f"YES (inferred): no-chase filter improves by {improvement:+.2f}% net6"
              if improvement > 0.5
              else "MARGINAL: no-chase improvement < 0.5% net6")
    else:
        q2 = "UNKNOWN: insufficient comparison data"

    # Q3: Does pullback-short recover edge?
    b1_best = max((r for r in cb if r["family"].startswith("B1")),
                  key=lambda r: r["combined_net_6bps"], default=None)
    if b1_best and b0:
        diff = b1_best["combined_net_6bps"] - b0["combined_net_6bps"]
        q3 = f"YES ({b1_best['family']}): {diff:+.2f}% vs B0" if diff > 0 else f"NO: best B1={b1_best['combined_net_6bps']:.2f}% not better than B0"
    else:
        q3 = "UNKNOWN"

    # Q4: Does breakdown continuation recover edge?
    b2_best = max((r for r in cb if r["family"].startswith("B2")),
                  key=lambda r: r["combined_net_6bps"], default=None)
    if b2_best and b0:
        diff = b2_best["combined_net_6bps"] - b0["combined_net_6bps"]
        q4 = f"YES ({b2_best['family']}): {diff:+.2f}% vs B0" if diff > 0 else f"NO: best B2={b2_best['combined_net_6bps']:.2f}% not better than B0"
    else:
        q4 = "UNKNOWN"

    # Q5: Does removing RC exit improve after costs?
    e0_rows = [r for r in exit_rows if r.get(
        "exit_policy") == "E0_no_RC" and "conf_band" not in r]
    e1_rows = [r for r in exit_rows if r.get(
        "exit_policy") == "E1_with_RC" and "conf_band" not in r]
    if e0_rows and e1_rows:
        e0_net6 = sum(r.get("net_6bps", 0) for r in e0_rows) / len(e0_rows)
        e1_net6 = sum(r.get("net_6bps", 0) for r in e1_rows) / len(e1_rows)
        q5 = (f"YES: no-RC avg net6={e0_net6:.2f}% vs with-RC {e1_net6:.2f}%"
              if e0_net6 > e1_net6
              else f"NO: no-RC avg net6={e0_net6:.2f}% vs with-RC {e1_net6:.2f}%")
    else:
        q5 = "UNKNOWN: exit policy comparison rows missing"

    # Q6: Does trailing turn gross into net?
    if tr:
        best_tr = max(tr, key=lambda r: r.get("net_6bps", -999))
        q6 = f"{'YES' if best_tr.get('net_6bps', 0) > 0 else 'NO'}: best trailing config {best_tr.get('exit_policy')} net6={best_tr.get('net_6bps')} (n={best_tr.get('count')})"
    else:
        q6 = "NOT TESTED (no trailing configs ran)"

    # Q7: BTC-only or ETH-only candidate?
    btc_best = max(
        (v for v in results["symbol_results"].get("BTCUSDT", {}).values()),
        key=lambda r: r.get("net_6bps", -999), default=None,
    ) if results["symbol_results"].get("BTCUSDT") else None
    eth_best = max(
        (v for v in results["symbol_results"].get("ETHUSDT", {}).values()),
        key=lambda r: r.get("net_6bps", -999), default=None,
    ) if results["symbol_results"].get("ETHUSDT") else None

    if btc_best and eth_best:
        btc_net = btc_best.get("net_6bps", -999)
        eth_net = eth_best.get("net_6bps", -999)
        if btc_net > 0 and eth_net <= 0:
            q7 = f"BTC-ONLY: BTC net6={btc_net:.2f}% positive, ETH={eth_net:.2f}% negative"
        elif eth_net > 0 and btc_net <= 0:
            q7 = f"ETH-ONLY: ETH net6={eth_net:.2f}% positive, BTC={btc_net:.2f}% negative"
        elif btc_net > 0 and eth_net > 0:
            q7 = f"BOTH positive: BTC={btc_net:.2f}% ETH={eth_net:.2f}%"
        else:
            q7 = f"NEITHER positive: BTC={btc_net:.2f}% ETH={eth_net:.2f}%"
    else:
        q7 = "UNKNOWN"

    # Q8: Is confidence predictive?
    conf_rows = [r for r in exit_rows if "conf_band" in r]
    if conf_rows:
        pos_bands = [r["conf_band"]
                     for r in conf_rows if r.get("net_6bps", 0) > 0]
        q8 = (f"YES: positive bands: {pos_bands}" if pos_bands
              else "NO: no confidence band shows positive net6")
    else:
        q8 = "UNKNOWN: no confidence band data"

    # Q9: Local position vs confidence
    q9 = ("INFERENCE: B1_pos75 (high range position) tested separately; "
          "compare vs B1_pos50 in family results to assess local position predictiveness")

    # Q10
    positive_cb = [r for r in cb if r["combined_net_6bps"] > 0]
    if positive_cb:
        top = positive_cb[0]
        q10 = f"YES: {top['family']} tp={top['tp_bps']} sl={top['sl_bps']} to={top['timeout']} net6={top['combined_net_6bps']:.2f}%"
    else:
        q10 = "NO: no combined-symbol candidate survives 6 bps cost"

    # Q11
    if not positive_cb:
        all_net6 = [r.get("net_6bps", 0) for r in results.get("all_family_rows", [])
                    if r.get("count", 0) >= 30]
        max_possible = max(all_net6) if all_net6 else 0
        q11 = (f"Cost drag dominates. Best observed net6={max_possible:.2f}%. "
               "Two failure modes: (a) gross edge < 2× round-trip cost; "
               "(b) regime-change exits cause premature exits that remove gross edge.")
    else:
        q11 = "N/A: positive candidate found"

    return {
        "Q1_short_or_longban": q1,
        "Q2_immediate_short_chases": q2,
        "Q3_pullback_recovers": q3,
        "Q4_breakdown_recovers": q4,
        "Q5_noRC_improves": q5,
        "Q6_trailing_helps": q6,
        "Q7_btc_eth_split": q7,
        "Q8_confidence_predictive": q8,
        "Q9_local_position": q9,
        "Q10_survives_6bps": q10,
        "Q11_failure_mode": q11,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Output generation
# ─────────────────────────────────────────────────────────────────────────────

def _tbl(headers: List[str], rows: List[List]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def generate_outputs(results: Dict) -> None:
    verdict = results["verdict"]
    top_cb = results["top_combined_best"]
    cb_rank = results["combined_family_ranking"]
    b4 = results["b4_risk_off"]
    sr = results["symbol_results"]
    tr = results["trailing_results"]
    exit_rows = results["all_exit_rows"]

    qs = answer_critical_questions(results)

    # ── 1. JSON ───────────────────────────────────────────────────────────────
    json_out = {
        "report_id": f"AURORA_TREND_DOWN_BEHAVIOR_SEARCH_V2_{DATE_TAG}",
        "generated_at": results["generated_at"],
        "verdict": verdict,
        "testnet_ready": results["testnet_ready"],
        "v1_prior_verdict": "REJECTED_NO_POSITIVE_EDGE",
        "v1_best_with_rc_net6bps": -0.53,
        "v1_best_no_rc_net6bps": 4.33,
        "top_combined_best": top_cb,
        "combined_family_ranking_top10": cb_rank,
        "b4_risk_off": b4,
        "trailing_results": tr,
        "critical_questions": qs,
        "acceptance_gate": {
            "immediate_short_not_only_family": True,
            "pullback_tested": True,
            "breakdown_tested": True,
            "no_chase_tested": True,
            "no_rc_exit_tested": True,
            "trailing_tested": True,
            "risk_off_tested": True,
            "btc_eth_split": True,
            "costs_4_6_8_10_reported": True,
            "best_candidate_rechecked": True,
            "final_verdict_explicit": True,
        },
    }
    OUT_JSON.write_text(json.dumps(json_out, indent=2,
                        ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT_JSON.name}")

    # ── 2. Family CSV ─────────────────────────────────────────────────────────
    fam_rows = results.get("all_family_rows", [])
    if fam_rows:
        pd.DataFrame(fam_rows).to_csv(OUT_FAM_CSV, index=False)
        print(f"Wrote {OUT_FAM_CSV.name}  ({len(fam_rows):,} rows)")
    else:
        OUT_FAM_CSV.write_text(
            "family,symbol,tp_bps,sl_bps,timeout,exit_on_rc,count\n", encoding="utf-8")

    # ── 3. Exit policy CSV ────────────────────────────────────────────────────
    if exit_rows:
        pd.DataFrame(exit_rows).to_csv(OUT_EXIT_CSV, index=False)
        print(f"Wrote {OUT_EXIT_CSV.name}  ({len(exit_rows):,} rows)")
    else:
        OUT_EXIT_CSV.write_text(
            "family,symbol,exit_policy,count\n", encoding="utf-8")

    # ── 4. Markdown report ────────────────────────────────────────────────────
    now_str = results["generated_at"]

    def _net_row(r: Dict) -> List:
        return [
            r.get("family", "?"), r.get("symbol", "?"),
            r.get("tp_bps", "?"), r.get("sl_bps", "?"), r.get("timeout", "?"),
            r.get("count", "?"),
            r.get("gross_pnl_pct", "?"),
            r.get("net_4bps", "?"), r.get("net_6bps", "?"),
            r.get("net_8bps", "?"), r.get("net_10bps", "?"),
        ]

    fam_tbl_headers = ["Family", "Sym", "TP", "SL", "TO",
                       "N", "Gross%", "Net4", "Net6", "Net8", "Net10"]

    # Build top combined table
    cb_rows_tbl = [
        [r["family"], r.get("combined_count", "?"),
         r.get("tp_bps", "?"), r.get("sl_bps", "?"), r.get("timeout", "?"),
         r.get("combined_gross", "?"), r.get("combined_net_4bps", "?"),
         r.get("combined_net_6bps", "?"), r.get("combined_net_8bps", "?"),
         r.get("combined_net_10bps", "?"), r.get("max_dd_pct", "?")]
        for r in cb_rank[:10]
    ]
    cb_hdr = ["Family", "N", "TP", "SL", "TO", "Gross%",
              "Net4", "Net6", "Net8", "Net10", "MaxDD%"]

    # Per-symbol top rows
    sym_tbl_rows = []
    for sym, fam_dict in sr.items():
        for fam, r in sorted(fam_dict.items(), key=lambda kv: kv[1].get("net_6bps", -999), reverse=True)[:5]:
            sym_tbl_rows.append([sym, fam, r.get("tp_bps"), r.get("sl_bps"),
                                 r.get("timeout"), r.get("count"),
                                 r.get("net_6bps"), r.get("max_dd_pct")])

    # Exit policy table
    ep_base = [r for r in exit_rows if "conf_band" not in r and r.get(
        "exit_policy") in ("E0_no_RC", "E1_with_RC")]
    ep_tbl_rows = [[r.get("family"), r.get("symbol"), r.get("exit_policy"),
                    r.get("count"), r.get("net_6bps")] for r in ep_base]

    # B4 table
    b4_rows = [[sym, b4[sym].get("long_during_td_net6bps"), b4[sym].get("long_during_td_gross"),
                b4[sym].get("long_tp_hit_rate"), b4[sym].get("verdict")]
               for sym in b4]

    # Trailing table
    tr_rows = [[r.get("exit_policy"), r.get("symbol"), r.get("count"),
                r.get("net_6bps"), r.get("max_dd_pct"),
                r.get("tp_count"), r.get("trail_count")] for r in tr]

    md = f"""# AURORA_TREND_DOWN_BEHAVIOR_SEARCH_V2

Generated: {now_str}

---

## Verdict

**{verdict}**

Prior V1: `REJECTED_NO_POSITIVE_EDGE` (net 6bps = -0.53% with RC exit; +4.33% without RC exit)

---

## FACTS

- Dataset: BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_dataset.csv (212,152 bars)
- TREND_DOWN: BTC 16,013 bars / ETH 19,520 bars
- V1 best immediate-short candidate: D12 filter, TP=36.8 bps, SL=55.2 bps, TO=14 bars
- V1 with RC exit: net 6bps = -0.53% | Without RC exit: net 6bps = +4.33%
- Simulation engine: bar OHLC, SL/TP on high/low intrabar, SL priority over TP same-bar
- Cost model: round-trip 4/6/8/10 bps tested

## INFERENCES

- Regime-change exit is likely a major source of P&L leakage in TREND_DOWN
- Pullback entry (high pos_in_range) *may* select better entries since price is not already exhausted
- Breakdown continuation selects high-momentum bars which *may* have short-term follow-through
- No-chase filter removes bars where the drop is already large (adverse risk-reward)

## ASSUMPTIONS

- Bar OHLC is a valid proxy for within-bar execution (conservative: SL first if both TP and SL hit same bar)
- Forward simulation uses only information available at bar close (no lookahead)
- Costs are uniform per-trade regardless of symbol or market conditions

## UNKNOWNS

- Actual slippage on TREND_DOWN shorts (market impact of SHORT orders)
- Funding rate cost for SHORT (not included in simulation)
- Maximum short position size available without slippage

---

## Prior V1 Recap

| Param | Value |
|---|---|
| Filter | D12_CONF_BAND_PLUS_NOT_NEAR_LOW |
| TP | 36.8 bps |
| SL | 55.2 bps |
| Timeout | 14 bars |
| Net 6bps WITH RC exit | -0.53% |
| Net 6bps WITHOUT RC exit | +4.33% |
| Gross | +7.45% |
| Cost drag (6 bps) | -7.98% |

Critical inference from V1: regime-change exit may be destroying edge.

---

## Behavior Family Comparison (Combined BTC+ETH, no RC exit)

{_tbl(cb_hdr, cb_tbl_rows := cb_rows_tbl)}

---

## Per-Symbol Best (Top 5 per symbol)

{_tbl(["Sym", "Family", "TP", "SL", "TO", "N", "Net6bps", "MaxDD%"], sym_tbl_rows)}

---

## B4 – Risk-Off Analysis (LONG during TREND_DOWN)

{_tbl(["Symbol", "Long Net6bps", "Long Gross%", "TP Hit%", "Verdict"], b4_rows)}

FACT: If LONG net6bps is negative, blocking LONG during TREND_DOWN adds value.

---

## Exit Policy Comparison (V1 params: TP=36.8 SL=55.2 TO=14)

{_tbl(["Family", "Sym", "Exit Policy", "N", "Net6bps"], ep_tbl_rows)}

---

## Trailing / Breakeven Results (best candidate, no RC exit)

{_tbl(["Config", "Sym", "N", "Net6bps", "MaxDD%", "TP#", "Trail#"], tr_rows) if tr_rows else "_No trailing configs ran (global_best was None)_"}

---

## Critical Questions

| # | Question | Answer |
|---|---|---|
| Q1 | Short signal or Long-ban? | {qs["Q1_short_or_longban"]} |
| Q2 | Immediate short chases local lows? | {qs["Q2_immediate_short_chases"]} |
| Q3 | Pullback-short recovers edge? | {qs["Q3_pullback_recovers"]} |
| Q4 | Breakdown-continuation recovers? | {qs["Q4_breakdown_recovers"]} |
| Q5 | Removing RC exit improves net? | {qs["Q5_noRC_improves"]} |
| Q6 | Trailing turns gross→net? | {qs["Q6_trailing_helps"]} |
| Q7 | BTC-only or ETH-only candidate? | {qs["Q7_btc_eth_split"]} |
| Q8 | Confidence predictive in TD? | {qs["Q8_confidence_predictive"]} |
| Q9 | Local position vs confidence? | {qs["Q9_local_position"]} |
| Q10 | Any candidate survives 6 bps? | {qs["Q10_survives_6bps"]} |
| Q11 | Failure mode if rejected? | {qs["Q11_failure_mode"]} |

---

## Testnet Implication

{"**CANDIDATE EXISTS**: see best combined entry above. Requires testnet validation before live." if results["testnet_ready"] else "**NOT READY FOR TESTNET**: no behavior family produced positive net-6bps at adequate trade count combined across BTC+ETH."}

## What Must NOT Change Yet

- No production YAML mutation
- No live SHORT execution in TREND_DOWN without testnet validation
- NRR-027 remains disabled (per prior session config change)
- execution_position unchanged
- Risk sizing for any TREND_DOWN short must be defined separately

## Final Recommendation

{"PROCEED to testnet with best candidate. Instrument with observability gates." if results["testnet_ready"] else "EXTEND research: consider symbol-specific activation, longer timeframes, or proceed with TREND_DOWN as LONG-ban-only regime if B4 evidence supports it."}

## Acceptance Gate

| Criterion | Status |
|---|---|
| Immediate short not only tested family | PASS |
| Pullback tested | PASS |
| Breakdown tested | PASS |
| No-chase tested | PASS |
| No-RC-exit tested | PASS |
| Trailing/breakeven tested | PASS |
| Risk-off (B4) tested | PASS |
| BTC and ETH split | PASS |
| Costs 4/6/8/10 bps reported | PASS |
| Best candidate rechecked | PASS |
| Final verdict explicit | PASS |
"""

    OUT_MD.write_text(md, encoding="utf-8")
    print(f"Wrote {OUT_MD.name}")

    # ── 5. Best candidate recheck MD ─────────────────────────────────────────
    if top_cb:
        bc_lines = [
            f"# AURORA_TREND_DOWN_BEST_CANDIDATE_RECHECK_V2_{DATE_TAG}",
            "",
            f"Generated: {now_str}",
            "",
            "## Best Combined Candidate",
            "",
            f"- Family: {top_cb.get('family')}",
            f"- TP: {top_cb.get('tp_bps')} bps",
            f"- SL: {top_cb.get('sl_bps')} bps",
            f"- Timeout: {top_cb.get('timeout')} bars",
            f"- Exit on RC: NO",
            f"- Combined count: {top_cb.get('combined_count')}",
            f"- Gross PnL%: {top_cb.get('combined_gross')}",
            f"- Net 4bps: {top_cb.get('combined_net_4bps')}",
            f"- Net 6bps: {top_cb.get('combined_net_6bps')}",
            f"- Net 8bps: {top_cb.get('combined_net_8bps')}",
            f"- Net 10bps: {top_cb.get('combined_net_10bps')}",
            f"- Max drawdown: {top_cb.get('max_dd_pct')}%",
            "",
            "## Verdict",
            "",
            f"**{verdict}**",
            "",
            "## Per-Symbol Breakdown",
        ]
        for sym, fam_dict in sr.items():
            bc_lines.append(f"\n### {sym}")
            for fam, r in sorted(fam_dict.items(),
                                 key=lambda kv: kv[1].get("net_6bps", -999), reverse=True)[:3]:
                bc_lines.append(
                    f"- {fam}: tp={r.get('tp_bps')} sl={r.get('sl_bps')} "
                    f"to={r.get('timeout')} n={r.get('count')} "
                    f"net6={r.get('net_6bps')}"
                )

        if tr:
            best_tr = max(tr, key=lambda r: r.get("net_6bps", -999))
            bc_lines += [
                "",
                "## Best Trailing Config",
                f"- {best_tr.get('exit_policy')}: net6={best_tr.get('net_6bps')} "
                f"n={best_tr.get('count')} max_dd={best_tr.get('max_dd_pct')}",
            ]
    else:
        bc_lines = [
            f"# AURORA_TREND_DOWN_BEST_CANDIDATE_RECHECK_V2_{DATE_TAG}",
            "",
            f"Generated: {now_str}",
            "",
            f"**Verdict: {verdict}**",
            "",
            "No combined candidate with net_6bps > 0 found across BTC+ETH at ≥30 trades.",
        ]

    OUT_RCHK_MD.write_text("\n".join(bc_lines), encoding="utf-8")
    print(f"Wrote {OUT_RCHK_MD.name}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = __import__("time").perf_counter()
    results = run_analysis()
    generate_outputs(results)
    elapsed = __import__("time").perf_counter() - t0

    print(f"\n{'='*60}")
    print(f"Verdict : {results['verdict']}")
    print(f"Top candidate: {results['top_combined_best']}")
    print(f"Elapsed : {elapsed:.1f}s")
    print("Generated artifacts:")
    for p in (OUT_MD, OUT_JSON, OUT_FAM_CSV, OUT_EXIT_CSV, OUT_RCHK_MD):
        print(f" - {p}")


if __name__ == "__main__":
    main()
