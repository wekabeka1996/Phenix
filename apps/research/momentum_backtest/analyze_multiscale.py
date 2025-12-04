"""
Analyze Multiscale Optimization Results

Groups results by bar_horizon_sec and finds best config.
"""

import optuna
import pandas as pd
import sys

def analyze_results():
    study_name = "multiscale_windows_v1"
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
        data.append(row)
        
    df = pd.DataFrame(data)
    
    # Group by Horizon
    print(f"\nResults by Horizon:")
    print(f"{'Horizon':<8} {'Count':<6} {'Best PnL':<10} {'Avg PnL':<10} {'Best Val':<10}")
    print("-" * 60)
    
    for h in [1, 5, 10]:
        df_h = df[df['bar_horizon_sec'] == h]
        if len(df_h) == 0:
            print(f"{h:<8} 0")
            continue
            
        best_pnl = df_h['pnl'].max()
        avg_pnl = df_h['pnl'].mean()
        best_val = df_h['value'].min()
        count = len(df_h)
        
        print(f"{h:<8} {count:<6} {best_pnl:<10.2f} {avg_pnl:<10.2f} {best_val:<10.4f}")
        
    # Top 10 Overall
    print(f"\nTop 10 Trials Overall:")
    df_top = df.sort_values('value').head(10)
    print(df_top[['bar_horizon_sec', 'value', 'trades', 'pnl', 'tfi_window_sec', 'depth_window_sec']].to_string(index=False))
    
    # Save
    df_top.to_csv("multiscale_top10.csv", index=False)
    print("\nSaved multiscale_top10.csv")
    
    # Best Trial
    best = study.best_trial
    print(f"\nBest Trial #{best.number}:")
    print(f"  Horizon: {best.params['bar_horizon_sec']}s")
    print(f"  Value: {best.value:.4f}")
    print(f"  PnL: ${best.user_attrs.get('pnl_usd', 0.0):.2f}")
    print(f"  Trades: {best.user_attrs.get('total_trades', 0)}")
    
    print("  Windows:")
    print(f"    TFI: {best.params['tfi_window_sec']}s")
    print(f"    Depth: {best.params['depth_window_sec']}s")
    print(f"    EMA: {best.params['ema_short_sec']}/{best.params['ema_long_sec']}s")
    print(f"    Vol: {best.params['vol_window_sec']}s")

if __name__ == "__main__":
    analyze_results()
