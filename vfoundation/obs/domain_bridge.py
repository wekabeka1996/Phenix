"""
DomainBridge — Phase 14D FSM bridge for orphan domains.

Allows non-FSM domains (neocortex, alpha_search, inflight_reconcile)
to register health functions and participate in MetaFSM topology auditing.

Constitution v2.2 §7: all domains must be auditable by TopologyAuditor.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

LOG = logging.getLogger(__name__)


class DomainBridge:
    """
    Bridge for non-FSM domains to expose health to TopologyAuditor.

    Args:
        domain_name: Must match owner field in verb_registry_v1.yaml
        bus: Optional FSMCore instance for emitting EVT:DOMAIN_STATUS
    """

    def __init__(self, domain_name: str, bus: Optional[Any] = None) -> None:
        self.domain_name = domain_name
        self._bus = bus
        self._health_fn: Optional[Callable[[], bool]] = None

    def register_health_fn(self, fn: Callable[[], bool]) -> None:
        """Register zero-argument health check. Replaces previous if called again."""
        self._health_fn = fn

    def is_healthy(self) -> bool:
        """
        Evaluate domain health. Returns True if no fn registered (optimistic).
        Returns False if fn returns False or raises.
        """
        if self._health_fn is None:
            return True
        try:
            return bool(self._health_fn())
        except Exception as exc:
            LOG.warning("DomainBridge[%s] health_fn raised: %s", self.domain_name, exc)
            return False

    def emit_status(self) -> None:
        """
        Emit EVT:DOMAIN_STATUS to bus. No-op if no bus configured.
        Never raises — all errors are logged.
        """
        if self._bus is None:
            return
        healthy = self.is_healthy()
        payload = {"domain": self.domain_name, "healthy": healthy}
        why = f"domain status: {'ok' if healthy else 'degraded'}"
        try:
            self._bus.emit("EVT:DOMAIN_STATUS", payload, why=why)
        except Exception as exc:
            LOG.warning("DomainBridge[%s] emit failed: %s", self.domain_name, exc)
