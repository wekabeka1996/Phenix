"""
Optuna Runner for Aurora (600 trials)
"""
import optuna
import pandas as pd
import sys
import argparse
import json

sys.path.insert(0, ".")

from apps.research.aurora_optuna.backtest_engine_aurora import BacktestEngineAurora
from apps.research.aurora_optuna.features_aurora import build_aurora_features
from apps.research.aurora_optuna.config import get_data_path, FEATURES_DATASET_TEMPLATE, FEATURES_DATASET_TEMPLATE_3M, FEATURES_DATASET_TEMPLATE_5M

def load_data(symbol, year, month, timeframe='1m'):
    template = FEATURES_DATASET_TEMPLATE
    if timeframe == '3m':
        template = FEATURES_DATASET_TEMPLATE_3M
    elif timeframe == '5m':
        template = FEATURES_DATASET_TEMPLATE_5M
        
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
            # Ensure column naming
            col_name = 'close_1s'
            if timeframe == '3m': col_name = 'close_180s'
            if timeframe == '5m': col_name = 'close_300s'
            
            if col_name in btc_df.columns:
                btc_df['btc_close_1s'] = btc_df[col_name]
    
    return df, btc_df

def objective(trial, df_features, btc_df, bar_seconds=60, mode='weighted_signal'):
    params = {}
    
    if mode == 'mean_reversion':
        # Mean Reversion Params
        bb_window = trial.suggest_categorical('bb_window', [20, 40, 60, 120])
        bb_std_dev = trial.suggest_float('bb_std_dev', 1.5, 3.0, step=0.1)
        min_vol_atr = trial.suggest_float('min_vol_atr', 0.001, 0.03, step=0.001)
        
        # Common Risk Params
        sl_pct = trial.suggest_float('sl_pct', 0.005, 0.05)
        max_hold_sec = trial.suggest_int('max_hold_sec', 60, 3600, step=60)
        
        # Execution Params (Phase 3+)
        tp_low_ratio = trial.suggest_float('tp_low_ratio', 0.3, 0.8)
        tp_high_ratio = trial.suggest_float('tp_high_ratio', 0.8, 2.0)
        partial_exit_pct = trial.suggest_float('partial_exit_pct', 0.3, 0.7)
        trailing_stop_activation_pct = trial.suggest_float('trailing_stop_activation_pct', 0.005, 0.03)
        trailing_stop_distance_pct = trial.suggest_float('trailing_stop_distance_pct', 0.002, 0.015)
        cooldown_sec = trial.suggest_int('cooldown_sec', 0, 300, step=30)
        
        # Regime Selection
        allowed_regimes = ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH'] # Default for mean reversion
        
        params = {
            'bb_window': bb_window,
            'bb_std_dev': bb_std_dev,
            'min_vol_atr': min_vol_atr,
            'sl_pct': sl_pct,
            'max_hold_sec': max_hold_sec,
            'tp_low_ratio': tp_low_ratio,
            'tp_high_ratio': tp_high_ratio,
            'partial_exit_pct': partial_exit_pct,
            'trailing_stop_activation_pct': trailing_stop_activation_pct,
            'trailing_stop_distance_pct': trailing_stop_distance_pct,
            'cooldown_sec': cooldown_sec,
            'allowed_regimes': allowed_regimes
        }
        
    else:
        # Weighted Signal Params (Original Aurora)
        # EMA params
        ema_period_short = trial.suggest_int('ema_period_short', 2, 12)
        ema_period_long = trial.suggest_int('ema_period_long', 5, 25)
        
        # Volume params (Finer steps: 10s)
        volume_window_sec = trial.suggest_int('volume_window_sec', 30, 300, step=10)
        volume_sma_length = trial.suggest_int('volume_sma_length', 3, 20)
        volume_cap_max = trial.suggest_float('volume_cap_max', 2.0, 5.0)
        
        # Liquidity params
        liquidity_depth_half = trial.suggest_float('liquidity_depth_half', 500, 5000, step=250)
        liquidity_kappa_min = trial.suggest_float('liquidity_kappa_min', 0.1, 0.5)
        
        # Decision params
        signal_threshold = trial.suggest_float('signal_threshold', 0.05, 0.30)
        max_risk_score = trial.suggest_float('max_risk_score', 0.5, 0.9)
        
        # REGIME SELECTION (Aurora integration!)
        # Optuna will decide which regimes to trade
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
        
        # OBI / TFI params (Finer steps: 10s)
        obi_window_sec = trial.suggest_int('obi_window_sec', 30, 300, step=10)
        tfi_window_sec = trial.suggest_int('tfi_window_sec', 30, 300, step=10)
        
        # Weights
        weight_ema = trial.suggest_float('weight_ema', 0.1, 0.5)
        weight_volume = trial.suggest_float('weight_volume', 0.1, 0.4)
        weight_macro = trial.suggest_float('weight_macro', 0.1, 0.5)
        weight_liquidity = trial.suggest_float('weight_liquidity', 0.1, 0.4)
        weight_obi = trial.suggest_float('weight_obi', 0.1, 0.5)
        weight_tfi = trial.suggest_float('weight_tfi', 0.1, 0.5)
        
        # Risk params (Finer steps: 30s)
        sl_pct = trial.suggest_float('sl_pct', 0.005, 0.02)
        max_hold_sec = trial.suggest_int('max_hold_sec', 60, 900, step=30)
        
        params = {
            'ema_period_short': ema_period_short,
            'ema_period_long': ema_period_long,
            'volume_window_sec': volume_window_sec,
            'volume_sma_length': volume_sma_length,
            'volume_cap_max': volume_cap_max,
            'liquidity_depth_half': liquidity_depth_half,
            'liquidity_kappa_min': liquidity_kappa_min,
            'obi_window_sec': obi_window_sec,
            'tfi_window_sec': tfi_window_sec,
            'signal_threshold': signal_threshold,
            'max_risk_score': max_risk_score,
            'weight_ema': weight_ema,
            'weight_volume': weight_volume,
            'weight_macro': weight_macro,
            'weight_liquidity': weight_liquidity,
            'weight_obi': weight_obi,
            'weight_tfi': weight_tfi,
            'sl_pct': sl_pct,
            'max_hold_sec': max_hold_sec,
            'allowed_regimes': allowed_regimes  # NEW: Regime filter
        }
    
    # Rebuild features with new params
    df_trial = build_aurora_features(df_features, btc_df, params, bar_seconds=bar_seconds)
    
    engine = BacktestEngineAurora(df_trial, params, strategy_mode=mode)
    metrics = engine.run()
    
    # Objective: Maximize PnL (or Sharpe/Calmar)
    # Let's use Total PnL for now, but maybe Calmar is better?
    # User wants "optimal parameters".
    
    # Penalty for too few trades
    if metrics['trades'] < 50:
        return -10000.0
        
    return metrics['total_pnl']

