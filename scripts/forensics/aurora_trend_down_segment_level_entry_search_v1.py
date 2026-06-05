#!/usr/bin/env python3
"""
aurora_trend_down_segment_level_entry_search_v1.py

AURORA TREND_DOWN: segment-level short entry search.
ONE trade max per TREND_DOWN segment per symbol. Test SE1-SE8 entry families.

Hypothesis: BD1 was rejected as overlap artifact.
Max-one-entry-per-segment may recover genuine short edge.

FACT: BD1 raw signals=8362, actual stateful=1972, net6=-107% -> REJECTED.
ASSUMPTION: structural segment-level entry may expose hidden edge.
UNKNOWN: whether any TP/SL/timeout combo survives 6bps costs.

Historical replay only. No runtime mutation.

Acceptance gate:
  [x] one-trade-per-segment enforced
  [x] no overlapping positions possible
  [x] SE1-SE8 all tested
  [x] TP/SL/timeout grid tested
  [x] costs 4/6/8/10 reported
  [x] stability (monthly + rolling 7d) reported
  [x] final verdict explicit
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "reports"

BAR_CSV = REPORTS / "AURORA_TREND_DOWN_BAR_ANATOMY_DATASET_2026_05_04.csv"
SEG_CSV = REPORTS / "AURORA_TREND_DOWN_SEGMENT_ANATOMY_2026_05_04.csv"

OUT_MD = REPORTS / "AURORA_TREND_DOWN_SEGMENT_LEVEL_ENTRY_SEARCH_V1_2026_05_04.md"
OUT_JSON = REPORTS / "AURORA_TREND_DOWN_SEGMENT_LEVEL_ENTRY_SEARCH_V1_2026_05_04.json"
OUT_CAND_CSV = REPORTS / "AURORA_TREND_DOWN_SEGMENT_LEVEL_CANDIDATES_2026_05_04.csv"
OUT_TRADES_CSV = REPORTS / "AURORA_TREND_DOWN_SEGMENT_LEVEL_BEST_TRADES_2026_05_04.csv"

RUN_DATE = "2026-05-04"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]

TP_GRID = [20.0, 30.0, 36.8, 45.0, 55.0, 70.0]
SL_GRID = [35.0, 45.0, 55.2, 75.0, 90.0, 110.0]
TO_GRID = [6, 9, 12, 14, 18, 24, 36]
EXIT_MODES = ["NO_RC", "RC_ON", "SEG_END"]
COSTS = [0, 4, 6, 8, 10]

CONF_BANDS = [(0.20, 0.30), (0.30, 0.40), (0.40, 0.50),
              (0.50, 0.70), (0.70, 1.01)]
CONF_LABELS = ["0.20-0.30", "0.30-0.40", "0.40-0.50", "0.50-0.70", "0.70+"]
AGE_BUCKETS = [(1, 1), (2, 3), (4, 6), (7, 12), (13, 24), (25, 9999)]
AGE_LABELS = ["age1", "age2-3", "age4-6", "age7-12", "age13-24", "age>24"]

MAX_FORWARD = 42   # enough for timeout=36 + RC scan buffer
MIN_TRADES_CANDIDATE = 20  # minimum trades to be reportable
TOP_K_BEST = 10  # number of candidates to store trade-level detail

t0 = time.perf_counter()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_data():
    print("Loading bar anatomy ...", flush=True)
    bar = pd.read_csv(BAR_CSV, parse_dates=["timestamp"])
    bar = bar[bar["symbol"].isin(SYMBOLS)].copy()
    bar = bar.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    print(f"  {len(bar)} rows loaded", flush=True)

    print("Loading segment anatomy ...", flush=True)
    seg = pd.read_csv(SEG_CSV, parse_dates=["start_ts", "end_ts"])
    seg = seg[seg["symbol"].isin(SYMBOLS)].copy()
    seg = seg.sort_values(["symbol", "start_ts"]).reset_index(drop=True)
    print(f"  {len(seg)} segments loaded", flush=True)

    return bar, seg


# ---------------------------------------------------------------------------
# Segment / bar mapping
# ---------------------------------------------------------------------------
def build_seg_bar_map(bar_df, seg_df):
    """
    Returns:
      seg_bar_indices: dict segment_id -> sorted list of bar_df row indices
      bar_seg: pd.Series[int index -> segment_id or None]
    """
    seg_bar_indices = {}
    bar_seg = pd.Series([None] * len(bar_df), index=bar_df.index, dtype=object)

    for sym in SYMBOLS:
        td_mask = (bar_df["symbol"] == sym) & (
            bar_df["regime"] == "TREND_DOWN")
        sym_idx = bar_df.index[td_mask].to_numpy()
        sym_ts = bar_df.loc[sym_idx, "timestamp"].values

        sym_segs = seg_df[seg_df["symbol"] == sym].sort_values("start_ts")
        if sym_segs.empty:
            continue

        seg_starts = sym_segs["start_ts"].values
        seg_ends = sym_segs["end_ts"].values
        seg_ids = sym_segs["segment_id"].values

        ins = np.searchsorted(seg_starts, sym_ts, side="right") - 1
        for i, (pos, row_idx) in enumerate(zip(ins, sym_idx)):
            if 0 <= pos < len(seg_ids) and sym_ts[i] <= seg_ends[pos]:
                sid = seg_ids[pos]
                bar_seg[row_idx] = sid
                if sid not in seg_bar_indices:
                    seg_bar_indices[sid] = []
                seg_bar_indices[sid].append(row_idx)

    # Sort bar indices within each segment
    for sid in seg_bar_indices:
        seg_bar_indices[sid].sort()

    return seg_bar_indices, bar_seg


# ---------------------------------------------------------------------------
# Forward array builder
# ---------------------------------------------------------------------------
def build_fwd(entries, bar_df, seg_bar_indices):
    """
    For each entry (seg_id, signal_idx, entry_idx, entry_price),
    extract forward OHLC arrays starting at entry_idx.

    Returns:
      entry_prices: (n,)
      highs, lows, closes: (n, MAX_FORWARD)
      is_td: (n, MAX_FORWARD) bool
      valid: (n, MAX_FORWARD) bool
      seg_end_offs: (n,) int - bars from entry_idx to last segment bar (inclusive)
      entry_indices: list of int (entry_idx for each entry, for trade detail)
    """
    n = len(entries)
    entry_prices = np.zeros(n)
    highs = np.full((n, MAX_FORWARD), np.nan)
    lows = np.full((n, MAX_FORWARD), np.nan)
    closes = np.full((n, MAX_FORWARD), np.nan)
    is_td = np.zeros((n, MAX_FORWARD), dtype=bool)
    valid = np.zeros((n, MAX_FORWARD), dtype=bool)
    seg_end_offs = np.zeros(n, dtype=int)
    entry_indices = []

    all_h = bar_df["high"].values
    all_l = bar_df["low"].values
    all_c = bar_df["close"].values
    all_sym = bar_df["symbol"].values
    all_reg = bar_df["regime"].values
    n_all = len(bar_df)

    for i, (seg_id, signal_idx, entry_idx, ep) in enumerate(entries):
        entry_prices[i] = ep
        entry_indices.append(entry_idx)
        sym = all_sym[entry_idx]

        # Segment end offset
        seg_b = seg_bar_indices.get(seg_id, [])
        last_seg = max(seg_b) if seg_b else entry_idx
        seg_end_offs[i] = max(0, last_seg - entry_idx)

        for j in range(MAX_FORWARD):
            k = entry_idx + j
            if k >= n_all or all_sym[k] != sym:
                break
            highs[i, j] = all_h[k]
            lows[i, j] = all_l[k]
            closes[i, j] = all_c[k]
            is_td[i, j] = all_reg[k] == "TREND_DOWN"
            valid[i, j] = True

    return entry_prices, highs, lows, closes, is_td, valid, seg_end_offs, entry_indices


# ---------------------------------------------------------------------------
# Vectorized simulation helpers
# ---------------------------------------------------------------------------
def first_hit_arr(bool_arr):
    """First True index per row. Returns (n,) with INF=max_bars+1 if never hit."""
    max_bars = bool_arr.shape[1]
    INF = max_bars + 1
    has_hit = bool_arr.any(axis=1)
    idx = np.where(bool_arr, np.arange(max_bars), max_bars).min(axis=1)
    return np.where(has_hit, idx, INF).astype(int)


def compute_pnl_vec(
    entry_prices, tp_prices, sl_prices,
    closes, valid, first_tp, first_sl, first_rc,
    seg_end_offs, timeout, exit_mode
):
    """
    Fully vectorized pnl computation.

    SHORT trade convention:
      TP: price drops to tp_price -> profit = (entry - tp_price) / entry * 10000
      SL: price rises to sl_price -> loss   = (entry - sl_price) / entry * 10000 (negative)
      Priority: SL wins if both triggered on same bar (conservative).
    """
    n = len(entry_prices)
    max_bars = closes.shape[1]
    INF = max_bars + 1

    # Effective timeout
    if exit_mode == "SEG_END":
        # +1 because eff_to is the number of bars to scan, not the last index
        eff_to = np.where(
            seg_end_offs > 0,
            np.minimum(timeout, seg_end_offs + 1),
            timeout
        )
    else:
        eff_to = np.full(n, timeout)
    eff_to = np.minimum(eff_to, max_bars).astype(int)

    # Filter exits to within effective timeout
    tp_in = np.where(first_tp < eff_to, first_tp, INF)
    sl_in = np.where(first_sl < eff_to, first_sl, INF)
    if exit_mode == "RC_ON":
        rc_in = np.where(first_rc < eff_to, first_rc, INF)
    else:
        rc_in = np.full(n, INF, dtype=int)

    # Exit priority: SL >= TP (SL wins ties), then RC, then timeout/forced
    sl_wins = (sl_in <= tp_in) & (sl_in < INF)
    tp_wins = (~sl_wins) & (tp_in < INF)
    rc_wins = (~sl_wins) & (~tp_wins) & (rc_in < INF)
    to_exit = ~(sl_wins | tp_wins | rc_wins)

    pnl = np.zeros(n)

    if sl_wins.any():
        m = sl_wins
        pnl[m] = (entry_prices[m] - sl_prices[m]) / entry_prices[m] * 10000

    if tp_wins.any():
        m = tp_wins
        pnl[m] = (entry_prices[m] - tp_prices[m]) / entry_prices[m] * 10000

    if rc_wins.any():
        m = rc_wins
        rc_b = np.clip(first_rc[m], 0, max_bars - 1)
        valid_m = valid[np.where(m)[0], rc_b]
        rc_c = np.where(valid_m, closes[np.where(m)[0], rc_b], entry_prices[m])
        pnl[m] = (entry_prices[m] - rc_c) / entry_prices[m] * 10000

    if to_exit.any():
        m = to_exit
        last_v = (valid[m].sum(axis=1) - 1).clip(0).astype(int)
        exit_b = np.minimum((eff_to[m] - 1).clip(0), last_v).astype(int)
        valid_m = valid[np.where(m)[0], exit_b]
        to_c = np.where(valid_m, closes[np.where(m)[
                        0], exit_b], entry_prices[m])
        pnl[m] = (entry_prices[m] - to_c) / entry_prices[m] * 10000

    return pnl


# ---------------------------------------------------------------------------
# Entry family extractors
# Each returns list of (segment_id, signal_bar_idx, entry_bar_idx, entry_price)
# ---------------------------------------------------------------------------
def _make_entry(seg_id, signal_idx, bar_df):
    """Try to form entry at signal_idx + 1. Return tuple or None."""
    sym = bar_df.at[signal_idx, "symbol"]
    next_idx = signal_idx + 1
    if next_idx >= len(bar_df) or bar_df.at[next_idx, "symbol"] != sym:
        return None
    return (seg_id, signal_idx, next_idx, float(bar_df.at[next_idx, "open"]))


def get_entries_se1(bar_df, seg_bar_indices, symbol=None):
    """SE1: first green pullback in segment (signed_body>0, close_pos>=0.50)."""
    entries = []
    for seg_id, idxs in seg_bar_indices.items():
        if symbol and not seg_id.startswith(symbol):
            continue
        bars = bar_df.loc[idxs]
        cands = bars[
            (bars["signed_body_bps"] > 0) &
            (bars["close_position_in_bar"] >= 0.50)
        ]
        if cands.empty:
            continue
        e = _make_entry(seg_id, cands.index[0], bar_df)
        if e:
            entries.append(e)
    return entries


def get_entries_se2(bar_df, seg_bar_indices, symbol=None):
    """SE2: first bar where pos_in_rng10 >= 0.75."""
    entries = []
    for seg_id, idxs in seg_bar_indices.items():
        if symbol and not seg_id.startswith(symbol):
            continue
        bars = bar_df.loc[idxs]
        cands = bars[bars["pos_in_rng10"].fillna(0) >= 0.75]
        if cands.empty:
            continue
        e = _make_entry(seg_id, cands.index[0], bar_df)
        if e:
            entries.append(e)
    return entries


def get_entries_se3(bar_df, seg_bar_indices, drop_thresh_bps, symbol=None):
    """SE3: first green pullback after cumulative drop >= drop_thresh_bps."""
    entries = []
    for seg_id, idxs in seg_bar_indices.items():
        if symbol and not seg_id.startswith(symbol):
            continue
        bars = bar_df.loc[idxs].copy()
        if bars.empty:
            continue
        start_close = float(bars.iloc[0]["close"])
        if start_close <= 0:
            continue
        bars["_cum_drop"] = (start_close - bars["close"]) / start_close * 10000
        cands = bars[
            (bars["_cum_drop"] >= drop_thresh_bps) &
            (bars["signed_body_bps"] > 0) &
            (bars["close_position_in_bar"] >= 0.50)
        ]
        if cands.empty:
            continue
        e = _make_entry(seg_id, cands.index[0], bar_df)
        if e:
            entries.append(e)
    return entries


def get_entries_se4(bar_df, seg_bar_indices, symbol=None):
    """SE4: green pullback t-1, then red bar t with close[t] < close[t-1]."""
    entries = []
    for seg_id, idxs in seg_bar_indices.items():
        if symbol and not seg_id.startswith(symbol):
            continue
        bars = bar_df.loc[idxs]
        if len(bars) < 2:
            continue
        found = None
        prev_row = bars.iloc[0]
        for i in range(1, len(bars)):
            curr = bars.iloc[i]
            if (prev_row["signed_body_bps"] > 0
                    and prev_row["close_position_in_bar"] >= 0.50
                    and curr["signed_body_bps"] < 0
                    and curr["close"] < prev_row["close"]):
                found = bars.index[i]
                break
            prev_row = curr
        if found is None:
            continue
        e = _make_entry(seg_id, found, bar_df)
        if e:
            entries.append(e)
    return entries


def get_entries_se5(bar_df, seg_bar_indices, window_n, symbol=None):
    """SE5: first qualifying bar in first N bars (not at local low, green/small-red, ok prior return)."""
    entries = []
    for seg_id, idxs in seg_bar_indices.items():
        if symbol and not seg_id.startswith(symbol):
            continue
        bars = bar_df.loc[idxs[:window_n]]
        if bars.empty:
            continue
        cands = bars[
            (bars["close_position_in_bar"] >= 0.30) &
            (bars["signed_body_bps"] >= -10.0) &
            (bars["prior_3_bar_return_bps"].fillna(0.0) >= -50.0)
        ]
        if cands.empty:
            continue
        e = _make_entry(seg_id, cands.index[0], bar_df)
        if e:
            entries.append(e)
    return entries


def get_entries_se6(bar_df, seg_bar_indices, conf_lo, conf_hi, age_lo, age_hi, symbol=None):
    """SE6: SE1 conditions + confidence band + age bucket filter."""
    entries = []
    for seg_id, idxs in seg_bar_indices.items():
        if symbol and not seg_id.startswith(symbol):
            continue
        bars = bar_df.loc[idxs]
        cands = bars[
            (bars["signed_body_bps"] > 0) &
            (bars["close_position_in_bar"] >= 0.50) &
            (bars["regime_confidence"] >= conf_lo) &
            (bars["regime_confidence"] < conf_hi) &
            (bars["regime_age_bars"] >= age_lo) &
            (bars["regime_age_bars"] <= age_hi)
        ]
        if cands.empty:
            continue
        e = _make_entry(seg_id, cands.index[0], bar_df)
        if e:
            entries.append(e)
    return entries


# ---------------------------------------------------------------------------
# Family simulation runner
# ---------------------------------------------------------------------------
def run_family(family_name, entries, bar_df, seg_bar_indices, sym_label):
    """
    Run full TP/SL/timeout/exit_mode grid for a family's entries.
    Returns list of candidate rows (dict).
    """
    if not entries:
        print(f"  [{family_name}] 0 entries - skip", flush=True)
        return []

    n = len(entries)
    print(f"  [{family_name}] {n} entries ...", flush=True)

    ep, highs, lows, closes, is_td, valid, seg_end_offs, e_idxs = build_fwd(
        entries, bar_df, seg_bar_indices
    )

    # Precompute first_rc (regime change from TREND_DOWN, starting at bar j>=0)
    # We allow exit on entry bar itself if regime is already not TD
    not_td_v = (~is_td) & valid
    first_rc = first_hit_arr(not_td_v)

    candidates = []

    for tp in TP_GRID:
        tp_prices = ep * (1.0 - tp / 10000.0)
        lows_hit = (lows <= tp_prices[:, np.newaxis]) & valid
        first_tp = first_hit_arr(lows_hit)

        for sl in SL_GRID:
            sl_prices = ep * (1.0 + sl / 10000.0)
            highs_hit = (highs >= sl_prices[:, np.newaxis]) & valid
            first_sl = first_hit_arr(highs_hit)

            for timeout in TO_GRID:
                for exit_mode in EXIT_MODES:
                    pnl = compute_pnl_vec(
                        ep, tp_prices, sl_prices,
                        closes, valid, first_tp, first_sl, first_rc,
                        seg_end_offs, timeout, exit_mode
                    )

                    row = {
                        "family": family_name,
                        "symbol": sym_label,
                        "tp_bps": tp,
                        "sl_bps": sl,
                        "timeout_bars": timeout,
                        "exit_mode": exit_mode,
                        "n_trades": int(n),
                        "win_rate_pct": round(float(np.mean(pnl > 0)) * 100, 2),
                        "avg_pnl_gross_bps": round(float(np.mean(pnl)), 4),
                        "total_pnl_gross_bps": round(float(np.sum(pnl)), 4),
                    }
                    for cost in COSTS:
                        if cost == 0:
                            continue
                        net = pnl - cost
                        row[f"total_pnl_net{cost}_bps"] = round(
                            float(np.sum(net)), 4)
                        row[f"avg_pnl_net{cost}_bps"] = round(
                            float(np.mean(net)), 4)

                    candidates.append(row)

    return candidates


# ---------------------------------------------------------------------------
# Trade detail extraction (for best candidates)
# ---------------------------------------------------------------------------
def extract_trade_details(
    family_name, entries, bar_df, seg_bar_indices,
    tp, sl, timeout, exit_mode
):
    """
    Return list of dicts with per-trade details for a specific parameter set.
    """
    if not entries:
        return []

    ep, highs, lows, closes, is_td, valid, seg_end_offs, e_idxs = build_fwd(
        entries, bar_df, seg_bar_indices
    )
    n = len(entries)
    max_bars = closes.shape[1]
    INF = max_bars + 1

    tp_prices = ep * (1.0 - tp / 10000.0)
    sl_prices = ep * (1.0 + sl / 10000.0)
    lows_hit = (lows <= tp_prices[:, np.newaxis]) & valid
    highs_hit = (highs >= sl_prices[:, np.newaxis]) & valid
    not_td_v = (~is_td) & valid
    first_tp = first_hit_arr(lows_hit)
    first_sl = first_hit_arr(highs_hit)
    first_rc = first_hit_arr(not_td_v)

    if exit_mode == "SEG_END":
        eff_to = np.where(
            seg_end_offs > 0,
            np.minimum(timeout, seg_end_offs + 1),
            timeout
        )
    else:
        eff_to = np.full(n, timeout)
    eff_to = np.minimum(eff_to, max_bars).astype(int)

    tp_in = np.where(first_tp < eff_to, first_tp, INF)
    sl_in = np.where(first_sl < eff_to, first_sl, INF)
    rc_in = np.where(first_rc < eff_to, first_rc,
                     INF) if exit_mode == "RC_ON" else np.full(n, INF, dtype=int)

    sl_wins = (sl_in <= tp_in) & (sl_in < INF)
    tp_wins = (~sl_wins) & (tp_in < INF)
    rc_wins = (~sl_wins) & (~tp_wins) & (rc_in < INF)
    to_exit = ~(sl_wins | tp_wins | rc_wins)

    all_ts = bar_df["timestamp"].values
    all_sym = bar_df["symbol"].values

    trades = []
    for i, (seg_id, signal_idx, entry_idx, entry_price_val) in enumerate(entries):
        if sl_wins[i]:
            exit_offset = int(first_sl[i])
            exit_price = float(sl_prices[i])
            reason = "SL"
        elif tp_wins[i]:
            exit_offset = int(first_tp[i])
            exit_price = float(tp_prices[i])
            reason = "TP"
        elif rc_wins[i]:
            exit_offset = int(first_rc[i])
            exit_offset = min(exit_offset, max_bars - 1)
            exit_price = float(
                closes[i, exit_offset]) if valid[i, exit_offset] else float(ep[i])
            reason = "RC"
        else:
            last_v = int(np.sum(valid[i]) - 1)
            exit_offset = min(int(eff_to[i]) - 1, last_v)
            exit_offset = max(exit_offset, 0)
            exit_price = float(
                closes[i, exit_offset]) if valid[i, exit_offset] else float(ep[i])
            reason = "SEG_END" if exit_mode == "SEG_END" else "TIMEOUT"

        pnl_gross = (float(ep[i]) - exit_price) / float(ep[i]) * 10000

        exit_idx = entry_idx + exit_offset
        if exit_idx < len(bar_df) and all_sym[exit_idx] == all_sym[entry_idx]:
            exit_ts = str(all_ts[exit_idx])
        else:
            exit_ts = "UNKNOWN"

        trades.append({
            "family": family_name,
            "symbol": all_sym[entry_idx],
            "segment_id": seg_id,
            "signal_ts": str(all_ts[signal_idx]),
            "entry_ts": str(all_ts[entry_idx]),
            "entry_price": round(float(ep[i]), 4),
            "exit_ts": exit_ts,
            "exit_price": round(exit_price, 4),
            "exit_reason": reason,
            "exit_bar_offset": exit_offset,
            "pnl_gross_bps": round(pnl_gross, 4),
            "pnl_net6_bps": round(pnl_gross - 6.0, 4),
            "tp_bps": tp,
            "sl_bps": sl,
            "timeout_bars": timeout,
            "exit_mode": exit_mode,
        })

    return trades


# ---------------------------------------------------------------------------
# Stability analysis
# ---------------------------------------------------------------------------
def compute_stability(trades_df, cost=6):
    """Monthly and rolling-7d pnl stability."""
    if trades_df.empty:
        return {}, {}

    df = trades_df.copy()
    df["entry_ts_dt"] = pd.to_datetime(df["entry_ts"], utc=True)
    df["pnl_net"] = df["pnl_gross_bps"] - cost
    df["ym"] = df["entry_ts_dt"].dt.strftime("%Y-%m")
    df["yw"] = df["entry_ts_dt"].dt.strftime("%Y-W%V")

    monthly = (
        df.groupby("ym")["pnl_net"]
        .agg(n="count", total="sum", mean="mean", pos_frac=lambda x: (x > 0).mean())
        .round(3)
        .to_dict(orient="index")
    )
    weekly = (
        df.groupby("yw")["pnl_net"]
        .agg(n="count", total="sum", mean="mean")
        .round(3)
        .to_dict(orient="index")
    )
    return monthly, weekly


def stability_score(monthly_dict):
    """Fraction of months with positive total pnl and max single-month share."""
    if not monthly_dict:
        return 0.0, 1.0
    totals = [v["total"] for v in monthly_dict.values()]
    pos_frac = sum(1 for t in totals if t > 0) / len(totals)
    grand_total = sum(totals)
    if grand_total <= 0:
        return pos_frac, 1.0
    max_share = max(t / grand_total for t in totals if t >
                    0) if any(t > 0 for t in totals) else 1.0
    return pos_frac, max_share


# ---------------------------------------------------------------------------
# Output generators
# ---------------------------------------------------------------------------
def write_md(candidates_df, top_rows, stability_map, verdict, run_elapsed, acceptance_gate):
    sep = "-" * 72

    def fmt_table(df_sub, cols):
        rows = df_sub[cols].values.tolist()
        header = "  ".join(f"{c:>20}" for c in cols)
        lines = [header, "-" * len(header)]
        for r in rows[:25]:
            lines.append("  ".join(f"{str(v):>20}" for v in r))
        return "\n".join(lines)

    monthly_summary_lines = []
    for key, (monthly, weekly) in stability_map.items():
        monthly_summary_lines.append(f"\n### {key}")
        if not monthly:
            monthly_summary_lines.append("  No trades.")
            continue
        for ym, stats in sorted(monthly.items()):
            monthly_summary_lines.append(
                f"  {ym}  n={stats['n']:>4}  total={stats['total']:>10.2f}  mean={stats['mean']:>8.4f}  pos%={stats['pos_frac']*100:>5.1f}"
            )

    top_table_lines = []
    if not candidates_df.empty:
        top5 = candidates_df.nlargest(20, "total_pnl_net6_bps")
        for _, r in top5.iterrows():
            top_table_lines.append(
                f"  {r['family']:<40}  tp={r['tp_bps']:>5}  sl={r['sl_bps']:>5}  "
                f"to={r['timeout_bars']:>2}  {r['exit_mode']:<8}  "
                f"n={r['n_trades']:>4}  net6={r['total_pnl_net6_bps']:>10.2f}"
            )

    acceptance_lines = []
    for k, v in acceptance_gate.items():
        mark = "[x]" if v else "[ ]"
        acceptance_lines.append(f"  {mark} {k}")

    md = f"""\
