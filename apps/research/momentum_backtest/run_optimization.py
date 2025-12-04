import pandas as pd
from apps.research.momentum_backtest.config import (
    get_processed_file_path,
    FEATURES_DATASET_TEMPLATE,
    DEFAULT_SYMBOL,
    DEFAULT_YEAR,
    DEFAULT_MONTH
)
from apps.research.momentum_backtest.walk_forward import run_walk_forward, aggregate_results

def main():
    # Load Data
    path = get_processed_file_path(FEATURES_DATASET_TEMPLATE, DEFAULT_SYMBOL, DEFAULT_YEAR, DEFAULT_MONTH)
    print(f"Loading features from {path}...")
    df = pd.read_csv(path)
    
    # Convert ts to datetime
    df['ts'] = pd.to_datetime(df['ts'])
    
    # Run Walk-Forward
    # We have limited data (1M rows = ~11.5 days).
    # Train 4 weeks is too long.
    # Let's use Train 1 week, Test 2 days, Step 2 days for this test.
    # 1M rows = 1,000,000 seconds = 277 hours = 11.5 days.
    
    print("Running Walk-Forward (Train=1w, Test=2d)...")
    results = run_walk_forward(df, train_weeks=1, test_weeks=0.3, step_weeks=0.3, n_trials=10) # 0.3 weeks ~ 2 days
    
    # Aggregate
    all_trades = aggregate_results(results)
    
    print(f"Total OOS Trades: {len(all_trades)}")
    
    # Save results?
    # Maybe print summary of first window
    if results:
        print("First Window Results:")
        print(results[0]['best_params'])
        print(results[0]['test_metrics'])

if __name__ == "__main__":
    main()
