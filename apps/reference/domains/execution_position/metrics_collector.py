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

    def __init__(self, window_size_minutes: int = 60, config: Optional[Any] = None):
        """
        Initialize Metrics Collector.

        Args:
            window_size_minutes: Rolling window size for metrics aggregation
        """
        self.window_size_seconds = window_size_minutes * 60
        self.logger = logging.getLogger(__name__)

        # Thread-safe storage for metrics
        self._lock = threading.RLock()
        self._metrics: Dict[str, Any] = {
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
            # Order timeout metrics
            "order_timeout_total": 0,
        }

        # Rolling window data for time-based analysis
        self._rolling_data: deque = deque(
            maxlen=10000)  # Store last 10k events

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
            trade_intents: int = int(
                self._metrics.get("trade_intents_total", 0))
            self._metrics["trade_intents_total"] = trade_intents + 1
            symbol_intents: int = int(
                self._symbol_metrics[symbol].get("intents", 0))
            self._symbol_metrics[symbol]["intents"] = symbol_intents + 1

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
                trade_accepted: int = int(
                    self._metrics.get("trade_decisions_accepted", 0))
                self._metrics["trade_decisions_accepted"] = trade_accepted + 1
                symbol_accepted: int = int(
                    self._symbol_metrics[symbol].get("accepted", 0))
                self._symbol_metrics[symbol]["accepted"] = symbol_accepted + 1
                self._symbol_metrics[symbol]["last_trade_time"] = time.time()
            else:
                trade_rejected: int = int(
                    self._metrics.get("trade_decisions_rejected", 0))
                self._metrics["trade_decisions_rejected"] = trade_rejected + 1
                symbol_rejected: int = int(
                    self._symbol_metrics[symbol].get("rejected", 0))
                self._symbol_metrics[symbol]["rejected"] = symbol_rejected + 1

                # Track rejection reasons
                if reason and "cooldown" in reason.lower():
                    cooldown_rejects: int = int(
                        self._metrics.get("guard_rejections_cooldown", 0))
                    self._metrics["guard_rejections_cooldown"] = cooldown_rejects + 1
                    symbol_cooldown: int = int(
                        self._symbol_metrics[symbol].get("cooldown_rejects", 0))
                    self._symbol_metrics[symbol]["cooldown_rejects"] = symbol_cooldown + 1
                else:
                    guard_other: int = int(
                        self._metrics.get("guard_rejections_other", 0))
                    self._metrics["guard_rejections_other"] = guard_other + 1

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
                exec_count: int = int(self._metrics.get(status_key, 0))
                self._metrics[status_key] = exec_count + 1

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
            fail_closed_dict: Dict[str, int] = self._metrics.get(
                "exposure_fail_closed_total", {})
            if isinstance(fail_closed_dict, dict):
                current_count: int = int(fail_closed_dict.get(reason, 0))
                fail_closed_dict[reason] = current_count + 1

    def record_postfill_hold(self, active_count: int) -> None:
        """EXP-FIX: Record post-fill hold status."""
        with self._lock:
            self._metrics["postfill_hold_active"] = active_count

    def record_postfill_expired(self) -> None:
        """EXP-FIX: Record expired post-fill hold."""
        with self._lock:
            expired_total: int = int(self._metrics.get(
                "postfill_hold_expired_total", 0))
            self._metrics["postfill_hold_expired_total"] = expired_total + 1

    def record_postfill_released(self) -> None:
        """EXP-FIX: Record released post-fill hold."""
        with self._lock:
            released_total: int = int(self._metrics.get(
                "postfill_hold_released_total", 0))
            self._metrics["postfill_hold_released_total"] = released_total + 1

    def record_cmd_open(self) -> None:
        """Record CMD:OPEN received."""
        with self._lock:
            cmd_open: int = int(self._metrics.get("cmd_open_total", 0))
            self._metrics["cmd_open_total"] = cmd_open + 1

    def record_open_success(self) -> None:
        """Record successful DEC:OPEN."""
        with self._lock:
            open_success: int = int(self._metrics.get("open_success_total", 0))
            self._metrics["open_success_total"] = open_success + 1

    def record_time_to_open(self, ms: float) -> None:
        """Record time from CMD:OPEN to DEC:OPEN in ms."""
        with self._lock:
            time_sum: float = float(
                self._metrics.get("time_to_open_ms_sum", 0.0))
            self._metrics["time_to_open_ms_sum"] = time_sum + ms
            time_count: int = int(self._metrics.get("time_to_open_count", 0))
            self._metrics["time_to_open_count"] = time_count + 1

    def record_retry(self, reason: str) -> None:
        """Record retry event."""
        with self._lock:
            retry: int = int(self._metrics.get("retry_count", 0))
            self._metrics["retry_count"] = retry + 1

    def record_qos_cooldown_hit(self) -> None:
        """Record QoS cooldown hit."""
        with self._lock:
            qos_hits: int = int(self._metrics.get("qos_cooldown_hits", 0))
            self._metrics["qos_cooldown_hits"] = qos_hits + 1

    def record_order_timeout(self) -> None:
        """Record order timeout event."""
        with self._lock:
            timeout_total: int = int(
                self._metrics.get("order_timeout_total", 0))
            self._metrics["order_timeout_total"] = timeout_total + 1

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Get summary metrics for the entire system."""
        with self._lock:
            trade_decisions_accepted: int = int(
                self._metrics.get("trade_decisions_accepted", 0))
            trade_decisions_rejected: int = int(
                self._metrics.get("trade_decisions_rejected", 0))
            total_decisions = trade_decisions_accepted + trade_decisions_rejected

            acceptance_rate = (
                float(trade_decisions_accepted) / float(total_decisions)
                if total_decisions > 0
                else 0.0
            )

            rejection_rate = (
                float(trade_decisions_rejected) / float(total_decisions)
                if total_decisions > 0
                else 0.0
            )

            # New metrics calculations
            cmd_open_total: int = int(self._metrics.get("cmd_open_total", 0))
            guard_rejections_other: int = int(
                self._metrics.get("guard_rejections_other", 0))
            defer_rate = (
                float(guard_rejections_other) / float(cmd_open_total)
                if cmd_open_total > 0
                else 0.0
            )
            qos_cooldown_hits: int = int(
                self._metrics.get("qos_cooldown_hits", 0))
            block_rate = (
                float(qos_cooldown_hits) / float(cmd_open_total)
                if cmd_open_total > 0
                else 0.0
            )
            mean_time_to_open_ms = (
                float(self._metrics.get("time_to_open_ms_sum", 0.0)) /
                float(self._metrics.get("time_to_open_count", 1))
                if int(self._metrics.get("time_to_open_count", 0)) > 0
                else 0.0
            )

            return {
                "total_intents": int(self._metrics.get("trade_intents_total", 0)),
                "total_accepted": int(self._metrics.get("trade_decisions_accepted", 0)),
                "total_rejected": int(self._metrics.get("trade_decisions_rejected", 0)),
                "acceptance_rate": acceptance_rate,
                "rejection_rate": rejection_rate,
                "cooldown_rejections": int(self._metrics.get("guard_rejections_cooldown", 0)),
                "other_rejections": int(self._metrics.get("guard_rejections_other", 0)),
                "executions_placed": int(self._metrics.get("executions_placed", 0)),
                "executions_filled": int(self._metrics.get("executions_filled", 0)),
                "executions_cancelled": int(self._metrics.get("executions_cancelled", 0)),
                "executions_rejected": int(self._metrics.get("executions_rejected", 0)),
                # New correlation metrics
                "open_success_total": int(self._metrics.get("open_success_total", 0)),
                "cmd_open_total": int(self._metrics.get("cmd_open_total", 0)),
                "mean_time_to_open_ms": mean_time_to_open_ms,
                "defer_rate": defer_rate,
                "block_rate": block_rate,
                "retry_count": int(self._metrics.get("retry_count", 0)),
                "qos_cooldown_hits": int(self._metrics.get("qos_cooldown_hits", 0)),
                # EXP-FIX: Exposure gate metrics
                "exposure_fail_closed": dict(
                    self._metrics.get("exposure_fail_closed_total", {})
                ),
                "postfill_hold_active": int(self._metrics.get("postfill_hold_active", 0)),
                "postfill_hold_expired_total": int(self._metrics.get(
                    "postfill_hold_expired_total", 0
                )),
                "exposure_mismatch": dict(self._metrics.get("exposure_mismatch_total", {})),
                # Order timeout metrics
                "order_timeout_total": int(self._metrics.get("order_timeout_total", 0)),
            }

    def get_symbol_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get metrics for a specific symbol."""
        with self._lock:
            metrics = self._symbol_metrics[symbol].copy()
            total_decisions = metrics["accepted"] + metrics["rejected"]

            if total_decisions > 0:
                metrics["acceptance_rate"] = metrics["accepted"] / \
                    total_decisions
                metrics["rejection_rate"] = metrics["rejected"] / \
                    total_decisions
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
            guard_cooldown: int = int(
                self._metrics.get("guard_rejections_cooldown", 0))
            guard_other: int = int(
                self._metrics.get("guard_rejections_other", 0))
            total_rejections = guard_cooldown + guard_other
            if total_rejections > 0:
                cooldown_ratio = (
                    float(guard_cooldown) /
                    float(total_rejections)
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
                patterns["recent_rejection_spike"] = rate_5min > (
                    rate_60min * 2)

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
                # Order timeout metrics
                "order_timeout_total": 0,
            }
            self._symbol_metrics.clear()
            self._rolling_data.clear()
