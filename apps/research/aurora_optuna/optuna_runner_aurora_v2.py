"""
Aurora Phase 2 Optuna Optimization
===================================
Strategy: Fix Phase 1 params, optimize Phase 2 (volatility, depth_imbalance, delta_price)
"""
import sys
import json
import argparse
from pathlib import Path
import optuna
import pandas as pd

sys.path.insert(0, ".")

from apps.research.aurora_optuna.backtest_engine_aurora import BacktestEngineAurora
from apps.research.aurora_optuna.features_aurora import build_aurora_features
from apps.research.aurora_optuna.config import get_data_path, FEATURES_DATASET_TEMPLATE_3M, FEATURES_DATASET_TEMPLATE_5M

# ============================================================================
# PHASE 1 FIXED PARAMETERS (From best_aurora_*.json)
# ============================================================================

FIXED_PARAMS_SOLUSDT_3M = {
    'ema_period_short': 7,
    'ema_period_long': 25,
    'volume_window_sec': 280,
    'volume_sma_length': 16,
    'volume_cap_max': 3.439,
    'liquidity_depth_half': 3000.0,
    'liquidity_kappa_min': 0.345,
    'obi_window_sec': 70,
    'tfi_window_sec': 160,
    'weight_ema': 0.467,
    'weight_volume': 0.242,
    'weight_macro': 0.138,  # Will re-optimize in Phase 2
    'weight_liquidity': 0.138,
    'weight_obi': 0.344,
    'weight_tfi': 0.363,
    'signal_threshold': 0.110,
    'max_risk_score': 0.784,
    'sl_pct': 0.526,
    'max_hold_sec': 660,
    'allowed_regimes': ['TREND_DOWN'],
}

FIXED_PARAMS_ETHUSDT_5M = {
    'ema_period_short': 5,
    'ema_period_long': 5,
    'volume_window_sec': 40,
    'volume_sma_length': 11,
    'volume_cap_max': 3.087,
    'liquidity_depth_half': 3750.0,
    'liquidity_kappa_min': 0.494,
    'obi_window_sec': 150,
    'tfi_window_sec': 80,
    'weight_ema': 0.174,
    'weight_volume': 0.236,
    'weight_macro': 0.382,  # Will re-optimize in Phase 2
    'weight_liquidity': 0.350,
    'weight_obi': 0.453,
    'weight_tfi': 0.471,
    'signal_threshold': 0.160,
    'max_risk_score': 0.567,
    'sl_pct': 1.591,
    'max_hold_sec': 720,
    'allowed_regimes': ['TREND_DOWN'],
}

FIXED_PARAMS_XRPUSDT_3M = {
    'ema_period_short': 12,
    'ema_period_long': 14,
    'volume_window_sec': 150,
    'volume_sma_length': 6,
    'volume_cap_max': 4.649,
    'liquidity_depth_half': 4750.0,
    'liquidity_kappa_min': 0.471,
    'obi_window_sec': 120,
    'tfi_window_sec': 240,
    'weight_ema': 0.427,
    'weight_volume': 0.385,
    'weight_macro': 0.411,  # Will re-optimize in Phase 2
    'weight_liquidity': 0.199,
    'weight_obi': 0.120,
    'weight_tfi': 0.402,
    'signal_threshold': 0.236,
    'max_risk_score': 0.831,
    'sl_pct': 1.671,
    'max_hold_sec': 660,
    'allowed_regimes': ['TREND_DOWN', 'LOW_VOLATILITY'],
}

FIXED_PARAMS_DOGEUSDT_3M = {
    'ema_period_short': 7,
    'ema_period_long': 6,
    'volume_window_sec': 180,
    'volume_sma_length': 4,
    'volume_cap_max': 3.370,
    'liquidity_depth_half': 3250.0,
    'liquidity_kappa_min': 0.239,
    'obi_window_sec': 50,
    'tfi_window_sec': 100,
    'weight_ema': 0.185,
    'weight_volume': 0.375,
    'weight_macro': 0.326,  # Will re-optimize in Phase 2
    'weight_liquidity': 0.242,
    'weight_obi': 0.146,
    'weight_tfi': 0.153,
    'signal_threshold': 0.172,
    'max_risk_score': 0.883,
    'sl_pct': 0.614,
    'max_hold_sec': 660,
    'allowed_regimes': ['LOW_VOLATILITY'],
}

