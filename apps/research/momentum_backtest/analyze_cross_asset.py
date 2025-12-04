"""
Analyze Cross-Asset Baseline Results
"""

import optuna
import pandas as pd
import json
from pathlib import Path

TARGET_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
YEAR = "2024"
MONTH = "01"

def analyze():
    results = []
    
    for symbol in TARGET_SYMBOLS:
        study_name = f"regime_filters_{symbol}_{YEAR}_{MONTH}"
        storage_name = f"sqlite:///{study_name}.db"
        
        try:
            # Check if db exists
            if not Path(f"{study_name}.db").exists():
                print(f"Database {study_name}.db not found. Skipping.")
                results.append({
                    'Symbol': symbol,
                    'PnL ($)': 'Pending',
                    'Trades': 'Pending',
                    'Calmar': 'Pending',
                    'Best Value': 'Pending',
                    'Regimes': 'Pending'
                })
                continue
                
            study = optuna.load_study(study_name=study_name, storage=storage_name)
            
            if len(study.trials) == 0:
                print(f"Study {study_name} has no trials.")
                continue
                
            best = study.best_trial
            
            # Check for penalty
            if best.value < -5000:
                pnl = "Invalid (<100 trades)"
                trades = "N/A"
                calmar = "N/A"
                regimes = "N/A"
            else:
                # Get metrics from user_attrs
                pnl = f"{best.user_attrs.get('pnl_usd', 0.0):.2f}"
                trades = best.user_attrs.get('total_trades', 0)
                calmar = f"{best.user_attrs.get('calmar', 0.0):.4f}"
                regimes = best.user_attrs.get('regime_allowlist', 'N/A')
            
            results.append({
                'Symbol': symbol,
                'PnL ($)': pnl,
                'Trades': trades,
                'Calmar': calmar,
                'Best Value': f"{best.value:.4f}",
                'Regimes': regimes
            })
            
        except Exception as e:
            print(f"Could not load study for {symbol}: {e}")
            results.append({
                'Symbol': symbol,
                'PnL ($)': 'Error',
                'Trades': 'Error',
                'Calmar': 'Error',
                'Best Value': 'Error',
                'Regimes': str(e)
            })
            
    df = pd.DataFrame(results)
    print("\nCROSS-ASSET BASELINE RESULTS:")
    print(df.to_string(index=False))
    
    # Save to CSV
    df.to_csv("cross_asset_results.csv", index=False)
    print("\nSaved cross_asset_results.csv")
    
    # Generate Markdown Report
    generate_markdown_report(df)

def generate_markdown_report(df):
    """Generate cross_asset_baseline.md report"""
    
    report_path = "apps/research/momentum_backtest/reports/cross_asset_baseline.md"
    
    # Ensure reports dir exists
    Path("apps/research/momentum_backtest/reports").mkdir(parents=True, exist_ok=True)
    
    with open(report_path, 'w') as f:
        f.write("# Cross-Asset Baseline Report\n\n")
        f.write("**Date**: 2025-12-02\n")
        f.write("**Period**: Jan 2024\n")
        f.write("**Strategy**: 5s Sniper + Regime Filters\n\n")
        
        f.write("---\n\n")
        
        f.write("## Summary\n\n")
        f.write("Extended 5s Sniper + Regime pipeline to 5 major crypto assets.\n")
        f.write("Used Jan 2024 data for baseline performance comparison.\n\n")
        
        f.write("## Results Table\n\n")
        # Manual markdown table generation to avoid tabulate dependency
        headers = df.columns.tolist()
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
        
        for _, row in df.iterrows():
            row_str = [str(x) for x in row.values]
            f.write("| " + " | ".join(row_str) + " |\n")
        f.write("\n\n")
        
        f.write("## Per-Symbol Analysis\n\n")
        
        for _, row in df.iterrows():
            symbol = row['Symbol']
            pnl = row['PnL ($)']
            trades = row['Trades']
            regimes = row['Regimes']
            
            f.write(f"### {symbol}\n\n")
            
            if pnl == 'Pending' or pnl == 'Error':
                f.write(f"**Status**: {pnl}\n\n")
                continue
                
            try:
                pnl_val = float(pnl)
                f.write(f"- **PnL**: ${pnl}\n")
                f.write(f"- **Trades**: {trades}\n")
                f.write(f"- **Allowed Regimes**: {regimes}\n")
                
                if pnl_val > 0:
                    f.write(f"- **Assessment**: ✅ **POSITIVE ALPHA** - Strategy profitable on this asset.\n")
                elif pnl_val > -50:
                    f.write(f"- **Assessment**: ⚠️ Near breakeven. Minor edge possible with refinement.\n")
                else:
                    f.write(f"- **Assessment**: ❌ Significant losses. No simple momentum alpha on this timeframe.\n")
                    
                f.write("\n")
            except:
                f.write(f"- **Status**: Error parsing results\n\n")
        
        f.write("---\n\n")
        f.write("## Conclusions\n\n")
        f.write("TBD after results analysis.\n")
    
    print(f"\nGenerated {report_path}")

if __name__ == "__main__":
    analyze()
