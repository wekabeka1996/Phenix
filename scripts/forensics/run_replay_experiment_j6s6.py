import json
import pandas as pd
import numpy as np
from pathlib import Path
import argparse
import subprocess

LOG_DIR = Path("logs/judge_experts")
BASE_RESULTS = LOG_DIR / "shadow_simulation_results.jsonl"

def parse_tf(cycle_key):
    parts = cycle_key.split(":")
    if len(parts) >= 3:
        return int(parts[2])
    return 0

def bootstrap_ci(data, n_resamples=1000, ci=0.95):
    if len(data) == 0:
        return (0, 0)
    resampled_means = []
    for _ in range(n_resamples):
        resample = np.random.choice(data, size=len(data), replace=True)
        resampled_means.append(np.mean(resample))
    lower = np.percentile(resampled_means, (1 - ci) / 2 * 100)
    upper = np.percentile(resampled_means, (1 + ci) / 2 * 100)
    return lower, upper

def run_experiment():
    if not BASE_RESULTS.exists():
        print("Base results not found. Run J6-S4 first.")
        return

    # Load Baseline
    data = []
    with open(BASE_RESULTS, "r") as f:
        for line in f:
            data.append(json.loads(line))
    df = pd.DataFrame(data)
    df["tf_sec"] = df["cycle_key"].apply(parse_tf)
    df_actionable = df[df["outcome"].isin(["FILLED_TP", "FILLED_SL", "FILLED_TIMEOUT"])].copy()

    results = []

    # A: Baseline
    res_a = df_actionable["net_pnl_pct"]
    ci_a = bootstrap_ci(res_a.values)
    results.append({"Variant": "A: Baseline", "Count": len(res_a), "Avg PnL %": res_a.mean(), "CI Lower": ci_a[0], "CI Upper": ci_a[1]})

    # B: Low Suppressed
    res_b = df_actionable[df_actionable["confidence_tier"] != "low"]["net_pnl_pct"]
    ci_b = bootstrap_ci(res_b.values)
    results.append({"Variant": "B: Low Suppressed", "Count": len(res_b), "Avg PnL %": res_b.mean(), "CI Lower": ci_b[0], "CI Upper": ci_b[1]})

    # C: 300s-only Low Suppressed
    res_c = df_actionable[(df_actionable["tf_sec"] == 300) & (df_actionable["confidence_tier"] != "low")]["net_pnl_pct"]
    ci_c = bootstrap_ci(res_c.values)
    results.append({"Variant": "C: 300s-only Low Suppressed", "Count": len(res_c), "Avg PnL %": res_c.mean(), "CI Lower": ci_c[0], "CI Upper": ci_c[1]})

    # D: 300s High-only
    res_d = df_actionable[(df_actionable["tf_sec"] == 300) & (df_actionable["confidence_tier"] == "high")]["net_pnl_pct"]
    ci_d = bootstrap_ci(res_d.values)
    results.append({"Variant": "D: 300s High-only", "Count": len(res_d), "Avg PnL %": res_d.mean(), "CI Lower": ci_d[0], "CI Upper": ci_d[1]})

    # E: 300s High-only Horizon Sweep
    # We'll load the existing files if they exist, or skip if not run yet.
    horizons = [12, 18, 24, 36] # Already run in J6-S5
    for h in horizons:
        fname = f"shadow_sim_h{h}.jsonl" if h != 12 else "shadow_simulation_results.jsonl"
        h_file = LOG_DIR / fname
        if h_file.exists():
            h_data = []
            with open(h_file, "r") as f:
                for line in f:
                    h_data.append(json.loads(line))
            h_df = pd.DataFrame(h_data)
            h_df["tf_sec"] = h_df["cycle_key"].apply(parse_tf)
            res_e = h_df[(h_df["outcome"].isin(["FILLED_TP", "FILLED_SL", "FILLED_TIMEOUT"])) & 
                         (h_df["tf_sec"] == 300) & 
                         (h_df["confidence_tier"] == "high")]["net_pnl_pct"]
            ci_e = bootstrap_ci(res_e.values)
            results.append({"Variant": f"E: 300s High-only (H={h})", "Count": len(res_e), "Avg PnL %": res_e.mean(), "CI Lower": ci_e[0], "CI Upper": ci_e[1]})

    # F: Symbol-filtered High Tier
    best_syms = ["ETHUSDT", "1000PEPEUSDT", "BTCUSDT"]
    res_f = df_actionable[(df_actionable["confidence_tier"] == "high") & (df_actionable["symbol"].isin(best_syms))]["net_pnl_pct"]
    ci_f = bootstrap_ci(res_f.values)
    results.append({"Variant": "F: Symbol-filtered High Tier", "Count": len(res_f), "Avg PnL %": res_f.mean(), "CI Lower": ci_f[0], "CI Upper": ci_f[1]})

    report_df = pd.DataFrame(results)
    print("\n--- REPLAY EXPERIMENT RESULTS ---")
    print(report_df.to_string(index=False))

    # Concentration analysis for Baseline
    print("\n--- CONCENTRATION ANALYSIS (Baseline) ---")
    print("By Symbol:")
    print(df_actionable.groupby("symbol")["net_pnl_pct"].agg(["count", "mean", "sum"]).sort_values("sum", ascending=False))
    print("\nBy Timeframe:")
    print(df_actionable.groupby("tf_sec")["net_pnl_pct"].agg(["count", "mean", "sum"]))
    print("\nBy Side:")
    print(df_actionable.groupby("entry_side")["net_pnl_pct"].agg(["count", "mean", "sum"]))

if __name__ == "__main__":
    run_experiment()
