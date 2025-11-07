"""
Backtest Engine for Alpha Models

Evaluates alpha model performance on historical data.
Calculates Sharpe ratio, max drawdown, win rate, and other metrics.
"""

import pandas as pd
import numpy as np
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from apps.reference.domains.alpha_search import AlphaModelRegistry

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Results of a backtest run."""

    model_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    avg_trade_return: float
    max_consecutive_losses: int
    profit_factor: float
    calmar_ratio: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'model_name': self.model_name,
            'symbol': self.symbol,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.win_rate,
            'total_return': self.total_return,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'avg_trade_return': self.avg_trade_return,
            'max_consecutive_losses': self.max_consecutive_losses,
            'profit_factor': self.profit_factor,
            'calmar_ratio': self.calmar_ratio
        }


class BacktestEngine:
    """
    Backtesting engine for alpha models.

    Loads historical data, generates signals, simulates trades,
    and calculates performance metrics.
    """

    def __init__(self, alpha_registry: AlphaModelRegistry):
        self.alpha_registry = alpha_registry
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")

    def backtest_model(
        self,
        model_name: str,
        symbol: str,
        historical_data: pd.DataFrame,
        initial_capital: float = 10000.0,
        position_size_pct: float = 0.1,
        stop_loss_pct: float = 0.02,
        take_profit_pct: float = 0.04,
        commission_pct: float = 0.001
    ) -> BacktestResult:
        """
        Backtest a single alpha model on historical data.

        Args:
            model_name: Name of the alpha model to test
            symbol: Trading symbol
            historical_data: OHLCV DataFrame with features
            initial_capital: Starting capital
            position_size_pct: Position size as % of capital
            stop_loss_pct: Stop loss percentage
            take_profit_pct: Take profit percentage
            commission_pct: Trading commission percentage

        Returns:
            BacktestResult with performance metrics
        """
        self.logger.info(f"Starting backtest for {model_name} on {symbol}")

        if historical_data.empty:
            raise ValueError("Historical data cannot be empty")

        # Get alpha model
        model = self.alpha_registry.get_model(model_name)
        if not model:
            raise ValueError(f"Model {model_name} not found in registry")

        # Generate alpha scores
        scores = self._generate_alpha_scores(model, symbol, historical_data)

        # Simulate trades
        trades = self._simulate_trades(
            scores, historical_data, initial_capital,
            position_size_pct, stop_loss_pct, take_profit_pct, commission_pct
        )

        # Calculate metrics
        result = self._calculate_metrics(
            model_name, symbol, trades, historical_data,
            initial_capital
        )

        self.logger.info(f"Backtest completed for {model_name}: "
                         f"{result.total_trades} trades, "
                         f"win_rate={result.win_rate:.2%}, "
                         f"sharpe={result.sharpe_ratio:.2f}")

        return result

    def _generate_alpha_scores(
        self, model, symbol: str, data: pd.DataFrame
    ) -> List[Dict[str, Any]]:
        """
        Generate alpha scores for each data point.

        Returns list of dicts with timestamp, score, confidence.
        """
        scores = []

        for idx, row in data.iterrows():
            try:
                # Extract market data and features
                market_data = {
                    'current_price': float(row['close'])
                }

                features = {}
                for col in data.columns:
                    if col not in ['timestamp', 'open', 'high', 'low', 'close', 'volume']:
                        features[col] = float(
                            row[col]) if pd.notna(row[col]) else 0.0

                # Generate alpha score
                if model.is_ready(features):
                    score = model.calculate_alpha(
                        symbol, market_data, features)
                    scores.append({
                        'timestamp': pd.to_datetime(row['timestamp']),
                        'score': float(score.score),
                        'confidence': float(score.confidence),
                        'price': float(row['close'])
                    })

            except Exception as e:
                self.logger.warning(
                    f"Error generating score for {symbol} at {row['timestamp']}: {e}")
                continue

        return scores

    def _simulate_trades(
        self,
        scores: List[Dict[str, Any]],
        data: pd.DataFrame,
        initial_capital: float,
        position_size_pct: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        commission_pct: float
    ) -> List[Dict[str, Any]]:
        """
        Simulate trades based on alpha scores.

        Returns list of completed trades.
        """
        trades = []
        capital = initial_capital
        position = None

        for score_data in scores:
            score = score_data['score']
            confidence = score_data['confidence']
            price = score_data['price']
            timestamp = score_data['timestamp']

            # Skip if confidence too low
            if confidence < 0.5:
                continue

            # Entry signal (strong positive score)
            if position is None and score > 0.3:
                position_size = capital * position_size_pct
                quantity = position_size / price

                position = {
                    'entry_price': price,
                    'quantity': quantity,
                    'entry_time': timestamp,
                    'stop_loss': price * (1 - stop_loss_pct),
                    'take_profit': price * (1 + take_profit_pct),
                    'commission': position_size * commission_pct
                }

                capital -= position['commission']
                self.logger.debug(f"Opened position at {price} ({timestamp})")

            # Exit signal (strong negative score) or stop loss/take profit
            elif position is not None:
                exit_reason = None

                # Check stop loss
                if price <= position['stop_loss']:
                    exit_reason = 'stop_loss'
                # Check take profit
                elif price >= position['take_profit']:
                    exit_reason = 'take_profit'
                # Exit signal
                elif score < -0.3:
                    exit_reason = 'signal_exit'

                if exit_reason:
                    exit_value = price * position['quantity']
                    entry_value = position['entry_price'] * \
                        position['quantity']
                    pnl = exit_value - entry_value
                    commission_exit = exit_value * commission_pct

                    capital += exit_value - commission_exit

                    trade = {
                        'entry_time': position['entry_time'],
                        'exit_time': timestamp,
                        'entry_price': position['entry_price'],
                        'exit_price': price,
                        'quantity': position['quantity'],
                        'pnl': pnl,
                        'commission': position['commission'] + commission_exit,
                        'exit_reason': exit_reason,
                        'return_pct': pnl / entry_value if entry_value != 0 else 0
                    }

                    trades.append(trade)
                    position = None

                    self.logger.debug(
                        f"Closed position: {exit_reason}, PnL: {pnl:.2f}")

        # Close any remaining position at the end
        if position is not None and scores:
            final_price = scores[-1]['price']
            exit_value = final_price * position['quantity']
            entry_value = position['entry_price'] * position['quantity']
            pnl = exit_value - entry_value
            commission_exit = exit_value * commission_pct

            capital += exit_value - commission_exit

            trade = {
                'entry_time': position['entry_time'],
                'exit_time': scores[-1]['timestamp'],
                'entry_price': position['entry_price'],
                'exit_price': final_price,
                'quantity': position['quantity'],
                'pnl': pnl,
                'commission': position['commission'] + commission_exit,
                'exit_reason': 'end_of_data',
                'return_pct': pnl / entry_value if entry_value != 0 else 0
            }

            trades.append(trade)

        return trades

    def _calculate_metrics(
        self,
        model_name: str,
        symbol: str,
        trades: List[Dict[str, Any]],
        data: pd.DataFrame,
        initial_capital: float
    ) -> BacktestResult:
        """Calculate performance metrics from trades."""

        if not trades:
            return BacktestResult(
                model_name=model_name,
                symbol=symbol,
                start_date=data['timestamp'].min(),
                end_date=data['timestamp'].max(),
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                avg_trade_return=0.0,
                max_consecutive_losses=0,
                profit_factor=0.0,
                calmar_ratio=0.0
            )

        # Basic trade metrics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t['pnl'] > 0)
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        # Returns
        trade_returns = [t['return_pct'] for t in trades]
        avg_trade_return = np.mean(trade_returns) if trade_returns else 0

        # Calculate equity curve
        equity = [initial_capital]
        for trade in trades:
            new_equity = equity[-1] + trade['pnl'] - trade['commission']
            equity.append(max(new_equity, 0))  # Don't go below zero

        total_return = (equity[-1] - initial_capital) / initial_capital

        # Sharpe ratio (assuming daily returns, risk-free rate = 0)
        if len(trade_returns) > 1:
            sharpe_ratio = np.mean(trade_returns) / \
                np.std(trade_returns) * np.sqrt(365)
        else:
            sharpe_ratio = 0.0

        # Max drawdown
        peak = initial_capital
        max_drawdown = 0.0

        for eq in equity:
            if eq > peak:
                peak = eq
            drawdown = (peak - eq) / peak
            max_drawdown = max(max_drawdown, drawdown)

        # Max consecutive losses
        max_consecutive_losses = 0
        current_losses = 0

        for trade in trades:
            if trade['pnl'] <= 0:
                current_losses += 1
                max_consecutive_losses = max(
                    max_consecutive_losses, current_losses)
            else:
                current_losses = 0

        # Profit factor
        gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
        profit_factor = gross_profit / \
            gross_loss if gross_loss > 0 else float('inf')

        # Calmar ratio (annual return / max drawdown)
        if max_drawdown > 0:
            calmar_ratio = total_return / max_drawdown
        else:
            calmar_ratio = float('inf')

        return BacktestResult(
            model_name=model_name,
            symbol=symbol,
            start_date=data['timestamp'].min(),
            end_date=data['timestamp'].max(),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            avg_trade_return=avg_trade_return,
            max_consecutive_losses=max_consecutive_losses,
            profit_factor=profit_factor,
            calmar_ratio=calmar_ratio
        )

    def compare_models(
        self,
        model_names: List[str],
        symbol: str,
        historical_data: pd.DataFrame,
        **backtest_kwargs
    ) -> List[BacktestResult]:
        """
        Compare multiple models on the same data.

        Returns sorted list of results (best Sharpe first).
        """
        results = []

        for model_name in model_names:
            try:
                result = self.backtest_model(
                    model_name, symbol, historical_data, **backtest_kwargs
                )
                results.append(result)
            except Exception as e:
                self.logger.error(f"Failed to backtest {model_name}: {e}")
                continue

        # Sort by Sharpe ratio (descending)
        results.sort(key=lambda x: x.sharpe_ratio, reverse=True)

        return results
