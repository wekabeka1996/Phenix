"""In-process dashboard metrics for Aurora strategy diagnostics.

The helper keeps a rolling history of closed trades for trade-based metrics and
tracks coarse memory-state coverage for operator visibility. It does not write
to persistent storage on its own.
"""

import logging
import statistics
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, Optional

from apps.reference.config_models import DashboardConfig

logger = logging.getLogger(__name__)


@dataclass
class TradeOutcome:
    """Closed-trade outcome consumed by DashboardMetrics.

    ``exit_ts`` remains optional in the DTO, but dashboard pruning assumes the
    caller only records completed trades with a real exit timestamp.
    """
    symbol: str
    entry_ts: float
    exit_ts: Optional[float]
    pnl_percent: float  # Percentage
    duration_sec: float
    is_win: bool


class DashboardMetrics:
    """
    Compute lightweight operator metrics from in-memory strategy state.

    Trade-based metrics use a rolling window keyed by trade exit time. Memory
    coverage is cumulative for the lifetime of the process and is not pruned.
    """

    def __init__(self, config: DashboardConfig):
        self.config = config
        self.window_size = self.config.sharpe_window_days * 24 * 60 * 60  # seconds

        # Closed trades are appended in exit order by current callers, so deque
        # pruning stays O(k) from the left edge of the active window.
        self.closed_trades: deque[TradeOutcome] = deque()
        # MemoryShield documents ~54 coarse state buckets; coverage uses the
        # same denominator instead of deriving it dynamically at runtime.
        self.memory_states_count: int = 54
        self.covered_states: set[str] = set()

        logger.info(
            f"DashboardMetrics initialized. Window: {self.config.sharpe_window_days} days.")

    def record_trade(self, outcome: TradeOutcome) -> None:
        """Add a closed trade and prune the rolling trade window."""
        self.closed_trades.append(outcome)
        self._prune_history(outcome.exit_ts)

    def record_state_visit(self, state_hash: str) -> None:
        """Mark a coarse memory-shield state as visited for coverage metrics."""
        self.covered_states.add(state_hash)

    def _prune_history(self, current_ts: float) -> None:
        """Drop trades whose exit timestamp falls outside the active window."""
        cutoff = current_ts - self.window_size
        while self.closed_trades and self.closed_trades[0].exit_ts < cutoff:
            self.closed_trades.popleft()

    def get_metrics(self) -> Dict[str, Any]:
        """Compute the configured metrics plus the always-present data point count."""
        metrics = {}

        if "data_points" not in metrics:
            metrics["data_points"] = len(self.closed_trades)

        if "win_rate" in self.config.metrics:
            wins = sum(1 for t in self.closed_trades if t.is_win)
            total = len(self.closed_trades)
            metrics["win_rate"] = (wins / total * 100.0) if total > 0 else 0.0

        if "sharpe_ratio" in self.config.metrics:
            # The config flag keeps the familiar metric name, but the payload
            # intentionally reports a raw mean/stddev ratio rather than an
            # annualized Sharpe number.
            pnls = [t.pnl_percent for t in self.closed_trades]
            if len(pnls) > 1:
                mean_ret = statistics.mean(pnls)
                std_dev = statistics.stdev(pnls)
                if std_dev > 1e-6:
                    metrics["sharpe_ratio_raw"] = mean_ret / std_dev
                else:
                    metrics["sharpe_ratio_raw"] = 0.0
            else:
                metrics["sharpe_ratio_raw"] = 0.0

        if "memory_coverage" in self.config.metrics:
            metrics["memory_coverage"] = (
                len(self.covered_states) / self.memory_states_count) * 100.0

        return metrics
