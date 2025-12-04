"""
Optuna Runner for Regime Filters (RND-REGIME-FILTERS-V1)

Optimizes which market regimes to allow for 5s Sniper strategy.
Uses best params from Multiscale V1 as baseline.
"""

import optuna
import pandas as pd
import numpy as np
import sys
import os
import json
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
from apps.research.momentum_backtest.regime_labeling import get_all_regimes

# Global cache
_datasets_cache = {}

def load_datasets(symbol, year, month):
    global _datasets_cache
    cache_key = f"{symbol}_{year}_{month}"
    if cache_key in _datasets_cache:
        return _datasets_cache[cache_key]

    print(f"Loading datasets for {symbol} {year}-{month}...")
    
    # Load 1s Golden (for exits)
    golden_path = get_processed_file_path(GOLDEN_DATASET_TEMPLATE, symbol, year, month)
    df_golden = pd.read_csv(golden_path)
    df_golden['ts'] = pd.to_datetime(df_golden['ts'])
    df_golden.set_index('ts', inplace=True)
    df_golden.sort_index(inplace=True)
    
    # Load 5s Features (best horizon from Multiscale V1)
    feat_filename = FEATURES_DATASET_TEMPLATE.replace("features", "features-h5")
    feat_path = get_processed_file_path(feat_filename, symbol, year, month)
    df_feat = pd.read_csv(feat_path)
    df_feat['ts'] = pd.to_datetime(df_feat['ts'])
    
    _datasets_cache[cache_key] = {
        'golden': df_golden,
        'features_h5': df_feat
    }
        
    print("Datasets loaded.")
    return _datasets_cache[cache_key]

def build_search_space(trial: optuna.Trial) -> dict:
    """
    Build parameter dict with regime binary flags.
    Uses best params from Multiscale #70 as baseline, but allows optimization.
    """
    params = {}
    
    # --- Fixed: Use 5s ---
    params['bar_horizon_sec'] = 5
    
    # --- Best Windows from Multiscale #70 ---
    # Allow slight variation or keep fixed?
    # For smoke test, keep windows fixed to isolate regime effect.
    params['tfi_window_sec'] = 20
    params['depth_window_sec'] = 20
    params['ema_short_sec'] = 60
    params['ema_long_sec'] = 300
    params['vol_window_sec'] = 300
    
    # --- Signal Weights: Allow optimization around Multiscale best ---
    # Multiscale #70 params (from logs):
    # w_tfi: 0.745, w_tob: 0.538, w_bs: 0.512, w_bl: 0.576, w_macro: 0.668,
    # w_delta_price: 0.703, w_volume_spike: 0.871, w_volatility_state: 0.844, w_depth_imbalance: 0.637
    
    # For speed, use narrower ranges (local search)
    params["w_tfi"] = trial.suggest_float("w_tfi", 0.6, 0.9)
    params["w_tob"] = trial.suggest_float("w_tob", 0.4, 0.7)
    params["w_bs"] = trial.suggest_float("w_bs", 0.4, 0.7)
    params["w_bl"] = trial.suggest_float("w_bl", 0.4, 0.7)
    params["w_macro"] = trial.suggest_float("w_macro", 0.5, 0.8)
    params["w_delta_price"] = trial.suggest_float("w_delta_price", 0.6, 0.9)
    params["w_volume_spike"] = trial.suggest_float("w_volume_spike", 0.7, 1.0)
    params["w_volatility_state"] = trial.suggest_float("w_volatility_state", 0.7, 1.0)
    params["w_depth_imbalance"] = trial.suggest_float("w_depth_imbalance", 0.5, 0.8)
    
    params["threshold"] = trial.suggest_float("threshold", 0.12, 0.20)
    
    # Gates (from Multiscale #70)
    params["depth_imbalance_phi_min"] = trial.suggest_float("depth_imbalance_phi_min", 0.60, 0.80)
    params["tob_phi_min"] = trial.suggest_float("tob_phi_min", 0.50, 0.75)
    params["ema_bias_long_phi_min"] = trial.suggest_float("ema_bias_long_phi_min", 0.45, 0.70)
    params["vol_state_phi_min"] = trial.suggest_float("vol_state_phi_min", 0.08, 0.18)
    params["vol_state_phi_max"] = trial.suggest_float("vol_state_phi_max", 0.80, 1.0)
    
    # Risk (from Multiscale #70)
    params["sl_pct"] = trial.suggest_float("sl_pct", 0.005, 0.010)
    params["sl_tp_ratio"] = trial.suggest_float("sl_tp_ratio", 2.0, 3.0)
    params["max_holding_secs"] = trial.suggest_int("max_holding_secs", 300, 600)
    
    params["funding_threshold_long"] = trial.suggest_float("funding_threshold_long", 0.0005, 0.0012)
    
    # Fixed
    params["position_size"] = 200.0
    params["commission"] = 0.0005
    params["slippage"] = 0.0001
    params["spread_half"] = 0.0001
    
    # --- Regime Binary Flags ---
    # Regimes
    regimes = [
        "UP_HIGH", "UP_NORMAL", "UP_LOW",
        "DOWN_HIGH", "DOWN_NORMAL", "DOWN_LOW",
        "FLAT_HIGH", "FLAT_NORMAL", "FLAT_LOW"
    ]
    
    TOXIC_REGIMES = {"DOWN_HIGH", "FLAT_HIGH"}
    
    regime_allowlist = []
    for r in regimes:
        if r in TOXIC_REGIMES:
            # Force toxic regimes to be disabled
            allowed = 0
            # We don't even suggest it to Optuna to save search space, or suggest fixed
            # trial.suggest_categorical(f'allow_{r}', [0]) 
            # But to keep params consistent in logs, let's just not add it to allowlist
            # and maybe not even ask Optuna for it?
            # Better to be explicit:
            trial.suggest_categorical(f'allow_{r}', [0])
        else:
            allowed = trial.suggest_categorical(f'allow_{r}', [0, 1])
            
        if allowed:
            regime_allowlist.append(r)
            
    # If regime_allowlist is empty, force at least one regime (avoid complete lockout)
    if not regime_allowlist:
        # Default to UP_NORMAL
        regime_allowlist = ["UP_NORMAL"]
    
    params['regime_allowlist'] = regime_allowlist
    
    return params

