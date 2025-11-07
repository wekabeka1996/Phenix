# apps/reference/monitoring/performance_monitor.py
"""
Performance Monitor for Phenix v1.

Tracks decision path performance metrics:
- p95 latency (SLO: 50ms overall, 100ms)
- timeout_rate < 1%
- WHY-coverage 95%

Provides real-time monitoring and alerting.
"""

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from statistics import quantiles
import json


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot."""
    timestamp: datetime
    total_decisions: int = 0
    successful_decisions: int = 0
    failed_decisions: int = 0
    timeouts: int = 0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    timeout_rate: float = 0.0
    slo_violations: int = 0
    why_coverage: float = 0.0


@dataclass
class DecisionTiming:
    """Timing data for a single decision."""
    rid: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    success: bool = False
    timeout: bool = False
    why_chain_length: int = 0
    error_message: Optional[str] = None


@dataclass
class SLOConfig:
    """SLO configuration."""
    p95_target_ms: float = 50.0  # p95 decision latency target
    p95_overall_target_ms: float = 100.0  # Overall p95 target
    timeout_rate_target: float = 0.01  # 1% timeout rate
    why_coverage_target: float = 0.95  # 95% WHY coverage
    alert_cooldown_minutes: int = 5  # Minutes between alerts


class PerformanceMonitor:
    """
    Monitors decision path performance and SLO compliance.

    Tracks latency, timeouts, and WHY coverage with configurable alerts.
    """

    def __init__(
        self,
        slo_config: Optional[SLOConfig] = None,
        max_samples: int = 10000,  # Keep last 10k decisions
        logger: Optional[logging.Logger] = None
    ):
        self.config = slo_config or SLOConfig()
        self.logger = logger or logging.getLogger(__name__)

        # Thread-safe storage for timing data
        self._timings: deque[DecisionTiming] = deque(maxlen=max_samples)
        self._lock = threading.RLock()

        # Alert state
        self._last_alert_time: Optional[datetime] = None
        self._alert_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []

        # Background monitoring
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False

        self.logger.info("PerformanceMonitor initialized")

    def start_decision(self, rid: str) -> str:
        """
        Start timing a decision.

        Returns timing_id for use with end_decision().
        """
        timing_id = f"{time.time()}_{rid}"  # Put timestamp first to avoid RID parsing issues
        timing = DecisionTiming(
            rid=rid,
            start_time=time.time(),
            timeout=False
        )

        with self._lock:
            self._timings.append(timing)

        self.logger.debug(f"Started timing decision for RID {rid}")
        return timing_id

    def end_decision(
        self,
        timing_id: str,
        success: bool = True,
        why_chain_length: int = 0,
        error_message: Optional[str] = None
    ) -> None:
        """
        End timing a decision.

        Args:
            timing_id: ID returned by start_decision()
            success: Whether decision was successful
            why_chain_length: Length of WHY chain (for coverage calculation)
            error_message: Error message if failed
        """
        rid = timing_id.split(
            '_', 1)[1]  # Extract RID (everything after first underscore)

        with self._lock:
            # Find the timing record
            for timing in reversed(self._timings):
                if timing.rid == rid and timing.end_time is None:
                    timing.end_time = time.time()
                    timing.duration_ms = (
                        timing.end_time - timing.start_time) * 1000
                    timing.success = success
                    timing.why_chain_length = why_chain_length
                    timing.error_message = error_message
                    break
            else:
                self.logger.warning(f"No active timing found for RID {rid}")
                return

        self.logger.debug(
            f"Ended timing for RID {rid}: {timing.duration_ms:.2f}ms, success={success}"
        )

    def record_timeout(self, rid: str) -> None:
        """Record a timeout for a decision."""
        with self._lock:
            # Find and mark as timeout
            for timing in reversed(self._timings):
                if timing.rid == rid and timing.end_time is None:
                    timing.timeout = True
                    timing.end_time = time.time()
                    timing.duration_ms = (
                        timing.end_time - timing.start_time) * 1000
                    break

        self.logger.warning(f"Recorded timeout for RID {rid}")

    def get_current_metrics(self) -> PerformanceMetrics:
        """Get current performance metrics."""
        with self._lock:
            if not self._timings:
                return PerformanceMetrics(timestamp=datetime.now())

            # Get completed timings
            completed = [t for t in self._timings if t.end_time is not None]
            if not completed:
                return PerformanceMetrics(timestamp=datetime.now())

            # Calculate metrics
            durations = [
                t.duration_ms for t in completed if t.duration_ms is not None]
            successful = [t for t in completed if t.success and not t.timeout]
            timeouts = [t for t in completed if t.timeout]
            failed = [t for t in completed if not t.success and not t.timeout]

            # Percentiles
            if len(durations) >= 2:
                percentiles = quantiles(durations, n=100)
                # 50th, 95th, 99th percentiles
                p50, p95, p99 = percentiles[49], percentiles[94], percentiles[98]
            elif len(durations) == 1:
                # All percentiles are the single value
                p50 = p95 = p99 = durations[0]
            else:
                p50 = p95 = p99 = 0.0

            # WHY coverage (decisions with WHY chain > 0)
            why_covered = sum(1 for t in completed if t.why_chain_length > 0)
            why_coverage = why_covered / len(completed) if completed else 0.0

            # SLO violations
            slo_violations = sum(1 for d in durations if d >
                                 self.config.p95_target_ms)

            return PerformanceMetrics(
                timestamp=datetime.now(),
                total_decisions=len(completed),
                successful_decisions=len(successful),
                failed_decisions=len(failed),
                timeouts=len(timeouts),
                p50_latency_ms=p50,
                p95_latency_ms=p95,
                p99_latency_ms=p99,
                timeout_rate=len(timeouts) /
                len(completed) if completed else 0.0,
                slo_violations=slo_violations,
                why_coverage=why_coverage
            )

    def check_slo_compliance(self) -> Dict[str, Any]:
        """Check SLO compliance and return status."""
        metrics = self.get_current_metrics()

        slo_status = {
            "p95_latency": {
                "current": metrics.p95_latency_ms,
                "target": self.config.p95_target_ms,
                "compliant": metrics.p95_latency_ms <= self.config.p95_target_ms
            },
            "timeout_rate": {
                "current": metrics.timeout_rate,
                "target": self.config.timeout_rate_target,
                "compliant": metrics.timeout_rate <= self.config.timeout_rate_target
            },
            "why_coverage": {
                "current": metrics.why_coverage,
                "target": self.config.why_coverage_target,
                "compliant": metrics.why_coverage >= self.config.why_coverage_target
            },
            "overall_compliant": all([
                metrics.p95_latency_ms <= self.config.p95_target_ms,
                metrics.timeout_rate <= self.config.timeout_rate_target,
                metrics.why_coverage >= self.config.why_coverage_target
            ])
        }

        return slo_status

    def add_alert_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Add callback for SLO violation alerts."""
        self._alert_callbacks.append(callback)

    def _send_alert(self, alert_type: str, data: Dict[str, Any]) -> None:
        """Send alert to all registered callbacks."""
        now = datetime.now()

        # Check cooldown
        if self._last_alert_time and (now - self._last_alert_time) < timedelta(minutes=self.config.alert_cooldown_minutes):
            return

        self._last_alert_time = now

        for callback in self._alert_callbacks:
            try:
                callback(alert_type, data)
            except Exception as e:
                self.logger.error(f"Error in alert callback: {e}")

    async def start_monitoring(self, check_interval_seconds: int = 60) -> None:
        """Start background monitoring task."""
        self._running = True
        self._monitoring_task = asyncio.create_task(
            self._background_monitoring(check_interval_seconds)
        )
        self.logger.info("Performance monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Performance monitoring stopped")

    async def _background_monitoring(self, check_interval_seconds: int) -> None:
        """Background task for SLO monitoring and alerting."""
        while self._running:
            try:
                await asyncio.sleep(check_interval_seconds)

                slo_status = self.check_slo_compliance()
                metrics = self.get_current_metrics()

                # Log current status
                self.logger.info(
                    f"Performance check: p95={metrics.p95_latency_ms:.1f}ms, "
                    f"timeouts={metrics.timeout_rate:.3%}, "
                    f"why_coverage={metrics.why_coverage:.1%}"
                )

                # Check for violations
                if not slo_status["overall_compliant"]:
                    violations = []
                    if not slo_status["p95_latency"]["compliant"]:
                        violations.append(
                            f"p95 latency {metrics.p95_latency_ms:.1f}ms > {self.config.p95_target_ms}ms"
                        )
                    if not slo_status["timeout_rate"]["compliant"]:
                        violations.append(
                            f"timeout rate {metrics.timeout_rate:.3%} > {self.config.timeout_rate_target:.1%}"
                        )
                    if not slo_status["why_coverage"]["compliant"]:
                        violations.append(
                            f"why coverage {metrics.why_coverage:.1%} < {self.config.why_coverage_target:.1%}"
                        )

                    alert_data = {
                        "violations": violations,
                        "metrics": {
                            "p95_latency_ms": metrics.p95_latency_ms,
                            "timeout_rate": metrics.timeout_rate,
                            "why_coverage": metrics.why_coverage,
                            "total_decisions": metrics.total_decisions
                        },
                        "timestamp": datetime.now().isoformat()
                    }

                    self.logger.warning(
                        f"SLO violations detected: {violations}")
                    self._send_alert("SLO_VIOLATION", alert_data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in background monitoring: {e}")

    def get_recent_timings(self, limit: int = 100) -> List[DecisionTiming]:
        """Get recent timing records."""
        with self._lock:
            return list(self._timings)[-limit:]

    def clear_old_data(self, max_age_hours: int = 24) -> int:
        """Clear timing data older than specified hours."""
        cutoff_time = time.time() - (max_age_hours * 3600)

        with self._lock:
            original_len = len(self._timings)
            self._timings = deque(
                [t for t in self._timings if t.start_time > cutoff_time],
                maxlen=self._timings.maxlen
            )
            cleared = original_len - len(self._timings)

        if cleared > 0:
            self.logger.info(f"Cleared {cleared} old timing records")

        return cleared

    def export_metrics_json(self) -> str:
        """Export current metrics as JSON string."""
        metrics = self.get_current_metrics()
        slo_status = self.check_slo_compliance()

        data = {
            "metrics": {
                "timestamp": metrics.timestamp.isoformat(),
                "total_decisions": metrics.total_decisions,
                "successful_decisions": metrics.successful_decisions,
                "failed_decisions": metrics.failed_decisions,
                "timeouts": metrics.timeouts,
                "p50_latency_ms": metrics.p50_latency_ms,
                "p95_latency_ms": metrics.p95_latency_ms,
                "p99_latency_ms": metrics.p99_latency_ms,
                "timeout_rate": metrics.timeout_rate,
                "slo_violations": metrics.slo_violations,
                "why_coverage": metrics.why_coverage
            },
            "slo_status": slo_status
        }

        return json.dumps(data, indent=2)
