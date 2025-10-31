#!/usr/bin/env python3
"""
Aurora Metrics Collector

Collects and aggregates trading metrics for monitoring and analysis.
Tracks trade success rates, rejection patterns, and system performance.
"""

import time
import threading
from typing import Dict, Any, List, Optional
from collections import defaultdict, deque
import logging


class MetricsCollector:
    """
    Aurora Metrics Collector for trading system monitoring.

    Collects metrics on trade intents, decisions, executions, and rejections
    to provide insights into system performance and identify issues.
    """

    def __init__(self, window_size_minutes: int = 60):
        """
        Initialize Metrics Collector.

        Args:
            window_size_minutes: Rolling window size for metrics aggregation
        """
        self.window_size_seconds = window_size_minutes * 60
        self.logger = logging.getLogger(__name__)

        # Thread-safe storage for metrics
        self._lock = threading.RLock()
        self._metrics = {
            "trade_intents_total": 0,
            "trade_decisions_accepted": 0,
            "trade_decisions_rejected": 0,
            "guard_rejections_cooldown": 0,
            "guard_rejections_other": 0,
            "executions_placed": 0,
            "executions_filled": 0,
            "executions_cancelled": 0,
            "executions_rejected": 0,
            # New correlation metrics
            "open_success_total": 0,
            "cmd_open_total": 0,
            "defer_rate": 0.0,
            "block_rate": 0.0,
            "retry_count": 0,
            "qos_cooldown_hits": 0,
            "time_to_open_ms_sum": 0.0,
            "time_to_open_count": 0,
            # EXP-FIX: Exposure gate metrics
            "exposure_fail_closed_total": defaultdict(int),
            "postfill_hold_active": 0,
            "postfill_hold_expired_total": 0,
            "exposure_mismatch_total": defaultdict(int),
        }

        # Rolling window data for time-based analysis
        self._rolling_data: deque = deque(maxlen=10000)  # Store last 10k events

        # Per-symbol metrics
        self._symbol_metrics: defaultdict = defaultdict(
            lambda: {
                "intents": 0,
                "accepted": 0,
                "rejected": 0,
                "cooldown_rejects": 0,
                "last_trade_time": 0.0,
            }
        )

    def record_trade_intent(self, symbol: str, side: str, **extra_data) -> None:
        """Record a trade intent."""
        with self._lock:
            self._metrics["trade_intents_total"] += 1
            self._symbol_metrics[symbol]["intents"] += 1

            event = {
                "type": "intent",
                "symbol": symbol,
                "side": side,
                "timestamp": time.time(),
                **extra_data,
            }
            self._rolling_data.append(event)

    def record_trade_decision(
        self,
        symbol: str,
        side: str,
        decision: str,
        reason: Optional[str] = None,
        **extra_data,
    ) -> None:
        """Record a trade decision (accepted/rejected)."""
        with self._lock:
            if decision.upper() == "ACCEPTED":
                self._metrics["trade_decisions_accepted"] += 1
                self._symbol_metrics[symbol]["accepted"] += 1
                self._symbol_metrics[symbol]["last_trade_time"] = time.time()
            else:
                self._metrics["trade_decisions_rejected"] += 1
                self._symbol_metrics[symbol]["rejected"] += 1

                # Track rejection reasons
                if reason and "cooldown" in reason.lower():
                    self._metrics["guard_rejections_cooldown"] += 1
                    self._symbol_metrics[symbol]["cooldown_rejects"] += 1
                else:
                    self._metrics["guard_rejections_other"] += 1

            event = {
                "type": "decision",
                "symbol": symbol,
                "side": side,
                "decision": decision,
                "reason": reason,
                "timestamp": time.time(),
                **extra_data,
            }
            self._rolling_data.append(event)

    def record_trade_execution(
        self, symbol: str, side: str, status: str, **extra_data
    ) -> None:
        """Record a trade execution status."""
        with self._lock:
            status_key = f"executions_{status.lower()}"
            if status_key in self._metrics:
                self._metrics[status_key] += 1

            event = {
                "type": "execution",
                "symbol": symbol,
                "side": side,
                "status": status,
                "timestamp": time.time(),
                **extra_data,
            }
            self._rolling_data.append(event)

    def record_exposure_fail_closed(self, reason: str) -> None:
        """EXP-FIX: Record exposure fail-closed event."""
        with self._lock:
            self._metrics["exposure_fail_closed_total"][reason] += 1

    def record_postfill_hold(self, active_count: int) -> None:
        """EXP-FIX: Record post-fill hold status."""
        with self._lock:
            self._metrics["postfill_hold_active"] = active_count

    def record_postfill_expired(self) -> None:
        """EXP-FIX: Record expired post-fill hold."""
        with self._lock:
            self._metrics["postfill_hold_expired_total"] += 1

    def record_postfill_released(self) -> None:
        """EXP-FIX: Record released post-fill hold."""
        with self._lock:
            self._metrics["postfill_hold_released_total"] = (
                self._metrics.get("postfill_hold_released_total", 0) + 1
            )

    def record_cmd_open(self) -> None:
        """Record CMD:OPEN received."""
        with self._lock:
            self._metrics["cmd_open_total"] += 1

    def record_open_success(self) -> None:
        """Record successful DEC:OPEN."""
        with self._lock:
            self._metrics["open_success_total"] += 1

    def record_time_to_open(self, ms: float) -> None:
        """Record time from CMD:OPEN to DEC:OPEN in ms."""
        with self._lock:
            self._metrics["time_to_open_ms_sum"] += ms
            self._metrics["time_to_open_count"] += 1

    def record_retry(self, reason: str) -> None:
        """Record retry event."""
        with self._lock:
            self._metrics["retry_count"] += 1

    def record_qos_cooldown_hit(self) -> None:
        """Record QoS cooldown hit."""
        with self._lock:
            self._metrics["qos_cooldown_hits"] += 1

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Get summary metrics for the entire system."""
        with self._lock:
            total_decisions = (
                self._metrics["trade_decisions_accepted"]
                + self._metrics["trade_decisions_rejected"]
            )

            acceptance_rate = (
                self._metrics["trade_decisions_accepted"] / total_decisions
                if total_decisions > 0
                else 0.0
            )

            rejection_rate = (
                self._metrics["trade_decisions_rejected"] / total_decisions
                if total_decisions > 0
                else 0.0
            )

            # New metrics calculations
            cmd_open_total = self._metrics["cmd_open_total"]
            defer_rate = (
                self._metrics["guard_rejections_other"] / cmd_open_total
                if cmd_open_total > 0
                else 0.0
            )
            block_rate = (
                self._metrics["qos_cooldown_hits"] / cmd_open_total
                if cmd_open_total > 0
                else 0.0
            )
            mean_time_to_open_ms = (
                self._metrics["time_to_open_ms_sum"] / self._metrics["time_to_open_count"]
                if self._metrics["time_to_open_count"] > 0
                else 0.0
            )

            return {
                "total_intents": self._metrics["trade_intents_total"],
                "total_accepted": self._metrics["trade_decisions_accepted"],
                "total_rejected": self._metrics["trade_decisions_rejected"],
                "acceptance_rate": acceptance_rate,
                "rejection_rate": rejection_rate,
                "cooldown_rejections": self._metrics["guard_rejections_cooldown"],
                "other_rejections": self._metrics["guard_rejections_other"],
                "executions_placed": self._metrics["executions_placed"],
                "executions_filled": self._metrics["executions_filled"],
                "executions_cancelled": self._metrics["executions_cancelled"],
                "executions_rejected": self._metrics["executions_rejected"],
                # New correlation metrics
                "open_success_total": self._metrics["open_success_total"],
                "cmd_open_total": self._metrics["cmd_open_total"],
                "mean_time_to_open_ms": mean_time_to_open_ms,
                "defer_rate": defer_rate,
                "block_rate": block_rate,
                "retry_count": self._metrics["retry_count"],
                "qos_cooldown_hits": self._metrics["qos_cooldown_hits"],
                # EXP-FIX: Exposure gate metrics
                "exposure_fail_closed": dict(
                    self._metrics["exposure_fail_closed_total"]
                ),
                "postfill_hold_active": self._metrics["postfill_hold_active"],
                "postfill_hold_expired_total": self._metrics[
                    "postfill_hold_expired_total"
                ],
                "exposure_mismatch": dict(self._metrics["exposure_mismatch_total"]),
            }

    def get_symbol_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get metrics for a specific symbol."""
        with self._lock:
            metrics = self._symbol_metrics[symbol].copy()
            total_decisions = metrics["accepted"] + metrics["rejected"]

            if total_decisions > 0:
                metrics["acceptance_rate"] = metrics["accepted"] / total_decisions
                metrics["rejection_rate"] = metrics["rejected"] / total_decisions
                metrics["cooldown_rejection_rate"] = (
                    metrics["cooldown_rejects"] / total_decisions
                )
            else:
                metrics["acceptance_rate"] = 0.0
                metrics["rejection_rate"] = 0.0
                metrics["cooldown_rejection_rate"] = 0.0

            return metrics

    def get_recent_rejections(self, minutes: int = 5) -> List[Dict[str, Any]]:
        """Get recent rejection events within the specified time window."""
        with self._lock:
            cutoff_time = time.time() - (minutes * 60)
            recent_rejections = []

            for event in reversed(self._rolling_data):
                if event["timestamp"] < cutoff_time:
                    break
                if (
                    event.get("type") == "decision"
                    and event.get("decision") != "ACCEPTED"
                ):
                    recent_rejections.append(event)

            return recent_rejections

    def get_rejection_patterns(self) -> Dict[str, Any]:
        """Analyze rejection patterns to identify common issues."""
        with self._lock:
            patterns: Dict[str, Any] = {
                "cooldown_dominant": False,
                "high_rejection_rate": False,
                "problem_symbols": [],
                "recent_rejection_spike": False,
            }

            # Check if cooldown is the dominant rejection reason
            total_rejections = (
                self._metrics["guard_rejections_cooldown"]
                + self._metrics["guard_rejections_other"]
            )
            if total_rejections > 0:
                cooldown_ratio = (
                    self._metrics["guard_rejections_cooldown"] / total_rejections
                )
                patterns["cooldown_dominant"] = cooldown_ratio > 0.8

            # Check overall rejection rate
            summary = self.get_summary_metrics()
            patterns["high_rejection_rate"] = summary["rejection_rate"] > 0.5

            # Find problem symbols (high rejection rate)
            for symbol, metrics in self._symbol_metrics.items():
                total_decisions = metrics["accepted"] + metrics["rejected"]
                if total_decisions >= 10:  # Minimum sample size
                    rejection_rate = metrics["rejected"] / total_decisions
                    if rejection_rate > 0.7:  # 70% rejection threshold
                        patterns["problem_symbols"].append(
                            {
                                "symbol": symbol,
                                "rejection_rate": rejection_rate,
                                "total_decisions": total_decisions,
                            }
                        )

            # Check for recent rejection spike (last 5 minutes vs last hour)
            recent_5min = self.get_recent_rejections(5)
            recent_60min = self.get_recent_rejections(60)

            if len(recent_60min) > 10:  # Minimum sample
                rate_5min = len(recent_5min) / 5  # rejections per minute
                rate_60min = len(recent_60min) / 60
                patterns["recent_rejection_spike"] = rate_5min > (rate_60min * 2)

            return patterns

    def reset(self) -> None:
        """Reset all metrics (useful for testing)."""
        with self._lock:
            self._metrics = {
                "trade_intents_total": 0,
                "trade_decisions_accepted": 0,
                "trade_decisions_rejected": 0,
                "guard_rejections_cooldown": 0,
                "guard_rejections_other": 0,
                "executions_placed": 0,
                "executions_filled": 0,
                "executions_cancelled": 0,
                "executions_rejected": 0,
                # New correlation metrics
                "open_success_total": 0,
                "cmd_open_total": 0,
                "defer_rate": 0.0,
                "block_rate": 0.0,
                "retry_count": 0,
                "qos_cooldown_hits": 0,
                "time_to_open_ms_sum": 0.0,
                "time_to_open_count": 0,
                # EXP-FIX: Exposure gate metrics
                "exposure_fail_closed_total": defaultdict(int),
                "postfill_hold_active": 0,
                "postfill_hold_expired_total": 0,
                "exposure_mismatch_total": defaultdict(int),
            }
            self._symbol_metrics.clear()
            self._rolling_data.clear()
