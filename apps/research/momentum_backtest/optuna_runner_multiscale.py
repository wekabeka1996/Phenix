"""
Optuna Runner for Multi-scale Feature Windows (RND-FEATURE-WINDOWS-V1)

Optimizes:
- Bar Horizon (1s, 5s, 10s)
- Feature Windows (TFI, Depth, EMA, Vol)
- Sniper Parameters (Weights, Gates, Risk)
"""

import optuna
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, ".")

from apps.research.momentum_backtest.backtest_engine_multiscale import BacktestEngineMultiscale
from apps.research.momentum_backtest.config import (
    get_processed_file_path,
    GOLDEN_DATASET_TEMPLATE,
    FEATURES_DATASET_TEMPLATE,
    DEFAULT_SYMBOL,
    DEFAULT_YEAR,
    DEFAULT_MONTH
)

# Global cache for datasets to avoid reloading
_datasets_cache = {}

def load_datasets():
    """Load all feature datasets and 1s Golden data into memory."""
    global _datasets_cache
    if _datasets_cache:
        return

    print("Loading datasets into memory...")
    
    # Load 1s Golden (for exits)
    golden_path = get_processed_file_path(GOLDEN_DATASET_TEMPLATE, DEFAULT_SYMBOL, DEFAULT_YEAR, DEFAULT_MONTH)
    print(f"  Loading {golden_path}...")
    df_golden = pd.read_csv(golden_path)
    df_golden['ts'] = pd.to_datetime(df_golden['ts'])
    df_golden.set_index('ts', inplace=True)
    df_golden.sort_index(inplace=True)
    _datasets_cache['golden'] = df_golden
    
    # Load Feature sets
    for h in [1, 5, 10]:
        feat_filename = FEATURES_DATASET_TEMPLATE.replace("features", f"features-h{h}")
        feat_path = get_processed_file_path(feat_filename, DEFAULT_SYMBOL, DEFAULT_YEAR, DEFAULT_MONTH)
        print(f"  Loading {feat_path}...")
        df_feat = pd.read_csv(feat_path)
        df_feat['ts'] = pd.to_datetime(df_feat['ts'])
        _datasets_cache[f'features_h{h}'] = df_feat
        
    print("Datasets loaded.")

def build_search_space(trial: optuna.Trial) -> dict:
    params = {}
    
    # --- Tier 2: Feature Windows ---
    params['bar_horizon_sec'] = trial.suggest_categorical("bar_horizon_sec", [1, 5, 10])
    
    params['tfi_window_sec'] = trial.suggest_categorical("tfi_window_sec", [20, 60, 120])
    params['depth_window_sec'] = trial.suggest_categorical("depth_window_sec", [5, 20, 60])
    params['ema_short_sec'] = trial.suggest_categorical("ema_short_sec", [60, 180])
    params['ema_long_sec'] = trial.suggest_categorical("ema_long_sec", [300, 900])
    params['vol_window_sec'] = trial.suggest_categorical("vol_window_sec", [60, 300])
    
    # --- Tier 1: Sniper Params (Local Search around V2 Best) ---
    # We use the best params from Sniper V2 as center, but allow some exploration
    # since changing windows might change optimal weights/gates.
    
    # Weights
    params["w_tfi"] = trial.suggest_float("w_tfi", 0.5, 1.0)
    params["w_tob"] = trial.suggest_float("w_tob", 0.1, 0.6)
    params["w_bs"] = trial.suggest_float("w_bs", 0.5, 1.0)
    params["w_bl"] = trial.suggest_float("w_bl", 0.5, 1.0)
    params["w_macro"] = trial.suggest_float("w_macro", 0.3, 0.8)
    params["w_delta_price"] = trial.suggest_float("w_delta_price", 0.7, 1.0)
    params["w_volume_spike"] = trial.suggest_float("w_volume_spike", 0.6, 1.0)
    params["w_volatility_state"] = trial.suggest_float("w_volatility_state", 0.7, 1.0)
    params["w_depth_imbalance"] = trial.suggest_float("w_depth_imbalance", 0.5, 1.0)
    
    params["threshold"] = trial.suggest_float("threshold", 0.1, 0.25)
    
    # Gates (Wide ranges to accommodate new windows)
    params["depth_imbalance_phi_min"] = trial.suggest_float("depth_imbalance_phi_min", 0.7, 0.95)
    params["tob_phi_min"] = trial.suggest_float("tob_phi_min", 0.4, 0.8)
    params["ema_bias_long_phi_min"] = trial.suggest_float("ema_bias_long_phi_min", 0.4, 0.7)
    params["vol_state_phi_min"] = trial.suggest_float("vol_state_phi_min", 0.05, 0.2)
    params["vol_state_phi_max"] = trial.suggest_float("vol_state_phi_max", 0.7, 1.0)
    
    # Risk
    params["sl_pct"] = trial.suggest_float("sl_pct", 0.003, 0.008)
    params["sl_tp_ratio"] = trial.suggest_float("sl_tp_ratio", 1.5, 3.0)
    params["max_holding_secs"] = trial.suggest_int("max_holding_secs", 200, 900)
    
    params["funding_threshold_long"] = trial.suggest_float("funding_threshold_long", 0.0003, 0.0010)
    
    # Fixed
    params["position_size"] = 200.0
    params["commission"] = 0.0005
    params["slippage"] = 0.0001
    params["spread_half"] = 0.0001
    
    return params

