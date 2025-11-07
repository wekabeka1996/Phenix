"""
Example usage of Backtest Engine

Demonstrates how to use the backtest engine to evaluate alpha models.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from apps.reference.alpha_discovery import BacktestEngine
from apps.reference.domains.alpha_search import AlphaModelRegistry


def create_sample_data(symbol: str, days: int = 30) -> pd.DataFrame:
    """Create sample OHLCV data with technical indicators."""
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=days * 24, freq='1H')

    # Generate realistic price data
    price_changes = np.random.randn(len(dates)) * 0.01
    prices = 100 * np.exp(np.cumsum(price_changes))

    data = pd.DataFrame({
        'timestamp': dates,
        'open': prices * (1 + np.random.randn(len(dates)) * 0.002),
        'high': prices * (1 + np.random.randn(len(dates)) * 0.005),
        'low': prices * (1 - np.random.randn(len(dates)) * 0.005),
        'close': prices,
        'volume': np.random.randint(1000, 10000, len(dates)),
    })

    # Ensure OHLC relationships
    for i in range(len(data)):
        row = data.iloc[i]
        data.loc[i, 'high'] = max(row['open'], row['close'], row['high'])
        data.loc[i, 'low'] = min(row['open'], row['close'], row['low'])

    # Add technical indicators
    data['rsi'] = 50 + np.random.randn(len(data)) * 15
    data['macd'] = np.random.randn(len(data)) * 0.5
    data['bb_upper'] = data['close'] * 1.02
    data['bb_lower'] = data['close'] * 0.98
    data['sma_20'] = data['close'].rolling(20).mean()
    data['ema_12'] = data['close'].ewm(span=12).mean()

    return data.fillna(method='bfill')


def main():
    """Example backtest execution."""
    print("🚀 Alpha Model Backtest Example")
    print("=" * 50)

    # Create sample data
    symbol = "BTCUSDT"
    data = create_sample_data(symbol, days=30)
    print(f"📊 Generated {len(data)} hours of sample data for {symbol}")
    print(
        f"📅 Date range: {data['timestamp'].min()} to {data['timestamp'].max()}")

    # Initialize components
    registry = AlphaModelRegistry()
    engine = BacktestEngine(registry)

    # Get available models
    model_names = registry.list_models()
    if not model_names:
        print("❌ No alpha models available in registry")
        return

    print(f"🤖 Available models: {', '.join(model_names)}")

    # Backtest each model
    results = []
    for model_name in model_names:
        print(f"\n🔬 Backtesting {model_name}...")

        try:
            result = engine.backtest_model(
                model_name=model_name,
                symbol=symbol,
                historical_data=data,
                initial_capital=10000.0,
                position_size_pct=0.1,
                stop_loss_pct=0.02,
                take_profit_pct=0.04,
                commission_pct=0.001
            )

            results.append(result)

            print("   📈 Results:")
            print(f"   💰 Total Trades: {result.total_trades}")
            print(f"   📊 Win Rate: {result.win_rate:.1%}")
            print(f"   📈 Sharpe Ratio: {result.sharpe_ratio:.2f}")
            print(f"   📉 Max Drawdown: {result.max_drawdown:.1%}")
            print(f"   💹 Total Return: {result.total_return:.2f}")
            print(
                f"   🎯 Max Consecutive Losses: {result.max_consecutive_losses}")
            print(f"   🏆 Profit Factor: {result.profit_factor:.2f}")
            print(f"   📊 Calmar Ratio: {result.calmar_ratio:.2f}")
        except Exception as e:
            print(f"   ❌ Error backtesting {model_name}: {e}")
            continue

    if not results:
        print("❌ No successful backtests")
        return

    # Compare models
    print(f"\n🏆 Model Comparison (sorted by Sharpe ratio):")
    print("-" * 70)
    print(f"{'Model':<12} {'Trades':<6} {'Win Rate':<8} {'Sharpe':<8} {'Max DD':<8}")
    print("-" * 70)

    for result in sorted(results, key=lambda x: x.sharpe_ratio, reverse=True):
        print(f"{result.model_name:<12} "
              f"{result.total_trades:<6} "
              f"{result.win_rate:<8.1%} "
              f"{result.sharpe_ratio:<8.2f} "
              f"{result.max_drawdown:<8.1%}")

    # Best model analysis
    best_result = max(results, key=lambda x: x.sharpe_ratio)
    print(f"\n🎉 Best Model: {best_result.model_name}")
    print(f"   Sharpe Ratio: {best_result.sharpe_ratio:.2f}")
    print(f"   Total Return: {best_result.total_return:.1%}")
    print(f"   Win Rate: {best_result.win_rate:.1%}")
    print(f"   Max Drawdown: {best_result.max_drawdown:.1%}")

    print("\n✅ Backtest example completed!")


if __name__ == "__main__":
    main()
