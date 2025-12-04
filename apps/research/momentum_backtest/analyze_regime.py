"""
Analyze Regime Filter Optimization Results
"""

import optuna
import pandas as pd
import sys

def analyze_results():
    study_name = "regime_filters_v1"
    storage_name = f"sqlite:///{study_name}.db"
    
    print(f"Loading study {study_name}...")
    try:
        study = optuna.load_study(study_name=study_name, storage=storage_name)
    except Exception as e:
        print(f"Error loading study: {e}")
        return
    
    print(f"Total trials: {len(study.trials)}")
    
    completed_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    print(f"Completed trials: {len(completed_trials)}")
    
    if not completed_trials:
        return

    # Convert to DataFrame
    data = []
    for t in completed_trials:
        row = t.params.copy()
        row['value'] = t.value
        row['trades'] = t.user_attrs.get('total_trades', 0)
        row['pnl'] = t.user_attrs.get('pnl_usd', 0.0)
        row['calmar'] = t.user_attrs.get('calmar', 0.0)
        row['regime_allowlist'] = t.user_attrs.get('regime_allowlist', "")
        
        # Count allowed regimes
        row['num_regimes'] = len(row['regime_allowlist'].split(',')) if row['regime_allowlist'] else 0
        
        data.append(row)
        
    df = pd.DataFrame(data)
    
    # Group by # of regimes
    print(f"\nResults by Regime Count:")
    print(f"{'# Regimes':<12} {'Count':<6} {'Best PnL':<10} {'Avg PnL':<10} {'Best Val':<10}")
    print("-" * 60)
    
    for n in sorted(df['num_regimes'].unique()):
        df_n = df[df['num_regimes'] == n]
        best_pnl = df_n['pnl'].max()
        avg_pnl = df_n['pnl'].mean()
        best_val = df_n['value'].min()
        count = len(df_n)
        
        print(f"{n:<12} {count:<6} {best_pnl:<10.2f} {avg_pnl:<10.2f} {best_val:<10.4f}")
        
    # Top 10 Overall
    print(f"\nTop 10 Trials Overall:")
    df_top = df.sort_values('value').head(10)
    print(df_top[['value', 'trades', 'pnl', 'num_regimes']].to_string(index=False))
    
    # Most common regimes in Top 10
    print(f"\nTop 10 Regime Analysis:")
    regime_flags = [col for col in df_top.columns if col.startswith('allow_')]
    regime_counts = {}
    for flag in regime_flags:
        regime_name = flag.replace('allow_', '')
        count = df_top[flag].sum()
        regime_counts[regime_name] = count
    
    print("Most Allowed Regimes (out of 10):")
    for regime, count in sorted(regime_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {regime:<15} {count}/10")
    
    # Save
    df_top.to_csv("regime_filters_top10.csv", index=False)
    print("\nSaved regime_filters_top10.csv")
    
    # Best Trial
    best = study.best_trial
    print(f"\nBest Trial #{best.number}:")
    print(f"  Value: {best.value:.4f}")
    print(f"  PnL: ${best.user_attrs.get('pnl_usd', 0.0):.2f}")
    print(f"  Trades: {best.user_attrs.get('total_trades', 0)}")
    print(f"  Regimes Allowed: {best.user_attrs.get('regime_allowlist', 'N/A')}")

if __name__ == "__main__":
    analyze_results()
