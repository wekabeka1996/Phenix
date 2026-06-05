"""Tests for AlertManager gaps — Blueprint 11.4."""
from __future__ import annotations

from vfoundation.obs.alert_manager import (
    ALERT_CB_OPEN,
    ALERT_ENTROPY_SPIKE,
    ALERT_ERR_RATE_HIGH,
    ALERT_TOPOLOGY_DRIFT,
    Alert,
    AlertLevel,
    AlertManager,
    InMemoryAlertHook,
)


class TestAlertHooksGaps:
    def test_unregister_all_clears_hooks(self) -> None:
        """unregister_all() removes all registered hooks."""
        mgr = AlertManager()
        mgr.register(InMemoryAlertHook())
        mgr.register(InMemoryAlertHook())
        assert mgr.hook_count() == 2
        mgr.unregister_all()
        assert mgr.hook_count() == 0

    def test_fire_returns_int_count(self) -> None:
        """fire() returns number of hooks notified."""
        mgr = AlertManager()
        mgr.register(InMemoryAlertHook())
        mgr.register(InMemoryAlertHook())
        alert = Alert(level=AlertLevel.ERROR, title="test", message="boom")
        count = mgr.fire(alert)
        assert count == 2

    def test_fire_returns_0_below_min_level(self) -> None:
        """fire() returns 0 when alert is below min_level."""
        mgr = AlertManager(min_level=AlertLevel.ERROR)
        mgr.register(InMemoryAlertHook())
        alert = Alert(level=AlertLevel.INFO, title="low", message="ignored")
        count = mgr.fire(alert)
        assert count == 0

    def test_alert_constants_defined(self) -> None:
        """Pre-defined alert type constants exist."""
        assert ALERT_ENTROPY_SPIKE == "ENTROPY_SPIKE"
        assert ALERT_TOPOLOGY_DRIFT == "TOPOLOGY_DRIFT"
        assert ALERT_ERR_RATE_HIGH == "ERR_RATE_HIGH"
        assert ALERT_CB_OPEN == "CB_OPEN"
