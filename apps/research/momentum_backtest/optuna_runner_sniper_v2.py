"""
Optuna Runner for Sniper Mode V2 (Deep Local Search)

Focuses on the neighborhood of the best trial (#194) from Depth Mode optimization.
Target: BNBUSDT March 2024
"""

import optuna
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, ".")

# Import base runner components
from apps.research.momentum_backtest.optuna_runner import objective as base_objective
from apps.research.momentum_backtest.optuna_runner import _df_features_global
import apps.research.momentum_backtest.optuna_runner as runner_module
from apps.research.momentum_backtest.walk_forward import run_walk_forward_for_params

# Best params from Trial #194
BEST_PARAMS = {
    'w_tfi': 0.7359,
    'w_tob': 0.2734,
    'w_bs': 0.7360,
    'w_bl': 0.8040,
    'w_macro': 0.4428,
    'w_delta_price': 0.9083,
    'w_volume_spike': 0.9057,
    'w_volatility_state': 0.8487,
    'w_depth_imbalance': 0.7653,
    'threshold': 0.1765,
    'depth_imbalance_phi_min': 0.8508,
    'tob_phi_min': 0.6274,
    'ema_bias_long_phi_min': 0.5245,
    'vol_state_phi_min': 0.0738,
    'vol_state_phi_max': 0.9017,
    'sl_pct': 0.006786,
    'sl_tp_ratio': 1.7061,
    'max_holding_secs': 403,
    'funding_threshold_long': 0.00072
}

def build_local_search_space(trial: optuna.Trial) -> dict:
    """
    Define NARROW parameter search space around BEST_PARAMS.
    """
    params = {}
    
    # Helper for local range
    def local_range(name, center, delta, low=0.0, high=1.0):
        return trial.suggest_float(name, max(low, center - delta), min(high, center + delta))
    
    # Feature weights (±0.15)
    params["w_tfi"] = local_range("w_tfi", BEST_PARAMS['w_tfi'], 0.15)
    params["w_tob"] = local_range("w_tob", BEST_PARAMS['w_tob'], 0.15)
    params["w_bs"] = local_range("w_bs", BEST_PARAMS['w_bs'], 0.15)
    params["w_bl"] = local_range("w_bl", BEST_PARAMS['w_bl'], 0.15)
    params["w_macro"] = local_range("w_macro", BEST_PARAMS['w_macro'], 0.15)
    params["w_delta_price"] = local_range("w_delta_price", BEST_PARAMS['w_delta_price'], 0.15)
    params["w_volume_spike"] = local_range("w_volume_spike", BEST_PARAMS['w_volume_spike'], 0.15)
    params["w_volatility_state"] = local_range("w_volatility_state", BEST_PARAMS['w_volatility_state'], 0.15)
    params["w_depth_imbalance"] = local_range("w_depth_imbalance", BEST_PARAMS['w_depth_imbalance'], 0.15)
    
    # Threshold (±0.05, min 0.05, max 0.3)
    params["threshold"] = local_range("threshold", BEST_PARAMS['threshold'], 0.05, 0.05, 0.3)
    
    # Entry Gates
    # Depth: [0.8, 0.95] (Best was 0.85)
    params["depth_imbalance_phi_min"] = trial.suggest_float("depth_imbalance_phi_min", 0.8, 0.95)
    
    # ToB: [0.5, 0.75] (Best was 0.63)
    params["tob_phi_min"] = trial.suggest_float("tob_phi_min", 0.5, 0.75)
    
    # EMA: [0.4, 0.65] (Best was 0.52)
    params["ema_bias_long_phi_min"] = trial.suggest_float("ema_bias_long_phi_min", 0.4, 0.65)
    
    # Volatility
    # Min: [0.0, 0.15] (Best was 0.07)
    params["vol_state_phi_min"] = trial.suggest_float("vol_state_phi_min", 0.0, 0.15)
    # Max: [0.8, 1.0] (Best was 0.90)
    params["vol_state_phi_max"] = trial.suggest_float("vol_state_phi_max", 0.8, 1.0)
    
    # Risk parameters
    # SL: [0.005, 0.010] (0.5% - 1.0%) - giving more room since it hit 0.7% cap
    params["sl_pct"] = trial.suggest_float("sl_pct", 0.005, 0.010)
    
    # TP Ratio: [1.2, 2.2] (Best was 1.7)
    params["sl_tp_ratio"] = trial.suggest_float("sl_tp_ratio", 1.2, 2.2)
    
    # Max Holding: [200, 600] (Best was 403)
    params["max_holding_secs"] = trial.suggest_int("max_holding_secs", 200, 600)
    
    # Funding veto (±0.0002)
    params["funding_threshold_long"] = local_range("funding_threshold_long", BEST_PARAMS['funding_threshold_long'], 0.0002, 0.0003, 0.0015)
    
    # Fixed parameters
    params["position_size"] = 200.0
    params["commission"] = 0.0005
    params["slippage"] = 0.0001
    params["spread_half"] = 0.0001
    
    return params

