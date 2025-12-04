"""
Walk-Forward Analysis for R&D Pipeline
Supports flexible time-based splits for parameter validation
"""

import pandas as pd
from typing import List, Dict, Tuple
from datetime import timedelta

from apps.research.momentum_backtest.backtest_engine_v2 import BacktestEngineV2
from apps.research.momentum_backtest.metrics import calculate_metrics


def build_time_splits(
    df: pd.DataFrame,
    train_days: int = 21,
    test_days: int = 7,
    step_days: int = 7,
) -> List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """
    Build Walk-Forward time windows.
    
    Returns list of tuples: (train_start, train_end, test_start, test_end)
    
    Args:
        df: DataFrame with 'ts' column
        train_days: Training period in days
        test_days: Test period in days
        step_days: Step size in days
        
    Returns:
        List of (train_start, train_end, test_start, test_end) tuples
    """
    df['ts'] = pd.to_datetime(df['ts'])
    start_time = df['ts'].min()
    end_time = df['ts'].max()
    
    windows = []
    current_train_start = start_time
    
    while True:
        train_end = current_train_start + timedelta(days=train_days)
        test_start = train_end
        test_end = test_start + timedelta(days=test_days)
        
        # Check if we have enough data
        if test_end > end_time:
            break
            
        windows.append((current_train_start, train_end, test_start, test_end))
        
        # Step forward
        current_train_start += timedelta(days=step_days)
    
    return windows


def run_walk_forward_for_params(
    df_features: pd.DataFrame,
    params: dict,
    train_days: int = 21,
    test_days: int = 7,
    step_days: int = 7,
) -> dict:
    """
    Run Walk-Forward validation for given parameters.
    
    For v1: uses same params across all windows (no per-window optimization).
    Evaluates params on OOS test windows and aggregates metrics.
    
    Args:
        df_features: Full features DataFrame
        params: Strategy parameters to test
        train_days: Training window size
        test_days: Test window size
        step_days: Step size
        
    Returns:
        Aggregated metrics dict
    """
    # Build splits
    windows = build_time_splits(df_features, train_days, test_days, step_days)
    
    if len(windows) == 0:
        print("WARNING: No valid windows in dataset")
        return {
            "total_pnl_usd": 0.0,
            "max_drawdown_pct": 0.0,
            "calmar": 0.0,
            "sortino": 0.0,
            "total_trades": 0,
        }
    
    print(f"Walk-Forward: {len(windows)} windows")
    
    all_trades = []
    all_equity_curves = []
    
    for i, (train_start, train_end, test_start, test_end) in enumerate(windows):
        print(f"\n  Window {i+1}/{len(windows)}: Test [{test_start} - {test_end}]")
        
        # Get test data slice
        mask_test = (df_features['ts'] >= test_start) & (df_features['ts'] < test_end)
        df_test = df_features[mask_test].copy().reset_index(drop=True)
        
        if len(df_test) == 0:
            print("    Empty test set, skipping")
            continue
        
        # Run backtest on test (OOS)
        engine = BacktestEngineV2(df_test, params)
        result = engine.run()
        
        trades_count = len(result['trades'])
        pnl = result.get('total_pnl_usd', 0.0)
        
        print(f"    Trades: {trades_count}, PnL: ${pnl:.2f}")
        
        all_trades.extend(result['trades'])
        all_equity_curves.append(result['equity_curve'])
    
    # Aggregate metrics
    if len(all_trades) == 0:
        return {
            "total_pnl_usd": 0.0,
            "max_drawdown_pct": 0.0,
            "calmar": 0.0,
            "sortino": 0.0,
            "total_trades": 0,
        }
    
    # Calculate aggregate metrics
    # Stitch equity curves
    stitched_equity = pd.concat(all_equity_curves)
    stitched_equity = stitched_equity.sort_index()
    
    # Use calculate_metrics on all OOS trades
    aggregate_metrics = calculate_metrics(all_trades, stitched_equity)
    
    return {
        "total_pnl_usd": aggregate_metrics.get('total_pnl', 0.0),
        "max_drawdown_pct": abs(aggregate_metrics.get('max_drawdown', 0.0)),
        "calmar": aggregate_metrics.get('calmar_ratio', 0.0),
        "sortino": aggregate_metrics.get('sortino_ratio', 0.0),
        "sharpe": aggregate_metrics.get('sharpe_ratio', 0.0),
        "total_trades": aggregate_metrics.get('total_trades', 0),
        "win_rate": aggregate_metrics.get('win_rate', 0.0),
    }
