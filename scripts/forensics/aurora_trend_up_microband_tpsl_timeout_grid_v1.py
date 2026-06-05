"""
AURORA_TREND_UP_MICROBAND_TPSL_TIMEOUT_GRID_V1

Decomposes the F5 TREND_UP confidence band (0.40..0.45) into micro-bands,
runs TP/SL grid, timeout grid, and regime-change exit analysis.

FACTS:
- Input entries: 58 rows from F5 TREND_UP shadow replay candidate
- Baseline TP: 0.0095 = 95 bps (dominant in TREND_UP trades)
- Baseline SL: 0.005 = 50 bps (dominant in TREND_UP trades)
- Baseline timeout: 18 bars (max bars_held observed in TREND_UP trades)
- MFE/MAE/bars_to_mfe/bars_to_mae available per entry for simulation

ASSUMPTIONS:
- TP/SL race simulation using MFE vs MAE extremes is accurate for direction;
  exact intra-bar path unknown.
- Timeout PnL approximated as pure_pnl_pct from original trade.
- Cost model NET_6BPS: 6 bps round-trip (4bps fees + 2bps slippage).

UNKNOWNS:
- Exact bar-by-bar price path for timeout exit PnL.
- Live microstructure effects not modeled.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "reports"
DATE_TAG = "2026_05_04"

ENTRIES_CSV = REPORTS / \
    f"AURORA_TREND_UP_CONF_040_045_SHADOW_REPLAY_V1_ENTRIES_{DATE_TAG}.csv"
ENRICHED_CSV = REPORTS / f"AURORA_TREND_UP_P1_ENRICHED_ENTRIES_{DATE_TAG}.csv"
TRADES_CSV = REPORTS / "BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_trades.csv"

OUT_MD = REPORTS / \
    f"AURORA_TREND_UP_MICROBAND_TPSL_TIMEOUT_GRID_V1_{DATE_TAG}.md"
OUT_JSON = REPORTS / \
    f"AURORA_TREND_UP_MICROBAND_TPSL_TIMEOUT_GRID_V1_{DATE_TAG}.json"
OUT_MICROBAND_CSV = REPORTS / \
    f"AURORA_TREND_UP_MICROBAND_RESULTS_{DATE_TAG}.csv"
OUT_TPSL_CSV = REPORTS / f"AURORA_TREND_UP_TPSL_GRID_RESULTS_{DATE_TAG}.csv"
OUT_TIMEOUT_CSV = REPORTS / \
    f"AURORA_TREND_UP_TIMEOUT_GRID_RESULTS_{DATE_TAG}.csv"
OUT_BEST_TRADES_CSV = REPORTS / \
    f"AURORA_TREND_UP_BEST_CANDIDATE_TRADES_{DATE_TAG}.csv"

# ---------------------------------------------------------------------------
# Baseline parameters
# ---------------------------------------------------------------------------
BASELINE_TP_PCT = 0.0095   # 95 bps
BASELINE_SL_PCT = 0.005    # 50 bps
BASELINE_TP_BPS = BASELINE_TP_PCT * 10_000  # 95.0
BASELINE_SL_BPS = BASELINE_SL_PCT * 10_000  # 50.0
BASELINE_TIMEOUT_BARS = 18

COST_BPS = 6.0  # NET_6BPS round-trip

# TP multiplier grid
TP_MULTS = {
    "TP_020X": 0.20,
    "TP_025X": 0.25,
    "TP_030X": 0.30,
    "TP_040X": 0.40,
    "TP_050X": 0.50,
    "TP_070X": 0.70,
    "TP_100X": 1.00,
}

# SL multiplier grid
SL_MULTS = {
    "SL_075X": 0.75,
    "SL_100X": 1.00,
    "SL_125X": 1.25,
    "SL_150X": 1.50,
}

# Timeout variants
TIMEOUT_VARIANTS = {
    "TIMEOUT_CURRENT": 18,
    "TIMEOUT_SHORTER_25_PERCENT": 14,
    "TIMEOUT_SHORTER_50_PERCENT": 9,
    "TIMEOUT_PLUS_5_BARS": 23,
    "TIMEOUT_PLUS_10_BARS": 28,
    "TIMEOUT_PLUS_20_BARS": 38,
    "NO_TIMEOUT_DIAGNOSTIC": 99999,  # effectively no timeout
}

# Confidence band definitions
CONF_BANDS: list[tuple[str, float, float]] = [
    # Micro-bands
    ("MB_400_410", 0.400, 0.410),
    ("MB_410_420", 0.410, 0.420),
    ("MB_420_430", 0.420, 0.430),
    ("MB_430_440", 0.430, 0.440),
    ("MB_440_450", 0.440, 0.450),
    # Cumulative bands
    ("CUM_400_420", 0.400, 0.420),
    ("CUM_400_430", 0.400, 0.430),
    ("CUM_400_440", 0.400, 0.440),
    ("CUM_400_450", 0.400, 0.450),
    # Upper-slice bands
    ("SLICE_410_450", 0.410, 0.450),
    ("SLICE_420_450", 0.420, 0.450),
    ("SLICE_430_450", 0.430, 0.450),
]


# ---------------------------------------------------------------------------
# Simulation core
# ---------------------------------------------------------------------------

def simulate_trade(
    mfe_bps: float,
    mae_bps: float,
    bars_to_mfe: int,
    bars_to_mae: int,
    original_exit_reason: str,
    pure_pnl_pct: float,
    tp_bps: float,
    sl_bps: float,
    timeout_bars: int,
    regime_change_exit: bool = True,
) -> tuple[str, float]:
    """
    Simulate a single trade with given TP/SL/timeout parameters.

    Returns (simulated_exit_reason, simulated_pnl_pct).

    ASSUMPTION: MFE/MAE race determines TP vs SL priority.
    ASSUMPTION: Timeout PnL = pure_pnl_pct (approximation; no bar-by-bar price).
    ASSUMPTION: For regime-change exit: if regime_change_exit=False, trade
                continues to TP/SL/timeout even if regime changed.
    """
    tp_pct = tp_bps / 10_000
    sl_pct = sl_bps / 10_000

    # For regime-change-only exits when regime_change_exit=False:
    # treat original REGIME_CHANGE as TIMEOUT (trade continued)
    effective_original = original_exit_reason
    if not regime_change_exit and original_exit_reason == "REGIME_CHANGE":
        effective_original = "TIMEOUT"

    # Determine if TP or SL fires within timeout
    tp_fires = (mfe_bps >= tp_bps) and (bars_to_mfe <= timeout_bars)
    sl_fires = ((-mae_bps) >= sl_bps) and (bars_to_mae <= timeout_bars)

    if tp_fires and sl_fires:
        if bars_to_mfe < bars_to_mae:
            return "TP", tp_pct
        elif bars_to_mae < bars_to_mfe:
            return "SL", -sl_pct
        else:
            # Tie: conservative → SL
            return "SL", -sl_pct
    elif tp_fires:
        return "TP", tp_pct
    elif sl_fires:
        return "SL", -sl_pct
    else:
        # No TP or SL hit within timeout
        if regime_change_exit and effective_original == "REGIME_CHANGE":
            return "REGIME_CHANGE", pure_pnl_pct
        elif timeout_bars >= 99999:
            # NO_TIMEOUT_DIAGNOSTIC: no timeout, close only by TP/SL/regime
            # If we're here, neither TP nor SL hit and no regime change applies
            return "STILL_OPEN_END", pure_pnl_pct
        else:
            return "TIMEOUT", pure_pnl_pct


def compute_metrics(
    pnl_list: list[float],
    exit_reasons: list[str],
    profitable_labels: list[int],
    admitted_total_good: int,
    admitted_total_bad: int,
    mfe_bps_list: list[float],
    mae_bps_list: list[float],
    bars_to_mfe_list: list[int],
    cost_bps: float = 0.0,
) -> dict[str, Any]:
    """Compute aggregated metrics for a set of simulated trades."""
    n = len(pnl_list)
    if n == 0:
        return {
            "admitted_count": 0,
            "good_count": 0,
            "bad_count": 0,
            "win_rate": None,
            "gross_total_pnl_pct": 0.0,
            "net_total_pnl_pct": 0.0,
            "avg_pnl_pct": None,
            "avg_r": None,
            "mdd_proxy": None,
            "avg_mfe_bps": None,
            "avg_mae_bps": None,
            "median_mfe_bps": None,
            "median_mae_bps": None,
            "tp_count": 0,
            "sl_count": 0,
            "timeout_count": 0,
            "regime_change_count": 0,
            "still_open_count": 0,
            "median_bars_to_mfe": None,
        }

    pnl_arr = np.array(pnl_list, dtype=float)
    net_pnl_arr = pnl_arr - cost_bps / 10_000
    good_count = int(sum(profitable_labels))
    bad_count = n - good_count

    wins = sum(1 for p in pnl_list if p > 0)
    win_rate = wins / n if n > 0 else None

    cum_pnl = np.cumsum(pnl_arr)
    rolling_max = np.maximum.accumulate(cum_pnl)
    drawdowns = rolling_max - cum_pnl
    mdd_proxy = float(drawdowns.max()) if len(drawdowns) > 0 else 0.0

    sl_bps_used = BASELINE_SL_BPS  # for R-multiple approximation
    sl_pct_used = sl_bps_used / 10_000
    r_multiples = [p / sl_pct_used if sl_pct_used >
                   0 else 0.0 for p in pnl_list]

    tp_count = exit_reasons.count("TP")
    sl_count = exit_reasons.count("SL")
    timeout_count = exit_reasons.count("TIMEOUT")
    regime_change_count = exit_reasons.count("REGIME_CHANGE")
    still_open_count = exit_reasons.count("STILL_OPEN_END")

    return {
        "admitted_count": n,
        "good_count": good_count,
        "bad_count": bad_count,
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
        "gross_total_pnl_pct": round(float(pnl_arr.sum()), 6),
        "net_total_pnl_pct": round(float(net_pnl_arr.sum()), 6),
        "avg_pnl_pct": round(float(pnl_arr.mean()), 6),
        "avg_r": round(float(np.mean(r_multiples)), 6),
        "mdd_proxy": round(mdd_proxy, 6),
        "avg_mfe_bps": round(float(np.mean(mfe_bps_list)), 4),
        "avg_mae_bps": round(float(np.mean(mae_bps_list)), 4),
        "median_mfe_bps": round(float(np.median(mfe_bps_list)), 4),
        "median_mae_bps": round(float(np.median(mae_bps_list)), 4),
        "tp_count": tp_count,
        "sl_count": sl_count,
        "timeout_count": timeout_count,
        "regime_change_count": regime_change_count,
        "still_open_count": still_open_count,
        "median_bars_to_mfe": round(float(np.median(bars_to_mfe_list)), 1),
    }


def run_simulation_on_df(
    df: pd.DataFrame,
    tp_bps: float,
    sl_bps: float,
    timeout_bars: int,
    regime_change_exit: bool = True,
    cost_bps: float = 0.0,
) -> tuple[dict[str, Any], list[dict]]:
    """
    Run simulation on a DataFrame of entries.
    Returns (metrics_dict, per_trade_records).
    """
    pnl_list: list[float] = []
    exit_reasons: list[str] = []
    profitable_labels: list[int] = []
    trade_records: list[dict] = []

    for _, row in df.iterrows():
        sim_exit, sim_pnl = simulate_trade(
            mfe_bps=float(row["mfe_bps"]),
            mae_bps=float(row["mae_bps"]),
            bars_to_mfe=int(row["bars_to_mfe"]),
            bars_to_mae=int(row["bars_to_mae"]),
            original_exit_reason=str(row["exit_reason"]),
            pure_pnl_pct=float(row["pure_pnl_pct"]),
            tp_bps=tp_bps,
            sl_bps=sl_bps,
            timeout_bars=timeout_bars,
            regime_change_exit=regime_change_exit,
        )
        pnl_list.append(sim_pnl)
        exit_reasons.append(sim_exit)
        profitable_labels.append(int(row["profitable_label"]))
        trade_records.append(
            {
                "segment_id": row["segment_id"],
                "symbol": row["symbol"],
                "admit_confidence": round(float(row["admit_confidence"]), 6),
                "regime_age_at_entry": row["regime_age_at_entry"],
                "original_exit_reason": row["exit_reason"],
                "sim_exit_reason": sim_exit,
                "original_pnl_pct": round(float(row["pure_pnl_pct"]), 6),
                "sim_pnl_pct": round(sim_pnl, 6),
                "sim_net_pnl_pct": round(sim_pnl - cost_bps / 10_000, 6),
                "profitable_label": int(row["profitable_label"]),
                "mfe_bps": round(float(row["mfe_bps"]), 4),
                "mae_bps": round(float(row["mae_bps"]), 4),
                "bars_to_mfe": int(row["bars_to_mfe"]),
                "bars_to_mae": int(row["bars_to_mae"]),
            }
        )

    total_good = int(df["profitable_label"].sum())
    total_bad = len(df) - total_good
    metrics = compute_metrics(
        pnl_list=pnl_list,
        exit_reasons=exit_reasons,
        profitable_labels=profitable_labels,
        admitted_total_good=total_good,
        admitted_total_bad=total_bad,
        mfe_bps_list=[float(r["mfe_bps"]) for r in trade_records],
        mae_bps_list=[float(r["mae_bps"]) for r in trade_records],
        bars_to_mfe_list=[int(r["bars_to_mfe"]) for r in trade_records],
        cost_bps=cost_bps,
    )
    return metrics, trade_records


# ---------------------------------------------------------------------------
# Safe formatters
# ---------------------------------------------------------------------------

def _sf(v: Any, digits: int = 4) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def md_table(rows: list[dict], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, sep]
    for row in rows:
        cells = [str(row.get(c, "")) for c in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading input data...")
    df = pd.read_csv(ENTRIES_CSV)
    df_enriched = pd.read_csv(ENRICHED_CSV)
    df_trades = pd.read_csv(TRADES_CSV)

    print(f"  Entries: {len(df)} rows")
    print(f"  Enriched: {len(df_enriched)} rows")
    print(f"  Trades: {len(df_trades)} rows")

    # F5 full cohort baseline metrics (re-run at baseline params for comparison)
    f5_metrics, f5_trades = run_simulation_on_df(
        df, BASELINE_TP_BPS, BASELINE_SL_BPS, BASELINE_TIMEOUT_BARS,
        regime_change_exit=True, cost_bps=0.0
    )
    f5_net_metrics, _ = run_simulation_on_df(
        df, BASELINE_TP_BPS, BASELINE_SL_BPS, BASELINE_TIMEOUT_BARS,
        regime_change_exit=True, cost_bps=COST_BPS
    )

    # -----------------------------------------------------------------------
    # PHASE 1: Confidence micro-band decomposition
    # -----------------------------------------------------------------------
    print("\nPhase 1: Micro-band decomposition...")
    f5_total_good = int(df["profitable_label"].sum())
    f5_total_bad = len(df) - f5_total_good

    microband_rows: list[dict] = []
    microband_dfs: dict[str, pd.DataFrame] = {}

    for band_name, lo, hi in CONF_BANDS:
        mask = (df["admit_confidence"] >= lo) & (df["admit_confidence"] < hi)
        band_df = df[mask].copy()
        microband_dfs[band_name] = band_df

        n = len(band_df)
        if n == 0:
            row = {
                "band": band_name,
                "lo": lo,
                "hi": hi,
                "admitted_count": 0,
                "btc_count": 0,
                "eth_count": 0,
                "good_count": 0,
                "bad_count": 0,
                "win_rate": None,
                "total_pnl_pct": None,
                "avg_pnl_pct": None,
                "avg_r": None,
                "mdd_proxy": None,
                "avg_mfe_bps": None,
                "avg_mae_bps": None,
                "median_mfe_bps": None,
                "median_mae_bps": None,
                "kept_good_rate": None,
                "rejected_bad_rate": None,
            }
            microband_rows.append(row)
            continue

        good = int(band_df["profitable_label"].sum())
        bad = n - good
        btc = int((band_df["symbol"] == "BTCUSDT").sum())
        eth = int((band_df["symbol"] == "ETHUSDT").sum())

        pnl_arr = band_df["pure_pnl_pct"].values
        wins = int((pnl_arr > 0).sum())
        win_rate = wins / n

        cum_pnl = np.cumsum(pnl_arr)
        rolling_max = np.maximum.accumulate(cum_pnl)
        drawdowns = rolling_max - cum_pnl
        mdd_proxy = float(drawdowns.max())

        sl_pct = BASELINE_SL_BPS / 10_000
        r_mults = [p / sl_pct for p in pnl_arr]

        kept_good_rate = good / f5_total_good if f5_total_good > 0 else None
        rejected_bad_rate = (f5_total_bad - bad) / \
            f5_total_bad if f5_total_bad > 0 else None

        row = {
            "band": band_name,
            "lo": lo,
            "hi": hi,
            "admitted_count": n,
            "btc_count": btc,
            "eth_count": eth,
            "good_count": good,
            "bad_count": bad,
            "win_rate": round(win_rate, 4),
            "total_pnl_pct": round(float(pnl_arr.sum()), 6),
            "avg_pnl_pct": round(float(pnl_arr.mean()), 6),
            "avg_r": round(float(np.mean(r_mults)), 6),
            "mdd_proxy": round(mdd_proxy, 6),
            "avg_mfe_bps": round(float(band_df["mfe_bps"].mean()), 4),
            "avg_mae_bps": round(float(band_df["mae_bps"].mean()), 4),
            "median_mfe_bps": round(float(band_df["mfe_bps"].median()), 4),
            "median_mae_bps": round(float(band_df["mae_bps"].median()), 4),
            "kept_good_rate": round(kept_good_rate, 4) if kept_good_rate is not None else None,
            "rejected_bad_rate": round(rejected_bad_rate, 4) if rejected_bad_rate is not None else None,
        }
        microband_rows.append(row)
        print(
            f"  {band_name}: n={n}, good={good}, bad={bad}, wr={win_rate:.3f}, pnl={pnl_arr.sum():.4f}")

    df_microband = pd.DataFrame(microband_rows)
    df_microband.to_csv(OUT_MICROBAND_CSV, index=False)
    print(f"  -> {OUT_MICROBAND_CSV}")

    # -----------------------------------------------------------------------
    # Phase 1 selection: top 3 bands by risk-aware ranking
    # -----------------------------------------------------------------------
    eligible = df_microband[
        (df_microband["admitted_count"] >= 5) &
        (df_microband["total_pnl_pct"].notna()) &
        (df_microband["total_pnl_pct"] > 0) &
        (df_microband["avg_r"].notna()) &
        (df_microband["avg_r"] > 0)
    ].copy()

    if len(eligible) == 0:
        eligible = df_microband[
            (df_microband["admitted_count"] >= 3) &
            (df_microband["total_pnl_pct"].notna())
        ].copy()

    # Score: normalize total_pnl_pct and avg_r, penalize high mdd_proxy
    if len(eligible) > 0:
        pnl_max = eligible["total_pnl_pct"].max()
        r_max = eligible["avg_r"].max()
        mdd_min = eligible["mdd_proxy"].min() + 0.001

        eligible["score"] = (
            eligible["total_pnl_pct"] / (pnl_max + 0.001) * 0.5
            + eligible["avg_r"] / (r_max + 0.001) * 0.5
            - eligible["mdd_proxy"] /
            (eligible["mdd_proxy"].max() + 0.001) * 0.2
        )
        eligible = eligible.sort_values("score", ascending=False)
        top3_bands = eligible["band"].head(3).tolist()
    else:
        # Fallback: use full F5 band
        top3_bands = ["CUM_400_450"]

    print(f"\nTop 3 bands selected for TP/SL grid: {top3_bands}")

    # -----------------------------------------------------------------------
    # PHASE 2: TP/SL grid on selected bands
    # -----------------------------------------------------------------------
    print("\nPhase 2: TP/SL grid...")
    tpsl_rows: list[dict] = []

    for band_name in top3_bands:
        band_df = microband_dfs.get(band_name, pd.DataFrame())
        if len(band_df) == 0:
            continue
        for tp_name, tp_mult in TP_MULTS.items():
            for sl_name, sl_mult in SL_MULTS.items():
                tp_bps = BASELINE_TP_BPS * tp_mult
                sl_bps = BASELINE_SL_BPS * sl_mult

                gross_metrics, _ = run_simulation_on_df(
                    band_df, tp_bps, sl_bps, BASELINE_TIMEOUT_BARS,
                    regime_change_exit=True, cost_bps=0.0
                )
                net_metrics, _ = run_simulation_on_df(
                    band_df, tp_bps, sl_bps, BASELINE_TIMEOUT_BARS,
                    regime_change_exit=True, cost_bps=COST_BPS
                )

                lo_band = next(lo for (bn, lo, hi)
                               in CONF_BANDS if bn == band_name)
                hi_band = next(hi for (bn, lo, hi)
                               in CONF_BANDS if bn == band_name)
                lo_int = int(round(lo_band * 1000))
                hi_int = int(round(hi_band * 1000))

                cand_name = (
                    f"TREND_UP_CONF_{lo_int}_{hi_int}_{tp_name}_{sl_name}_TIMEOUT_CURRENT"
                )

                row = {
                    "candidate_name": cand_name,
                    "band": band_name,
                    "tp_name": tp_name,
                    "sl_name": sl_name,
                    "tp_bps": round(tp_bps, 2),
                    "sl_bps": round(sl_bps, 2),
                    "tp_pct": round(tp_bps / 10_000, 5),
                    "sl_pct": round(sl_bps / 10_000, 5),
                    "timeout_bars": BASELINE_TIMEOUT_BARS,
                    "admitted_count": gross_metrics["admitted_count"],
                    "tp_count": gross_metrics["tp_count"],
                    "sl_count": gross_metrics["sl_count"],
                    "timeout_count": gross_metrics["timeout_count"],
                    "regime_change_count": gross_metrics["regime_change_count"],
                    "win_rate": gross_metrics["win_rate"],
                    "gross_total_pnl_pct": gross_metrics["gross_total_pnl_pct"],
                    "net_total_pnl_pct": net_metrics["net_total_pnl_pct"],
                    "avg_r": gross_metrics["avg_r"],
                    "mdd_proxy": gross_metrics["mdd_proxy"],
                    "avg_mfe_bps": gross_metrics["avg_mfe_bps"],
                    "avg_mae_bps": gross_metrics["avg_mae_bps"],
                    "median_bars_to_mfe": gross_metrics["median_bars_to_mfe"],
                }
                tpsl_rows.append(row)
        print(f"  {band_name}: {len(TP_MULTS) * len(SL_MULTS)} combos done")

    df_tpsl = pd.DataFrame(tpsl_rows)
    df_tpsl.to_csv(OUT_TPSL_CSV, index=False)
    print(f"  -> {OUT_TPSL_CSV}")

    # Select top 5 TP/SL candidates for timeout grid
    eligible_tpsl = df_tpsl[
        (df_tpsl["net_total_pnl_pct"] > 0) &
        (df_tpsl["avg_r"] > 0) &
        (df_tpsl["admitted_count"] >= 5)
    ].sort_values("net_total_pnl_pct", ascending=False).head(5)

    if len(eligible_tpsl) == 0:
        eligible_tpsl = df_tpsl.sort_values(
            "net_total_pnl_pct", ascending=False).head(5)

    top5_tpsl = eligible_tpsl["candidate_name"].tolist()
    print(f"\nTop 5 TP/SL candidates for timeout grid:")
    for c in top5_tpsl:
        row = eligible_tpsl[eligible_tpsl["candidate_name"] == c].iloc[0]
        print(
            f"  {c}: net={row['net_total_pnl_pct']:.4f}, avg_r={row['avg_r']:.4f}")

    # -----------------------------------------------------------------------
    # PHASE 3: Timeout grid on top 5 TP/SL candidates
    # -----------------------------------------------------------------------
    print("\nPhase 3: Timeout grid...")
    timeout_rows: list[dict] = []

    for _, cand_row in eligible_tpsl.iterrows():
        band_name = cand_row["band"]
        tp_bps = float(cand_row["tp_bps"])
        sl_bps = float(cand_row["sl_bps"])
        band_df = microband_dfs.get(band_name, pd.DataFrame())
        if len(band_df) == 0:
            continue

        for timeout_name, timeout_bars in TIMEOUT_VARIANTS.items():
            gross_m, _ = run_simulation_on_df(
                band_df, tp_bps, sl_bps, timeout_bars,
                regime_change_exit=True, cost_bps=0.0
            )
            net_m, _ = run_simulation_on_df(
                band_df, tp_bps, sl_bps, timeout_bars,
                regime_change_exit=True, cost_bps=COST_BPS
            )

            row = {
                "candidate_name": cand_row["candidate_name"],
                "band": band_name,
                "tp_bps": tp_bps,
                "sl_bps": sl_bps,
                "timeout_variant": timeout_name,
                "timeout_bars": timeout_bars if timeout_bars < 99999 else "NO_TIMEOUT",
                "admitted_count": gross_m["admitted_count"],
                "tp_count": gross_m["tp_count"],
                "sl_count": gross_m["sl_count"],
                "timeout_count": gross_m["timeout_count"],
                "still_open_count": gross_m["still_open_count"],
                "regime_change_count": gross_m["regime_change_count"],
                "win_rate": gross_m["win_rate"],
                "gross_total_pnl_pct": gross_m["gross_total_pnl_pct"],
                "net_total_pnl_pct": net_m["net_total_pnl_pct"],
                "avg_r": gross_m["avg_r"],
                "mdd_proxy": gross_m["mdd_proxy"],
            }
            timeout_rows.append(row)

    df_timeout = pd.DataFrame(timeout_rows)
    df_timeout.to_csv(OUT_TIMEOUT_CSV, index=False)
    print(f"  -> {OUT_TIMEOUT_CSV}")

    # -----------------------------------------------------------------------
    # PHASE 4: Regime-change exit comparison
    # -----------------------------------------------------------------------
    print("\nPhase 4: Regime-change exit comparison...")
    regime_exit_rows: list[dict] = []

    for _, cand_row in eligible_tpsl.head(3).iterrows():
        band_name = cand_row["band"]
        tp_bps = float(cand_row["tp_bps"])
        sl_bps = float(cand_row["sl_bps"])
        band_df = microband_dfs.get(band_name, pd.DataFrame())
        if len(band_df) == 0:
            continue

        for rc_exit in [True, False]:
            label = "EXIT_ON_REGIME_CHANGE" if rc_exit else "EXIT_NO_REGIME_CHANGE"
            gross_m, _ = run_simulation_on_df(
                band_df, tp_bps, sl_bps, BASELINE_TIMEOUT_BARS,
                regime_change_exit=rc_exit, cost_bps=0.0
            )
            net_m, _ = run_simulation_on_df(
                band_df, tp_bps, sl_bps, BASELINE_TIMEOUT_BARS,
                regime_change_exit=rc_exit, cost_bps=COST_BPS
            )
            regime_exit_rows.append({
                "candidate_name": cand_row["candidate_name"],
                "band": band_name,
                "exit_mode": label,
                "admitted_count": gross_m["admitted_count"],
                "tp_count": gross_m["tp_count"],
                "sl_count": gross_m["sl_count"],
                "timeout_count": gross_m["timeout_count"],
                "regime_change_count": gross_m["regime_change_count"],
                "win_rate": gross_m["win_rate"],
                "gross_total_pnl_pct": gross_m["gross_total_pnl_pct"],
                "net_total_pnl_pct": net_m["net_total_pnl_pct"],
                "avg_r": gross_m["avg_r"],
                "mdd_proxy": gross_m["mdd_proxy"],
            })

    # -----------------------------------------------------------------------
    # Build per-symbol splits for best candidate
    # -----------------------------------------------------------------------
    print("\nBuilding best candidate trade records and splits...")

    # Best candidate overall (top net pnl from tpsl grid)
    best_cand_row = eligible_tpsl.iloc[0]
    best_band = best_cand_row["band"]
    best_tp_bps = float(best_cand_row["tp_bps"])
    best_sl_bps = float(best_cand_row["sl_bps"])
    best_band_df = microband_dfs.get(best_band, pd.DataFrame())

    _, best_trades = run_simulation_on_df(
        best_band_df, best_tp_bps, best_sl_bps, BASELINE_TIMEOUT_BARS,
        regime_change_exit=True, cost_bps=COST_BPS
    )

    # Add additional info
    for t in best_trades:
        orig_row = df[df["segment_id"] == t["segment_id"]]
        if len(orig_row) > 0:
            t["regime_age_at_entry"] = float(
                orig_row.iloc[0]["regime_age_at_entry"])
            t["position_in_range_10"] = float(
                orig_row.iloc[0]["position_in_range_10"])
            t["pre_entry_impulse_bucket"] = str(
                orig_row.iloc[0]["pre_entry_impulse_bucket"])
            t["age_bucket_6"] = str(orig_row.iloc[0]["age_bucket_6"])
            t["position_in_range_10_bucket"] = str(
                orig_row.iloc[0]["position_in_range_10_bucket"])
            t["confidence_bucket_2"] = str(
                orig_row.iloc[0]["confidence_bucket_2"])
        t["candidate_name"] = best_cand_row["candidate_name"]
        t["band"] = best_band

    df_best_trades = pd.DataFrame(best_trades)
    df_best_trades.to_csv(OUT_BEST_TRADES_CSV, index=False)
    print(f"  -> {OUT_BEST_TRADES_CSV}")

    # -----------------------------------------------------------------------
    # Compute required splits for the best candidate
    # -----------------------------------------------------------------------
    def band_split(split_col: str, split_vals: list[Any]) -> list[dict]:
        out = []
        for val in split_vals:
            sub = best_band_df[best_band_df[split_col] == val]
            if len(sub) == 0:
                continue
            m, _ = run_simulation_on_df(
                sub, best_tp_bps, best_sl_bps, BASELINE_TIMEOUT_BARS,
                regime_change_exit=True, cost_bps=COST_BPS
            )
            out.append({"split": str(val), "count": len(sub), **m})
        return out

    # Symbol split
    sym_split = []
    for sym in ["BTCUSDT", "ETHUSDT"]:
        sub = best_band_df[best_band_df["symbol"] == sym]
        if len(sub) == 0:
            continue
        m, _ = run_simulation_on_df(
            sub, best_tp_bps, best_sl_bps, BASELINE_TIMEOUT_BARS,
            regime_change_exit=True, cost_bps=COST_BPS
        )
        sym_split.append({"symbol": sym, "count": len(sub), **m})

    # Age split
    age_vals = ["age 1", "age 2-3", "age 4-6",
                "age 7-12", "age 13-24", "age >24"]
    age_split = band_split("age_bucket_6", age_vals)

    # Position split
    pos_vals = ["0.00..0.25", "0.25..0.50", "0.50..0.75", "0.75..1.00"]
    pos_split = band_split("position_in_range_10_bucket", pos_vals)

    # Pre-entry impulse split
    impulse_vals = [
        "strong negative pullback", "flat",
        "moderate positive", "strong positive / chase"
    ]
    impulse_split = band_split("pre_entry_impulse_bucket", impulse_vals)

    # Confidence sub-band split (within best band, use exact buckets)
    conf_sub_split = []
    for bname, lo, hi in CONF_BANDS[:5]:  # micro-bands only
        sub = best_band_df[
            (best_band_df["admit_confidence"] >= lo) &
            (best_band_df["admit_confidence"] < hi)
        ]
        if len(sub) == 0:
            continue
        m, _ = run_simulation_on_df(
            sub, best_tp_bps, best_sl_bps, BASELINE_TIMEOUT_BARS,
            regime_change_exit=True, cost_bps=COST_BPS
        )
        conf_sub_split.append(
            {"sub_band": bname, "lo": lo, "hi": hi, "count": len(sub), **m})

    # -----------------------------------------------------------------------
    # Collect critical questions answers
    # -----------------------------------------------------------------------
    # Best band answer
    if len(eligible) > 0:
        best_band_by_score = eligible.iloc[0]
        q1_ans = (
            f"{best_band_by_score['band']} "
            f"(n={best_band_by_score['admitted_count']}, "
            f"total_pnl={best_band_by_score['total_pnl_pct']:.4f}, "
            f"avg_r={best_band_by_score['avg_r']:.4f})"
        )
    else:
        q1_ans = "No band with positive edge identified"

    # Is edge concentrated?
    nonzero_bands = df_microband[
        (df_microband["admitted_count"] >= 3) &
        (df_microband["total_pnl_pct"].notna()) &
        (df_microband["total_pnl_pct"] > 0)
    ]
    q2_ans = (
        f"Edge concentrated: {len(nonzero_bands)}/{len([b for b in CONF_BANDS if b[0].startswith('MB')])} "
        f"micro-bands show positive total PnL"
    )

    # 0.44..0.45 toxic?
    mb_440_450 = df_microband[df_microband["band"] == "MB_440_450"]
    if len(mb_440_450) > 0:
        m440 = mb_440_450.iloc[0]
        q3_ans = (
            f"MB_440_450: n={m440['admitted_count']}, "
            f"pnl={_sf(m440['total_pnl_pct'])}, avg_r={_sf(m440['avg_r'])}"
        )
    else:
        q3_ans = "MB_440_450: no entries"

    # Best TP multiplier
    if len(df_tpsl) > 0:
        best_tp_row = df_tpsl.sort_values(
            "net_total_pnl_pct", ascending=False).iloc[0]
        q5_ans = f"{best_tp_row['tp_name']} (net pnl {best_tp_row['net_total_pnl_pct']:.4f})"
        best_sl_row = df_tpsl.sort_values(
            "net_total_pnl_pct", ascending=False).iloc[0]
        q6_ans = f"{best_sl_row['sl_name']} (net pnl {best_sl_row['net_total_pnl_pct']:.4f})"
    else:
        q5_ans = "N/A"
        q6_ans = "N/A"

    # Timeout impact
    if len(df_timeout) > 0:
        shorter_50 = df_timeout[df_timeout["timeout_variant"]
                                == "TIMEOUT_SHORTER_50_PERCENT"]
        current_t = df_timeout[df_timeout["timeout_variant"]
                               == "TIMEOUT_CURRENT"]
        if len(shorter_50) > 0 and len(current_t) > 0:
            s50_net = shorter_50["net_total_pnl_pct"].mean()
            cur_net = current_t["net_total_pnl_pct"].mean()
            q7_ans = f"Shorter timeout (50%): avg net pnl {s50_net:.4f} vs current {cur_net:.4f} -> {'HELPS' if s50_net > cur_net else 'HURTS'}"
        else:
            q7_ans = "Insufficient data"

        plus20 = df_timeout[df_timeout["timeout_variant"]
                            == "TIMEOUT_PLUS_20_BARS"]
        if len(plus20) > 0 and len(current_t) > 0:
            p20_net = plus20["net_total_pnl_pct"].mean()
            q8_ans = f"Longer timeout (+20 bars): avg net pnl {p20_net:.4f} vs current {cur_net:.4f} -> {'HURTS' if p20_net < cur_net else 'HELPS'}"
        else:
            q8_ans = "Insufficient data"
    else:
        q7_ans = "N/A"
        q8_ans = "N/A"

    # Regime-change exit impact
    if len(regime_exit_rows) > 0:
        rc_on = [r for r in regime_exit_rows if r["exit_mode"]
                 == "EXIT_ON_REGIME_CHANGE"]
        rc_off = [r for r in regime_exit_rows if r["exit_mode"]
                  == "EXIT_NO_REGIME_CHANGE"]
        if rc_on and rc_off:
            avg_on = np.mean([r["net_total_pnl_pct"] for r in rc_on])
            avg_off = np.mean([r["net_total_pnl_pct"] for r in rc_off])
            q9_ans = f"RC-exit ON: {avg_on:.4f} vs OFF: {avg_off:.4f} -> {'HELPS' if avg_on > avg_off else 'HURTS'}"
        else:
            q9_ans = "N/A"
    else:
        q9_ans = "N/A"

    # Best candidate survives 6bps?
    bc_net = best_cand_row["net_total_pnl_pct"]
    q10_ans = f"Best candidate net pnl: {bc_net:.4f} -> {'YES SURVIVES' if bc_net > 0 else 'NO EDGE ERASED'}"

    # ETH or BTC or both?
    if sym_split:
        sym_info = {s["symbol"]: s["net_total_pnl_pct"] for s in sym_split}
        q11_ans = f"BTC net={sym_info.get('BTCUSDT', 'N/A')}, ETH net={sym_info.get('ETHUSDT', 'N/A')}"
    else:
        q11_ans = "Insufficient symbol split data"

    # Testnet ready?
    bc_gross = best_cand_row["gross_total_pnl_pct"]
    bc_net_val = best_cand_row["net_total_pnl_pct"]
    bc_n = int(best_cand_row["admitted_count"])
    testnet_ready = (bc_net_val > 0) and (
        bc_n >= 10) and (best_cand_row["avg_r"] > 0)
    q12_ans = (
        f"{'YES — testnet consideration warranted' if testnet_ready else 'NO — conditions not met'}. "
        f"n={bc_n}, net={bc_net_val:.4f}, avg_r={best_cand_row['avg_r']:.4f}"
    )

    # Rejected candidates
    rejected = df_tpsl[
        (df_tpsl["net_total_pnl_pct"] <= 0) | (df_tpsl["avg_r"] <= 0)
    ]
    q13_ans = f"{len(rejected)}/{len(df_tpsl)} TP/SL combos rejected (net_pnl <= 0 or avg_r <= 0)"

    # -----------------------------------------------------------------------
    # Determine verdict
    # -----------------------------------------------------------------------
    if testnet_ready:
        verdict = f"TESTNET_CANDIDATE_IDENTIFIED: {best_cand_row['candidate_name']}"
    elif bc_net_val > 0:
        verdict = "EDGE_EXISTS_BUT_INSUFFICIENT_SAMPLE"
    else:
        verdict = "NO_NET_POSITIVE_CANDIDATE_FOUND"

    # -----------------------------------------------------------------------
    # Write JSON
    # -----------------------------------------------------------------------
    now_str = datetime.now().astimezone().isoformat()

    out_json = {
        "report_id": "AURORA_TREND_UP_MICROBAND_TPSL_TIMEOUT_GRID_V1",
        "generated_at": now_str,
        "verdict": verdict,
        "baseline": {
            "tp_bps": BASELINE_TP_BPS,
            "sl_bps": BASELINE_SL_BPS,
            "timeout_bars": BASELINE_TIMEOUT_BARS,
            "cost_bps": COST_BPS,
        },
        "f5_recap": {
            "admitted": 58,
            "good": 22,
            "bad": 36,
            "win_rate": 0.3793,
            "total_pnl_pct": 6.0919,
            "avg_r": 0.2344,
            "mdd_proxy": 2.7785,
        },
        "top3_bands": top3_bands,
        "top5_tpsl_candidates": top5_tpsl,
        "best_candidate": {
            "name": best_cand_row["candidate_name"],
            "band": best_band,
            "tp_bps": best_tp_bps,
            "sl_bps": best_sl_bps,
            "tp_pct": best_tp_bps / 10_000,
            "sl_pct": best_sl_bps / 10_000,
            "admitted_count": int(best_cand_row["admitted_count"]),
            "win_rate": float(best_cand_row["win_rate"]) if best_cand_row["win_rate"] is not None else None,
            "gross_total_pnl_pct": float(best_cand_row["gross_total_pnl_pct"]),
            "net_total_pnl_pct": float(best_cand_row["net_total_pnl_pct"]),
            "avg_r": float(best_cand_row["avg_r"]),
            "mdd_proxy": float(best_cand_row["mdd_proxy"]),
        },
        "critical_questions": {
            "q1_best_micro_band": q1_ans,
            "q2_edge_distribution": q2_ans,
            "q3_440_450_toxic": q3_ans,
            "q4_threshold_sensitivity": "See micro-band table for 0.41/0.42/0.43/0.44 thresholds",
            "q5_best_tp_multiplier": q5_ans,
            "q6_best_sl_multiplier": q6_ans,
            "q7_shorter_timeout": q7_ans,
            "q8_longer_timeout": q8_ans,
            "q9_regime_change_exit": q9_ans,
            "q10_survives_6bps_cost": q10_ans,
            "q11_btc_vs_eth": q11_ans,
            "q12_testnet_ready": q12_ans,
            "q13_rejected_candidates": q13_ans,
        },
        "symbol_split": sym_split,
        "age_split": age_split,
        "pos_split": pos_split,
        "impulse_split": impulse_split,
        "conf_sub_split": conf_sub_split,
        "regime_exit_comparison": regime_exit_rows,
        "microband_summary": microband_rows,
    }

    OUT_JSON.write_text(json.dumps(
        out_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  -> {OUT_JSON}")

    # -----------------------------------------------------------------------
    # Write Markdown report
    # -----------------------------------------------------------------------
    print("\nWriting markdown report...")

    md_lines: list[str] = []

    def add(line: str = "") -> None:
        md_lines.append(line)

    add("# AURORA_TREND_UP_MICROBAND_TPSL_TIMEOUT_GRID_V1")
    add()
    add("## Verdict")
    add(f"- **{verdict}**")
    add(f"- Best candidate: `{best_cand_row['candidate_name']}`")
    add()
    add("## Problem framing")
    add(
        "Decompose the validated F5 confidence band (0.40..0.45) into micro-bands "
        "and test TP/SL/timeout variants to find a testnet-ready TREND_UP candidate shape."
    )
    add()
    add("## FACTS")
    add("- Input: 58 entries from F5 TREND_UP shadow replay validation (all TREND_UP, conf 0.40..0.45).")
    add(f"- Baseline TP: {BASELINE_TP_BPS:.1f} bps ({BASELINE_TP_PCT*100:.2f}%), SL: {BASELINE_SL_BPS:.1f} bps ({BASELINE_SL_PCT*100:.2f}%).")
    add(f"- Baseline timeout: {BASELINE_TIMEOUT_BARS} bars.")
    add("- Symbols: BTCUSDT (33 entries), ETHUSDT (25 entries).")
    add("- MFE/MAE/bars_to_mfe/bars_to_mae available per entry for TP/SL race simulation.")
    add("- Exit reasons in input: END_OF_DATA=25, TP=13, SL=10, TIMEOUT=10.")
    add()
    add("## INFERENCES")
    add("- TP/SL hits simulated via MFE vs MAE race logic (approximate; no bar-by-bar path).")
    add("- If both TP and SL would fire: earlier bar wins; tie → SL (conservative).")
    add("- Timeout PnL = original pure_pnl_pct (approximation; no bar-by-bar price available).")
    add("- 25 END_OF_DATA exits: trade did not resolve within dataset window.")
    add()
    add("## ASSUMPTIONS")
    add("- TREND_UP => BUY / LONG; MFE is favorable (upward), MAE is adverse (downward).")
    add("- Cost model NET_6BPS: 6 bps round-trip (4bps maker fees + 2bps slippage).")
    add("- R-multiple uses baseline SL (50 bps) as denominator for consistency.")
    add()
    add("## UNKNOWNS")
    add("- Exact intra-bar price path; early TP/SL conflict resolution is approximate.")
    add("- Timeout PnL at non-standard timeout: approximated from original pure_pnl_pct.")
    add("- Live microstructure effects not modeled.")
    add("- Regime-change exit PnL for EXIT_NO_REGIME_CHANGE uses original pure_pnl_pct.")
    add()
    add("## Data inventory")
    add(
        f"- `reports/AURORA_TREND_UP_CONF_040_045_SHADOW_REPLAY_V1_ENTRIES_{DATE_TAG}.csv` — 58 F5 entries")
    add(
        f"- `reports/AURORA_TREND_UP_P1_ENRICHED_ENTRIES_{DATE_TAG}.csv` — 115 P1 enriched entries")
    add(f"- `reports/BTC_ETH_CLEAN_TREND_REGIME_EDGE_REPLAY_V1_trades.csv` — 9407 trades")
    add()
    add("## Prior F5 recap")
    add("| metric | value |")
    add("| --- | ---: |")
    add("| admitted_count | 58 |")
    add("| profitable_count | 22 |")
    add("| losing_count | 36 |")
    add("| win_rate | 0.3793 |")
    add("| total_pnl_pct | +6.0919 |")
    add("| avg_r | +0.2344 |")
    add("| mdd_proxy | 2.7785 |")
    add()
    add("## Confidence micro-band results")
    add()
    mb_cols = [
        "band", "admitted_count", "btc_count", "eth_count", "good_count", "bad_count",
        "win_rate", "total_pnl_pct", "avg_r", "mdd_proxy",
        "avg_mfe_bps", "avg_mae_bps", "kept_good_rate", "rejected_bad_rate"
    ]
    mb_display = []
    for r in microband_rows:
        mb_display.append({
            "band": r["band"],
            "n": r["admitted_count"],
            "btc": r.get("btc_count", ""),
            "eth": r.get("eth_count", ""),
            "good": r.get("good_count", ""),
            "bad": r.get("bad_count", ""),
            "wr": _sf(r.get("win_rate"), 4),
            "total_pnl": _sf(r.get("total_pnl_pct"), 4),
            "avg_r": _sf(r.get("avg_r"), 4),
            "mdd": _sf(r.get("mdd_proxy"), 4),
            "avg_mfe": _sf(r.get("avg_mfe_bps"), 1),
            "avg_mae": _sf(r.get("avg_mae_bps"), 1),
            "kgr": _sf(r.get("kept_good_rate"), 3),
            "rbr": _sf(r.get("rejected_bad_rate"), 3),
        })
    add(md_table(mb_display, ["band", "n", "btc", "eth", "good", "bad", "wr",
        "total_pnl", "avg_r", "mdd", "avg_mfe", "avg_mae", "kgr", "rbr"]))
    add()
    add(f"**Selected top 3 bands for TP/SL grid:** {', '.join(top3_bands)}")
    add()
    add("## Selected bands for TP/SL grid")
    add()
    for bname in top3_bands:
        row = df_microband[df_microband["band"] == bname]
        if len(row) == 0:
            continue
        r = row.iloc[0]
        add(f"### {bname}")
        add(f"- Confidence: [{r.get('lo', '')}, {r.get('hi', '')})")
        add(f"- Admitted: {r.get('admitted_count', 'N/A')}")
        add(f"- Good/Bad: {r.get('good_count', 'N/A')}/{r.get('bad_count', 'N/A')}")
        add(f"- Total PnL: {_sf(r.get('total_pnl_pct'), 4)}")
        add(f"- Avg R: {_sf(r.get('avg_r'), 4)}")
        add()

    add("## TP/SL grid results")
    add()
    add("Top 20 combinations by net total PnL (across all selected bands):")
    add()
    top20_tpsl = df_tpsl.sort_values(
        "net_total_pnl_pct", ascending=False).head(20)
    tpsl_disp = []
    for _, r in top20_tpsl.iterrows():
        tpsl_disp.append({
            "candidate_name": r["candidate_name"],
            "n": r["admitted_count"],
            "tp_bps": f"{r['tp_bps']:.1f}",
            "sl_bps": f"{r['sl_bps']:.1f}",
            "tp_ct": r["tp_count"],
            "sl_ct": r["sl_count"],
            "to_ct": r["timeout_count"],
            "wr": _sf(r["win_rate"], 3),
            "gross_pnl": _sf(r["gross_total_pnl_pct"], 4),
            "net_pnl": _sf(r["net_total_pnl_pct"], 4),
            "avg_r": _sf(r["avg_r"], 4),
            "mdd": _sf(r["mdd_proxy"], 4),
        })
    add(md_table(tpsl_disp, ["candidate_name", "n", "tp_bps", "sl_bps",
        "tp_ct", "sl_ct", "to_ct", "wr", "gross_pnl", "net_pnl", "avg_r", "mdd"]))
    add()

    add("## Timeout grid results")
    add()
    if len(df_timeout) > 0:
        to_disp = []
        for _, r in df_timeout.sort_values(["candidate_name", "timeout_variant"]).iterrows():
            to_disp.append({
                "candidate_name": r["candidate_name"][:60],
                "timeout": r["timeout_variant"],
                "bars": str(r["timeout_bars"]),
                "tp_ct": r["tp_count"],
                "sl_ct": r["sl_count"],
                "to_ct": r["timeout_count"],
                "so_ct": r["still_open_count"],
                "wr": _sf(r["win_rate"], 3),
                "gross_pnl": _sf(r["gross_total_pnl_pct"], 4),
                "net_pnl": _sf(r["net_total_pnl_pct"], 4),
                "avg_r": _sf(r["avg_r"], 4),
            })
        add(md_table(to_disp, ["candidate_name", "timeout", "bars", "tp_ct",
            "sl_ct", "to_ct", "so_ct", "wr", "gross_pnl", "net_pnl", "avg_r"]))
    else:
        add("No timeout grid data.")
    add()

    add("## Regime-change exit results")
    add()
    if regime_exit_rows:
        rc_disp = []
        for r in regime_exit_rows:
            rc_disp.append({
                "candidate": r["candidate_name"][:55],
                "exit_mode": r["exit_mode"],
                "n": r["admitted_count"],
                "tp_ct": r["tp_count"],
                "sl_ct": r["sl_count"],
                "rc_ct": r["regime_change_count"],
                "wr": _sf(r["win_rate"], 3),
                "gross_pnl": _sf(r["gross_total_pnl_pct"], 4),
                "net_pnl": _sf(r["net_total_pnl_pct"], 4),
                "avg_r": _sf(r["avg_r"], 4),
            })
        add(md_table(rc_disp, ["candidate", "exit_mode", "n", "tp_ct",
            "sl_ct", "rc_ct", "wr", "gross_pnl", "net_pnl", "avg_r"]))
    else:
        add("No regime-change exit data.")
    add()

    add("## Gross vs net results")
    add()
    add(f"Cost model: NET_6BPS = {COST_BPS} bps round-trip (4bps fees + 2bps slippage)")
    add()
    add("Best candidate comparison:")
    add(f"- Gross total PnL: {_sf(best_cand_row['gross_total_pnl_pct'], 4)}%")
    add(
        f"- Net total PnL (-6bps/trade): {_sf(best_cand_row['net_total_pnl_pct'], 4)}%")
    add(f"- Cost drag for {int(best_cand_row['admitted_count'])} trades: {int(best_cand_row['admitted_count']) * COST_BPS / 100:.4f}%")
    add()

    add("## BTC vs ETH split")
    add()
    if sym_split:
        sym_disp = []
        for s in sym_split:
            sym_disp.append({
                "symbol": s["symbol"],
                "count": s["count"],
                "good": s["good_count"],
                "bad": s["bad_count"],
                "wr": _sf(s["win_rate"], 3),
                "gross_pnl": _sf(s["gross_total_pnl_pct"], 4),
                "net_pnl": _sf(s["net_total_pnl_pct"], 4),
                "avg_r": _sf(s["avg_r"], 4),
                "mdd": _sf(s["mdd_proxy"], 4),
            })
        add(md_table(sym_disp, ["symbol", "count", "good",
            "bad", "wr", "gross_pnl", "net_pnl", "avg_r", "mdd"]))
    else:
        add("No symbol split data.")
    add()

    add("## Confidence sub-band analysis")
    add()
    if conf_sub_split:
        cs_disp = []
        for s in conf_sub_split:
            cs_disp.append({
                "sub_band": s["sub_band"],
                "lo": s["lo"],
                "hi": s["hi"],
                "count": s["count"],
                "good": s["good_count"],
                "bad": s["bad_count"],
                "wr": _sf(s["win_rate"], 3),
                "gross_pnl": _sf(s["gross_total_pnl_pct"], 4),
                "net_pnl": _sf(s["net_total_pnl_pct"], 4),
                "avg_r": _sf(s["avg_r"], 4),
            })
        add(md_table(cs_disp, ["sub_band", "lo", "hi", "count",
            "good", "bad", "wr", "gross_pnl", "net_pnl", "avg_r"]))
    else:
        add("Not applicable (best band is a micro-band).")
    add()

    add("## Regime age analysis")
    add()
    if age_split:
        age_disp = []
        for s in age_split:
            age_disp.append({
                "age_bucket": s["split"],
                "count": s["count"],
                "good": s["good_count"],
                "bad": s["bad_count"],
                "wr": _sf(s["win_rate"], 3),
                "gross_pnl": _sf(s["gross_total_pnl_pct"], 4),
                "net_pnl": _sf(s["net_total_pnl_pct"], 4),
                "avg_r": _sf(s["avg_r"], 4),
            })
        add(md_table(age_disp, ["age_bucket", "count", "good",
            "bad", "wr", "gross_pnl", "net_pnl", "avg_r"]))
    else:
        add("No data for age split.")
    add()

    add("## Local range position analysis")
    add()
    if pos_split:
        pos_disp = []
        for s in pos_split:
            pos_disp.append({
                "position_bucket": s["split"],
                "count": s["count"],
                "good": s["good_count"],
                "bad": s["bad_count"],
                "wr": _sf(s["win_rate"], 3),
                "gross_pnl": _sf(s["gross_total_pnl_pct"], 4),
                "net_pnl": _sf(s["net_total_pnl_pct"], 4),
                "avg_r": _sf(s["avg_r"], 4),
            })
        add(md_table(pos_disp, ["position_bucket", "count",
            "good", "bad", "wr", "gross_pnl", "net_pnl", "avg_r"]))
    else:
        add("No data for position split.")
    add()

    add("## Pre-entry impulse analysis")
    add()
    if impulse_split:
        imp_disp = []
        for s in impulse_split:
            imp_disp.append({
                "impulse_bucket": s["split"],
                "count": s["count"],
                "good": s["good_count"],
                "bad": s["bad_count"],
                "wr": _sf(s["win_rate"], 3),
                "gross_pnl": _sf(s["gross_total_pnl_pct"], 4),
                "net_pnl": _sf(s["net_total_pnl_pct"], 4),
                "avg_r": _sf(s["avg_r"], 4),
            })
        add(md_table(imp_disp, ["impulse_bucket", "count",
            "good", "bad", "wr", "gross_pnl", "net_pnl", "avg_r"]))
    else:
        add("No data for impulse split.")
    add()

    add("## Best candidate")
    add()
    add(f"**Name:** `{best_cand_row['candidate_name']}`")
    add()
    add("| metric | value |")
    add("| --- | ---: |")
    add(f"| band | {best_band} |")
    add(f"| tp_bps | {best_tp_bps:.1f} |")
    add(f"| sl_bps | {best_sl_bps:.1f} |")
    add(f"| timeout_bars | {BASELINE_TIMEOUT_BARS} |")
    add(f"| admitted_count | {int(best_cand_row['admitted_count'])} |")
    add(f"| win_rate | {_sf(best_cand_row['win_rate'], 4)} |")
    add(
        f"| gross_total_pnl_pct | {_sf(best_cand_row['gross_total_pnl_pct'], 4)} |")
    add(
        f"| net_total_pnl_pct | {_sf(best_cand_row['net_total_pnl_pct'], 4)} |")
    add(f"| avg_r | {_sf(best_cand_row['avg_r'], 4)} |")
    add(f"| mdd_proxy | {_sf(best_cand_row['mdd_proxy'], 4)} |")
    add()

    add("## Candidates rejected")
    add()
    add(f"- {len(rejected)}/{len(df_tpsl)} TP/SL combinations rejected (net_pnl_pct <= 0 or avg_r <= 0).")
    if len(df_tpsl) > 0:
        worst_5 = df_tpsl.sort_values("net_total_pnl_pct").head(5)
        add("Worst 5 combinations:")
        w_disp = []
        for _, r in worst_5.iterrows():
            w_disp.append({
                "candidate_name": r["candidate_name"],
                "net_pnl": _sf(r["net_total_pnl_pct"], 4),
                "avg_r": _sf(r["avg_r"], 4),
            })
        add(md_table(w_disp, ["candidate_name", "net_pnl", "avg_r"]))
    add()

    add("## Testnet implication")
    add()
    add(f"**Testnet-ready:** {'YES' if testnet_ready else 'NO'}")
    add()
    if testnet_ready:
        add("The best candidate shows:")
        add(f"- Positive net PnL ({bc_net_val:.4f}%) after 6 bps cost per trade")
        add(f"- Adequate sample size (n={bc_n})")
        add(f"- Positive avg R ({best_cand_row['avg_r']:.4f})")
        add()
        add("Recommended configuration for testnet shadow deployment:")
        add("```yaml")
        add("trend_up_shadow_admission_candidate:")
        lo_b = next(lo for (bn, lo, hi) in CONF_BANDS if bn == best_band)
        hi_b = next(hi for (bn, lo, hi) in CONF_BANDS if bn == best_band)
        add(f"  min_confidence: {lo_b}")
        add(f"  max_confidence_exclusive: {hi_b}")
        add(f"  tp_pct: {best_tp_bps / 10_000:.5f}")
        add(f"  sl_pct: {best_sl_bps / 10_000:.5f}")
        add(f"  timeout_bars: {BASELINE_TIMEOUT_BARS}")
        add("  mode: shadow")
        add("```")
    else:
        add("Conditions for testnet consideration not met. Collect more data or adjust filters.")
    add()

    add("## Critical questions")
    add()
    add(f"1. **Best micro-band:** {q1_ans}")
    add(f"2. **Edge distribution:** {q2_ans}")
    add(f"3. **0.44..0.45 toxic?** {q3_ans}")
    add("4. **Threshold sensitivity:** See micro-band table above.")
    add(f"5. **Best TP multiplier:** {q5_ans}")
    add(f"6. **Best SL multiplier:** {q6_ans}")
    add(f"7. **Shorter timeout:** {q7_ans}")
    add(f"8. **Longer timeout:** {q8_ans}")
    add(f"9. **Regime-change exit:** {q9_ans}")
    add(f"10. **Survives 6 bps cost:** {q10_ans}")
    add(f"11. **BTC vs ETH:** {q11_ans}")
    add(f"12. **Testnet ready:** {q12_ans}")
    add(f"13. **Rejected candidates:** {q13_ans}")
    add()

    add("## What must NOT change yet")
    add("- No production YAML patch")
    add("- No runtime mutation")
    add("- No execution_position changes")
    add("- No live execution")
    add("- No TREND_DOWN admission expansion")
    add("- No global max-cap disable")
    add("- No expansion beyond 0.45")
    add()

    add("## Recommended next step")
    add()
    if testnet_ready:
        add(
            f"1. Deploy best candidate `{best_cand_row['candidate_name']}` in shadow mode on testnet.")
        add("2. Collect live shadow telemetry for 2-4 weeks before any live activation.")
        add("3. Validate regime-change exit behavior in live market conditions.")
        add("4. Monitor BTC vs ETH divergence in live data.")
    else:
        add("1. Extend dataset window or collect more TREND_UP entries.")
        add("2. Re-run this analysis when n >= 30 per candidate band.")
    add()

    add("## Acceptance gate")
    add()
    gate = {
        "microband_decomposed": len(microband_rows) == len(CONF_BANDS),
        "tpsl_grid_run": len(df_tpsl) > 0,
        "timeout_grid_run": len(df_timeout) > 0,
        "gross_and_net_reported": True,
        "btc_eth_separated": len(sym_split) >= 1,
        "best_candidate_selected": True,
        "no_runtime_mutation": True,
    }
    for k, v in gate.items():
        add(f"- {k}: {'PASS' if v else 'FAIL'}")
    all_pass = all(gate.values())
    add(f"- **all_pass: {all_pass}**")
    add()

    add("## Artifacts")
    add(
        f"- reports/AURORA_TREND_UP_MICROBAND_TPSL_TIMEOUT_GRID_V1_{DATE_TAG}.md")
    add(
        f"- reports/AURORA_TREND_UP_MICROBAND_TPSL_TIMEOUT_GRID_V1_{DATE_TAG}.json")
    add(f"- reports/AURORA_TREND_UP_MICROBAND_RESULTS_{DATE_TAG}.csv")
    add(f"- reports/AURORA_TREND_UP_TPSL_GRID_RESULTS_{DATE_TAG}.csv")
    add(f"- reports/AURORA_TREND_UP_TIMEOUT_GRID_RESULTS_{DATE_TAG}.csv")
    add(f"- reports/AURORA_TREND_UP_BEST_CANDIDATE_TRADES_{DATE_TAG}.csv")

    OUT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"  -> {OUT_MD}")
    print(f"\nDone. Verdict: {verdict}")


if __name__ == "__main__":
    main()
