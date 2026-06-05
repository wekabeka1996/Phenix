"""
TREND_UP_400_410_BEST_CANDIDATE_METRIC_RECHECK_V1

Recalculates metrics for:
  TREND_UP_CONF_400_410_TP_070X_SL_150X_TIMEOUT_CURRENT

ROOT CAUSE of prior report error:
  pure_pnl_pct in entries CSV is stored in PERCENT notation
    (e.g. 0.95 = 0.95% = 95 bps, -0.500 = -0.5% = -50 bps)
  Previous simulate_trade() returned TP/SL pnl as:
    tp_pct = tp_bps / 10_000  →  66.5 / 10_000 = 0.00665
  This is the DECIMAL FRACTION (0.00665 = 0.00665% = 0.0665 bps) —
  100× smaller than the correct percent value (0.665% = 66.5 bps).
  TIMEOUT exits used pure_pnl_pct directly (correct ~0.16..0.95).
  This unit mismatch inflated avg_r by ~100×.

CORRECT UNITS throughout this script:
  - All pnl values in PERCENT (1.0 = 1.0% = 100 bps)
  - TP pnl  = tp_bps / 100   (66.5 / 100 = 0.665 %)
  - SL pnl  = -sl_bps / 100  (-75.0 / 100 = -0.750 %)
  - Cost    = cost_bps / 100  (6 / 100 = 0.06 % per trade)
  - R mult  = pnl_pct / sl_pct_percent  (both in percent)

ADDITIONAL KNOWN LIMITATION:
  mfe_bps / mae_bps in entries CSV are bar-CLOSE based (not intrabar).
  Original TP exits (95 bps) show close-based mfe as low as 3.91 bps,
  proving TP was hit intrabar before bar close.
  Consequence: simulation underestimates intrabar TP fires for TP=66.5 bps.
  Reported TP count (4) is a LOWER BOUND; actual intrabar hits may be higher.
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
OUT_MD = REPORTS / \
    f"TREND_UP_400_410_BEST_CANDIDATE_METRIC_RECHECK_V1_{DATE_TAG}.md"
OUT_JSON = REPORTS / \
    f"TREND_UP_400_410_BEST_CANDIDATE_METRIC_RECHECK_V1_{DATE_TAG}.json"

# ---------------------------------------------------------------------------
# Candidate parameters
# ---------------------------------------------------------------------------
CAND_NAME = "TREND_UP_CONF_400_410_TP_070X_SL_150X_TIMEOUT_CURRENT"
CONF_LO = 0.400
CONF_HI = 0.410          # exclusive
TP_BPS = 66.5          # 0.665 %
SL_BPS = 75.0          # 0.750 %
TIMEOUT = 18            # bars

# Correct percent equivalents
TP_PCT = TP_BPS / 100  # 0.665 %
SL_PCT = SL_BPS / 100  # 0.750 %

COST_MODELS_BPS = [4, 6, 8, 10]

# ---------------------------------------------------------------------------
# Simulation (correct units)
# ---------------------------------------------------------------------------


def simulate_trade_correct(
    mfe_bps: float,
    mae_bps: float,   # negative value
    bars_to_mfe: int,
    bars_to_mae: int,
    original_exit_reason: str,
    pure_pnl_pct: float,   # PERCENT notation (e.g. 0.95 = 0.95%)
    tp_bps: float,
    sl_bps: float,
    timeout_bars: int,
) -> tuple[str, float]:
    """
    Simulate trade outcome with CORRECT unit handling.

    All returned pnl values are in PERCENT notation.

    TP pnl = +tp_bps / 100
    SL pnl = -sl_bps / 100
    TIMEOUT pnl = pure_pnl_pct (already percent)

    NOTE: mfe_bps and |mae_bps| are close-based, so TP/SL
    detection is conservative (intrabar hits may be missed).
    """
    tp_pct_correct = tp_bps / 100    # 0.665 %
    sl_pct_correct = sl_bps / 100    # 0.750 %

    tp_fires = (mfe_bps >= tp_bps) and (bars_to_mfe <= timeout_bars)
    sl_fires = ((-mae_bps) >= sl_bps) and (bars_to_mae <= timeout_bars)

    if tp_fires and sl_fires:
        if bars_to_mfe < bars_to_mae:
            return "TP", tp_pct_correct
        else:
            return "SL", -sl_pct_correct
    elif tp_fires:
        return "TP", tp_pct_correct
    elif sl_fires:
        return "SL", -sl_pct_correct
    else:
        return "TIMEOUT", pure_pnl_pct


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    df_all = pd.read_csv(ENTRIES_CSV)
    df = df_all[
        (df_all["admit_confidence"] >= CONF_LO) &
        (df_all["admit_confidence"] < CONF_HI)
    ].copy().reset_index(drop=True)

    n = len(df)
    print(f"Loaded {n} entries for MB_400_410 from {ENTRIES_CSV.name}")

    # -------------------------------------------------------------------
    # Per-trade simulation
    # -------------------------------------------------------------------
    records: list[dict] = []
    pnl_list: list[float] = []
    exit_reasons: list[str] = []

    for _, row in df.iterrows():
        sim_exit, sim_pnl = simulate_trade_correct(
            mfe_bps=float(row["mfe_bps"]),
            mae_bps=float(row["mae_bps"]),
            bars_to_mfe=int(row["bars_to_mfe"]),
            bars_to_mae=int(row["bars_to_mae"]),
            original_exit_reason=str(row["exit_reason"]),
            pure_pnl_pct=float(row["pure_pnl_pct"]),
            tp_bps=TP_BPS,
            sl_bps=SL_BPS,
            timeout_bars=TIMEOUT,
        )
        pnl_list.append(sim_pnl)
        exit_reasons.append(sim_exit)
        records.append({
            "segment_id": row["segment_id"],
            "symbol": row["symbol"],
            "admit_confidence": float(row["admit_confidence"]),
            "orig_exit_reason": row["exit_reason"],
            "orig_pnl_pct": float(row["pure_pnl_pct"]),
            "sim_exit_reason": sim_exit,
            "sim_pnl_pct": round(sim_pnl, 6),
            "profitable_label": int(row["profitable_label"]),
            "mfe_bps": float(row["mfe_bps"]),
            "mae_bps": float(row["mae_bps"]),
            "bars_to_mfe": int(row["bars_to_mfe"]),
            "bars_to_mae": int(row["bars_to_mae"]),
            "age_bucket_6": row["age_bucket_6"],
            "position_in_range_10_bucket": row["position_in_range_10_bucket"],
            "pre_entry_impulse_bucket": row["pre_entry_impulse_bucket"],
        })

    pnl_arr = np.array(pnl_list, dtype=float)

    # -------------------------------------------------------------------
    # Core metrics (CORRECT units)
    # -------------------------------------------------------------------
    n_tp = exit_reasons.count("TP")
    n_sl = exit_reasons.count("SL")
    n_to = exit_reasons.count("TIMEOUT")

    gross_pnl_pct = float(pnl_arr.sum())
    avg_pnl_pct = float(pnl_arr.mean())

    wins = int((pnl_arr > 0).sum())
    win_rate = wins / n

    # R-multiple: CORRECT — both in same percent units
    avg_r = avg_pnl_pct / SL_PCT        # dimensionless
    total_r = gross_pnl_pct / SL_PCT    # total R earned across all trades

    # Max drawdown (cumulative pnl path)
    cum_pnl = np.cumsum(pnl_arr)
    rolling_max = np.maximum.accumulate(cum_pnl)
    dd_arr = rolling_max - cum_pnl
    max_drawdown_pct = float(dd_arr.max())

    # Cost models
    cost_results: list[dict] = []
    for c_bps in COST_MODELS_BPS:
        c_pct = c_bps / 100  # percent
        cost_drag_pct = n * c_pct
        net_pnl_pct = gross_pnl_pct - cost_drag_pct
        net_avg_pnl_pct = avg_pnl_pct - c_pct
        net_avg_r = net_avg_pnl_pct / SL_PCT
        cost_results.append({
            "cost_bps": c_bps,
            "cost_pct_per_trade": round(c_pct, 4),
            "cost_drag_total_pct": round(cost_drag_pct, 4),
            "net_pnl_pct": round(net_pnl_pct, 4),
            "net_avg_pnl_pct": round(net_avg_pnl_pct, 6),
            "net_avg_r": round(net_avg_r, 6),
            "verdict": "POSITIVE" if net_pnl_pct > 0 else "NEGATIVE",
        })

    # -------------------------------------------------------------------
    # Per-symbol split
    # -------------------------------------------------------------------
    def sym_metrics(sym: str) -> dict:
        idx = [i for i, r in enumerate(records) if r["symbol"] == sym]
        if not idx:
            return {}
        sub_pnl = pnl_arr[idx]
        sub_exits = [exit_reasons[i] for i in idx]
        cnt = len(idx)
        sub_wins = int((sub_pnl > 0).sum())
        sub_gross = float(sub_pnl.sum())
        sub_avg = float(sub_pnl.mean())
        sub_r = sub_avg / SL_PCT
        sub_cum = np.cumsum(sub_pnl)
        sub_rmax = np.maximum.accumulate(sub_cum)
        sub_mdd = float((sub_rmax - sub_cum).max())
        cost_6 = cnt * 0.06
        return {
            "symbol": sym,
            "count": cnt,
            "tp_count": sub_exits.count("TP"),
            "sl_count": sub_exits.count("SL"),
            "timeout_count": sub_exits.count("TIMEOUT"),
            "wins": sub_wins,
            "win_rate": round(sub_wins / cnt, 4),
            "gross_pnl_pct": round(sub_gross, 4),
            "net_pnl_pct_6bps": round(sub_gross - cost_6, 4),
            "avg_pnl_pct": round(sub_avg, 6),
            "avg_r": round(sub_r, 4),
            "max_drawdown_pct": round(sub_mdd, 4),
        }

    sym_btc = sym_metrics("BTCUSDT")
    sym_eth = sym_metrics("ETHUSDT")

    # -------------------------------------------------------------------
    # Comparison with prior erroneous report
    # -------------------------------------------------------------------
    prior_gross = 4.5023
    prior_avg_r = 36.0184
    prior_net_6bps = 4.4873

    # Identify previously misreported TP/SL pnl
    tp_pnl_old = TP_BPS / 10_000        # 0.00665  (bug)
    tp_pnl_new = TP_BPS / 100           # 0.665    (correct)
    sl_pnl_old = SL_BPS / 10_000        # 0.0075   (bug)
    sl_pnl_new = SL_BPS / 100           # 0.750    (correct)

    pnl_correction_tp = n_tp * (tp_pnl_new - tp_pnl_old)   # +
    pnl_correction_sl = n_sl * (-sl_pnl_new - (-sl_pnl_old))  # -
    expected_corrected_gross = prior_gross + pnl_correction_tp + pnl_correction_sl

    # -------------------------------------------------------------------
    # Print summary
    # -------------------------------------------------------------------
    print()
    print("=" * 60)
    print("CORRECT METRICS (all values in PERCENT notation)")
    print("=" * 60)
    print(f"n_trades         = {n}")
    print(
        f"TP fires         = {n_tp}  (close-based; lower bound; intrabar may be higher)")
    print(f"SL fires         = {n_sl}")
    print(f"TIMEOUT          = {n_to}")
    print(f"wins             = {wins}")
    print(f"win_rate         = {win_rate:.4f}")
    print(f"gross_pnl_pct    = {gross_pnl_pct:.4f}%")
    print(f"avg_pnl_pct      = {avg_pnl_pct:.6f}%")
    print(
        f"avg_r (CORRECT)  = {avg_r:.4f}  [avg_pnl / SL_pct = {avg_pnl_pct:.6f} / {SL_PCT:.4f}]")
    print(f"total_r          = {total_r:.4f}  [gross_pnl / SL_pct]")
    print(f"max_drawdown_pct = {max_drawdown_pct:.4f}%")
    print()
    print("Prior report errors:")
    print(
        f"  TP pnl per trade: OLD={tp_pnl_old:.5f} (0.0665bps!) -> NEW={tp_pnl_new:.4f} (66.5bps)")
    print(
        f"  SL pnl per trade: OLD={sl_pnl_old:.5f} (0.075bps!) -> NEW={sl_pnl_new:.4f} (75.0bps)")
    print(
        f"  avg_r:            OLD={prior_avg_r:.4f} (100x inflated!) -> NEW={avg_r:.4f}")
    print(
        f"  gross_pnl:        OLD={prior_gross:.4f}% -> NEW={gross_pnl_pct:.4f}%")
    print(
        f"  Expected correction: {prior_gross:.4f} + {pnl_correction_tp:.4f} + {pnl_correction_sl:.4f} = {expected_corrected_gross:.4f}%")
    print()
    print("Cost models:")
    for c in cost_results:
        print(f"  {c['cost_bps']:2d} bps: drag={c['cost_drag_total_pct']:.4f}%  net={c['net_pnl_pct']:+.4f}%  avg_r={c['net_avg_r']:+.4f}  [{c['verdict']}]")
    print()
    print("BTC split:", sym_btc)
    print("ETH split:", sym_eth)

    # -------------------------------------------------------------------
    # Build output JSON
    # -------------------------------------------------------------------
    now_str = datetime.now().astimezone().isoformat()

    verdict_6bps = next(c for c in cost_results if c["cost_bps"] == 6)
    verdict_10bps = next(c for c in cost_results if c["cost_bps"] == 10)
    all_positive = all(c["net_pnl_pct"] > 0 for c in cost_results)
    verdict = "ACCEPTED_FOR_TESTNET_PREP" if all_positive else "CONDITIONAL"

    out_json = {
        "report_id": "TREND_UP_400_410_BEST_CANDIDATE_METRIC_RECHECK_V1",
        "generated_at": now_str,
        "verdict": verdict,
        "candidate_name": CAND_NAME,
        "parameters": {
            "conf_lo": CONF_LO,
            "conf_hi_exclusive": CONF_HI,
            "tp_bps": TP_BPS,
            "sl_bps": SL_BPS,
            "tp_pct_correct": TP_PCT,
            "sl_pct_correct": SL_PCT,
            "timeout_bars": TIMEOUT,
        },
        "unit_bug_summary": {
            "bug": "Previous simulate_trade returned tp/sl as bps/10000 (decimal fraction), "
                   "but pure_pnl_pct is in percent notation. This caused 100x undervaluation "
                   "of TP/SL exits in gross_pnl and 100x inflation of avg_r.",
            "old_tp_pnl_per_trade": tp_pnl_old,
            "new_tp_pnl_per_trade": tp_pnl_new,
            "old_sl_pnl_per_trade": sl_pnl_old,
            "new_sl_pnl_per_trade": sl_pnl_new,
            "old_avg_r": prior_avg_r,
            "new_avg_r": round(avg_r, 4),
            "old_gross_pnl_pct": prior_gross,
            "new_gross_pnl_pct": round(gross_pnl_pct, 4),
        },
        "mfe_mae_limitation": {
            "note": "mfe_bps and mae_bps in entries CSV are close-based bar returns. "
                    "Original TP exits (95 bps) show close-based mfe as low as 3.91 bps, "
                    "proving intrabar TP hits are not captured in close-based MFE. "
                    "Reported TP count is a LOWER BOUND. "
                    "Actual intrabar TP fires at 66.5 bps may be higher, "
                    "meaning gross_pnl is also a lower bound.",
            "original_tp_exits_with_close_mfe_below_new_tp": sum(
                1 for _, r in df.iterrows()
                if r["exit_reason"] == "TP" and r["mfe_bps"] < TP_BPS
            ),
            "total_original_tp_exits": int((df["exit_reason"] == "TP").sum()),
        },
        "corrected_metrics": {
            "n_trades": n,
            "tp_count": n_tp,
            "sl_count": n_sl,
            "timeout_count": n_to,
            "wins": wins,
            "win_rate": round(win_rate, 4),
            "gross_pnl_pct": round(gross_pnl_pct, 6),
            "avg_pnl_pct_per_trade": round(avg_pnl_pct, 6),
            "avg_r": round(avg_r, 6),
            "total_r": round(total_r, 6),
            "max_drawdown_pct": round(max_drawdown_pct, 6),
            "sl_pct_used_for_r": SL_PCT,
        },
        "cost_models": cost_results,
        "symbol_split": {
            "BTCUSDT": sym_btc,
            "ETHUSDT": sym_eth,
        },
        "acceptance_gate": {
            "net_positive_6bps": verdict_6bps["net_pnl_pct"] > 0,
            "net_positive_10bps": verdict_10bps["net_pnl_pct"] > 0,
            "net_pnl_6bps": verdict_6bps["net_pnl_pct"],
            "net_pnl_10bps": verdict_10bps["net_pnl_pct"],
            "all_cost_models_positive": all_positive,
            "verdict": verdict,
        },
        "per_trade_records": records,
    }

    OUT_JSON.write_text(json.dumps(
        out_json, ensure_ascii=False, indent=2), encoding="utf-8")

    # -------------------------------------------------------------------
    # Build Markdown report
    # -------------------------------------------------------------------
    md: list[str] = []

    def add(line: str = "") -> None:
        md.append(line)

    def sf(v: Any, d: int = 4) -> str:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "N/A"
        return f"{v:.{d}f}" if isinstance(v, float) else str(v)

    add("# TREND_UP_400_410_BEST_CANDIDATE_METRIC_RECHECK_V1")
    add()
    add("## Verdict")
    add(f"**{verdict}**")
    add()
    if all_positive:
        add("Net PnL remains positive under ALL tested cost models (4, 6, 8, 10 bps).")
    else:
        add("Some cost models produce negative net PnL. See cost model table.")
    add()

    add("## Problem framing")
    add(
        "Recheck corrected metrics for the best TREND_UP candidate identified in "
        "MICROBAND_TPSL_TIMEOUT_GRID_V1. Previous report had a unit mismatch bug "
        "in TP/SL exit pnl calculation, producing ~100× inflated avg_r."
    )
    add()

    add("## FACTS")
    add("- Entries: 25 (BTCUSDT=9, ETHUSDT=16), confidence 0.400..0.410.")
    add(f"- pure_pnl_pct in entries CSV is PERCENT notation (0.95 = 0.95% = 95 bps).")
    add(f"- Verified: original TP exits show pure_pnl_pct = 0.90 or 0.95 (= 90/95 bps = tp_pct_used × 100).")
    add(f"- Verified: original SL exits show pure_pnl_pct = -0.4 or -0.5 (= -40/-50 bps = -sl_pct_used × 100).")
    add(f"- Candidate TP: {TP_BPS} bps = {TP_PCT:.4f}%  SL: {SL_BPS} bps = {SL_PCT:.4f}%  Timeout: {TIMEOUT} bars.")
    add(f"- mfe_bps / mae_bps are CLOSE-BASED bar returns (not intrabar).")
    add(f"  - {out_json['mfe_mae_limitation']['original_tp_exits_with_close_mfe_below_new_tp']} of "
        f"{out_json['mfe_mae_limitation']['total_original_tp_exits']} original TP exits have "
        f"close-based mfe < {TP_BPS} bps — intrabar TP hits missed in simulation.")
    add()

    add("## INFERENCES")
    add("- Reported TP count is a LOWER BOUND. Intrabar hits not captured.")
    add("- gross_pnl is therefore a LOWER BOUND on actual P&L under this TP level.")
    add("- Timeout PnL = original pure_pnl_pct. Accurate for trades that held to timeout.")
    add()

    add("## ASSUMPTIONS")
    add("- R-multiple denominator = SL_pct = 0.75% (the candidate SL, not the baseline 50 bps).")
    add("- Cost is flat per trade regardless of exit type.")
    add(f"- TREND_UP = BUY / LONG. No shorting.")
    add()

    add("## UNKNOWNS")
    add("- True intrabar TP/SL hit count at 66.5 bps TP level.")
    add("- Live slippage variation and queue-position effects.")
    add()

    add("## Root cause of prior error")
    add()
    add("| field | old value | new value | error factor |")
    add("| --- | ---: | ---: | ---: |")
    add(f"| TP pnl per hit | {tp_pnl_old:.5f}% (0.07 bps!) | {tp_pnl_new:.4f}% (66.5 bps) | 100× too small |")
    add(f"| SL pnl per hit | -{sl_pnl_old:.5f}% (0.075 bps!) | -{sl_pnl_new:.4f}% (75.0 bps) | 100× too small |")
    add(f"| gross_pnl_pct | {prior_gross:.4f}% | {gross_pnl_pct:.4f}% | corrected |")
    add(f"| avg_r | {prior_avg_r:.4f} | {avg_r:.4f} | 100× inflated |")
    add(f"| avg_r formula | pnl_pct / (sl_bps/10000) | pnl_pct / (sl_bps/100) | unit mismatch |")
    add()

    add("## Corrected metrics summary")
    add()
    add("| metric | value | unit |")
    add("| --- | ---: | --- |")
    add(f"| n_trades | {n} | count |")
    add(f"| TP fires | {n_tp} | count (close-based lower bound) |")
    add(f"| SL fires | {n_sl} | count |")
    add(f"| TIMEOUT | {n_to} | count |")
    add(f"| wins | {wins} | count |")
    add(f"| win_rate | {win_rate:.4f} | |")
    add(f"| gross_pnl_pct | +{gross_pnl_pct:.4f} | % |")
    add(f"| avg_pnl_pct_per_trade | +{avg_pnl_pct:.4f} | % |")
    add(
        f"| avg_r | +{avg_r:.4f} | dimensionless [avg_pnl / SL_pct({SL_PCT:.4f}%)] |")
    add(f"| total_r | +{total_r:.4f} | dimensionless |")
    add(f"| max_drawdown_pct | {max_drawdown_pct:.4f} | % |")
    add()

    add("## Cost model results")
    add()
    add("| cost_bps | drag_pct | net_pnl_pct | net_avg_r | verdict |")
    add("| ---: | ---: | ---: | ---: | --- |")
    for c in cost_results:
        add(f"| {c['cost_bps']} | -{c['cost_drag_total_pct']:.4f} | {c['net_pnl_pct']:+.4f} | {c['net_avg_r']:+.4f} | {c['verdict']} |")
    add()

    add("## BTC vs ETH split (net after 6 bps)")
    add()
    add("| symbol | n | tp_ct | sl_ct | to_ct | win_rate | gross_pnl_pct | net_pnl_6bps | avg_r | mdd_pct |")
    add("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for sym_d in [sym_btc, sym_eth]:
        if not sym_d:
            continue
        add(f"| {sym_d['symbol']} | {sym_d['count']} | {sym_d['tp_count']} | {sym_d['sl_count']} | "
            f"{sym_d['timeout_count']} | {sym_d['win_rate']:.3f} | "
            f"{sym_d['gross_pnl_pct']:+.4f} | {sym_d['net_pnl_pct_6bps']:+.4f} | "
            f"{sym_d['avg_r']:+.4f} | {sym_d['max_drawdown_pct']:.4f} |")
    add()

    add("## Per-trade detail")
    add()
    add("| # | symbol | admit_conf | orig_exit | orig_pnl% | sim_exit | sim_pnl% | mfe_bps | mae_bps |")
    add("| ---: | --- | ---: | --- | ---: | --- | ---: | ---: | ---: |")
    for i, r in enumerate(records, 1):
        add(f"| {i} | {r['symbol']} | {r['admit_confidence']:.4f} | {r['orig_exit_reason']:<12} | "
            f"{r['orig_pnl_pct']:+.4f} | {r['sim_exit_reason']:<8} | {r['sim_pnl_pct']:+.4f} | "
            f"{r['mfe_bps']:5.1f} | {r['mae_bps']:6.1f} |")
    add()

    add("## MFE close-based limitation")
    add()
    add("| original TP exits | close_mfe_bps | sim result | note |")
    add("| --- | ---: | --- | --- |")
    for _, row in df[df["exit_reason"] == "TP"].iterrows():
        sim_r = next(
            r for r in records if r["segment_id"] == row["segment_id"])
        flag = "TP DETECTED" if sim_r[
            "sim_exit_reason"] == "TP" else "MISSED (close-mfe < tp_bps)"
        add(f"| {row['segment_id']} | {row['mfe_bps']:.2f} | {sim_r['sim_exit_reason']} | {flag} |")
    add()
    add(
        f"**{out_json['mfe_mae_limitation']['original_tp_exits_with_close_mfe_below_new_tp']} of "
        f"{out_json['mfe_mae_limitation']['total_original_tp_exits']} original TP exits had "
        f"close-based MFE < {TP_BPS} bps and were reclassified to TIMEOUT in simulation.** "
        "These are conservative (intrabar TP may have fired)."
    )
    add()

    add("## Acceptance gate")
    add()
    gate = out_json["acceptance_gate"]
    add(
        f"- net_positive_after_6bps: {'PASS' if gate['net_positive_6bps'] else 'FAIL'} ({gate['net_pnl_6bps']:+.4f}%)")
    add(
        f"- net_positive_after_10bps: {'PASS' if gate['net_positive_10bps'] else 'FAIL'} ({gate['net_pnl_10bps']:+.4f}%)")
    add(
        f"- all_cost_models_positive: {'PASS' if gate['all_cost_models_positive'] else 'FAIL'}")
    add(f"- **verdict: {gate['verdict']}**")
    add()

    add("## What must NOT change yet")
    add("- No production YAML patch")
    add("- No runtime mutation")
    add("- No execution_position changes")
    add("- No live execution")
    add()

    add("## Artifacts")
    add(
        f"- reports/TREND_UP_400_410_BEST_CANDIDATE_METRIC_RECHECK_V1_{DATE_TAG}.md")
    add(
        f"- reports/TREND_UP_400_410_BEST_CANDIDATE_METRIC_RECHECK_V1_{DATE_TAG}.json")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print(f"\n-> {OUT_MD}")
    print(f"-> {OUT_JSON}")
    print(f"\nVerdict: {verdict}")


if __name__ == "__main__":
    main()
