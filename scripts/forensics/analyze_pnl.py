#!/usr/bin/env python3
import json
import pandas as pd
from pathlib import Path
from collections import defaultdict

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"

def analyze_pnl():
    file_path = LOGS_DIR / "order_log_v1.jsonl"
    if not file_path.exists():
        print("Error: order_log_v1.jsonl not found.")
        return
        
    trades = defaultdict(lambda: {
        "symbol": "UNKNOWN",
        "side": "UNKNOWN",
        "regime": "UNKNOWN",
        "realized_pnl": 0.0,
        "commission": 0.0,
        "fills": 0
    })
    
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            try:
                ev = json.loads(line)
                typ = ev.get("event_type")
                
                if typ == "ORDER_INTENT" or typ == "DECISION_INTENT_REJECTED" or typ == "ORDER_PLACED":
                    lid = ev.get("lifecycle_id") or ev.get("rid")
                    if lid:
                        if "symbol" in ev: trades[lid]["symbol"] = ev["symbol"]
                        if "side" in ev: trades[lid]["side"] = ev["side"]
                        if "regime" in ev: trades[lid]["regime"] = ev["regime"]
                        
                elif typ == "ORDER_FILLED":
                    lid = ev.get("lifecycle_id")
                    if not lid: continue
                    meta = ev.get("metadata", {})
                    pnl = meta.get("realized_pnl", 0.0)
                    comm = meta.get("commission", 0.0)
                    
                    trades[lid]["realized_pnl"] += pnl
                    trades[lid]["commission"] += comm
                    trades[lid]["fills"] += 1
                    
                    if trades[lid]["symbol"] == "UNKNOWN" and "symbol" in ev:
                        trades[lid]["symbol"] = ev["symbol"]
                        
            except Exception as e:
                pass
                
    # Keep only those with fills and non-zero pnl (or close events)
    results = []
    for lid, t in trades.items():
        if t["fills"] > 0 and t["realized_pnl"] != 0.0:
            results.append(t)
            
    if not results:
        print("No completed trades with PnL found in order_log_v1.jsonl.")
        return
        
    df = pd.DataFrame(results)
    
    df["net_pnl"] = df["realized_pnl"] - df["commission"]
    df["is_win"] = df["net_pnl"] > 0
    
    total_pnl = df["net_pnl"].sum()
    total_gross = df["realized_pnl"].sum()
    total_comm = df["commission"].sum()
    win_rate = df["is_win"].mean() * 100
    
    # Calculate exact chronological Drawdown
    df = df.sort_index()
    df['cum_pnl'] = df['net_pnl'].cumsum()
    df['peak'] = df['cum_pnl'].cummax()
    df['drawdown'] = df['cum_pnl'] - df['peak']
    max_dd = df['drawdown'].min()
    
    print("=== HIGH-LEVEL METRICS ===")
    print(f"Total Gross: ${total_gross:.4f}")
    print(f"Total Comm : ${total_comm:.4f}")
    print(f"Net PnL    : ${total_pnl:.4f}")
    print(f"Win Rate   : {win_rate:.1f}% ({df['is_win'].sum()} wins / {len(df)} total trades)")
    print(f"Max DD     : ${max_dd:.4f}")
    print("\n--- BY SYMBOL ---")
    sym_df = df.groupby("symbol").agg(
        Net_PnL=("net_pnl", "sum"),
        Win_Rate=("is_win", lambda x: x.mean() * 100),
        Trades=("fills", "count")
    ).sort_values("Net_PnL", ascending=False)
    print(sym_df.to_string())
    
    print("\n--- PERFORMANCE WITHOUT 'TREND_UP' ---")
    df_no_trend = df[df['regime'] != 'TREND_UP'].copy()
    if len(df_no_trend) > 0:
        total_pnl_n = df_no_trend['net_pnl'].sum()
        win_rate_n = df_no_trend['is_win'].mean() * 100
        df_no_trend = df_no_trend.sort_index()
        df_no_trend['cum_pnl'] = df_no_trend['net_pnl'].cumsum()
        df_no_trend['peak'] = df_no_trend['cum_pnl'].cummax()
        max_dd_n = (df_no_trend['cum_pnl'] - df_no_trend['peak']).min()
        print(f"Net PnL  : ${total_pnl_n:.4f}")
        print(f"Win Rate : {win_rate_n:.1f}% ({df_no_trend['is_win'].sum()} wins / {len(df_no_trend)} trades)")
        print(f"Max DD   : ${max_dd_n:.4f}")
    else:
        print("No trades left without TREND_UP")

    print("\n--- SYMBOLS IN LOW_VOLATILITY REGIME ---")
    df_low_vol = df[df['regime'] == 'LOW_VOLATILITY']
    if len(df_low_vol) > 0:
        low_vol_syms = df_low_vol.groupby("symbol").agg(
            Net_PnL=("net_pnl", "sum"),
            Trades=("fills", "count")
        )
        print(low_vol_syms.to_string())
    else:
        print("No trades occurred in LOW_VOLATILITY.")

if __name__ == "__main__":
    analyze_pnl()
