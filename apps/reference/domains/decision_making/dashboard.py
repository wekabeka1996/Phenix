import logging
from collections import deque
from enum import Enum
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import statistics

from apps.reference.config_models import DashboardConfig

logger = logging.getLogger(__name__)


@dataclass
class TradeOutcome:
    """Recorded trade outcome for metrics."""
    symbol: str
    entry_ts: float
    exit_ts: Optional[float]
    pnl_percent: float  # Percentage
    duration_sec: float
    is_win: bool


class DashboardMetrics:
    """
    Computes and tracks strategy performance metrics over a rolling window.
    Metrics: Sharpe Ratio, Win Rate, Memory Coverage.
    """
    def __init__(self, config: DashboardConfig):
        self.config = config
        self.window_size = self.config.sharpe_window_days * 24 * 60 * 60  # seconds
        
        # In-memory storage for rolling calculation
        # In production this might be backed by DB/WAL
        self.closed_trades: deque[TradeOutcome] = deque() # Sorted by exit_ts
        self.memory_states_count: int = 54 # Total theoretical states
        self.covered_states: set = set()
        
        logger.info(f"DashboardMetrics initialized. Window: {self.config.sharpe_window_days} days.")

    def record_trade(self, outcome: TradeOutcome):
        """Add a closed trade to the history."""
        self.closed_trades.append(outcome)
        self._prune_history(outcome.exit_ts)
        
    def record_state_visit(self, state_hash: str):
        """Mark a memory state as visited."""
        self.covered_states.add(state_hash)

    def _prune_history(self, current_ts: float):
        """Remove trades older than window_size."""
        cutoff = current_ts - self.window_size
        while self.closed_trades and self.closed_trades[0].exit_ts < cutoff:
            self.closed_trades.popleft()

    def get_metrics(self) -> Dict[str, Any]:
        """Compute current metrics based on window."""
        metrics = {}
        
        if "data_points" not in metrics:
            metrics["data_points"] = len(self.closed_trades)

        if "win_rate" in self.config.metrics:
            wins = sum(1 for t in self.closed_trades if t.is_win)
            total = len(self.closed_trades)
            metrics["win_rate"] = (wins / total * 100.0) if total > 0 else 0.0
            
        if "sharpe_ratio" in self.config.metrics:
            # Simplified Annualized Sharpe (assuming risk-free 0)
            # Sharpe = Mean(Returns) / StdDev(Returns) * sqrt(252) usually
            # We use local window stats
            pnls = [t.pnl_percent for t in self.closed_trades]
            if len(pnls) > 1:
                mean_ret = statistics.mean(pnls)
                std_dev = statistics.stdev(pnls)
                if std_dev > 1e-6:
                    # Annualize roughly assuming N trades per day? 
                    # Or just return raw ratio for this window. 
                    # Standard practice for HFT/bot: Sharpe per trade * sqrt(Annual Trades)
                    # Let's return raw Mean/StdDev for now to avoid misleading "Annualized"
                    metrics["sharpe_ratio_raw"] = mean_ret / std_dev
                else:
                    metrics["sharpe_ratio_raw"] = 0.0
            else:
                metrics["sharpe_ratio_raw"] = 0.0

        if "memory_coverage" in self.config.metrics:
            metrics["memory_coverage"] = (len(self.covered_states) / self.memory_states_count) * 100.0
            
        return metrics
