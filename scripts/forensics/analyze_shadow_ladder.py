import json
import pandas as pd
from pathlib import Path
import re

import argparse

LOG_DIR = Path("logs/judge_experts")

def parse_tf(cycle_key):
    # ENTRY:SYMBOL:TF:TS
    parts = cycle_key.split(":")
    if len(parts) >= 3:
        return int(parts[2])
    return 0

def analyze(filename="shadow_simulation_results.jsonl"):
    results_file = LOG_DIR / filename
    if not results_file.exists():
        print(f"Results file {results_file} not found.")
        return

    data = []
    with open(results_file, "r") as f:
        for line in f:
            data.append(json.loads(line))

    df = pd.DataFrame(data)
    df["tf_sec"] = df["cycle_key"].apply(parse_tf)
    
    # Audit: Duplicates
    dupes = df["plan_id"].duplicated().sum()
    print(f"--- SANITY AUDIT ---")
    print(f"Total Rows: {len(df)}")
    print(f"Duplicate Plan IDs: {dupes}")
    
    # Audit: ERROR rows
    errors = df[df["outcome"] == "ERROR"]
    print(f"ERROR Rows: {len(errors)}")
    if len(errors) > 0:
        print(errors.groupby("outcome_reason").size())

    # Tier Breakdown
    print("\n--- TIER DIAGNOSTICS ---")
    tier_stats = df.groupby("confidence_tier").agg(
        trades=("net_pnl_pct", "count"),
        avg_net_pnl=("net_pnl_pct", "mean"),
        total_net_pnl=("net_pnl_pct", "sum"),
        tp_rate=("outcome", lambda x: (x == "FILLED_TP").mean()),
        sl_rate=("outcome", lambda x: (x == "FILLED_SL").mean()),
        timeout_rate=("outcome", lambda x: (x == "FILLED_TIMEOUT").mean()),
        no_fill_rate=("outcome", lambda x: (x == "NOT_FILLED_TIMEOUT").mean())
    )
    print(tier_stats)

    # Tier-specific Symbol Breakdown
    print("\n--- SYMBOL BY TIER DIAGNOSTICS ---")
    for tier in df["confidence_tier"].unique():
        print(f"\nTier: {tier}")
        tier_df = df[df["confidence_tier"] == tier]
        sym_stats = tier_df.groupby("symbol").agg(
            trades=("net_pnl_pct", "count"),
            avg_net_pnl=("net_pnl_pct", "mean"),
            tp_rate=("outcome", lambda x: (x == "FILLED_TP").mean()),
            sl_rate=("outcome", lambda x: (x == "FILLED_SL").mean())
        ).sort_values("avg_net_pnl", ascending=False)
        print(sym_stats)

    # Timeframe Breakdown
    print("\n--- TIMEFRAME DIAGNOSTICS ---")
    tf_stats = df.groupby(["tf_sec", "confidence_tier"]).agg(
        trades=("net_pnl_pct", "count"),
        avg_net_pnl=("net_pnl_pct", "mean")
    )
    print(tf_stats)

    # Side Breakdown
    print("\n--- SIDE DIAGNOSTICS ---")
    side_stats = df.groupby("entry_side").agg(
        trades=("net_pnl_pct", "count"),
        avg_net_pnl=("net_pnl_pct", "mean")
    )
    print(side_stats)

    # Fill Latency
    print("\n--- FILL LATENCY DIAGNOSTICS ---")
    # bars_to_fill = fill_bar_idx - signal_bar_idx
    # In our simulator, fill_bar_idx is absolute. signal_bar_idx is also available? 
    # Actually we didn't save signal_bar_idx in results.
    # But we have fill_ts_ms and ts_ms.
    # We can estimate bars_to_fill = (fill_ts_ms - ts_ms) / (tf_sec * 1000)
    
    df_filled = df[df["outcome"] != "NOT_FILLED_TIMEOUT"].copy()
    df_filled["bars_to_fill"] = (df_filled["fill_ts_ms"] - df_filled["ts_ms"]) / (df_filled["tf_sec"] * 1000)
    
    print("Avg Bars to Fill:", df_filled["bars_to_fill"].mean())
    print("Fill Latency Distribution:")
    print(df_filled["bars_to_fill"].value_counts(normalize=True).head(5))

    # Exit Latency
    print("\n--- EXIT LATENCY DIAGNOSTICS ---")
    # duration_bars is already in the results
    print("Avg Duration Bars (after fill):", df_filled["duration_bars"].mean())
    print("Outcome by Duration (Avg):")
    print(df_filled.groupby("outcome")["duration_bars"].mean())

    # TP/SL Distance
    print("\n--- TP/SL DISTANCE ANALYSIS ---")
    df["tp_dist_bps"] = abs(df["tp_price"] - df["limit_price"]) / df["limit_price"] * 10000
    df["sl_dist_bps"] = abs(df["sl_price"] - df["limit_price"]) / df["limit_price"] * 10000
    
    dist_stats = df.groupby("confidence_tier").agg(
        avg_tp_bps=("tp_dist_bps", "mean"),
        avg_sl_bps=("sl_dist_bps", "mean")
    )
    print(dist_stats)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, default="shadow_simulation_results.jsonl")
    args = parser.parse_args()
    analyze(args.file)
