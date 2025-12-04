import optuna
import pandas as pd
import sys

def analyze_results(db_url):
    print(f"Loading study from {db_url}...")
    study = optuna.load_study(study_name="bnb_momentum_wf_v1", storage=db_url)
    
    print(f"Total trials: {len(study.trials)}")
    print(f"Best score: {study.best_value:.4f}")
    
    print("\n" + "="*100)
    print("TOP 10 TRIALS (V3 EXTENDED - 9 WEIGHTS)")
    print("="*100)
    
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
            # Original 5 weights
            "w_tfi": params.get("w_tfi"),
            "w_tob": params.get("w_tob"),
            "w_bs": params.get("w_bs"),
            "w_bl": params.get("w_bl"),
            "w_macro": params.get("w_macro"),
            # Extended 4 weights
            "w_delta_price": params.get("w_delta_price"),
            "w_volume_spike": params.get("w_volume_spike"),
            "w_volatility_state": params.get("w_volatility_state"),
            "w_depth_imbalance": params.get("w_depth_imbalance"),
            "threshold": params.get("threshold")
        }
        data.append(row)
        
        print(f"\n#{i} Score: {t.value:.4f} (Trial {t.number})")
        print(f"   Metrics: Trades={row['Trades']}, PnL=${row['PnL']:.2f}, Calmar={row['Calmar']:.3f}, DD={row['MaxDD']:.3f}, WR={row['WinRate']:.1%}")
        print(f"   Original 5: TFI={row['w_tfi']:.2f}, ToB={row['w_tob']:.2f}, BS={row['w_bs']:.2f}, BL={row['w_bl']:.2f}, Macro={row['w_macro']:.2f}")
        print(f"   Extended 4: DeltaP={row['w_delta_price']:.2f}, VolSpike={row['w_volume_spike']:.2f}, VolState={row['w_volatility_state']:.2f}, DepthImb={row['w_depth_imbalance']:.2f}")
        print(f"   Threshold: {row['threshold']:.3f}")
        
    df = pd.DataFrame(data)
    
    # Calculate average weights for Top-10
    print("\n" + "="*100)
    print("AVERAGE WEIGHTS (TOP 10)")
    print("="*100)
    print(f"w_tfi:              {df['w_tfi'].mean():.3f} ± {df['w_tfi'].std():.3f}")
    print(f"w_tob:              {df['w_tob'].mean():.3f} ± {df['w_tob'].std():.3f}")
    print(f"w_bs:               {df['w_bs'].mean():.3f} ± {df['w_bs'].std():.3f}")
    print(f"w_bl:               {df['w_bl'].mean():.3f} ± {df['w_bl'].std():.3f}")
    print(f"w_macro:            {df['w_macro'].mean():.3f} ± {df['w_macro'].std():.3f}")
    print(f"w_delta_price:      {df['w_delta_price'].mean():.3f} ± {df['w_delta_price'].std():.3f}")
    print(f"w_volume_spike:     {df['w_volume_spike'].mean():.3f} ± {df['w_volume_spike'].std():.3f}")
    print(f"w_volatility_state: {df['w_volatility_state'].mean():.3f} ± {df['w_volatility_state'].std():.3f}")
    print(f"w_depth_imbalance:  {df['w_depth_imbalance'].mean():.3f} ± {df['w_depth_imbalance'].std():.3f}")
    print(f"threshold:          {df['threshold'].mean():.3f} ± {df['threshold'].std():.3f}")
    
    # Weight importance ranking
    print("\n" + "="*100)
    print("WEIGHT IMPORTANCE RANKING (by mean value)")
    print("="*100)
    weight_cols = ['w_tfi', 'w_tob', 'w_bs', 'w_bl', 'w_macro', 'w_delta_price', 'w_volume_spike', 'w_volatility_state', 'w_depth_imbalance']
    weight_means = df[weight_cols].mean().sort_values(ascending=False)
    for i, (name, value) in enumerate(weight_means.items(), 1):
        print(f"{i}. {name:20s}: {value:.3f}")
    
    return df

if __name__ == "__main__":
    db_url = "sqlite:///apps/research/momentum_backtest/data/optuna_v3_extended_400.db"
    df = analyze_results(db_url)
    
    # Save to CSV
    output_path = "apps/research/momentum_backtest/data/optuna_v3_top10.csv"
    df.to_csv(output_path, index=False)
    print(f"\n✅ Top-10 saved to {output_path}")
