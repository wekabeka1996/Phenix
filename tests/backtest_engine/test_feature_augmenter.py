"""
Tests for BacktestFeatureAugmenter.

Verifies MACD, Stochastic, Momentum, RSI calculations produce valid values.
"""

import polars as pl
import pytest
from datetime import datetime, timedelta


def _generate_sample_ohlcv(n_rows: int = 100) -> pl.DataFrame:
    """Generate sample OHLCV data for testing."""
    base_price = 100.0
    data = {
        "ts": [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_rows)],
        "symbol": ["BTCUSDT"] * n_rows,
        "open": [base_price + i * 0.1 for i in range(n_rows)],
        "high": [base_price + i * 0.1 + 0.5 for i in range(n_rows)],
        "low": [base_price + i * 0.1 - 0.3 for i in range(n_rows)],
        "close": [base_price + i * 0.1 + 0.2 for i in range(n_rows)],
        "volume": [1000.0 + i * 10 for i in range(n_rows)],
    }
    return pl.DataFrame(data)


class TestMACDCalculation:
    """Tests for MACD indicator."""
    
    def test_macd_columns_exist(self):
        """Verify MACD adds expected columns."""
        from backtest_engine.feature_augmenter import compute_macd
        
        df = _generate_sample_ohlcv(50)
        result = compute_macd(df)
        
        assert "macd_line" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_histogram" in result.columns
    
    def test_macd_values_reasonable(self):
        """MACD values should be within reasonable range for trending data."""
        from backtest_engine.feature_augmenter import compute_macd
        
        df = _generate_sample_ohlcv(50)
        result = compute_macd(df)
        
        # Skip first few rows (warmup period for EMA)
        macd_line = result["macd_line"].drop_nulls()
        
        # For trending up data, MACD should be positive
        assert macd_line[-1] > 0, "MACD should be positive for uptrend"


class TestStochasticCalculation:
    """Tests for Stochastic oscillator."""
    
    def test_stochastic_columns_exist(self):
        """Verify Stochastic adds expected columns."""
        from backtest_engine.feature_augmenter import compute_stochastic
        
        df = _generate_sample_ohlcv(50)
        result = compute_stochastic(df)
        
        assert "stochastic_k" in result.columns
        assert "stochastic_d" in result.columns
    
    def test_stochastic_bounds(self):
        """Stochastic values should be between 0 and 100."""
        from backtest_engine.feature_augmenter import compute_stochastic
        
        df = _generate_sample_ohlcv(50)
        result = compute_stochastic(df)
        
        stoch_k = result["stochastic_k"].drop_nulls()
        
        # All values should be 0-100
        assert stoch_k.min() >= 0, "Stochastic K should be >= 0"
        assert stoch_k.max() <= 100, "Stochastic K should be <= 100"


class TestMomentumCalculation:
    """Tests for price momentum."""
    
    def test_momentum_columns_exist(self):
        """Verify momentum adds expected columns."""
        from backtest_engine.feature_augmenter import compute_momentum
        
        df = _generate_sample_ohlcv(100)
        result = compute_momentum(df)
        
        assert "price_momentum_5m" in result.columns
        assert "price_momentum_1h" in result.columns
        assert "price_momentum_1d" in result.columns
    
    def test_momentum_sign_for_uptrend(self):
        """Momentum should be positive for uptrending data."""
        from backtest_engine.feature_augmenter import compute_momentum
        
        df = _generate_sample_ohlcv(100)
        result = compute_momentum(df)
        
        # Skip warmup rows
        mom_5m = result["price_momentum_5m"][-10:]
        
        # All should be positive (uptrend)
        assert mom_5m.mean() > 0, "Momentum should be positive for uptrend"


class TestRSICalculation:
    """Tests for RSI indicator."""
    
    def test_rsi_column_exists(self):
        """Verify RSI adds expected column."""
        from backtest_engine.feature_augmenter import compute_rsi
        
        df = _generate_sample_ohlcv(50)
        result = compute_rsi(df)
        
        assert "rsi_14" in result.columns
    
    def test_rsi_bounds(self):
        """RSI should be between 0 and 100."""
        from backtest_engine.feature_augmenter import compute_rsi
        
        df = _generate_sample_ohlcv(50)
        result = compute_rsi(df)
        
        rsi = result["rsi_14"].drop_nulls()
        
        assert rsi.min() >= 0, "RSI should be >= 0"
        assert rsi.max() <= 100, "RSI should be <= 100"


class TestBacktestFeatureAugmenter:
    """Integration tests for full augmenter."""
    
    def test_augment_adds_all_features(self):
        """Full augment should add all expected columns."""
        from backtest_engine.feature_augmenter import BacktestFeatureAugmenter
        
        df = _generate_sample_ohlcv(100)
        augmenter = BacktestFeatureAugmenter(df)
        result = augmenter.augment()
        
        expected_features = augmenter.get_feature_names()
        for feat in expected_features:
            assert feat in result.columns, f"Missing feature: {feat}"
    
    def test_augment_preserves_row_count(self):
        """Augmentation should not change row count."""
        from backtest_engine.feature_augmenter import BacktestFeatureAugmenter
        
        df = _generate_sample_ohlcv(100)
        augmenter = BacktestFeatureAugmenter(df)
        result = augmenter.augment()
        
        assert len(result) == len(df), "Row count should be preserved"
    
    def test_augment_handles_multiple_symbols(self):
        """Augmenter should process multiple symbols correctly."""
        from backtest_engine.feature_augmenter import BacktestFeatureAugmenter
        
        df1 = _generate_sample_ohlcv(50)
        df2 = _generate_sample_ohlcv(50).with_columns(pl.lit("ETHUSDT").alias("symbol"))
        combined = pl.concat([df1, df2])
        
        augmenter = BacktestFeatureAugmenter(combined)
        result = augmenter.augment()
        
        assert len(result) == 100
        assert result["symbol"].unique().len() == 2