def objective_local(trial: optuna.Trial) -> float:
    """
    Objective function with strict trade count constraints (180-600).
    """
    global _df_features_global
    
    # Use the module-level global variable from runner_module
    # This is critical because run_optimization sets it there
    df_features = runner_module._df_features_global
    
    if df_features is None:
        raise ValueError("Must set _df_features_global before running optimization")
    
    # Build parameters
    params = build_local_search_space(trial)
    
    # Run Walk-Forward validation
    metrics = run_walk_forward_for_params(
        df_features,
        params,
        train_days=21,
        test_days=7,
        step_days=7
    )
    
    total_trades = metrics["total_trades"]
    calmar = metrics["calmar"]
    max_dd_pct = metrics["max_drawdown_pct"]
    pnl = metrics["total_pnl_usd"]
    
    # Log metrics
    trial.set_user_attr("total_trades", total_trades)
    trial.set_user_attr("calmar", calmar)
    trial.set_user_attr("max_dd_pct", max_dd_pct)
    trial.set_user_attr("pnl_usd", pnl)
    trial.set_user_attr("win_rate", metrics.get("win_rate", 0.0))
    
    # Constraints
    MIN_TRADES = 180
    MAX_TRADES = 600
    
    if total_trades < MIN_TRADES:
        # Penalty for too few trades
        score = 1000.0 + (MIN_TRADES - total_trades)
        print(f"  Trial {trial.number}: {total_trades} trades (<{MIN_TRADES}) - PENALTY Score={score:.1f}")
        return score
        
    if total_trades > MAX_TRADES:
        # Penalty for too many trades (spam)
        score = 1000.0 + (total_trades - MAX_TRADES)
        print(f"  Trial {trial.number}: {total_trades} trades (>{MAX_TRADES}) - PENALTY Score={score:.1f}")
        return score
    
    # Score Calculation
    if calmar > 0:
        score = -calmar
    else:
        # Base penalty + PnL penalty + DD penalty
        base_penalty = 10.0
        pnl_penalty = -pnl * 0.001 
        dd_penalty = max_dd_pct * 10.0
        score = base_penalty + pnl_penalty + dd_penalty
    
    print(f"  Trial {trial.number}: Trades={total_trades}, Calmar={calmar:.3f}, PnL={pnl:.2f}, Score={score:.3f}")
    
    return score

def run_optimization():
    print("="*80)
    print("OPTUNA SNIPER V2: DEEP LOCAL SEARCH")
    print("="*80)
    
    # Load features
    features_path = "apps/research/momentum_backtest/data/BNBUSDT-features-2024-03.csv"
    print(f"Loading features from {features_path}...")
    
    if not Path(features_path).exists():
        print(f"ERROR: Features file not found at {features_path}")
        return
    
    df = pd.read_csv(features_path)
    df['ts'] = pd.to_datetime(df['ts'])
    
    # Set global features in runner_module so objective_local can access it
    runner_module._df_features_global = df
    
    print(f"Loaded {len(df)} rows")
    
    # Create study
    study_name = "sniper_bnb_2024_03_v2_local"
    storage_name = f"sqlite:///{study_name}.db"
    
    study = optuna.create_study(
        study_name=study_name,
        storage=storage_name,
        direction="minimize",
        load_if_exists=True
    )
    
    print(f"Starting optimization (600 trials)...")
    
    try:
        study.optimize(objective_local, n_trials=600)
    except KeyboardInterrupt:
        print("\nOptimization interrupted by user.")
    
    print(f"\n{'='*80}")
    print("OPTIMIZATION COMPLETE")
    print(f"{'='*80}")
    
    print(f"Best Trial #{study.best_trial.number}")
    print(f"Value: {study.best_value:.4f}")
    print("Params:")
    for k, v in study.best_params.items():
        print(f"  {k}: {v}")
    
    # Save best params
    best_params_df = pd.DataFrame([study.best_params])
    best_params_df.to_json("sniper_v2_best_params.json", orient="records", lines=True)
    print(f"\nSaved best params to sniper_v2_best_params.json")

if __name__ == "__main__":
    run_optimization()
