"""Tests for vfoundation.core.meta_fsm_v2 — Phase 3.3."""
from __future__ import annotations

import time
from typing import Tuple
from unittest.mock import MagicMock

import pytest

from vfoundation.core.meta_fsm_v2 import MetaFSMv2
from vfoundation.obs.entropy_monitor import EntropyMonitor
from vfoundation.core.protocol import Message


# ── Helpers ──────────────────────────────────────────────────────────

def _make_entropy(spike: bool = False, reason: str = "") -> MagicMock:
    """Create a mock EntropyMonitor with controlled detect_spike()."""
    mock = MagicMock(spec=EntropyMonitor)
    mock.detect_spike.return_value = (spike, reason)
    return mock


# ── Initial state ────────────────────────────────────────────────────

class TestInitialState:
    def test_starts_in_normal(self) -> None:
        meta = MetaFSMv2()
        assert meta.state == "NORMAL"
        assert meta.mode == "normal"

    def test_no_entropy_monitor_stays_normal(self) -> None:
        meta = MetaFSMv2(entropy_monitor=None)
        state, resp = meta.tick()
        assert state == "NORMAL"
        assert resp is None


# ── Spike → LOW_RISK ─────────────────────────────────────────────────

class TestSpikeTransition:
    def test_entropy_spike_triggers_low_risk(self) -> None:
        entropy = _make_entropy(spike=True, reason="VOLUME_SPIKE: 200 events")
        meta = MetaFSMv2(entropy_monitor=entropy)

        state, resp = meta.tick()
        assert state == "LOW_RISK"
        assert resp is not None
        assert resp.verb == "SWITCH_TO_LOW_RISK_MODE"
        assert resp.dst == "risk_strategy"

    def test_no_spike_stays_normal(self) -> None:
        entropy = _make_entropy(spike=False)
        meta = MetaFSMv2(entropy_monitor=entropy)

        state, resp = meta.tick()
        assert state == "NORMAL"
        assert resp is None


# ── LOW_RISK → COOLDOWN → NORMAL lifecycle ──────────────────────────

class TestFullLifecycle:
    def test_spike_stabilize_cooldown_normal(self) -> None:
        entropy = _make_entropy(spike=True, reason="ERROR_SPIKE")
        meta = MetaFSMv2(entropy_monitor=entropy, cooldown_sec=0.01)

        # Tick 1: spike → LOW_RISK
        state, _ = meta.tick()
        assert state == "LOW_RISK"

        # Now entropy stabilizes
        entropy.detect_spike.return_value = (False, "")

        # Tick 2: no spike → COOLDOWN
        state, resp = meta.tick()
        assert state == "COOLDOWN"

        # Wait for cooldown
        time.sleep(0.02)

        # Tick 3: cooldown elapsed → NORMAL
        state, resp = meta.tick()
        assert state == "NORMAL"
        assert resp is not None
        assert resp.verb == "NORMAL_MODE_RESTORED"

    def test_cooldown_not_yet_elapsed(self) -> None:
        entropy = _make_entropy(spike=True, reason="spike")
        meta = MetaFSMv2(entropy_monitor=entropy, cooldown_sec=999)

        meta.tick()  # → LOW_RISK
        entropy.detect_spike.return_value = (False, "")
        meta.tick()  # → COOLDOWN

        # Cooldown hasn't elapsed (999s)
        state, resp = meta.tick()
        assert state == "COOLDOWN"
        assert resp is None


# ── DEGRADED state ───────────────────────────────────────────────────

class TestDegraded:
    def test_topology_drift_triggers_degraded(self) -> None:
        meta = MetaFSMv2()
        state, resp = meta.inject_event("EVT", "TOPOLOGY_DRIFT_DETECTED", "domain X missing")
        assert state == "DEGRADED"
        assert resp is not None
        assert resp.verb == "SWITCH_TO_LOW_RISK_MODE"

    def test_recovery_from_degraded(self) -> None:
        meta = MetaFSMv2(cooldown_sec=0.01)
        meta.inject_event("EVT", "TOPOLOGY_DRIFT_DETECTED", "test")
        assert meta.state == "DEGRADED"

        state, _ = meta.inject_event("EVT", "RECOVERY_SIGNAL", "all domains back")
        assert state == "COOLDOWN"

        time.sleep(0.02)
        state, resp = meta.tick()
        assert state == "NORMAL"

    def test_force_recover_from_degraded(self) -> None:
        meta = MetaFSMv2()
        meta.inject_event("EVT", "TOPOLOGY_DRIFT_DETECTED", "test")
        state, resp = meta.inject_event("CMD", "FORCE_RECOVER", "operator override")
        assert state == "NORMAL"
        assert resp is not None
        assert resp.verb == "NORMAL_MODE_RESTORED"


# ── Force recover from LOW_RISK ─────────────────────────────────────

class TestForceRecover:
    def test_force_recover_from_low_risk(self) -> None:
        entropy = _make_entropy(spike=True, reason="test")
        meta = MetaFSMv2(entropy_monitor=entropy)
        meta.tick()  # → LOW_RISK

        state, resp = meta.inject_event("CMD", "FORCE_RECOVER", "manual")
        assert state == "NORMAL"
        assert resp.verb == "NORMAL_MODE_RESTORED"


# ── Metrics ──────────────────────────────────────────────────────────

class TestMetrics:
    def test_metrics_tracks_transitions(self) -> None:
        entropy = _make_entropy(spike=True, reason="test")
        meta = MetaFSMv2(entropy_monitor=entropy)
        meta.tick()  # → LOW_RISK

        m = meta.get_metrics()
        assert m["state"] == "LOW_RISK"
        assert m["fsm_metrics"]["transitions"] >= 1


# ── Edge cases ───────────────────────────────────────────────────────

class TestEdgeCases:
    def test_unknown_event_is_rejected(self) -> None:
        meta = MetaFSMv2()
        state, resp = meta.inject_event("CMD", "NONEXISTENT_VERB", "test")
        assert state == "NORMAL"
        assert resp is not None
        assert resp.op == "ERR"
