"""
Analyze Depth Mode Optimization Results

Extracts top trials from the sqlite database and generates a report.
"""

import optuna
import pandas as pd
import sys

def analyze_results():
    study_name = "depth_mode_entry_exit_v1"
    storage_name = f"sqlite:///{study_name}.db"
    
    print(f"Loading study {study_name}...")
    study = optuna.load_study(study_name=study_name, storage=storage_name)
    
    print(f"Total trials: {len(study.trials)}")
    
    # Filter completed trials
    completed_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    print(f"Completed trials: {len(completed_trials)}")
    
    # Sort by value (minimize)
    sorted_trials = sorted(completed_trials, key=lambda t: t.value)
    
    # Top 10
    print(f"\nTop 10 Trials:")
    print(f"{'Trial':<6} {'Value':<10} {'Params Summary'}")
    print("-" * 80)
    
    top_trials_data = []
    
    for t in sorted_trials[:10]:
        p = t.params
        params_str = (f"depth_min={p['depth_imbalance_phi_min']:.2f}, "
                      f"sl={p['sl_pct']*100:.2f}%, "
                      f"hold={p['max_holding_secs']}s")
        print(f"{t.number:<6} {t.value:<10.4f} {params_str}")
        
        row = p.copy()
        row['trial_id'] = t.number
        row['value'] = t.value
        top_trials_data.append(row)
    
    # Save top 10 to CSV
    df_top = pd.DataFrame(top_trials_data)
    df_top.to_csv("depth_mode_top10.csv", index=False)
    print(f"\nSaved top 10 trials to depth_mode_top10.csv")
    
    # Analyze best parameters
    best = study.best_trial
    print(f"\nBest Trial Analysis (#{best.number}):")
    print(f"  Value: {best.value:.4f}")
    
    print("\n  Entry Gates:")
    print(f"    Depth Min: {best.params['depth_imbalance_phi_min']:.3f}")
    print(f"    ToB Min: {best.params['tob_phi_min']:.3f}")
    print(f"    EMA Min: {best.params['ema_bias_long_phi_min']:.3f}")
    print(f"    Vol Range: {best.params['vol_state_phi_min']:.3f} - {best.params['vol_state_phi_max']:.3f}")
    
    print("\n  Exit Params:")
    print(f"    SL: {best.params['sl_pct']*100:.3f}%")
    print(f"    TP Ratio: {best.params['sl_tp_ratio']:.2f} (TP ~ {best.params['sl_pct']*best.params['sl_tp_ratio']*100:.3f}%)")
    print(f"    Max Hold: {best.params['max_holding_secs']}s")
    
    # Parameter Importance
    try:
        importance = optuna.importance.get_param_importance(study)
        print(f"\nParameter Importance:")
        for k, v in list(importance.items())[:5]:
            print(f"  {k}: {v:.3f}")
    except Exception as e:
        print(f"Could not calculate importance: {e}")

if __name__ == "__main__":
    analyze_results()