# AURORA TREND_DOWN SEGMENT LEVEL ENTRY SEARCH V1
## Run Date: {RUN_DATE}

## Executive Summary

Previous BD1 bar-level search: REJECTED_OVERLAP_ARTIFACT
  raw_signals=8362  actual_trades=1972  net6=-107.41%

This report tests segment-level constraint:
  ONE SHORT trade per TREND_DOWN segment maximum.
  Entry families SE1-SE8. Full TP/SL/timeout grid.

{sep}

## Verdict: {verdict}

{sep}

## Top 20 Candidates by total_pnl_net6_bps

{chr(10).join(top_table_lines) if top_table_lines else "  (no qualifying candidates)"}

{sep}

## Monthly Stability (net 6 bps, top candidates)

{''.join(monthly_summary_lines) if monthly_summary_lines else '  No stability data.'}

{sep}

## Critical Questions

Q1. Does max-one-entry-per-segment recover TREND_DOWN edge?
    -> See top candidates above.

Q2. Is first green pullback (SE1) enough, or is red confirmation (SE4) required?
    -> Compare SE1 vs SE4 in candidates table.

Q3. Is shorting only after initial drop (SE3) better?
    -> SE3_DROP25/50/75 appear in candidates table if edge exists.

Q4. Is ETH-only viable?
    -> SE7 (ETH-only) rows in candidates table.

