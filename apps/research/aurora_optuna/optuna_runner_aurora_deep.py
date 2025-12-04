"""
Aurora DEEP Optimization (Phase 1 + Phase 2 Combined)
======================================================
Strategy: Optimize ALL parameters together with FINER steps
Trials: 15000 (Deep Search)
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
# DEEP OBJECTIVE FUNCTION (ALL PARAMS)
# ============================================================================

def objective_deep(trial, df_base, btc_df, bar_seconds):
    """
    Optimize ALL parameters with finer steps (15K trials).
    
    Phase 1 + Phase 2 combined:
    - EMA, Volume, Liquidity, OBI, TFI (Phase 1)
    - Volatility, Depth Imbalance, Delta Price (Phase 2)
    - All weights, thresholds, exit params
    """
    
    # ===== PHASE 1 PARAMETERS =====
    
    # EMA params
    ema_period_short = trial.suggest_int('ema_period_short', 2, 12)
    ema_period_long = trial.suggest_int('ema_period_long', 5, 25)
    
    # Volume params (FINER STEP: 5s instead of 10s)
    volume_window_sec = trial.suggest_int('volume_window_sec', 30, 300, step=5)
    volume_sma_length = trial.suggest_int('volume_sma_length', 3, 20)
    volume_cap_max = trial.suggest_float('volume_cap_max', 2.0, 5.0)
    
    # Liquidity params
    liquidity_depth_half = trial.suggest_float('liquidity_depth_half', 500, 5000, step=250)
    liquidity_kappa_min = trial.suggest_float('liquidity_kappa_min', 0.1, 0.5)
    
    # OBI / TFI params (FINER STEP: 5s instead of 10s)
    obi_window_sec = trial.suggest_int('obi_window_sec', 30, 300, step=5)
    tfi_window_sec = trial.suggest_int('tfi_window_sec', 30, 300, step=5)
    
    # Macro Sync Window
    macro_sync_window = trial.suggest_int('macro_sync_window', 20, 120, step=10)
    
    # ===== PHASE 2 PARAMETERS =====
    
    # Volatility State
    volatility_window_sec = trial.suggest_int('volatility_window_sec', 30, 300, step=5)
    volatility_sma_length = trial.suggest_int('volatility_sma_length', 3, 20)
    volatility_cap_max = trial.suggest_float('volatility_cap_max', 2.0, 5.0)
    
    # Depth Imbalance
    depth_imbalance_smoothing = trial.suggest_categorical('depth_imbalance_smoothing', [True, False])
    
    # Delta Price
    delta_price_spike_filter_ms = trial.suggest_int('delta_price_spike_filter_ms', 1000, 10000, step=1000)
    
    # ===== WEIGHTS (Phase 1 + Phase 2) =====
    
    weight_ema = trial.suggest_float('weight_ema', 0.05, 0.5)
    weight_volume = trial.suggest_float('weight_volume', 0.05, 0.4)
    weight_macro = trial.suggest_float('weight_macro', 0.05, 0.5)
    weight_liquidity = trial.suggest_float('weight_liquidity', 0.05, 0.4)
    weight_obi = trial.suggest_float('weight_obi', 0.05, 0.5)
    weight_tfi = trial.suggest_float('weight_tfi', 0.05, 0.5)
    
    # Phase 2 weights
    weight_volatility = trial.suggest_float('weight_volatility', 0.0, 0.4)
    weight_depth_imbalance = trial.suggest_float('weight_depth_imbalance', 0.0, 0.4)
    weight_delta_price = trial.suggest_float('weight_delta_price', 0.0, 0.3)
    
    # ===== DECISION & RISK PARAMS =====
    
    signal_threshold = trial.suggest_float('signal_threshold', 0.05, 0.30)
    max_risk_score = trial.suggest_float('max_risk_score', 0.5, 0.9)
    
    # Exit params (FINER STEP: 15s instead of 30s)
    sl_pct = trial.suggest_float('sl_pct', 0.005, 0.02)  # 0.5% - 2%
    max_hold_sec = trial.suggest_int('max_hold_sec', 60, 900, step=15)
    
    # ===== REGIME SELECTION =====
    
    use_trend_up = trial.suggest_categorical('use_trend_up', [True, False])
    use_trend_down = trial.suggest_categorical('use_trend_down', [True, False])
    use_mean_rev = trial.suggest_categorical('use_mean_rev', [True, False])
    use_low_vol = trial.suggest_categorical('use_low_vol', [True, False])
    use_high_vol = trial.suggest_categorical('use_high_vol', [False])  # Usually bad
    
    allowed_regimes = []
    if use_trend_up:
        allowed_regimes.append('TREND_UP')
    if use_trend_down:
        allowed_regimes.append('TREND_DOWN')
    if use_mean_rev:
        allowed_regimes.append('MEAN_REVERSION')
    if use_low_vol:
        allowed_regimes.append('LOW_VOLATILITY')
    if use_high_vol:
        allowed_regimes.append('HIGH_VOLATILITY')
    
    # Ensure at least one regime is selected
    if not allowed_regimes:
        allowed_regimes = ['LOW_VOLATILITY']
    
    # ===== BUILD PARAMS DICT =====
    
    params = {
        # Phase 1
        'ema_period_short': ema_period_short,
        'ema_period_long': ema_period_long,
        'volume_window_sec': volume_window_sec,
        'volume_sma_length': volume_sma_length,
        'volume_cap_max': volume_cap_max,
        'liquidity_depth_half': liquidity_depth_half,
        'liquidity_kappa_min': liquidity_kappa_min,
        'obi_window_sec': obi_window_sec,
        'tfi_window_sec': tfi_window_sec,
        'macro_sync_window': macro_sync_window,
        
        # Phase 2
        'volatility_window_sec': volatility_window_sec,
        'volatility_sma_length': volatility_sma_length,
        'volatility_cap_max': volatility_cap_max,
        'depth_imbalance_smoothing': depth_imbalance_smoothing,
        'delta_price_spike_filter_ms': delta_price_spike_filter_ms,
        
        # Weights
        'weight_ema': weight_ema,
        'weight_volume': weight_volume,
        'weight_macro': weight_macro,
        'weight_liquidity': weight_liquidity,
        'weight_obi': weight_obi,
        'weight_tfi': weight_tfi,
        'weight_volatility': weight_volatility,
        'weight_depth_imbalance': weight_depth_imbalance,
        'weight_delta_price': weight_delta_price,
        
        # Decision & Risk
        'signal_threshold': signal_threshold,
        'max_risk_score': max_risk_score,
        'sl_pct': sl_pct,
        'max_hold_sec': max_hold_sec,
        'allowed_regimes': allowed_regimes,
    }
    
    # ===== BUILD FEATURES & BACKTEST =====
    
    df_trial = build_aurora_features(df_base, btc_df, params, bar_seconds=bar_seconds)
    engine = BacktestEngineAurora(df_trial, params)
    metrics = engine.run()
    
    # Penalty for too few trades
    if metrics['trades'] < 30:
        return -10000.0
    
    return metrics['total_pnl']

# ============================================================================
# MAIN RUNNER
# ============================================================================

def run_deep_optimization(symbol, year, month, timeframe, n_trials=15000):
    """Run DEEP optimization (all params) for a symbol."""
    
    bar_seconds_map = {
        '3m': 180,
        '5m': 300,
    }
    bar_seconds = bar_seconds_map.get(timeframe, 180)
    
    print(f"\n{'='*80}")
    print(f"🚀 DEEP OPTIMIZATION: {symbol} ({timeframe})")
    print(f"{'='*80}")
    print(f"Mode: ALL PARAMETERS (Phase 1 + Phase 2)")
    print(f"Step Size: FINER (volume/obi/tfi: 5s, max_hold: 15s)")
    print(f"Trials: {n_trials} (Deep Search)")
    print(f"Expected Duration: ~8-12 hours")
    print(f"{'='*80}\n")
    
    # Load data
    df, btc_df = load_data(symbol, year, month, timeframe)
    
    # Create study
    study_name = f"aurora_deep_{symbol}_{year}_{month}_{timeframe}"
    storage = f"sqlite:///aurora_deep_{timeframe}.db"
    
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        direction="maximize",
        load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=42)  # Reproducible
    )
    
    # Run optimization
    study.optimize(
        lambda t: objective_deep(t, df, btc_df, bar_seconds),
        n_trials=n_trials,
        show_progress_bar=True
    )
    
    print("\n" + "="*80)
    print("🏆 BEST PARAMETERS FOUND:")
    print("="*80)
    for key, value in study.best_params.items():
        print(f"  {key}: {value}")
    
    print(f"\nBest Value: ${study.best_value:.2f}")
    
    # Run final backtest with best params
    best_params = study.best_params.copy()
    
    # Convert regime selections to allowed_regimes list
    allowed_regimes = []
    if best_params.get('use_trend_up'):
        allowed_regimes.append('TREND_UP')
    if best_params.get('use_trend_down'):
        allowed_regimes.append('TREND_DOWN')
    if best_params.get('use_mean_rev'):
        allowed_regimes.append('MEAN_REVERSION')
    if best_params.get('use_low_vol'):
        allowed_regimes.append('LOW_VOLATILITY')
    if best_params.get('use_high_vol'):
        allowed_regimes.append('HIGH_VOLATILITY')
    
    if not allowed_regimes:
        allowed_regimes = ['LOW_VOLATILITY']
    
    best_params['allowed_regimes'] = allowed_regimes
    
    df_final = build_aurora_features(df, btc_df, best_params, bar_seconds=bar_seconds)
    engine = BacktestEngineAurora(df_final, best_params)
    metrics = engine.run()
    
    # Save results
    output_file = f"best_aurora_{symbol}_{timeframe}_DEEP.json"
    with open(output_file, "w") as f:
        json.dump({
            'params': best_params,
            'value': study.best_value,
            'metrics': metrics,
            'trials': n_trials,
            'optimization_type': 'DEEP_15K'
        }, f, indent=2)
    
    print(f"\n{'='*80}")
    print("📊 FINAL METRICS:")
    print(f"{'='*80}")
    print(f"  PnL: ${metrics['total_pnl']:.2f}")
    print(f"  Trades: {metrics['trades']}")
    print(f"  Win Rate: {metrics['win_rate']:.1%}")
    print(f"  Max DD: ${metrics['max_dd']:.2f}")
    print(f"  Calmar: {metrics['calmar']:.2f}")
    print(f"\n💾 Saved: {output_file}")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aurora DEEP Optimization (15K trials)")
    parser.add_argument("--symbol", required=True, choices=["SOLUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT", "BTCUSDT"])
    parser.add_argument("--timeframe", required=True, choices=["3m", "5m"])
    parser.add_argument("--year", default="2024")
    parser.add_argument("--month", default="01")
    parser.add_argument("--n-trials", type=int, default=15000)
    args = parser.parse_args()
    
    run_deep_optimization(args.symbol, args.year, args.month, args.timeframe, args.n_trials)
