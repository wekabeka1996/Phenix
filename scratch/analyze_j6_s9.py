import json
import pandas as pd
import numpy as np
from pathlib import Path

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

def main():
    log_dir = Path("logs/judge_experts")
    plan_files = list(log_dir.glob("shadow_entry_plan_*.jsonl"))
    
    # 1. Window inventory
    all_plans = []
    for pf in plan_files:
        with open(pf, "r") as f:
            for line in f:
                all_plans.append(json.loads(line))
                
    if not all_plans:
        print("No plans found.")
        return
        
    df_plans = pd.DataFrame(all_plans)
    df_plans["date"] = pd.to_datetime(df_plans["ts_ms"], unit="ms").dt.date
    
    print("--- A. Forward-walk inventory ---")
    dates = df_plans["date"].unique()
    dates.sort()
    print(f"Available dates: {dates}")
    print(f"Symbols covered: {df_plans['symbol'].unique()}")
    print(f"Timeframes covered: {df_plans['tf_sec'].unique()}")
    
    plans_per_day = df_plans.groupby("date").size()
    actionable_per_day = df_plans[df_plans["actionable"] == True].groupby("date").size()
    print("Plans per day:")
    print(plans_per_day)
    print("Actionable plans per day:")
    print(actionable_per_day)
    
    # 2. Daily replay results
    res_file = log_dir / "shadow_simulation_results.jsonl"
    if not res_file.exists():
        print("No simulation results found.")
        return
        
    res_data = []
    with open(res_file, "r") as f:
        for line in f:
            res_data.append(json.loads(line))
            
    df_res = pd.DataFrame(res_data)
    df_res["date"] = pd.to_datetime(df_res["ts_ms"], unit="ms").dt.date
    df_res["tf_sec"] = df_res["cycle_key"].apply(parse_tf)
    
    # Only actionable outcomes
    df_act = df_res[df_res["outcome"].isin(["FILLED_TP", "FILLED_SL", "FILLED_TIMEOUT"])].copy()
    
    print("\n--- B. Daily replay report ---")
    for date in sorted(df_act["date"].unique()):
        d_df = df_act[df_act["date"] == date]
        d_all = df_res[df_res["date"] == date]
        total = len(d_all)
        act = len(d_df)
        
        print(f"\nDate: {date}")
        print(f"Total actionable (simulated): {total}")
        print(f"Filled: {act}")
        print(f"Avg PnL %: {d_df['net_pnl_pct'].mean():.4f}")
        print(f"Median PnL %: {d_df['net_pnl_pct'].median():.4f}")
        print(f"Total PnL %: {d_df['net_pnl_pct'].sum():.4f}")
        print(f"Fill rate: {act/total:.4f}")
        
        # Outcomes
        print(d_df["outcome"].value_counts(normalize=True))
        
        print("High vs Medium:")
        print(d_df["confidence_tier"].value_counts())
        
        print("TF Breakdown:")
        print(d_df.groupby("tf_sec")["net_pnl_pct"].mean())
        
        print("Symbol Breakdown:")
        print(d_df.groupby("symbol")["net_pnl_pct"].mean())
        
        print("Side Breakdown:")
        print(d_df.groupby("entry_side")["net_pnl_pct"].mean())

    print("\n--- C. Rolling robustness view ---")
    rolling_df = df_act.groupby("date")["net_pnl_pct"].agg(["mean", "count"]).reset_index()
    rolling_df["cumulative_mean"] = df_act["net_pnl_pct"].expanding().mean().groupby(df_act["date"]).last().values
    
    print(rolling_df)
    
    if len(dates) >= 2:
        print(f"Overall Cumulative Avg PnL: {df_act['net_pnl_pct'].mean():.4f}")
        ci = bootstrap_ci(df_act["net_pnl_pct"].values)
        print(f"Cumulative 95% CI: [{ci[0]:.4f}, {ci[1]:.4f}]")
        
    print("\n--- D. Candidate-surface tracking ---")
    policies = [
        ("Medium+High all TF", df_act),
        ("High-only all TF", df_act[df_act["confidence_tier"] == "high"]),
        ("300s High-only", df_act[(df_act["confidence_tier"] == "high") & (df_act["tf_sec"] == 300)]),
        ("ETH/PEPE High-only", df_act[(df_act["confidence_tier"] == "high") & (df_act["symbol"].isin(["1000PEPEUSDT", "ETHUSDT"]))]),
        ("Excluding DOGE/XRP", df_act[~df_act["symbol"].isin(["DOGEUSDT", "XRPUSDT"])]),
        ("SELL-only", df_act[df_act["entry_side"] == "SELL"]),
        ("BUY-only", df_act[df_act["entry_side"] == "BUY"])
    ]
    
    for name, df_p in policies:
        if len(df_p) > 0:
            avg = df_p["net_pnl_pct"].mean()
            ci = bootstrap_ci(df_p["net_pnl_pct"].values)
            print(f"{name}: count={len(df_p)}, avg={avg:.4f}, 95% CI=[{ci[0]:.4f}, {ci[1]:.4f}]")
        else:
            print(f"{name}: No data")
            
    print("\n--- E. Market/regime context ---")
    print("Regime labels not consistently present in basic output. (Reported as missing)")

if __name__ == "__main__":
    main()
