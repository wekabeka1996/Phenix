import pandas as pd
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch

from apps.research.momentum_backtest.features_builder import build_features

@pytest.fixture
def temp_data_dir(tmp_path):
    return tmp_path

def create_dummy_golden(path):
    # Create 100 seconds of data to allow rolling windows to work partially
    dates = pd.date_range(start="2024-03-01 00:00:00", periods=100, freq="1s")
    
    data = {
        'ts': dates,
        'open_1s': np.linspace(100, 110, 100),
        'high_1s': np.linspace(100, 110, 100) + 0.1,
        'low_1s': np.linspace(100, 110, 100) - 0.1,
        'close_1s': np.linspace(100, 110, 100),
        'vol_1s': np.random.rand(100) * 10,
        'buy_vol_1s': np.random.rand(100) * 5,
        'sell_vol_1s': np.random.rand(100) * 5,
        'tob_bid_qty_1s': np.random.rand(100) * 100,
        'tob_ask_qty_1s': np.random.rand(100) * 100,
        'funding_rate_1s': np.zeros(100) + 0.0001
    }
    
    df = pd.DataFrame(data)
    df.to_parquet(path, index=False)
    return df

def test_build_features(temp_data_dir):
    golden_path = temp_data_dir / "BNBUSDT-1s-golden-2024-03.parquet"
    features_path = temp_data_dir / "BNBUSDT-features-2024-03.parquet"
    
    create_dummy_golden(golden_path)
    
    # Mock config paths
    with patch('apps.research.momentum_backtest.features_builder.get_processed_file_path') as mock_get_processed:
        
        def side_effect(template, symbol, year, month):
            if "golden" in template: return golden_path
            if "features" in template: return features_path
            return Path("error")
        
        mock_get_processed.side_effect = side_effect
        
        build_features()
        
    # Verify output
    assert features_path.exists()
    df = pd.read_parquet(features_path)
    
    print(df.columns)
    
    expected_cols = [
        'ts', 'close_1s', 'high_1s', 'low_1s',
        'tfi_1m', 'tob_imbalance', 'ema_bias_short', 'ema_bias_long',
        'vol_state', 'macro_corr_1h', 'funding_rate_1s', 'funding_norm'
    ]
    
    for col in expected_cols:
        assert col in df.columns
        
    # Check values
    # TFI should be between -1 and 1
    assert df['tfi_1m'].min() >= -1.0
    assert df['tfi_1m'].max() <= 1.0
    
    # ToB Imbalance should be between -1 and 1
    assert df['tob_imbalance'].min() >= -1.0
    assert df['tob_imbalance'].max() <= 1.0
    
    # Check length
    assert len(df) == 100