def run(symbol, year, month, n_trials=600, timeframe='1m', mode='weighted_signal'):
    df, btc_df = load_data(symbol, year, month, timeframe)
    
    bar_seconds = 60
    if timeframe == '3m':
        bar_seconds = 180
    elif timeframe == '5m':
        bar_seconds = 300
    
    study_name = f"aurora_{mode}_{symbol}_{year}_{month}_{timeframe}"
    storage = f"sqlite:///aurora_{mode}_{timeframe}.db"
    
    study = optuna.create_study(study_name=study_name, storage=storage, direction="maximize", load_if_exists=True)
    study.optimize(lambda t: objective(t, df, btc_df, bar_seconds, mode=mode), n_trials=n_trials)
    
    print("Best Params:", study.best_params)
    print("Best Value:", study.best_value)
    
    # Save results
    best_params = study.best_params
    
    # Rebuild features for best params to get metrics
    final_params = best_params.copy()
    
    if mode == 'weighted_signal':
        # Helper to reconstruct params for weighted signal
        allowed_regimes = []
        if best_params.get('use_trend_up'): allowed_regimes.append('TREND_UP')
        if best_params.get('use_trend_down'): allowed_regimes.append('TREND_DOWN')
        if best_params.get('use_mean_rev'): allowed_regimes.append('MEAN_REVERSION')
        if best_params.get('use_low_vol'): allowed_regimes.append('LOW_VOLATILITY')
        if best_params.get('use_high_vol'): allowed_regimes.append('HIGH_VOLATILITY')
        if not allowed_regimes: allowed_regimes = ['LOW_VOLATILITY']
        final_params['allowed_regimes'] = allowed_regimes
    else:
        # Mean Reversion defaults
        final_params['allowed_regimes'] = ['FLAT_LOW', 'FLAT_NORMAL', 'FLAT_HIGH']
    
    df_final = build_aurora_features(df, btc_df, final_params, bar_seconds=bar_seconds)
    engine = BacktestEngineAurora(df_final, final_params, strategy_mode=mode)
    metrics = engine.run()
    
    with open(f"best_aurora_{mode}_{symbol}_{timeframe}.json", "w") as f:
        json.dump({'params': final_params, 'value': study.best_value, 'metrics': metrics}, f, indent=2)
    
    print(f"Final PnL: {metrics['total_pnl']:.2f}, Trades: {metrics['trades']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--year", default="2024")
    parser.add_argument("--month", default="01")
    parser.add_argument("--n-trials", type=int, default=600)
    parser.add_argument("--timeframe", type=str, default="1m", choices=["1m", "3m", "5m"])
    parser.add_argument("--mode", type=str, default="weighted_signal", choices=["weighted_signal", "mean_reversion"])
    args = parser.parse_args()
    
    run(args.symbol, args.year, args.month, args.n_trials, args.timeframe, args.mode)
