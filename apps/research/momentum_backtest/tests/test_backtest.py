import pandas as pd
import numpy as np
import pytest
from apps.research.momentum_backtest.backtest_engine import BacktestEngine

def create_synthetic_data():
    # Create 3 scenarios
    # 1. TP Trade: Price 100 -> 101 (1%) -> TP (0.8% target)
    # 2. SL Trade: Price 100 -> 99 (1%) -> SL (0.4% target)
    # 3. Time Exit: Price 100 -> 100.1 (flat) -> Time Exit
    
    # We need enough seconds.
    # Scenario 1:
    # t=0: Signal=1, Price=100.
    # t=1: Price=100.
    # t=2: Price=101. (High=101). TP hit.
    
    dates = pd.date_range(start="2024-03-01 00:00:00", periods=1000, freq="1s")
    df = pd.DataFrame({'ts': dates})
    
    # Initialize columns
    df['open_1s'] = 100.0
    df['high_1s'] = 100.0
    df['low_1s'] = 100.0
    df['close_1s'] = 100.0
    df['tfi_1m'] = 0.0
    df['tob_imbalance'] = 0.0
    df['ema_bias_short'] = 0.0
    df['ema_bias_long'] = 0.0
    df['macro_corr_1h'] = 0.0
    df['funding_rate_1s'] = 0.0
    
    # Scenario 1: TP
    # t=10: Signal.
    # t=11: Entry.
    # t=20: Price jumps to 101.
    
    # We force signal by setting tfi_1m high enough if w_tfi=1
    df.loc[10, 'tfi_1m'] = 1.0 
    
    df.loc[20, 'high_1s'] = 101.0
    df.loc[20, 'close_1s'] = 101.0
    
    # Scenario 2: SL
    # t=50: Signal.
    # t=60: Price drops to 99.
    df.loc[50, 'tfi_1m'] = 1.0
    
    df.loc[60, 'low_1s'] = 99.0
    df.loc[60, 'close_1s'] = 99.0
    
    # Scenario 3: Time Exit
    # t=100: Signal.
    # Wait until t=100 + max_holding (e.g. 10s for test).
    df.loc[100, 'tfi_1m'] = 1.0
    
    return df

def test_backtest_engine():
    df = create_synthetic_data()
    
    params = {
        'w_tfi': 1.0,
        'threshold': 0.5,
        'sl_pct': 0.004, # 0.4% -> SL at 99.6
        'sl_tp_ratio': 2.0, # TP at 0.8% -> 100.8
        'max_holding_secs': 10,
        'position_size': 100.0,
        'commission': 0.0,
        'slippage': 0.0,
        'spread_half': 0.0
    }
    
    engine = BacktestEngine(df, params)
    results = engine.run()
    
    trades = results['trades']
    metrics = results['metrics']
    
    print(f"Trades: {len(trades)}")
    for t in trades:
        print(t)
        
    # Expected Trades:
    # 1. Entry at t=10 (signal) -> t=11 (execution at close of t=10? No, loop uses current close).
    # Logic:
    # if signal[i] == 1: Enter at current_close * ...
    # So entry at t=10.
    # Exit at t=20. High=101 > TP(100.8). TP hit.
    # PnL > 0.
    
    # 2. Entry at t=50.
    # Exit at t=60. Low=99 < SL(99.6). SL hit.
    # PnL < 0.
    
    # 3. Entry at t=100.
    # Exit at t=110 (Time). Price is 100. PnL 0.
    
    assert len(trades) == 3
    
    # Trade 1: TP
    assert trades[0].exit_reason == 'TP'
    assert trades[0].pnl > 0
    
    # Trade 2: SL
    assert trades[1].exit_reason == 'SL'
    assert trades[1].pnl < 0
    
    # Trade 3: TIME
    assert trades[2].exit_reason == 'TIME'
    
    # Metrics
    assert metrics['total_trades'] == 3
    assert metrics['win_rate'] == 1/3 # Only TP is win. Time exit is flat (0 PnL) -> usually counted as loss or ignore? Code: pnl > 0. So 0 is loss.
    