def prepare_features(df_raw: pd.DataFrame, params: dict) -> pd.DataFrame:
    df = df_raw.copy()
    
    # Map selected windows to columns
    w = params['tfi_window_sec']
    df['tfi_phi'] = df[f'tfi_phi_{w}s']
    
    w = params['depth_window_sec']
    df['depth_imbalance_phi'] = df[f'depth_imbalance_phi_{w}s']
    df['tob_phi'] = df[f'tob_phi_{w}s']
    
    w_s = params['ema_short_sec']
    w_l = params['ema_long_sec']
    df['ema_bias_short_phi'] = df[f'ema_bias_short_phi_{w_s}s']
    df['ema_bias_long_phi'] = df[f'ema_bias_long_phi_{w_l}s']
    
    w = params['vol_window_sec']
    df['volatility_state_phi'] = df[f'volatility_state_phi_{w}s']
    df['volume_spike_phi'] = df[f'volume_spike_phi_{w}s']
    
    return df

def objective(trial: optuna.Trial, symbol: str, year: str, month: str) -> float:
    datasets = load_datasets(symbol, year, month)
    
    params = build_search_space(trial)
    
    # Get 5s features
    df_feat_raw = datasets['features_h5']
    
    # Prepare features
    df_features = prepare_features(df_feat_raw, params)
    
    # Filter for last week of the month (dynamic based on year/month)
    # Calculate last day of month
    import calendar
    year_int = int(year)
    month_int = int(month)
    last_day = calendar.monthrange(year_int, month_int)[1]
    
    # Last 7 days
    end_ts = pd.Timestamp(f"{year}-{month}-{last_day}") + pd.Timedelta(days=1)  # Exclusive end
    start_ts = end_ts - pd.Timedelta(days=7)
    
    mask = (df_features['ts'] >= start_ts) & (df_features['ts'] < end_ts)
    df_test = df_features[mask].copy().reset_index(drop=True)
    
    if len(df_test) == 0:
        return 10000.0
    
    engine = BacktestEngineMultiscale(df_test, datasets['golden'], params)
    metrics = engine.run()
    
    total_trades = len(metrics['trades'])
    pnl = metrics['total_pnl_usd']
    calmar = metrics['calmar']
    max_dd = metrics['max_drawdown_pct']
    
    # Log
    trial.set_user_attr("total_trades", total_trades)
    trial.set_user_attr("pnl_usd", pnl)
    trial.set_user_attr("calmar", calmar)
    trial.set_user_attr("regime_allowlist", ",".join(params['regime_allowlist']))
    
    # Constraints
    MIN_TRADES_BASELINE = 100  # Strict baseline requirement
    MAX_TRADES = 1500
    
    if total_trades < MIN_TRADES_BASELINE:
        # Strict penalty for insufficient trades
        # Since we are MAXIMIZING PnL, penalty must be a large NEGATIVE number
        score = -10000.0 - (MIN_TRADES_BASELINE - total_trades)
        print(f"  Trial {trial.number}: {total_trades} trades (<{MIN_TRADES_BASELINE}), Regimes={len(params['regime_allowlist'])} - PENALTY")
        return score
        
    if total_trades > MAX_TRADES:
        score = -10000.0 - (total_trades - MAX_TRADES)
        print(f"  Trial {trial.number}: {total_trades} trades (>{MAX_TRADES}) - PENALTY")
        return score
        
    # Score
    if calmar > 0:
        score = -calmar
    else:
        base_penalty = 10.0
        pnl_penalty = -pnl * 0.001
        dd_penalty = max_dd * 10.0
        score = base_penalty + pnl_penalty + dd_penalty
        
    allowed = ",".join(params['regime_allowlist'][:3])  # Show first 3
    if len(params['regime_allowlist']) > 3:
        allowed += f"+{len(params['regime_allowlist'])-3}"
        
    print(f"  Trial {trial.number}: Trades={total_trades}, PnL={pnl:.2f}, Regimes=[{allowed}], Score={score:.3f}")
    
    return score

