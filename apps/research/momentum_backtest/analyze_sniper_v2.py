"""
Analyze Sniper V2 Optimization Results (Deep Local Search)

Extracts top trials from the sqlite database and generates a report.
"""

import optuna
import pandas as pd
import sys

def analyze_results():
    study_name = "sniper_bnb_2024_03_v2_local"
    storage_name = f"sqlite:///{study_name}.db"
    
    print(f"Loading study {study_name}...")
    try:
        study = optuna.load_study(study_name=study_name, storage=storage_name)
    except Exception as e:
        print(f"Error loading study: {e}")
        return
    
    print(f"Total trials: {len(study.trials)}")
    
    # Filter completed trials
    completed_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    print(f"Completed trials: {len(completed_trials)}")
    
    if not completed_trials:
        print("No completed trials found.")
        return
    
    # Sort by value (minimize)
    sorted_trials = sorted(completed_trials, key=lambda t: t.value)
    
    # Top 10
    print(f"\nTop 10 Trials:")
    print(f"{'Trial':<6} {'Value':<10} {'Trades':<8} {'PnL':<10} {'Params Summary'}")
    print("-" * 100)
    
    top_trials_data = []
    
    for t in sorted_trials[:10]:
        p = t.params
        trades = t.user_attrs.get('total_trades', 'N/A')
        pnl = t.user_attrs.get('pnl_usd', 0.0)
        
        params_str = (f"depth={p['depth_imbalance_phi_min']:.2f}, "
                      f"sl={p['sl_pct']*100:.2f}%, "
                      f"hold={p['max_holding_secs']}s")
        
        print(f"{t.number:<6} {t.value:<10.4f} {trades:<8} {pnl:<10.2f} {params_str}")
        
        row = p.copy()
        row['trial_id'] = t.number
        row['value'] = t.value
        row['trades'] = trades
        row['pnl'] = pnl
        top_trials_data.append(row)
    
    # Save top 10 to CSV
    df_top = pd.DataFrame(top_trials_data)
    df_top.to_csv("sniper_v2_top10.csv", index=False)
    print(f"\nSaved top 10 trials to sniper_v2_top10.csv")
    
    # Average params of Top 10
    print(f"\nAverage Parameters (Top 10):")
    avg_params = df_top.mean(numeric_only=True)
    
    print(f"  SL %: {avg_params['sl_pct']*100:.3f}%")
    print(f"  TP Ratio: {avg_params['sl_tp_ratio']:.2f}")
    print(f"  Depth Min: {avg_params['depth_imbalance_phi_min']:.3f}")
    print(f"  Max Hold: {avg_params['max_holding_secs']:.0f}s")
    
    # Best Trial Analysis
    best = study.best_trial
    print(f"\nBest Trial Analysis (#{best.number}):")
    print(f"  Value: {best.value:.4f}")
    print(f"  Trades: {best.user_attrs.get('total_trades', 'N/A')}")
    print(f"  PnL: ${best.user_attrs.get('pnl_usd', 'N/A'):.2f}")
    print(f"  Calmar: {best.user_attrs.get('calmar', 'N/A'):.3f}")
    print(f"  Win Rate: {best.user_attrs.get('win_rate', 'N/A'):.1%}")

if __name__ == "__main__":
    analyze_results()
