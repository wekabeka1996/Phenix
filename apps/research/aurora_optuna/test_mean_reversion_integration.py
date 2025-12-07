import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, ".")

from apps.research.aurora_optuna.backtest_engine_aurora import BacktestEngineAurora
from apps.research.aurora_optuna.features_aurora import build_aurora_features

def create_dummy_data(n_rows=1000):
    """Create dummy OHLCV data with clear BB signals"""
    dates = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_rows)]
    
    # Create a sine wave price to trigger BB signals
    t = np.linspace(0, 4*np.pi, n_rows)
    price = 100 + 10 * np.sin(t) + np.random.normal(0, 0.5, n_rows)
    
    df = pd.DataFrame({
        'ts': dates,
        'open': price,
        'high': price + 0.5,
        'low': price - 0.5,
        'close': price,
        'vol': np.random.random(n_rows) * 1000,
        'tob_bid_qty': np.random.random(n_rows) * 10,
        'tob_ask_qty': np.random.random(n_rows) * 10,
        'buy_vol': np.random.random(n_rows) * 500,
        'sell_vol': np.random.random(n_rows) * 500,
    })
    
    # Add regime column
    df['regime'] = 'FLAT_NORMAL'
    
    return df

def test_mean_reversion_logic():
    print("Testing Mean Reversion Logic...")
    
    # 1. Create Data
    df = create_dummy_data()
    
    # 2. Build Features (including BB)
    params = {
        'bb_window': 20,
        'bb_std_dev': 2.0,
        'min_vol_atr': 0.001,
        'allowed_regimes': ['FLAT_NORMAL', 'TREND_UP', 'TREND_DOWN', 'UNCERTAIN', 'LOW_VOLATILITY', 'HIGH_VOLATILITY']
    }
    
    # Mock BTC df (not needed for this test but required by function signature)
    btc_df = df.copy()
    
    print("Building features...")
    df_features = build_aurora_features(df, btc_df, params)
    
    # Verify BB columns exist
    assert 'bb_mid_20' in df_features.columns
    assert 'bb_upper_20' in df_features.columns
    assert 'bb_lower_20' in df_features.columns
    print("✅ BB columns created")
    
    # DEBUG: Inspect data
    print("\n--- Data Inspection ---")
    print(df_features[['ts', 'close', 'bb_lower_20', 'bb_upper_20', 'bb_width_20', 'regime']].tail(10))
    
    # Check if any price is outside bands
    long_candidates = df_features[df_features['close'] < df_features['bb_lower_20']]
    short_candidates = df_features[df_features['close'] > df_features['bb_upper_20']]
    print(f"\nCandidates (Raw): Longs={len(long_candidates)}, Shorts={len(short_candidates)}")
    
    if len(long_candidates) > 0:
        print("Sample Long Candidate:")
        print(long_candidates.iloc[0][['close', 'bb_lower_20', 'bb_width_20']])
        
    # 3. Run Backtest in Mean Reversion Mode
    engine_mr = BacktestEngineAurora(df_features, params, strategy_mode='mean_reversion')
    metrics_mr = engine_mr.run()
    
    print(f"Mean Reversion Metrics: {metrics_mr}")
    
    # Verify trades were made
    assert metrics_mr['trades'] > 0
    print(f"✅ Mean Reversion generated {metrics_mr['trades']} trades")
    
    # 4. Run Backtest in Weighted Signal Mode (Comparison)
    # Add dummy signal weights to ensure it runs
    params_ws = params.copy()
    params_ws['signal_threshold'] = 0.1
    params_ws['weight_ema'] = 0.5
    params_ws['weight_volume'] = 0.5
    
    engine_ws = BacktestEngineAurora(df_features, params_ws, strategy_mode='weighted_signal')
    metrics_ws = engine_ws.run()
    
    print(f"Weighted Signal Metrics: {metrics_ws}")
    
    # Verify modes produce different results (likely)
    if metrics_mr['trades'] != metrics_ws['trades']:
        print("✅ Modes produced different trade counts (expected)")
    else:
        print("⚠️ Modes produced same trade counts (coincidence?)")

if __name__ == "__main__":
    test_mean_reversion_logic()