def prepare_features(df_raw: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Select specific window columns and rename to standard names.
    """
    df = df_raw.copy()
    
    # Map selected windows to columns
    # TFI
    w = params['tfi_window_sec']
    df['tfi_phi'] = df[f'tfi_phi_{w}s']
    
    # Depth / ToB
    w = params['depth_window_sec']
    df['depth_imbalance_phi'] = df[f'depth_imbalance_phi_{w}s']
    df['tob_phi'] = df[f'tob_phi_{w}s']
    
    # EMA
    w_s = params['ema_short_sec']
    w_l = params['ema_long_sec']
    df['ema_bias_short_phi'] = df[f'ema_bias_short_phi_{w_s}s']
    df['ema_bias_long_phi'] = df[f'ema_bias_long_phi_{w_l}s']
    
    # Vol
    w = params['vol_window_sec']
    df['volatility_state_phi'] = df[f'volatility_state_phi_{w}s']
    df['volume_spike_phi'] = df[f'volume_spike_phi_{w}s']
    
    # Others (fixed/default)
    # macro_phi, delta_price_phi are already there
    
    return df

def objective(trial: optuna.Trial) -> float:
    load_datasets()
    
    params = build_search_space(trial)
    
    # Get correct feature set
    h = params['bar_horizon_sec']
    df_feat_raw = _datasets_cache[f'features_h{h}']
    
    # Prepare features (column mapping)
    df_features = prepare_features(df_feat_raw, params)
    
    # Run Backtest
    # We use the FULL dataset (March 2024) for now, or Walk-Forward?
    # User said "Smoke-run Optuna (100-200 trials)".
    # Let's run on full dataset for simplicity/speed in smoke test, or split?
    # Walk-forward is better but slower.
    # Let's run on the LAST WEEK (like in previous smoke tests) to be comparable.
    # Or full month?
    # Let's use the same Walk-Forward logic as before (1 window: last week).
    
    # Filter for last week (approx)
    # March 22-29
    start_ts = pd.Timestamp("2024-03-22")
    end_ts = pd.Timestamp("2024-03-29")
    
    mask = (df_features['ts'] >= start_ts) & (df_features['ts'] < end_ts)
    df_test = df_features[mask].copy().reset_index(drop=True)
    
    if len(df_test) == 0:
        return 10000.0
    
    engine = BacktestEngineMultiscale(df_test, _datasets_cache['golden'], params)
    metrics = engine.run()
    
    total_trades = len(metrics['trades'])
    pnl = metrics['total_pnl_usd']
    calmar = metrics['calmar']
    max_dd = metrics['max_drawdown_pct']
    
    # Log
    trial.set_user_attr("total_trades", total_trades)
    trial.set_user_attr("pnl_usd", pnl)
    trial.set_user_attr("calmar", calmar)
    
    # Constraints
    # Adjust min trades based on horizon?
    # 1s: 180 trades.
    # 10s: maybe fewer opportunities? Or same?
    # Let's keep 150 as soft limit.
    MIN_TRADES = 150
    MAX_TRADES = 800
    
    if total_trades < MIN_TRADES:
        score = 1000.0 + (MIN_TRADES - total_trades)
        print(f"  Trial {trial.number} (h={h}s): {total_trades} trades (<{MIN_TRADES}) - PENALTY")
        return score
        
    if total_trades > MAX_TRADES:
        score = 1000.0 + (total_trades - MAX_TRADES)
        print(f"  Trial {trial.number} (h={h}s): {total_trades} trades (>{MAX_TRADES}) - PENALTY")
        return score
        
    # Score
    if calmar > 0:
        score = -calmar
    else:
        base_penalty = 10.0
        pnl_penalty = -pnl * 0.001
        dd_penalty = max_dd * 10.0
        score = base_penalty + pnl_penalty + dd_penalty
        
    print(f"  Trial {trial.number} (h={h}s): Trades={total_trades}, PnL={pnl:.2f}, Score={score:.3f}")
    
    return score

def run_optimization():
    print("="*80)
    print("OPTUNA MULTISCALE FEATURE WINDOWS")
    print("="*80)
    
    study_name = "multiscale_windows_v1"
    storage_name = f"sqlite:///{study_name}.db"
    
    study = optuna.create_study(
        study_name=study_name,
        storage=storage_name,
        direction="minimize",
        load_if_exists=True
    )
    
    print(f"Starting optimization (200 trials)...")
    try:
        study.optimize(objective, n_trials=200)
    except KeyboardInterrupt:
        print("Interrupted.")
        
    print("Best Params:")
    print(study.best_params)
    
    # Save best
    pd.DataFrame([study.best_params]).to_json("multiscale_best_params.json", orient="records", lines=True)

if __name__ == "__main__":
    run_optimization()
