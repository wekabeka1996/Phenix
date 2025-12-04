"""
Aurora Phase 3 Analysis Script
==============================
Analyzes Phase 3 optimization results and compares them with Phase 2/DEEP baselines.
Generates a summary report.
"""
import json
import pandas as pd
from pathlib import Path
import glob

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def main():
    print("Analyzing Phase 3 Results...")
    
    # Find all Phase 3 result files
    phase3_files = glob.glob("best_aurora_*_phase3.json")
    
    results = []
    
    for p3_file in phase3_files:
        p3_data = load_json(p3_file)
        symbol = p3_data['symbol']
        timeframe = p3_data['timeframe']
        
        # Find baseline (DEEP or Phase 2)
        deep_file = f"best_aurora_{symbol}_{timeframe}_DEEP.json"
        phase2_file = f"best_aurora_{symbol}_{timeframe}_phase2.json"
        
        baseline_pnl = 0.0
        baseline_source = "Unknown"
        
        if Path(deep_file).exists():
            base_data = load_json(deep_file)
            baseline_pnl = base_data.get('metrics', {}).get('pnl', 0.0)
            baseline_source = "DEEP"
        elif Path(phase2_file).exists():
            base_data = load_json(phase2_file)
            baseline_pnl = base_data.get('metrics', {}).get('pnl', 0.0)
            baseline_source = "Phase 2"
            
        p3_pnl = p3_data['metrics']['pnl']
        improvement = ((p3_pnl - baseline_pnl) / baseline_pnl) * 100 if baseline_pnl != 0 else 0.0
        
        results.append({
            "Symbol": symbol,
            "Timeframe": timeframe,
            "Baseline Source": baseline_source,
            "Baseline PnL": baseline_pnl,
            "Phase 3 PnL": p3_pnl,
            "Improvement %": improvement,
            "Params": p3_data['params']
        })
    
    # Create DataFrame
    df = pd.DataFrame(results)
    if df.empty:
        print("No Phase 3 results found yet.")
        return

    print("\nSummary Table:")
    print(df[['Symbol', 'Baseline PnL', 'Phase 3 PnL', 'Improvement %']].to_markdown(index=False, floatfmt=".2f"))
    
    # Generate Markdown Report
    report = "# Aurora Phase 3: Full Spectrum Optimization Results\n\n"
    report += "## Performance Comparison\n\n"
    report += df[['Symbol', 'Baseline PnL', 'Phase 3 PnL', 'Improvement %']].to_markdown(index=False, floatfmt=".2f")
    report += "\n\n"
    
    report += "## Key Findings\n"
    for _, row in df.iterrows():
        report += f"### {row['Symbol']} ({row['Timeframe']})\n"
        report += f"- **Improvement**: {row['Improvement %']:.1f}%\n"
        report += "- **Key Parameters**:\n"
        
        params = row['Params']
        # Highlight key Phase 3 params
        report += f"  - Side Bias Penalty: {params.get('side_bias_penalty_factor', 0):.2f} (Window: {params.get('side_bias_window_sec', 0)}s)\n"
        report += f"  - High Vol Threshold: {params.get('regime_threshold_high_vol', 1.0):.2f}x\n"
        report += f"  - Low Vol Sizing: {params.get('sizing_low_vol', 1.0):.2f}x\n"
        report += f"  - EMA Clamp: ±{params.get('ema_clamp_max', 0.02):.3f}\n\n"
        
    with open("apps/research/new_alpha/RESULTS_PHASE3.md", "w") as f:
        f.write(report)
        
    print("\nReport saved to apps/research/new_alpha/RESULTS_PHASE3.md")

if __name__ == "__main__":
    main()
