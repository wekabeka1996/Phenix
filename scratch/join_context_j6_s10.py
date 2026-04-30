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
        rows.append("| " + " | ".join([str(x) for x in row.values]) + " |")
    return "\n".join([header, sep] + rows)

def main():
    log_dir = Path("reports/judge_shadow_sim/j6_s11_1_smoke")
    out_dir = Path("reports/judge_shadow_sim")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Load context mappings
    envelopes = {}
    for f in log_dir.glob("envelope_*.jsonl"):
        with open(f, "r") as handle:
            for line in handle:
                try:
                    data = json.loads(line)
                    envelopes[data["cycle_key"]] = data
                except Exception:
                    pass
                    
    verdicts = {}
    for f in log_dir.glob("verdict_*.jsonl"):
        with open(f, "r") as handle:
            for line in handle:
                try:
                    data = json.loads(line)
                    verdicts[data["cycle_key"]] = data
                except Exception:
                    pass

    # 2. Join results
    res_file = log_dir / "shadow_simulation_results.jsonl"
    if not res_file.exists():
        print("No simulation results found!")
        return

    joined_rows = []
    counters = {
        "processed": 0,
        "joined_cycle_key": 0,
        "missing_envelope": 0,
        "missing_verdict": 0,
        "missing_regime": 0,
        "null_regime": 0
    }
    
    with open(res_file, "r") as handle:
        for line in handle:
            counters["processed"] += 1
            res = json.loads(line)
            ck = res["cycle_key"]
            
            env = envelopes.get(ck)
            ver = verdicts.get(ck)
            
            if env or ver:
                counters["joined_cycle_key"] += 1
            if not env:
                counters["missing_envelope"] += 1
            if not ver:
                counters["missing_verdict"] += 1
                
            regime = env.get("regime") if env else None
            if env and "regime" not in env:
                counters["missing_regime"] += 1
            elif regime is None:
                counters["null_regime"] += 1
                
            joined = {
                "cycle_key": ck,
                "symbol": res.get("symbol"),
                "tf_sec": res.get("tf_sec", 0) if "tf_sec" in res else (int(ck.split(":")[2]) if len(ck.split(":"))>=3 else 0),
                "ts_ms": res.get("ts_ms"),
                "tier": res.get("confidence_tier"),
                "side": res.get("entry_side"),
                "net_pnl_pct": res.get("net_pnl_pct"),
                "outcome": res.get("outcome"),
                "final_entry_verdict": ver.get("entry_verdict") if ver else None,
                "regime": regime,
                "regime_confidence": env.get("regime_confidence") if env else None,
                "strategy_id": env.get("strategy_id") if env else None,
                "features_ref": env.get("features_ref") if env else None,
                "dissent_noted": ver.get("dissent_noted") if ver else None,
                "source_verdict_id": ver.get("verdict_id") if ver else None,
                "source_envelope_id": ver.get("envelope_id") if ver else None
            }
            joined_rows.append(joined)

    # 3. Save joined results
    with open(out_dir / "J6_S10_CONTEXT_JOINED_RESULTS.jsonl", "w") as out:
        for row in joined_rows:
            out.write(json.dumps(row) + "\n")
            
    with open(out_dir / "J6_S10_CONTEXT_JOIN_SUMMARY.json", "w") as out:
        out.write(json.dumps(counters, indent=2))
        
    df = pd.DataFrame(joined_rows)
    df["date"] = pd.to_datetime(df["ts_ms"], unit="ms").dt.date
    df_act = df[df["outcome"].isin(["FILLED_TP", "FILLED_SL", "FILLED_TIMEOUT"])].copy()

    # Create the Markdown report
    lines = []
    lines.append("# J6-S10 Context Join Report\n")
    lines.append("## 1. Join Statistics\n")
    lines.append(f"- **Simulation Rows Processed:** {counters['processed']}")
    lines.append(f"- **Successfully Joined by `cycle_key`:** {counters['joined_cycle_key']}")
    lines.append(f"- **Missing Envelope:** {counters['missing_envelope']}")
    lines.append(f"- **Missing Verdict:** {counters['missing_verdict']}")
    lines.append(f"- **Missing Regime Key:** {counters['missing_regime']}")
    lines.append(f"- **Null Regime Value:** {counters['null_regime']}\n")
    
    if len(joined_rows) > 0:
        lines.append("### Sample Joined Row:")
        lines.append("```json")
        lines.append(json.dumps(joined_rows[0], indent=2))
        lines.append("```\n")

    lines.append("## 2. Context Coverage\n")
    cov = df.groupby(["date", "symbol", "tf_sec"])["regime"].apply(lambda x: x.notnull().mean() * 100).reset_index()
    cov.rename(columns={"regime": "regime_coverage_pct"}, inplace=True)
    lines.append(df_to_markdown(cov))
    lines.append("\n")

    lines.append("## 3. Regime Breakdown (Actionable Only)\n")
    if "regime" in df_act.columns and df_act["regime"].notnull().any():
        grp = df_act.groupby("regime")
        metrics = grp["net_pnl_pct"].agg(["mean", "count"]).reset_index()
        lines.append("### By Regime")
        lines.append(df_to_markdown(metrics))
        lines.append("\n")
        
        lines.append("### High/Medium Split by Regime")
        hm_split = df_act.groupby(["regime", "tier"])["net_pnl_pct"].agg(["mean", "count"]).reset_index()
        lines.append(df_to_markdown(hm_split))
        lines.append("\n")
        
        lines.append("### BUY/SELL by Regime")
        bs_split = df_act.groupby(["regime", "side"])["net_pnl_pct"].agg(["mean", "count"]).reset_index()
        lines.append(df_to_markdown(bs_split))
        lines.append("\n")
        
        lines.append("### Timeframe (180/300/900) by Regime")
        tf_split = df_act.groupby(["regime", "tf_sec"])["net_pnl_pct"].agg(["mean", "count"]).reset_index()
        lines.append(df_to_markdown(tf_split))
        lines.append("\n")
    else:
        lines.append("*No valid regime labels available in context.*")
        
    lines.append("## 4. Regime Confidence Breakdown\n")
    if "regime_confidence" in df_act.columns and df_act["regime_confidence"].notnull().any():
        bins = [-np.inf, 0.35, 0.50, 0.70, np.inf]
        labels = ["<0.35", "0.35-0.50", "0.50-0.70", ">0.70"]
        df_act["conf_bucket"] = pd.cut(pd.to_numeric(df_act["regime_confidence"], errors="coerce"), bins=bins, labels=labels)
        df_act["conf_bucket"] = df_act["conf_bucket"].cat.add_categories(["missing"]).fillna("missing")
        conf_metrics = df_act.groupby("conf_bucket")["net_pnl_pct"].agg(["mean", "count"]).reset_index()
        lines.append(df_to_markdown(conf_metrics))
        lines.append("\n")
    else:
        lines.append("*No valid regime confidence labels available in context.*")
        
    lines.append("## 5. Dissent Noted Breakdown\n")
    if "dissent_noted" in df_act.columns:
        diss_metrics = df_act.groupby("dissent_noted")["net_pnl_pct"].agg(["mean", "count"]).reset_index()
        lines.append(df_to_markdown(diss_metrics))
        lines.append("\n")

    lines.append("## 6. Candidate Surface Re-check (Context Aware)\n")
    policies = [
        ("Medium+High all TF", df_act),
        ("High-only all TF", df_act[df_act["tier"] == "high"]),
        ("300s High-only", df_act[(df_act["tier"] == "high") & (df_act["tf_sec"] == 300)]),
        ("ETH/PEPE High-only", df_act[(df_act["tier"] == "high") & (df_act["symbol"].isin(["1000PEPEUSDT", "ETHUSDT"]))]),
        ("SELL-only", df_act[df_act["side"] == "SELL"]),
        ("BUY-only", df_act[df_act["side"] == "BUY"])
    ]
    
    p_results = []
    for name, df_p in policies:
        if len(df_p) > 0:
            avg = df_p["net_pnl_pct"].mean()
            ci = bootstrap_ci(df_p["net_pnl_pct"].values)
            p_results.append({"Policy": name, "Count": len(df_p), "Avg PnL %": avg, "CI Lower": ci[0], "CI Upper": ci[1]})
            
    if p_results:
        pdf = pd.DataFrame(p_results)
        lines.append(df_to_markdown(pdf))
        
    with open(out_dir / "J6_S10_CONTEXT_JOIN_REPORT.md", "w") as out:
        out.write("\n".join(lines))

if __name__ == "__main__":
    main()