def run_optimization(symbol: str, year: str, month: str, n_trials: int = 150):
    print("="*80)
    print(f"OPTUNA REGIME FILTERS (5s Sniper) - {symbol} {year}-{month}")
    print("="*80)
    
    study_name = f"regime_filters_{symbol}_{year}_{month}"
    storage_name = f"sqlite:///{study_name}.db"
    
    # Load previous best params if available (from v1 or multiscale)
    # For now, we start fresh or continue existing study
    
    study = optuna.create_study(
        study_name=study_name,
        storage=storage_name,
        direction="maximize",
        load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=42)
    )
    
    print(f"Running optimization for {symbol} ({year}-{month})...")
    try:
        study.optimize(lambda t: objective(t, symbol, year, month), n_trials=n_trials)
    except KeyboardInterrupt:
        print("Interrupted.")
        
    print("\nBest Params:")
    print(study.best_params)
    print(f"\nBest Regime Allowlist: {study.best_trial.user_attrs.get('regime_allowlist', 'N/A')}")
    
    # Save best params
    output_file_params = f"regime_filters_best_params_{symbol}.json"
    pd.DataFrame([study.best_params]).to_json(output_file_params, orient="records", lines=True)
    
    # Save best metrics
    best_metrics = {
        "symbol": symbol,
        "year": year,
        "month": month,
        "best_value": study.best_value,
        "pnl_usd": study.best_trial.user_attrs.get('pnl_usd', 0.0),
        "total_trades": study.best_trial.user_attrs.get('total_trades', 0),
        "calmar": study.best_trial.user_attrs.get('calmar', 0.0),
        "regime_allowlist": study.best_trial.user_attrs.get('regime_allowlist', 'N/A'),
        "n_trials": len(study.trials)
    }
    output_file_metrics = f"regime_filters_best_metrics_{symbol}.json"
    with open(output_file_metrics, 'w') as f:
        json.dump(best_metrics, f, indent=2)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, default=DEFAULT_SYMBOL)
    parser.add_argument("--year", type=str, default=DEFAULT_YEAR)
    parser.add_argument("--month", type=str, default=DEFAULT_MONTH)
    parser.add_argument("--n-trials", type=int, default=150)
    args = parser.parse_args()
    
    run_optimization(symbol=args.symbol, year=args.year, month=args.month, n_trials=args.n_trials)
