"""
TASK: RND-BACKTEST-LOG-FIRST-ENTRIES

Скрипт для запуску backtest з debug logging на реальних даних BNB.
Мета: Знайти причину нуль трейдів на real data після підтвердження що engine працює.
"""

import pandas as pd
from apps.research.momentum_backtest.config import (
    get_processed_file_path,
    FEATURES_DATASET_TEMPLATE,
    DEFAULT_SYMBOL,
    DEFAULT_YEAR,
    DEFAULT_MONTH
)
from apps.research.momentum_backtest.backtest_engine import BacktestEngine


def main():
    # Load real data
    path = get_processed_file_path(FEATURES_DATASET_TEMPLATE, DEFAULT_SYMBOL, DEFAULT_YEAR, DEFAULT_MONTH)
    print(f"Loading features from {path}...")
    df = pd.read_csv(path)
    
    # Convert ts to datetime
    df['ts'] = pd.to_datetime(df['ts'])
    
    # Take first 10,000 rows for analysis
    df_subset = df.head(10000).copy()
    
    print(f"\nData loaded:")
    print(f"  Shape: {df_subset.shape}")
    print(f"  Date range: {df_subset['ts'].min()} to {df_subset['ts'].max()}")
    
    # Check for NaN/inf in critical columns
    print(f"\nData quality check:")
    for col in ['tfi_1m', 'tob_imbalance', 'ema_bias_short', 'ema_bias_long', 'funding_rate_1s']:
        nan_count = df_subset[col].isna().sum()
        inf_count = np.isinf(df_subset[col]).sum() if np.issubdtype(df_subset[col].dtype, np.number) else 0
        print(f"  {col}: {nan_count} NaNs, {inf_count} Infs")
    
    # Aggressive params to maximize signal rate
    params = {
        'w_tfi': 1.0,
        'w_tob': 0.0,
        'w_bs': 0.0,
        'w_bl': 0.0,
        'threshold': 0.05,  # Low threshold
        'sl_pct': 0.004,
        'sl_tp_ratio': 2.0,
        'macro_corr_weight': 0.0,
        'funding_threshold_long': 1.0,  # Very high to not block
        'max_holding_secs': 300,
        'position_size': 200.0,
        'commission': 0.0005,
        'slippage': 0.0001,
        'spread_half': 0.0001
    }
    
    print(f"\nRunning backtest with params:")
    print(f"  threshold: {params['threshold']}")
    print(f"  funding_threshold_long: {params['funding_threshold_long']}")
    
    # Run with debug=True
    print(f"\n{'='*60}")
    print("DEBUG MODE: First signals")
    print('='*60)
    
    engine = BacktestEngine(df_subset, params)
    results = engine.run(debug=True, debug_limit=20)  # Log first 20 signals
    
    print(f"\n{'='*60}")
    print("RESULTS")
    print('='*60)
    print(f"Total trades: {len(results['trades'])}")
    print(f"Total PnL: {results['metrics']['total_pnl']:.2f}")
    print(f"Win rate: {results['metrics']['win_rate']:.2%}")
    
    if results['trades']:
        print(f"\nFirst 3 trades:")
        for i, trade in enumerate(results['trades'][:3]):
            print(f"\nTrade {i+1}:")
            print(f"  Entry: {trade.entry_time} @ ${trade.entry_price:.2f}")
            print(f"  Exit: {trade.exit_time} @ ${trade.exit_price:.2f}")
            print(f"  Reason: {trade.exit_reason}")
            print(f"  PnL: ${trade.pnl:.2f}")
    else:
        print("\n❌ STILL ZERO TRADES ON REAL DATA")
        print("\nPossible causes to investigate:")
        print("  1. All signals have funding_veto = True?")
        print("  2. NaN/Inf values blocking signal generation?")
        print("  3. Data type mismatch in signal_arr?")


if __name__ == "__main__":
    import numpy as np
    main()
