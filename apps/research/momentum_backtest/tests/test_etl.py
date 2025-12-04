import pandas as pd
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch

from apps.research.momentum_backtest.etl import process_golden_dataset, load_agg_trades, load_book_ticker, load_funding_rate

@pytest.fixture
def temp_data_dir(tmp_path):
    return tmp_path

def create_dummy_agg_trades(path):
    # Create 10 seconds of trades
    # 1s: price 100, qty 1, buy
    # 2s: price 101, qty 2, sell
    # ...
    data = []
    base_time = pd.Timestamp("2024-03-01 00:00:00")
    
    # Second 0: 2 trades. 100 (buy), 100.5 (sell)
    data.append([1, 100.0, 1.0, 0, 0, (base_time + pd.Timedelta(milliseconds=100)).value // 10**6, False]) # Buy
    data.append([2, 100.5, 2.0, 0, 0, (base_time + pd.Timedelta(milliseconds=500)).value // 10**6, True])  # Sell
    
    # Second 1: 1 trade. 101 (buy)
    data.append([3, 101.0, 5.0, 0, 0, (base_time + pd.Timedelta(seconds=1, milliseconds=100)).value // 10**6, False])
    
    # Second 2: No trades (gap)
    
    # Second 3: 1 trade. 99 (sell)
    data.append([4, 99.0, 10.0, 0, 0, (base_time + pd.Timedelta(seconds=3, milliseconds=100)).value // 10**6, True])
    
    df = pd.DataFrame(data, columns=['agg_trade_id', 'price', 'quantity', 'first_trade_id', 'last_trade_id', 'transact_time', 'is_buyer_maker'])
    df.to_csv(path, index=False, header=False)
    return df

def create_dummy_book_ticker(path):
    data = []
    base_time = pd.Timestamp("2024-03-01 00:00:00")
    
    # Initial state
    data.append([1, 99.9, 10, 100.1, 20, (base_time).value // 10**6, 0])
    
    # Update at 1.5s
    data.append([2, 100.0, 15, 100.2, 25, (base_time + pd.Timedelta(seconds=1, milliseconds=500)).value // 10**6, 0])
    
    df = pd.DataFrame(data, columns=['update_id', 'best_bid_price', 'best_bid_qty', 'best_ask_price', 'best_ask_qty', 'transaction_time', 'event_time'])
    df.to_csv(path, index=False, header=False)
    return df

def create_dummy_funding(path):
    data = []
    base_time = pd.Timestamp("2024-03-01 00:00:00")
    
    # Initial funding
    data.append([(base_time).value // 10**6, 0.0001, 100.0])
    
    df = pd.DataFrame(data, columns=['calc_time', 'funding_rate', 'mark_price'])
    df.to_csv(path, index=False, header=False)
    return df

def test_process_golden_dataset(temp_data_dir):
    # Setup paths
    agg_path = temp_data_dir / "BNBUSDT-aggTrades-2024-03.csv"
    bt_path = temp_data_dir / "BNBUSDT-bookTicker-2024-03.csv"
    fr_path = temp_data_dir / "BNBUSDT-fundingRate-2024-03.csv"
    out_path = temp_data_dir / "BNBUSDT-1s-golden-2024-03.parquet"
    
    create_dummy_agg_trades(agg_path)
    create_dummy_book_ticker(bt_path)
    create_dummy_funding(fr_path)
    
    # Mock config paths
    with patch('apps.research.momentum_backtest.etl.get_raw_file_path') as mock_get_raw:
        with patch('apps.research.momentum_backtest.etl.get_processed_file_path') as mock_get_processed:
            
            def side_effect_raw(template, symbol, year, month):
                if "aggTrades" in template: return agg_path
                if "bookTicker" in template: return bt_path
                if "fundingRate" in template: return fr_path
                return Path("error")
            
            mock_get_raw.side_effect = side_effect_raw
            mock_get_processed.return_value = out_path
            
            process_golden_dataset()
            
    # Verify output
    assert out_path.exists()
    df = pd.read_parquet(out_path)
    
    print(df)
    
    # Check length: 0s to 3s = 4 seconds (0, 1, 2, 3)
    # But resample might go up to the last timestamp.
    # Last trade is at 3.1s. So we expect 0, 1, 2, 3.
    # Wait, resample('1s') bins:
    # 0s: [0, 1)
    # 1s: [1, 2)
    # 2s: [2, 3)
    # 3s: [3, 4)
    # So we expect 4 rows.
    
    assert len(df) == 4
    
    # Check 0s
    # Trades: 100, 100.5. Open 100, Close 100.5.
    # Vol: 1+2=3. BuyVol: 1. SellVol: 2.
    row0 = df.iloc[0]
    assert row0['open_1s'] == 100.0
    assert row0['close_1s'] == 100.5
    assert row0['vol_1s'] == 3.0
    assert row0['buy_vol_1s'] == 1.0
    assert row0['sell_vol_1s'] == 2.0
    
    # Check 1s
    # Trades: 101. Open 101, Close 101.
    # Vol: 5. BuyVol: 5. SellVol: 0.
    # BookTicker: update at 1.5s. So for 1s bin (1.0-2.0), the last value is the one at 1.5s?
    # Wait, resample().last() takes the last value IN the bin.
    # At 1.5s we have update.
    # So for bin 1s, we have value from 1.5s.
    # Value at 1.5s: Bid 100, Ask 100.2. Qty 15, 25.
    row1 = df.iloc[1]
    assert row1['close_1s'] == 101.0
    assert row1['tob_bid_qty_1s'] == 15.0
    assert row1['tob_ask_qty_1s'] == 25.0
    
    # Check 2s (Gap)
    # Should carry over Close from 1s (101.0).
    # Vol 0.
    # BookTicker should carry over (ffill).
    row2 = df.iloc[2]
    assert row2['close_1s'] == 101.0
    assert row2['vol_1s'] == 0.0
    assert row2['tob_bid_qty_1s'] == 15.0
    
    # Check Funding
    assert row0['funding_rate_1s'] == 0.0001
