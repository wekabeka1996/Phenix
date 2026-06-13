"""
Shadow Book
===========

Enhanced virtual PnL tracker per scenario.
Tracks metrics beyond the basic virtual trader in BacktestPlugin:
- Cumulative PnL
- Sharpe ratio (rolling)
- Maximum drawdown
- Win rate
- Trade log persistence
- Per-symbol breakdown
- Per-regime breakdown
- Temporal analysis (hour-of-day, day-of-week)
"""

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ShadowTrade:
    """Record of a completed shadow trade."""
    scenario_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    pnl: float
    entry_ts: int
    exit_ts: int
    bars_held: int
    provider_id: str
    regime: str = "DEFAULT"


class ShadowBook:
    """
    Per-scenario shadow PnL tracking with advanced metrics.

    Receives score results from ScenarioWorker and maintains
    virtual positions for PnL calculation.

    Supports granular breakdowns by symbol, regime, and temporal buckets.
    """

    def __init__(
        self,
        scenario_id: str,
        notional_size: float = 1000.0,
    ):
        self._scenario_id = scenario_id
        self._notional_size = notional_size

        # Trade history
        self._trades: List[ShadowTrade] = []

        # Running metrics
        self._cumulative_pnl: float = 0.0
        self._peak_equity: float = 0.0
        self._max_drawdown: float = 0.0
        self._pnl_history: List[float] = []  # per-trade PnL for Sharpe

    def record_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        entry_ts: int,
        exit_ts: int,
        bars_held: int,
        provider_id: str,
        regime: str = "DEFAULT",
    ) -> ShadowTrade:
        """Record a completed virtual trade and update metrics."""
        if side == "BUY":
            pnl = (exit_price - entry_price) / \
                entry_price * self._notional_size
        else:
            pnl = (entry_price - exit_price) / \
                entry_price * self._notional_size

        trade = ShadowTrade(
            scenario_id=self._scenario_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            bars_held=bars_held,
            provider_id=provider_id,
            regime=regime,
        )

        self._trades.append(trade)
        self._cumulative_pnl += pnl
        self._pnl_history.append(pnl)

        # Update drawdown
        self._peak_equity = max(self._peak_equity, self._cumulative_pnl)
        current_dd = self._peak_equity - self._cumulative_pnl
        self._max_drawdown = max(self._max_drawdown, current_dd)

        return trade

    def get_metrics(self) -> Dict[str, Any]:
        """Return comprehensive shadow metrics."""
        return {
            "scenario_id": self._scenario_id,
            **self._compute_metrics(self._trades),
            "notional_size": self._notional_size,
        }

    def get_metrics_by_symbol(self) -> Dict[str, Dict[str, Any]]:
        """Return metrics grouped by trading symbol."""
        groups: Dict[str, List[ShadowTrade]] = defaultdict(list)
        for t in self._trades:
            groups[t.symbol].append(t)
        return {
            symbol: {"symbol": symbol, **self._compute_metrics(trades)}
            for symbol, trades in sorted(groups.items())
        }

    def get_metrics_by_regime(self) -> Dict[str, Dict[str, Any]]:
        """Return metrics grouped by market regime."""
        groups: Dict[str, List[ShadowTrade]] = defaultdict(list)
        for t in self._trades:
            groups[t.regime].append(t)
        return {
            regime: {"regime": regime, **self._compute_metrics(trades)}
            for regime, trades in sorted(groups.items())
        }

    def get_metrics_by_symbol_and_regime(
        self,
    ) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Return cross-tabulated metrics: (symbol, regime) → metrics."""
        groups: Dict[Tuple[str, str], List[ShadowTrade]] = defaultdict(list)
        for t in self._trades:
            groups[(t.symbol, t.regime)].append(t)
        return {
            key: {"symbol": key[0], "regime": key[1], **self._compute_metrics(trades)}
            for key, trades in sorted(groups.items())
        }

    def get_metrics_by_hour(self) -> Dict[int, Dict[str, Any]]:
        """Return metrics grouped by hour of day (UTC, 0-23)."""
        groups: Dict[int, List[ShadowTrade]] = defaultdict(list)
        for t in self._trades:
            hour = self._ts_to_hour_utc(t.entry_ts)
            groups[hour].append(t)
        return {
            hour: {"hour_utc": hour, **self._compute_metrics(trades)}
            for hour, trades in sorted(groups.items())
        }

    def get_metrics_by_day_of_week(self) -> Dict[str, Dict[str, Any]]:
        """Return metrics grouped by day of week (UTC)."""
        groups: Dict[str, List[ShadowTrade]] = defaultdict(list)
        for t in self._trades:
            day_name = self._ts_to_day_name_utc(t.entry_ts)
            groups[day_name].append(t)
        # Sort by day order (Monday-Sunday)
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return {
            day: {"day_of_week": day, **self._compute_metrics(groups[day])}
            for day in day_order
            if day in groups
        }

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _compute_metrics(self, trades: List[ShadowTrade]) -> Dict[str, Any]:
        """Compute standard metrics for a list of trades."""
        total = len(trades)
        wins = sum(1 for t in trades if t.pnl > 0)
        losses = sum(1 for t in trades if t.pnl <= 0)
        pnl_list = [t.pnl for t in trades]
        cum_pnl = sum(pnl_list)

        # Drawdown
        peak = 0.0
        max_dd = 0.0
        equity = 0.0
        for p in pnl_list:
            equity += p
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / max(total, 1), 4),
            "cumulative_pnl": round(cum_pnl, 4),
            "max_drawdown": round(max_dd, 4),
            "sharpe_ratio": self._calc_sharpe_from_list(pnl_list),
            "avg_pnl_per_trade": round(cum_pnl / max(total, 1), 4),
        }

    def _calc_sharpe(self, risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio from trade PnL history."""
        return self._calc_sharpe_from_list(self._pnl_history, risk_free_rate)

    @staticmethod
    def _calc_sharpe_from_list(
        pnl_list: List[float],
        risk_free_rate: float = 0.0,
    ) -> float:
        """Calculate Sharpe ratio from a PnL list."""
        if len(pnl_list) < 2:
            return 0.0

        mean_pnl = sum(pnl_list) / len(pnl_list)
        variance = sum(
            (p - mean_pnl) ** 2 for p in pnl_list
        ) / (len(pnl_list) - 1)

        std_pnl = math.sqrt(variance) if variance > 0 else 0.0
        if std_pnl == 0:
            return 0.0

        return round((mean_pnl - risk_free_rate) / std_pnl, 4)

    @staticmethod
    def _ts_to_hour_utc(ts_ms: int) -> int:
        """Convert epoch milliseconds to hour of day (UTC)."""
        try:
            dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            return dt.hour
        except (OSError, OverflowError, ValueError):
            return 0

    @staticmethod
    def _ts_to_day_name_utc(ts_ms: int) -> str:
        """Convert epoch milliseconds to day name (UTC)."""
        try:
            dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            return dt.strftime("%A")
        except (OSError, OverflowError, ValueError):
            return "Unknown"

    @property
    def trades(self) -> List[ShadowTrade]:
        return self._trades

    @property
    def cumulative_pnl(self) -> float:
        return self._cumulative_pnl
