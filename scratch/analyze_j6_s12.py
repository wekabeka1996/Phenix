import json
import pandas as pd
from pathlib import Path
import numpy as np

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

def df_to_markdown(df):
    if df.empty:
        return ""
    cols = df.columns.tolist()
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = []
    for _, row in df.iterrows():
        rows.append("| " + " | ".join([f"{x:.4f}" if isinstance(x, float) else str(x) for x in row.values]) + " |")
    return "\n".join([header, sep] + rows)

def main():
    log_dir = Path("logs/judge_experts")
    out_dir = Path("reports/judge_shadow_sim")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Load context mappings
    envelopes = {}
    total_envelopes = 0
    envelopes_with_regime = 0
    envelopes_with_missing_reason = 0
    
    for f in log_dir.glob("envelope_*.jsonl"):
        with open(f, "r") as handle:
            for line in handle:
                try:
                    data = json.loads(line)
                    envelopes[data["cycle_key"]] = data
                    total_envelopes += 1
                    if data.get("regime") is not None:
                        envelopes_with_regime += 1
                    if data.get("regime_missing_reason") == "REGIME_CONTEXT_MISSING":
                        envelopes_with_missing_reason += 1
                except Exception:
                    pass
                    
    # Load simulation results
    res_file = log_dir / "shadow_simulation_results.jsonl"
    if not res_file.exists():
        print("No simulation results found!")
        return

    joined_rows = []
    counters = {
        "simulation_rows": 0,
        "joined_cycle_key": 0,
        "missing_envelope": 0,
        "null_regime": 0,
        "non_null_regime": 0
    }
    
    symbols_covered = set()
    tf_covered = set()
    regimes_present = set()
    
    with open(res_file, "r") as handle:
        for line in handle:
            counters["simulation_rows"] += 1
            res = json.loads(line)
            ck = res["cycle_key"]
            
            env = envelopes.get(ck)
            
            if env:
                counters["joined_cycle_key"] += 1
            else:
                counters["missing_envelope"] += 1
                
            regime = env.get("regime") if env else None
            if env and regime is None:
                counters["null_regime"] += 1
            elif regime is not None:
                counters["non_null_regime"] += 1
                regimes_present.add(regime)
                
            symbol = res.get("symbol")
            tf_sec = res.get("tf_sec", 0) if "tf_sec" in res else (int(ck.split(":")[2]) if len(ck.split(":"))>=3 else 0)
            symbols_covered.add(symbol)
            tf_covered.add(tf_sec)
            
            joined = {
                "cycle_key": ck,
                "symbol": symbol,
                "tf_sec": tf_sec,
                "ts_ms": res.get("ts_ms"),
                "tier": res.get("confidence_tier"),
                "side": res.get("entry_side"),
                "net_pnl_pct": res.get("net_pnl_pct"),
                "outcome": res.get("outcome"),
                "regime": regime,
            }
            joined_rows.append(joined)

    # 3. Save joined results
    with open(out_dir / "J6_S12_REGIME_STRATIFIED_RESULTS.jsonl", "w") as out:
        for row in joined_rows:
            out.write(json.dumps(row) + "\n")
            
    df = pd.DataFrame(joined_rows)
    df_act = df[df["outcome"].isin(["FILLED_TP", "FILLED_SL", "FILLED_TIMEOUT"])].copy()

    # Create the JSON summary
    summary_json = {
        "inventory": {
            "dates_covered": [str(d) for d in pd.to_datetime(df["ts_ms"], unit="ms").dt.date.unique()],
            "total_envelopes": total_envelopes,
            "envelopes_with_non_null_regime": envelopes_with_regime,
            "envelopes_with_missing_reason": envelopes_with_missing_reason,
            "simulation_rows_available": counters["simulation_rows"],
            "joined_rows": counters["joined_cycle_key"],
            "joined_rows_with_non_null_regime": counters["non_null_regime"],
            "symbols_covered": list(symbols_covered),
            "tf_sec_covered": list(tf_covered),
            "regimes_present": list(regimes_present)
        }
    }
    
    # Calculate Regime-stratified metrics
    def calculate_metrics(df_subset):
        if len(df_subset) == 0:
            return {}
        res = {
            "count": len(df_subset),
            "avg_net_pnl_pct": float(df_subset["net_pnl_pct"].mean()),
            "median_net_pnl_pct": float(df_subset["net_pnl_pct"].median()),
            "total_net_pnl_pct": float(df_subset["net_pnl_pct"].sum()),
            "fill_rate": float(len(df_subset) / len(df_subset) if len(df_subset) > 0 else 0), # assuming df_act is already filled
            "tp_rate": float((df_subset["outcome"] == "FILLED_TP").mean()),
            "sl_rate": float((df_subset["outcome"] == "FILLED_SL").mean()),
            "timeout_rate": float((df_subset["outcome"] == "FILLED_TIMEOUT").mean()),
        }
        if len(df_subset) > 30:
            ci = bootstrap_ci(df_subset["net_pnl_pct"].values)
            res["bootstrap_95ci"] = [float(ci[0]), float(ci[1])]
        return res
        
    regime_metrics = {}
    for regime in df_act["regime"].dropna().unique():
        df_r = df_act[df_act["regime"] == regime]
        regime_metrics[regime] = calculate_metrics(df_r)
        
        # High vs Medium split
        regime_metrics[regime]["tier_split"] = {
            "high": calculate_metrics(df_r[df_r["tier"] == "high"]),
            "medium": calculate_metrics(df_r[df_r["tier"] == "medium"])
        }
        
        # BUY vs SELL
        regime_metrics[regime]["side_split"] = {
            "BUY": calculate_metrics(df_r[df_r["side"] == "BUY"]),
            "SELL": calculate_metrics(df_r[df_r["side"] == "SELL"])
        }
        
        # Timeframe split
        regime_metrics[regime]["tf_split"] = {
            str(tf): calculate_metrics(df_r[df_r["tf_sec"] == tf]) for tf in [180, 300, 900]
        }
        
        # Symbol contribution
        regime_metrics[regime]["symbol_split"] = {
            sym: calculate_metrics(df_r[df_r["symbol"] == sym]) for sym in df_r["symbol"].unique()
        }
        
    summary_json["regime_metrics"] = regime_metrics
    
    # Candidate surface re-check
    policies = {
        "Medium+High all TF": df_act,
        "High-only all TF": df_act[df_act["tier"] == "high"],
        "300s High-only": df_act[(df_act["tier"] == "high") & (df_act["tf_sec"] == 300)],
        "ETH/PEPE High-only": df_act[(df_act["tier"] == "high") & (df_act["symbol"].isin(["1000PEPEUSDT", "ETHUSDT"]))],
        "BUY-only": df_act[df_act["side"] == "BUY"],
        "SELL-only": df_act[df_act["side"] == "SELL"],
        "excluding_DOGE_XRP": df_act[~df_act["symbol"].isin(["DOGEUSDT", "XRPUSDT"])]
    }
    
    candidate_surfaces = {}
    for policy_name, df_p in policies.items():
        candidate_surfaces[policy_name] = {"overall": calculate_metrics(df_p), "by_regime": {}}
        for regime in df_p["regime"].dropna().unique():
            candidate_surfaces[policy_name]["by_regime"][regime] = calculate_metrics(df_p[df_p["regime"] == regime])
            
    summary_json["candidate_surfaces"] = candidate_surfaces
    
    with open(out_dir / "J6_S12_REGIME_STRATIFIED_RESULTS.json", "w") as out:
        out.write(json.dumps(summary_json, indent=2))
        
    print("Metrics generated successfully.")

if __name__ == "__main__":
    main()
