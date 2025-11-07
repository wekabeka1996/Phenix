"""
Tests for Backtest Engine
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from apps.reference.alpha_discovery import BacktestEngine, BacktestResult
from apps.reference.domains.alpha_search import AlphaModelRegistry


class TestBacktestEngine:
    """Test cases for BacktestEngine."""

    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data with features."""
        dates = pd.date_range('2023-01-01', periods=100, freq='1H')
        np.random.seed(42)

        data = pd.DataFrame({
            'timestamp': dates,
            'open': 100 + np.random.randn(100) * 2,
            'high': 102 + np.random.randn(100) * 2,
            'low': 98 + np.random.randn(100) * 2,
            'close': 100 + np.random.randn(100) * 2,
            'volume': np.random.randint(1000, 10000, 100),
            'rsi': 50 + np.random.randn(100) * 10,
            'macd': np.random.randn(100) * 0.5,
            'bb_upper': 102 + np.random.randn(100),
            'bb_lower': 98 + np.random.randn(100)
        })

        # Ensure high >= close >= low and high >= open >= low
        for i in range(len(data)):
            high = max(data.loc[i, ['open', 'close', 'high']].max(),
                       data.loc[i, 'low'] + abs(np.random.randn()) * 2)
            low = min(data.loc[i, ['open', 'close', 'low']].min(),
                      data.loc[i, 'high'] - abs(np.random.randn()) * 2)
            data.loc[i, 'high'] = high
            data.loc[i, 'low'] = low

        return data

    @pytest.fixture
    def mock_alpha_model(self):
        """Create a mock alpha model."""
        model = Mock()
        model.name = "TestModel"
        model.is_ready.return_value = True

        # Mock alpha score with some positive/negative signals
        scores = []
        for i in range(100):
            score = np.random.randn() * 0.5
            confidence = 0.6 + np.random.rand() * 0.4
            scores.append(Mock(score=score, confidence=confidence))

        model.calculate_alpha.side_effect = scores
        return model

    @pytest.fixture
    def mock_registry(self, mock_alpha_model):
        """Create a mock alpha model registry."""
        registry = Mock(spec=AlphaModelRegistry)
        registry.get_model.return_value = mock_alpha_model
        return registry

    @pytest.fixture
    def backtest_engine(self, mock_registry):
        """Create BacktestEngine instance."""
        return BacktestEngine(mock_registry)

    def test_backtest_result_creation(self):
        """Test BacktestResult dataclass creation."""
        result = BacktestResult(
            model_name="TestModel",
            symbol="BTCUSDT",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 2),
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=0.6,
            total_return=0.15,
            sharpe_ratio=1.2,
            max_drawdown=0.05,
            avg_trade_return=0.015,
            max_consecutive_losses=2,
            profit_factor=1.8,
            calmar_ratio=3.0
        )

        assert result.model_name == "TestModel"
        assert result.symbol == "BTCUSDT"
        assert result.total_trades == 10
        assert result.win_rate == 0.6
        assert result.sharpe_ratio == 1.2

    def test_backtest_result_to_dict(self):
        """Test BacktestResult serialization."""
        result = BacktestResult(
            model_name="TestModel",
            symbol="BTCUSDT",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 1, 2),
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
            win_rate=0.6,
            total_return=0.15,
            sharpe_ratio=1.2,
            max_drawdown=0.05,
            avg_trade_return=0.015,
            max_consecutive_losses=2,
            profit_factor=1.8,
            calmar_ratio=3.0
        )

        data = result.to_dict()
        assert isinstance(data, dict)
        assert data['model_name'] == "TestModel"
        assert data['win_rate'] == 0.6
        assert 'start_date' in data

    def test_backtest_model_basic(self, backtest_engine, sample_data, mock_alpha_model):
        """Test basic backtest execution."""
        result = backtest_engine.backtest_model(
            "TestModel", "BTCUSDT", sample_data
        )

        assert isinstance(result, BacktestResult)
        assert result.model_name == "TestModel"
        assert result.symbol == "BTCUSDT"
        assert result.total_trades >= 0
        assert 0 <= result.win_rate <= 1
        assert isinstance(result.sharpe_ratio, (int, float))
        assert isinstance(result.max_drawdown, (int, float))

    def test_backtest_model_empty_data(self, backtest_engine):
        """Test backtest with empty data raises error."""
        empty_data = pd.DataFrame()

        with pytest.raises(ValueError, match="Historical data cannot be empty"):
            backtest_engine.backtest_model("TestModel", "BTCUSDT", empty_data)

    def test_backtest_model_missing_model(self, backtest_engine, sample_data, mock_registry):
        """Test backtest with non-existent model raises error."""
        mock_registry.get_model.return_value = None

        with pytest.raises(ValueError, match="Model TestModel not found"):
            backtest_engine.backtest_model("TestModel", "BTCUSDT", sample_data)

    def test_calculate_metrics_no_trades(self, backtest_engine, sample_data):
        """Test metrics calculation with no trades."""
        trades = []

        result = backtest_engine._calculate_metrics(
            "TestModel", "BTCUSDT", trades, sample_data, 10000.0
        )

        assert result.total_trades == 0
        assert result.winning_trades == 0
        assert result.win_rate == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.max_drawdown == 0.0

    def test_calculate_metrics_with_trades(self, backtest_engine, sample_data):
        """Test metrics calculation with sample trades."""
        trades = [
            {
                'entry_time': datetime(2023, 1, 1, 1),
                'exit_time': datetime(2023, 1, 1, 2),
                'entry_price': 100.0,
                'exit_price': 105.0,
                'quantity': 10.0,
                'pnl': 50.0,
                'commission': 1.0,
                'exit_reason': 'take_profit',
                'return_pct': 0.05
            },
            {
                'entry_time': datetime(2023, 1, 1, 3),
                'exit_time': datetime(2023, 1, 1, 4),
                'entry_price': 105.0,
                'exit_price': 102.0,
                'quantity': 10.0,
                'pnl': -30.0,
                'commission': 1.0,
                'exit_reason': 'stop_loss',
                'return_pct': -0.0286
            }
        ]

        result = backtest_engine._calculate_metrics(
            "TestModel", "BTCUSDT", trades, sample_data, 10000.0
        )

        assert result.total_trades == 2
        assert result.winning_trades == 1
        assert result.losing_trades == 1
        assert result.win_rate == 0.5
        assert result.avg_trade_return == pytest.approx(
            (0.05 - 0.0286) / 2, abs=0.01)
        assert result.profit_factor == 50.0 / 30.0  # gross_profit / gross_loss

    def test_compare_models(self, backtest_engine, sample_data, mock_registry):
        """Test model comparison functionality."""
        # Mock two different models
        model1 = Mock()
        model1.name = "Model1"
        model1.is_ready.return_value = True
        model1.calculate_alpha.side_effect = [
            Mock(score=0.5, confidence=0.8) for _ in range(100)
        ]

        model2 = Mock()
        model2.name = "Model2"
        model2.is_ready.return_value = True
        model2.calculate_alpha.side_effect = [
            Mock(score=-0.2, confidence=0.7) for _ in range(100)
        ]

        def get_model_side_effect(name):
            if name == "Model1":
                return model1
            elif name == "Model2":
                return model2
            return None

        mock_registry.get_model.side_effect = get_model_side_effect

        results = backtest_engine.compare_models(
            ["Model1", "Model2"], "BTCUSDT", sample_data
        )

        assert len(results) == 2
        assert all(isinstance(r, BacktestResult) for r in results)
        # Results should be sorted by Sharpe ratio (descending)
        assert results[0].sharpe_ratio >= results[1].sharpe_ratio

    def test_simulate_trades_basic_flow(self, backtest_engine, sample_data):
        """Test basic trade simulation flow."""
        scores = [
            {'timestamp': datetime(2023, 1, 1, 1), 'score': 0.5,
             'confidence': 0.8, 'price': 100.0},
            {'timestamp': datetime(2023, 1, 1, 2), 'score': -
             0.5, 'confidence': 0.9, 'price': 105.0},
        ]

        trades = backtest_engine._simulate_trades(
            scores, sample_data, 10000.0, 0.1, 0.02, 0.04, 0.001
        )

        assert isinstance(trades, list)
        if trades:  # May not generate trades depending on signals
            assert all('pnl' in trade for trade in trades)
            assert all('entry_time' in trade for trade in trades)
            assert all('exit_time' in trade for trade in trades)