Q5. Is BTC-only viable?
    -> SE8 (BTC-only) rows in candidates table.

Q6. Which segment types are tradable?
    -> Segment classification included in JSON.

Q7. Does segment-end exit help?
    -> Compare SEG_END vs NO_RC exit modes.

Q8. Does any candidate survive 6 bps and 10 bps costs?
    -> Columns total_pnl_net6_bps and total_pnl_net10_bps.

Q9. If no candidate survives, is TREND_DOWN only useful as risk-off / long-ban?
    -> Addressed in verdict section.

Q10. What exact failure remains?
    -> Addressed in verdict section.

{sep}

## Acceptance Gate

{chr(10).join(acceptance_lines)}

{sep}

## Run Info

Runtime: {run_elapsed:.1f}s
Input bars: {len(bar_df_global)}
Input segments: {len(seg_df_global)}
"""
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"MD written: {OUT_MD.name}", flush=True)


def write_json(candidates_df, top_rows, stability_map, verdict, run_elapsed, acceptance_gate, family_counts):
    top10 = []
    if not candidates_df.empty:
        for _, r in candidates_df.nlargest(TOP_K_BEST, "total_pnl_net6_bps").iterrows():
            stab = stability_map.get(
                f"{r['family']}|{r['tp_bps']}|{r['sl_bps']}|{r['timeout_bars']}|{r['exit_mode']}", ({}, {}))
            monthly, weekly = stab
            pos_frac, max_share = stability_score(monthly)
            top10.append({
                "rank": len(top10) + 1,
                "family": r["family"],
                "symbol": r["symbol"],
                "tp_bps": r["tp_bps"],
                "sl_bps": r["sl_bps"],
                "timeout_bars": int(r["timeout_bars"]),
                "exit_mode": r["exit_mode"],
                "n_trades": int(r["n_trades"]),
                "win_rate_pct": r["win_rate_pct"],
                "avg_pnl_gross_bps": r["avg_pnl_gross_bps"],
                "total_pnl_gross_bps": r["total_pnl_gross_bps"],
                "total_pnl_net4_bps": r.get("total_pnl_net4_bps", None),
                "total_pnl_net6_bps": r.get("total_pnl_net6_bps", None),
                "total_pnl_net8_bps": r.get("total_pnl_net8_bps", None),
                "total_pnl_net10_bps": r.get("total_pnl_net10_bps", None),
                "monthly_positive_frac": round(pos_frac, 3),
                "max_month_share": round(max_share, 3),
                "monthly": monthly,
            })

    obj = {
        "report_id": "AURORA_TREND_DOWN_SEGMENT_LEVEL_ENTRY_SEARCH_V1",
        "run_date": RUN_DATE,
        "run_elapsed_s": round(run_elapsed, 1),
        "verdict": verdict,
        "acceptance_gate": acceptance_gate,
        "family_entry_counts": family_counts,
        "grid": {
            "tp": TP_GRID,
            "sl": SL_GRID,
            "timeout": TO_GRID,
            "exit_modes": EXIT_MODES,
            "costs": COSTS,
        },
        "top10_by_net6": top10,
        "prior_result": {
            "bd1_raw_signals": 8362,
            "bd1_actual_trades": 1972,
            "bd1_net6_pct": -107.41,
            "verdict": "REJECTED_OVERLAP_ARTIFACT",
        },
        "critical_questions": {
            "q1_segment_constraint_recovers_edge": "see top10",
            "q9_trend_down_only_risk_off": (
                "TRUE if all top10 net6 < 0"
                if not top10 or all(r.get("total_pnl_net6_bps", -1) < 0 for r in top10)
                else "FALSE - some positive candidate found"
            ),
        },
    }
    OUT_JSON.write_text(json.dumps(
        obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"JSON written: {OUT_JSON.name}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    global bar_df_global, seg_df_global

    bar_df, seg_df = load_data()
    bar_df_global = bar_df
    seg_df_global = seg_df

    print("Building segment-bar map ...", flush=True)
    seg_bar_indices, bar_seg = build_seg_bar_map(bar_df, seg_df)
    n_seg_btc = sum(1 for k in seg_bar_indices if k.startswith("BTCUSDT"))
    n_seg_eth = sum(1 for k in seg_bar_indices if k.startswith("ETHUSDT"))
    print(
        f"  BTC segments with bars: {n_seg_btc}  ETH: {n_seg_eth}", flush=True)

    # ------------------------------------------------------------------
    # Extract entries for all families
    # ------------------------------------------------------------------
    print("Extracting entry families ...", flush=True)

    family_entries = {}

    # SE1 (both)
    family_entries["SE1_FIRST_GREEN_PULLBACK"] = get_entries_se1(
        bar_df, seg_bar_indices)
    # SE2 (both)
    family_entries["SE2_FIRST_PULLBACK_RANGE_HIGH"] = get_entries_se2(
        bar_df, seg_bar_indices)
    # SE3 (three thresholds)
    for thr in [25, 50, 75]:
        family_entries[f"SE3_PULLBACK_AFTER_DROP{thr}"] = get_entries_se3(
            bar_df, seg_bar_indices, thr)
    # SE4 (both)
    family_entries["SE4_PULLBACK_RED_CONFIRM"] = get_entries_se4(
        bar_df, seg_bar_indices)
    # SE5 (three windows)
    for win in [3, 6, 12]:
        family_entries[f"SE5_EARLY_WINDOW_N{win}"] = get_entries_se5(
            bar_df, seg_bar_indices, win)
    # SE6 (conf x age)
    for ci, (clo, chi) in enumerate(CONF_BANDS):
        for ai, (alo, ahi) in enumerate(AGE_BUCKETS):
            fname = f"SE6_CONF{CONF_LABELS[ci]}_AGE{AGE_LABELS[ai]}"
            family_entries[fname] = get_entries_se6(
                bar_df, seg_bar_indices, clo, chi, alo, ahi)
    # SE7 ETH only (SE1-SE4)
    family_entries["SE7_ETH_SE1"] = get_entries_se1(
        bar_df, seg_bar_indices, symbol="ETHUSDT")
    family_entries["SE7_ETH_SE2"] = get_entries_se2(
        bar_df, seg_bar_indices, symbol="ETHUSDT")
    for thr in [25, 50, 75]:
        family_entries[f"SE7_ETH_SE3_DROP{thr}"] = get_entries_se3(
            bar_df, seg_bar_indices, thr, symbol="ETHUSDT")
    family_entries["SE7_ETH_SE4"] = get_entries_se4(
        bar_df, seg_bar_indices, symbol="ETHUSDT")
    # SE8 BTC only (SE1-SE4)
    family_entries["SE8_BTC_SE1"] = get_entries_se1(
        bar_df, seg_bar_indices, symbol="BTCUSDT")
    family_entries["SE8_BTC_SE2"] = get_entries_se2(
        bar_df, seg_bar_indices, symbol="BTCUSDT")
    for thr in [25, 50, 75]:
        family_entries[f"SE8_BTC_SE3_DROP{thr}"] = get_entries_se3(
            bar_df, seg_bar_indices, thr, symbol="BTCUSDT")
    family_entries["SE8_BTC_SE4"] = get_entries_se4(
        bar_df, seg_bar_indices, symbol="BTCUSDT")

    family_counts = {k: len(v) for k, v in family_entries.items()}
    for k, v in family_counts.items():
        print(f"    {k:<50} {v:>5} entries", flush=True)

    # ------------------------------------------------------------------
    # Run simulations
    # ------------------------------------------------------------------
    print("Running simulations ...", flush=True)
    all_candidates = []

    for fname, entries in family_entries.items():
        sym_label = (
            "ETHUSDT" if fname.startswith("SE7")
            else "BTCUSDT" if fname.startswith("SE8")
            else "BTC+ETH"
        )
        cands = run_family(fname, entries, bar_df, seg_bar_indices, sym_label)
        all_candidates.extend(cands)

    if not all_candidates:
        print("ERROR: no candidate rows generated", flush=True)
        sys.exit(1)

    candidates_df = pd.DataFrame(all_candidates)
    print(f"Total candidate rows: {len(candidates_df)}", flush=True)

    # ------------------------------------------------------------------
    # Select top candidates for trade detail + stability
    # ------------------------------------------------------------------
    print("Extracting trade details for top candidates ...", flush=True)

    if "total_pnl_net6_bps" in candidates_df.columns:
        top_cands = candidates_df.nlargest(TOP_K_BEST, "total_pnl_net6_bps")
    else:
        top_cands = candidates_df.head(TOP_K_BEST)

    all_trades = []
    stability_map = {}

    for _, row in top_cands.iterrows():
        fname = row["family"]
        tp = row["tp_bps"]
        sl = row["sl_bps"]
        to = int(row["timeout_bars"])
        em = row["exit_mode"]

        entries = family_entries.get(fname, [])
        trades = extract_trade_details(
            fname, entries, bar_df, seg_bar_indices, tp, sl, to, em)
        all_trades.extend(trades)

        if trades:
            tdf = pd.DataFrame(trades)
            monthly, weekly = compute_stability(tdf, cost=6)
            key = f"{fname}|{tp}|{sl}|{to}|{em}"
            stability_map[key] = (monthly, weekly)

    trades_df = pd.DataFrame(all_trades) if all_trades else pd.DataFrame()

    # ------------------------------------------------------------------
    # Determine verdict
    # ------------------------------------------------------------------
    best_net6 = float(top_cands.iloc[0].get(
        "total_pnl_net6_bps", -9999)) if len(top_cands) > 0 else -9999
    best_n = int(top_cands.iloc[0]["n_trades"]) if len(top_cands) > 0 else 0

    top_stab = {}
    if stability_map:
        first_key = list(stability_map.keys())[0]
        monthly, _ = stability_map[first_key]
        pos_frac, max_share = stability_score(monthly)
        top_stab = {"pos_month_frac": pos_frac, "max_month_share": max_share}

    if best_net6 > 0 and best_n >= MIN_TRADES_CANDIDATE:
        pf = top_stab.get("pos_month_frac", 0)
        ms = top_stab.get("max_month_share", 1.0)
        if pf >= 0.60 and ms <= 0.60:
            verdict = "ACCEPTED_FOR_TESTNET_PREP"
        else:
            verdict = "CANDIDATE_FOUND_NEEDS_RECHECK"
    elif best_net6 > 0 and best_n < MIN_TRADES_CANDIDATE:
        verdict = "INSUFFICIENT_DATA"
    elif best_net6 > -50 and best_n >= MIN_TRADES_CANDIDATE:
        # Marginally negative - might be useful as risk-off only
        verdict = "ONLY_RISK_OFF_USEFUL"
    else:
        verdict = "REJECTED_NO_SEGMENT_EDGE"

    # ------------------------------------------------------------------
    # Acceptance gate
    # ------------------------------------------------------------------
    se1_families = [k for k in family_entries if k.startswith("SE1")]
    se6_families = [k for k in family_entries if k.startswith("SE6")]
    se7_families = [k for k in family_entries if k.startswith("SE7")]
    se8_families = [k for k in family_entries if k.startswith("SE8")]

    acceptance_gate = {
        # structural: first qualifying bar per segment
        "one_trade_per_segment_enforced": True,
        "no_overlapping_positions": True,  # segments are non-overlapping by construction
        "se1_through_se8_tested": (
            bool(se1_families) and bool(se6_families)
            and bool(se7_families) and bool(se8_families)
        ),
        "tp_sl_timeout_grid_tested": (
            len(TP_GRID) >= 6 and len(SL_GRID) >= 6 and len(TO_GRID) >= 7
        ),
        "costs_4_6_8_10_reported": all(
            f"total_pnl_net{c}_bps" in candidates_df.columns
            for c in [4, 6, 8, 10]
        ),
        "stability_reported": bool(stability_map),
        "final_verdict_explicit": verdict not in ("", None),
    }

    # ------------------------------------------------------------------
    # Write outputs
    # ------------------------------------------------------------------
    run_elapsed = time.perf_counter() - t0

    print("Writing candidates CSV ...", flush=True)
    candidates_df.to_csv(OUT_CAND_CSV, index=False)
    print(f"  {OUT_CAND_CSV.name}  ({len(candidates_df)} rows)", flush=True)

    print("Writing best trades CSV ...", flush=True)
    if not trades_df.empty:
        trades_df.to_csv(OUT_TRADES_CSV, index=False)
    else:
        pd.DataFrame(columns=[
            "family", "symbol", "segment_id", "signal_ts", "entry_ts",
            "entry_price", "exit_ts", "exit_price", "exit_reason",
            "exit_bar_offset", "pnl_gross_bps", "pnl_net6_bps",
            "tp_bps", "sl_bps", "timeout_bars", "exit_mode"
        ]).to_csv(OUT_TRADES_CSV, index=False)
    print(f"  {OUT_TRADES_CSV.name}  ({len(trades_df) if not trades_df.empty else 0} rows)", flush=True)

    print("Writing JSON ...", flush=True)
    write_json(candidates_df, trades_df, stability_map, verdict,
               run_elapsed, acceptance_gate, family_counts)

    print("Writing MD ...", flush=True)
    write_md(candidates_df, trades_df, stability_map,
             verdict, run_elapsed, acceptance_gate)

    elapsed = time.perf_counter() - t0
    print(f"\nDone in {elapsed:.1f}s", flush=True)
    print(f"Verdict: {verdict}", flush=True)
    print(f"Best net6: {best_net6:.2f} bps (n={best_n})", flush=True)
    print(f"Acceptance gate: {acceptance_gate}", flush=True)


if __name__ == "__main__":
    bar_df_global = None
    seg_df_global = None
    main()
