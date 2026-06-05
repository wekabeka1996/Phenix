"""
Health & metrics aggregation — Phase 14.2 extraction from fsm.py.

Encapsulates observability logic used by ExecPosFSM.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING

from apps.reference.core.time import get_clock
from apps.reference.utils.accessors import aget

if TYPE_CHECKING:
    pass

LOG = logging.getLogger(__name__)


class HealthMetricsMixin:
    """
    Mixin providing health checks and metrics aggregation for ExecPosFSM.

    Expects:
        self._flows_lock: threading.Lock
        self.open_flows: dict
        self.manage_flows: dict
        self.close_flows: dict
        self.watchdog: OrderTimeoutWatchdog
        self._orphan_metrics: dict
        self._orphan_cfg: dict
        self._gate_metrics: dict
        self._symbol_last_tidy_ts: dict
        self._last_entry_block_ts: dict
        self._guardian_unified: bool
        self._guardian_emit_tidy_event: bool
        self._guardian_emit_tidy_monitoring_event: bool
        self.adapter: Optional[BinanceAdapter]
        self._last_status_ts: float
        self._domain_bridge: DomainBridge
    """

    def get_metrics(self) -> Dict[str, Any]:
        """Aggregate metrics from all managed FSMs."""
        all_metrics: Dict[str, Any] = {}
        with self._flows_lock:
            for symbol, open_fsm in self.open_flows.items():
                all_metrics[f"{symbol}_open"] = open_fsm.get_metrics()
            for symbol, manage_fsm in self.manage_flows.items():
                all_metrics[f"{symbol}_manage"] = manage_fsm.get_metrics()
            for symbol, close_fsm in self.close_flows.items():
                all_metrics[f"{symbol}_close"] = close_fsm.get_metrics()

        # Include watchdog metrics
        if hasattr(self, 'watchdog'):
            all_metrics["order_timeout_watchdog"] = self.watchdog.get_metrics()

        # Include orphan-monitor metrics
        all_metrics["orphan_monitor"] = {
            **self._orphan_metrics,
            "cfg": {
                "enabled": self._orphan_cfg["enabled"],
                "periodic_interval_sec": self._orphan_cfg["periodic_interval_sec"],
                "min_order_age_sec": self._orphan_cfg["min_order_age_sec"],
                "batch_cancel_limit": self._orphan_cfg["batch_cancel_limit"],
                "rate_limit_per_min": self._orphan_cfg["rate_limit_per_min"],
            },
        }

        # Include gate metrics (SYMBOL_TIDY entry gate)
        try:
            gate_blocked = int(self._gate_metrics["gate_entry_blocked_tidy"])
            gate_allowed = int(self._gate_metrics["gate_entry_allowed_tidy"])
            all_metrics["gate"] = {
                "entry_blocked_tidy": gate_blocked,
                "entry_allowed_tidy": gate_allowed,
            }
            # Flat fields for quick access in /metrics JSON
            all_metrics["gate_entry_blocked_tidy"] = gate_blocked
            all_metrics["gate_entry_allowed_tidy"] = gate_allowed
            # Per-symbol stamps
            all_metrics["symbol_last_tidy_ts"] = dict(
                self._symbol_last_tidy_ts)
            all_metrics["last_entry_block_ts"] = dict(
                self._last_entry_block_ts)
        except Exception:
            # Be robust if attributes missing
            all_metrics["gate"] = {
                "entry_blocked_tidy": 0,
                "entry_allowed_tidy": 0,
            }
            all_metrics["gate_entry_blocked_tidy"] = 0
            all_metrics["gate_entry_allowed_tidy"] = 0
            all_metrics["symbol_last_tidy_ts"] = {}
            all_metrics["last_entry_block_ts"] = {}

        try:
            guardian = aget(self, "order_guardian", None)
            if guardian:
                guardian_metrics = guardian.get_metrics()
                all_metrics["order_guardian"] = guardian_metrics
                all_metrics["guardian_unified"] = self._guardian_unified
                all_metrics["guardian_emit_tidy_event"] = self._guardian_emit_tidy_event
                all_metrics["guardian_emit_tidy_monitoring_event"] = (
                    self._guardian_emit_tidy_monitoring_event
                )
        except Exception:
            pass

        return all_metrics

    async def handle_tick_async(self) -> None:
        """
        Async periodic tick for housekeeping.
        Calls non-async handle_tick for consistency.
        """
        self.handle_tick()

    def handle_tick(self) -> None:
        """
        Periodic tick for house-keeping.
        Phase 14D: Emits EVT:DOMAIN_STATUS every 60s.
        """
        try:
            now = get_clock().now_sec()
        except Exception:
            now = datetime.now(timezone.utc).timestamp()

        if now - self._last_status_ts >= 60:
            self._domain_bridge.emit_status()
            self._last_status_ts = now

    def is_healthy(self) -> bool:
        """
        Evaluate domain health.
        Healthy if adapter is connected and watchdog is running.
        """
        if self.adapter is not None and hasattr(self.adapter, "is_healthy"):
            if not self.adapter.is_healthy():
                return False

        # Check watchdog
        if self.watchdog and hasattr(self.watchdog, "is_running"):
            if not self.watchdog.is_running():
                return False

        return True
