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
    
    print("--- A. Window inventory ---")
    dates = df_plans["date"].unique()
    print(f"Available dates: {dates}")
    print(f"Symbols covered: {df_plans['symbol'].unique()}")
    print(f"Timeframes covered: {df_plans['tf_sec'].unique()}")
    print("Plans per day:")
    print(df_plans.groupby("date").size())
    print("Actionable plans per day:")
    print(df_plans[df_plans["actionable"] == True].groupby("date").size())
    
    # 2. Results evaluation
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
    
    print("\n--- B. Day-split robustness ---")
    for date in df_act["date"].unique():
        d_df = df_act[df_act["date"] == date]
        print(f"\nDate: {date}")
        print(f"Avg PnL %: {d_df['net_pnl_pct'].mean():.4f}")
        print(f"Total PnL %: {d_df['net_pnl_pct'].sum():.4f}")
        print(f"Fill rate: {len(d_df)/len(df_res[df_res['date'] == date]):.4f}")
        print("Outcomes:")
        print(d_df["outcome"].value_counts(normalize=True))
        print("High vs Medium split:")
        print(d_df["confidence_tier"].value_counts())
        
    print("\n--- C. Symbol robustness ---")
    print("High tier performance by symbol:")
    print(df_act[df_act["confidence_tier"] == "high"].groupby("symbol")["net_pnl_pct"].agg(["mean", "sum", "count"]))
    print("Medium tier performance by symbol:")
    print(df_act[df_act["confidence_tier"] == "medium"].groupby("symbol")["net_pnl_pct"].agg(["mean", "sum", "count"]))
    print("Combined performance by symbol:")
    print(df_act.groupby("symbol")["net_pnl_pct"].agg(["mean", "sum", "count"]).sort_values("sum", ascending=False))
    
    print("\n--- D. Timeframe robustness ---")
    for tf in [180, 300, 900]:
        tf_df = df_act[df_act["tf_sec"] == tf]
        if len(tf_df) > 0:
            print(f"TF {tf}: avg pnl = {tf_df['net_pnl_pct'].mean():.4f}, count = {len(tf_df)}")
            
    print("\n--- E. Side robustness ---")
    print(df_act.groupby("entry_side")["net_pnl_pct"].agg(["mean", "sum", "count"]))
    
    print("\n--- F & G. Policy comparison & CI ---")
    policies = [
        ("Medium+High only", df_act),
        ("High only", df_act[df_act["confidence_tier"] == "high"]),
        ("300s High only", df_act[(df_act["confidence_tier"] == "high") & (df_act["tf_sec"] == 300)]),
        ("PEPE/ETH 300s High only", df_act[(df_act["confidence_tier"] == "high") & (df_act["tf_sec"] == 300) & (df_act["symbol"].isin(["1000PEPEUSDT", "ETHUSDT"]))]),
        ("Excluding DOGE/XRP", df_act[~df_act["symbol"].isin(["DOGEUSDT", "XRPUSDT"])])
    ]
    
    for name, df_p in policies:
        if len(df_p) > 0:
            avg = df_p["net_pnl_pct"].mean()
            ci = bootstrap_ci(df_p["net_pnl_pct"].values)
            print(f"{name}: count={len(df_p)}, avg={avg:.4f}, 95% CI=[{ci[0]:.4f}, {ci[1]:.4f}]")
        else:
            print(f"{name}: No data")

if __name__ == "__main__":
    main()
