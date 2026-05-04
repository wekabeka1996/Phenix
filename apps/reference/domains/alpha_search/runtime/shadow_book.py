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
"""

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


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


class ShadowBook:
    """
    Per-scenario shadow PnL tracking with advanced metrics.

    Receives score results from ScenarioWorker and maintains
    virtual positions for PnL calculation.
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
        total = len(self._trades)
        wins = sum(1 for t in self._trades if t.pnl > 0)
        losses = sum(1 for t in self._trades if t.pnl <= 0)

        return {
            "scenario_id": self._scenario_id,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / max(total, 1), 4),
            "cumulative_pnl": round(self._cumulative_pnl, 4),
            "max_drawdown": round(self._max_drawdown, 4),
            "sharpe_ratio": self._calc_sharpe(),
            "avg_pnl_per_trade": round(
                self._cumulative_pnl / max(total, 1), 4
            ),
            "notional_size": self._notional_size,
        }

    def _calc_sharpe(self, risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio from trade PnL history."""
        if len(self._pnl_history) < 2:
            return 0.0

        mean_pnl = sum(self._pnl_history) / len(self._pnl_history)
        variance = sum(
            (p - mean_pnl) ** 2 for p in self._pnl_history
        ) / (len(self._pnl_history) - 1)

        std_pnl = math.sqrt(variance) if variance > 0 else 0.0
        if std_pnl == 0:
            return 0.0

        return round((mean_pnl - risk_free_rate) / std_pnl, 4)

    @property
    def trades(self) -> List[ShadowTrade]:
        return self._trades

    @property
    def cumulative_pnl(self) -> float:
        return self._cumulative_pnl
