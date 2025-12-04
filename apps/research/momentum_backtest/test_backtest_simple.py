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
    
    print(f"Data shape: {df.shape}")
    print(f"Date range: {df['ts'].min()} to {df['ts'].max()}")
    print(f"\nFirst few rows:")
    print(df.head())
    
    print(f"\nFeature stats:")
    print(df[['tfi_1m', 'tob_imbalance', 'ema_bias_short', 'ema_bias_long']].describe())
    
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
    
    print(f"\nRunning backtest with params: {params}")
    engine = BacktestEngine(df, params)
    results = engine.run()
    
    print(f"\nResults:")
    print(f"Total trades: {len(results['trades'])}")
    print(f"Metrics: {results['metrics']}")
    
    if results['trades']:
        print(f"\nFirst 5 trades:")
        for i, trade in enumerate(results['trades'][:5]):
            print(f"{i+1}. {trade}")

if __name__ == "__main__":
    main()
