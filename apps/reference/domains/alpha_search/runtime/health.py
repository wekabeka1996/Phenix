"""
Health Monitor
==============

Periodic health checks for all scenario workers:
- Heartbeat tracking (last processed timestamp)
- Memory estimation per scenario
- Degradation: mark scenario degraded on consecutive failures
"""

import logging
import sys
import time
from typing import Any, Dict, Optional, Set

from .contracts import RuntimeConfig

LOG = logging.getLogger(__name__)


class HealthMonitor:
    """
    Monitors health of scenario workers and triggers degradation.

    Workers are marked degraded if they exceed consecutive failure threshold.
    Degraded workers are skipped during fan-out until recovered.
    """

    CONSECUTIVE_FAILURE_THRESHOLD = 3

    def __init__(self, config: RuntimeConfig):
        self._memory_budget_mb = config.memory_budget_mb_per_scenario
        self._heartbeat_sec = config.health_heartbeat_sec

        # Per-scenario state
        self._last_heartbeat: Dict[str, float] = {}
        self._consecutive_failures: Dict[str, int] = {}
        self._degraded: Set[str] = set()

        # Global stats
        self._total_checks = 0
        self._total_degradations = 0

    def record_success(self, scenario_id: str) -> None:
        """Record a successful snapshot processing."""
        self._last_heartbeat[scenario_id] = time.time()
        if self._consecutive_failures.get(scenario_id, 0) > 0:
            self._consecutive_failures[scenario_id] = 0
        # Auto-recover from degradation on success
        if scenario_id in self._degraded:
            self._degraded.discard(scenario_id)
            LOG.info(f"[{scenario_id}] Recovered from degraded state")

    def record_failure(self, scenario_id: str, error: Optional[str] = None) -> None:
        """Record a failed snapshot processing."""
        count = self._consecutive_failures.get(scenario_id, 0) + 1
        self._consecutive_failures[scenario_id] = count

        if count >= self.CONSECUTIVE_FAILURE_THRESHOLD:
            if scenario_id not in self._degraded:
                self._degraded.add(scenario_id)
                self._total_degradations += 1
                LOG.warning(
                    f"[{scenario_id}] DEGRADED after {count} consecutive failures"
                    f"{f': {error}' if error else ''}"
                )

    def is_degraded(self, scenario_id: str) -> bool:
        """Check if a scenario is currently degraded."""
        return scenario_id in self._degraded

    def check_health(
        self,
        worker_ids: list,
    ) -> Dict[str, str]:
        """
        Run health check on all known workers.

        Returns:
            {scenario_id: "healthy" | "degraded" | "stale"}
        """
        self._total_checks += 1
        now = time.time()
        statuses = {}

        for sid in worker_ids:
            if sid in self._degraded:
                statuses[sid] = "degraded"
            elif sid in self._last_heartbeat:
                age = now - self._last_heartbeat[sid]
                if age > self._heartbeat_sec * 3:
                    statuses[sid] = "stale"
                else:
                    statuses[sid] = "healthy"
            else:
                statuses[sid] = "unknown"

        return statuses

    @property
    def degraded_scenarios(self) -> Set[str]:
        return self._degraded.copy()

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_checks": self._total_checks,
            "total_degradations": self._total_degradations,
            "currently_degraded": list(self._degraded),
            "heartbeat_ages": {
                sid: round(time.time() - ts, 1)
                for sid, ts in self._last_heartbeat.items()
            },
        }
