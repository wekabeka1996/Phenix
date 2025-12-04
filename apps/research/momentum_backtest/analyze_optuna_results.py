import optuna
import pandas as pd
import sys

def analyze_results(db_url):
    print(f"Loading study from {db_url}...")
    study = optuna.load_study(study_name="bnb_momentum_wf_v1", storage=db_url)
    
    print(f"Total trials: {len(study.trials)}")
    print(f"Best score: {study.best_value:.4f}")
    
    print("\n" + "="*80)
    print("TOP 10 TRIALS")
    print("="*80)
    
    # Get all completed trials
    trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    
    # Sort by value (score) ascending
    trials.sort(key=lambda t: t.value)
    
    top_10 = trials[:10]
    
    data = []
    for i, t in enumerate(top_10, 1):
        params = t.params
        attrs = t.user_attrs
        
        row = {
            "Rank": i,
            "Score": t.value,
            "Trades": attrs.get("total_trades"),
            "PnL": attrs.get("pnl_usd"),
            "Calmar": attrs.get("calmar"),
            "MaxDD": attrs.get("max_dd_pct"),
            "WinRate": attrs.get("win_rate"),
            "w_tfi": params.get("w_tfi"),
            "w_macro": params.get("w_macro"),
            "threshold": params.get("threshold")
        }
        data.append(row)
        
        print(f"\n#{i} Score: {t.value:.4f}")
        print(f"   Metrics: Trades={row['Trades']}, PnL=${row['PnL']:.2f}, Calmar={row['Calmar']:.3f}, DD={row['MaxDD']:.3f}, WR={row['WinRate']:.1%}")
        print(f"   Params:  w_tfi={row['w_tfi']:.3f}, w_macro={row['w_macro']:.3f}, th={row['threshold']:.3f}")
        
    df = pd.DataFrame(data)
    return df

if __name__ == "__main__":
    db_url = "sqlite:///apps/research/momentum_backtest/data/optuna_v2_full.db"
    analyze_results(db_url)
