"""Tests for DomainBridge — FSM bridge for orphan domains (Phase 14D)."""
import pytest
from unittest.mock import MagicMock
from vfoundation.obs.domain_bridge import DomainBridge


class TestDomainBridgeHealth:
    def test_no_health_fn_defaults_to_healthy(self):
        assert DomainBridge("neocortex").is_healthy() is True

    def test_healthy_fn_returns_true(self):
        b = DomainBridge("alpha")
        b.register_health_fn(lambda: True)
        assert b.is_healthy() is True

    def test_unhealthy_fn_returns_false(self):
        b = DomainBridge("alpha")
        b.register_health_fn(lambda: False)
        assert b.is_healthy() is False

    def test_exception_in_fn_returns_false_no_raise(self):
        b = DomainBridge("broken")
        def bad(): raise RuntimeError("crash")
        b.register_health_fn(bad)
        assert b.is_healthy() is False

    def test_last_registered_fn_wins(self):
        b = DomainBridge("test")
        b.register_health_fn(lambda: False)
        b.register_health_fn(lambda: True)
        assert b.is_healthy() is True

    def test_domain_name_stored(self):
        b = DomainBridge("my_domain")
        assert b.domain_name == "my_domain"


class TestDomainBridgeEmit:
    def test_emit_no_bus_no_crash(self):
        DomainBridge("neocortex").emit_status()

    def test_emit_with_bus_calls_emit(self):
        bus = MagicMock()
        DomainBridge("neocortex", bus=bus).emit_status()
        bus.emit.assert_called_once()

    def test_emit_event_name_contains_domain_status(self):
        bus = MagicMock()
        DomainBridge("neocortex", bus=bus).emit_status()
        event_name = bus.emit.call_args[0][0]
        assert "DOMAIN_STATUS" in event_name

    def test_emit_payload_has_domain_name(self):
        bus = MagicMock()
        DomainBridge("alpha_search", bus=bus).emit_status()
        payload = bus.emit.call_args[0][1]
        assert payload.get("domain") == "alpha_search"

    def test_emit_payload_has_healthy_flag(self):
        bus = MagicMock()
        b = DomainBridge("alpha_search", bus=bus)
        b.register_health_fn(lambda: True)
        b.emit_status()
        assert bus.emit.call_args[0][1]["healthy"] is True

    def test_emit_unhealthy_reflected_in_payload(self):
        bus = MagicMock()
        b = DomainBridge("alpha_search", bus=bus)
        b.register_health_fn(lambda: False)
        b.emit_status()
        assert bus.emit.call_args[0][1]["healthy"] is False


class TestDomainBridgeIsolation:
    def test_multiple_bridges_are_independent(self):
        b1 = DomainBridge("d1")
        b2 = DomainBridge("d2")
        b1.register_health_fn(lambda: False)
        b2.register_health_fn(lambda: True)
        assert b1.is_healthy() is False
        assert b2.is_healthy() is True