FIXED_PARAMS_MAP = {
    'SOLUSDT': FIXED_PARAMS_SOLUSDT_3M,
    'ETHUSDT': FIXED_PARAMS_ETHUSDT_5M,
    'XRPUSDT': FIXED_PARAMS_XRPUSDT_3M,
    'DOGEUSDT': FIXED_PARAMS_DOGEUSDT_3M,
}

TIMEFRAME_MAP = {
    'SOLUSDT': '3m',
    'ETHUSDT': '5m',
    'XRPUSDT': '3m',
    'DOGEUSDT': '3m',
}

BAR_SECONDS_MAP = {
    'SOLUSDT': 180,
    'ETHUSDT': 300,
    'XRPUSDT': 180,
    'DOGEUSDT': 180,
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_data(symbol, year, month, timeframe):
    """Load pre-built feature data."""
    template = FEATURES_DATASET_TEMPLATE_3M if timeframe == '3m' else FEATURES_DATASET_TEMPLATE_5M
    feat_path = get_data_path(template, symbol, year, month)
    
    print(f"Loading data from {feat_path}...")
    df = pd.read_csv(feat_path)
    df['ts'] = pd.to_datetime(df['ts'])
    
    # Load BTC data for macro sync
    btc_df = None
    if symbol != "BTCUSDT":
        btc_path = get_data_path(template, "BTCUSDT", year, month)
        if btc_path.exists():
            btc_df = pd.read_csv(btc_path)
            btc_df['ts'] = pd.to_datetime(btc_df['ts'])
            
            col_name = 'close_1s'
            if timeframe == '3m':
                col_name = 'close_180s'
            elif timeframe == '5m':
                col_name = 'close_300s'
            
            if col_name in btc_df.columns:
                btc_df['btc_close_1s'] = btc_df[col_name]
    
    return df, btc_df

# ============================================================================
# PHASE 2 OBJECTIVE FUNCTION
# ============================================================================

def objective_phase2(trial, df_base, btc_df, fixed_params, bar_seconds):
    """
    Optimize Phase 2 features while keeping Phase 1 fixed.
    
    Phase 2 Features:
    - Volatility State (window, sma_length, cap_max, weight)
    - Depth Imbalance (smoothing, weight)
    - Delta Price (spike_filter, weight)
    - Macro Sync Window (re-optimize window + weight)
    """
    # Start with fixed Phase 1 params
    params = fixed_params.copy()
    
    # ===== PHASE 2 PARAMETERS (OPTIMIZE) =====
    
    # Volatility State
    params['volatility_window_sec'] = trial.suggest_int('volatility_window_sec', 30, 300, step=10)
    params['volatility_sma_length'] = trial.suggest_int('volatility_sma_length', 3, 20)
    params['volatility_cap_max'] = trial.suggest_float('volatility_cap_max', 2.0, 5.0)
    params['weight_volatility'] = trial.suggest_float('weight_volatility', 0.0, 0.4)
    
    # Depth Imbalance
    params['depth_imbalance_smoothing'] = trial.suggest_categorical('depth_imbalance_smoothing', [True, False])
    params['weight_depth_imbalance'] = trial.suggest_float('weight_depth_imbalance', 0.0, 0.4)
    
    # Delta Price
    params['delta_price_spike_filter_ms'] = trial.suggest_int('delta_price_spike_filter_ms', 1000, 10000, step=1000)
    params['weight_delta_price'] = trial.suggest_float('weight_delta_price', 0.0, 0.3)
    
    # Macro Sync Window (re-optimize!)
    params['macro_sync_window'] = trial.suggest_int('macro_sync_window', 20, 120, step=10)
    # Re-optimize macro weight (since window changed)
    params['weight_macro'] = trial.suggest_float('weight_macro', 0.05, 0.5)
    
    # Rebuild features with Phase 1 (fixed) + Phase 2 (optimized) params
    df_trial = build_aurora_features(df_base, btc_df, params, bar_seconds=bar_seconds)
    
    # Run backtest
    engine = BacktestEngineAurora(df_trial, params)
    metrics = engine.run()
    
    # Penalty for too few trades
    if metrics['trades'] < 30:
        return -10000.0
    
    return metrics['total_pnl']

# ============================================================================
# MAIN RUNNER
# ============================================================================

def run_phase2(symbol, year, month, n_trials=600):
    """Run Phase 2 optimization for a symbol."""
    # Get fixed params and timeframe
    if symbol not in FIXED_PARAMS_MAP:
        raise ValueError(f"No Phase 1 params found for {symbol}")
    
    fixed_params = FIXED_PARAMS_MAP[symbol]
    timeframe = TIMEFRAME_MAP[symbol]
    bar_seconds = BAR_SECONDS_MAP[symbol]
    
    print(f"\n{'='*80}")
    print(f"Phase 2 Optimization: {symbol} ({timeframe})")
    print(f"{'='*80}")
    print(f"Fixed Phase 1 Params: {len(fixed_params)} parameters locked")
    print(f"Optimizing Phase 2: volatility, depth_imbalance, delta_price, macro_window")
    print(f"Trials: {n_trials}")
    print(f"{'='*80}\n")
    
    # Load data
    df, btc_df = load_data(symbol, year, month, timeframe)
    
    # Create study
    study_name = f"aurora_phase2_{symbol}_{year}_{month}_{timeframe}"
    storage = f"sqlite:///aurora_phase2_{timeframe}.db"
    
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction="maximize",
        load_if_exists=True
    )
    
    # Run optimization
    study.optimize(
        lambda t: objective_phase2(t, df, btc_df, fixed_params, bar_seconds),
        n_trials=n_trials,
        show_progress_bar=True
    )
    
    print("\n" + "="*80)
    print("Best Params (Phase 2 Only):")
    print("="*80)
    for key, value in study.best_params.items():
        print(f"  {key}: {value}")
    
    print(f"\nBest Value: {study.best_value:.2f}")
    
    # Combine Phase 1 + Phase 2 and run final backtest
    final_params = fixed_params.copy()
    final_params.update(study.best_params)
    
    df_final = build_aurora_features(df, btc_df, final_params, bar_seconds=bar_seconds)
    engine = BacktestEngineAurora(df_final, final_params)
    metrics = engine.run()
    
    # Save results
    output_file = f"best_aurora_{symbol}_{timeframe}_phase2.json"
    with open(output_file, "w") as f:
        json.dump({
            'phase1_params': fixed_params,
            'phase2_params': study.best_params,
            'combined_params': final_params,
            'value': study.best_value,
            'metrics': metrics
        }, f, indent=2)
    
    print(f"\n{'='*80}")
    print("Final Metrics:")
    print(f"{'='*80}")
    print(f"  PnL: ${metrics['total_pnl']:.2f}")
    print(f"  Trades: {metrics['trades']}")
    print(f"  Win Rate: {metrics['win_rate']:.1%}")
    print(f"  Max DD: ${metrics['max_dd']:.2f}")
    print(f"  Calmar: {metrics['calmar']:.2f}")
    print(f"\nSaved: {output_file}")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aurora Phase 2 Optimization")
    parser.add_argument("--symbol", default="SOLUSDT", choices=["SOLUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT"])
    parser.add_argument("--year", default="2024")
    parser.add_argument("--month", default="01")
    parser.add_argument("--n-trials", type=int, default=600)
    args = parser.parse_args()
    
    run_phase2(args.symbol, args.year, args.month, args.n_trials)
