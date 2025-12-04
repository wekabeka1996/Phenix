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
    # Load Data
    path = get_processed_file_path(FEATURES_DATASET_TEMPLATE, DEFAULT_SYMBOL, DEFAULT_YEAR, DEFAULT_MONTH)
    print(f"Loading features from {path}...")
    df = pd.read_csv(path)
    
    # Convert ts to datetime
    df['ts'] = pd.to_datetime(df['ts'])
    
    # Take only first 1000 rows for debugging
    df = df.head(1000).copy()
    
    print(f"Data shape: {df.shape}")
    print(f"Date range: {df['ts'].min()} to {df['ts'].max()}")
    
    # Simple backtest with aggressive params
    params = {
        'w_tfi': 1.0,
        'w_tob': 0.0,
        'w_bs': 0.0,
        'w_bl': 0.0,
        'threshold': 0.0,  # Very low threshold to generate signals
        'sl_pct': 0.01,
        'sl_tp_ratio': 2.0,
        'macro_corr_weight': 0.0,
        'funding_threshold_long': 1.0,  # Very high to not veto
        'max_holding_secs': 300,
        'position_size': 200.0,
        'commission': 0.0005,
        'slippage': 0.0001,
        'spread_half': 0.0001
    }
    
    # Check signals manually
    score_raw = params['w_tfi'] * df['tfi_1m']
    signals = (score_raw > params['threshold']).astype(int)
    
    print(f"\nManual signal check:")
    print(f"Total signals: {signals.sum()}")
    print(f"First 10 signals: {signals.head(10).tolist()}")
    
    print(f"\nRunning backtest...")
    engine = BacktestEngine(df, params)
    results = engine.run()
    
    print(f"\nResults:")
    print(f"Total trades: {len(results['trades'])}")
    
    if results['trades']:
        print(f"\nFirst 5 trades:")
        for i, trade in enumerate(results['trades'][:5]):
            print(f"{i+1}. {trade}")
    else:
        print("\nNo trades! Debugging...")
        # Check if signals are present in the engine
        print(f"Checking engine internals...")

if __name__ == "__main__":
    main()
