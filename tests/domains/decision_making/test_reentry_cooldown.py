"""
Tests for REENTRY-COOLDOWN-FIX-006.

Verify that reentry cooldown is enforced after ANY position close,
including manual close and portfolio update.
"""

import decimal
import time
from typing import Dict, Any
from unittest.mock import MagicMock, patch

import pytest


class _DummyFsm:
    """Mock FSM for testing."""
    def __init__(self):
        self.emitted: list[tuple[str, dict, str | None]] = []
        self._listeners: dict[str, list] = {}

    def emit(self, event_name: str, payload=None, why=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}, why))

    def listen(self, event_name: str, callback) -> None:
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(callback)


@pytest.fixture
def mock_config():
    """Create mock config for decision making."""
    from apps.reference.config_loader import ConfigLoader
    return ConfigLoader().load_config()


@pytest.fixture
def decision_making(mock_config):
    """Create DecisionMaking instance with mock FSM."""
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    
    fsm = _DummyFsm()
    dm = DecisionMaking(fsm=fsm, config=mock_config)
    return dm


class TestReentryCooldownPortfolioAware:
    """
    REENTRY-COOLDOWN-FIX-006: Cooldown must trigger on ANY exit.
    
    Root cause: Last exit timestamp was only set when Aurora handler
    detected neutral signal, but not on:
    - Manual close (via portfolio update)
    - ExecutionPosition lifecycle events
    - System-driven close via different path
    """
    
    def test_exit_detected_via_portfolio_update(self, decision_making):
        """
        Exit detected via portfolio update should trigger cooldown.
        
        Scenario:
        1. Position exists: SOL -4
        2. Portfolio update arrives with SOL position = 0
        3. Verify: _last_exit_mono_ts is set
        """
        from types import SimpleNamespace
        # Setup: Simulate previous portfolio with SOL position
        decision_making._prev_position_qty["SOLUSDT"] = decimal.Decimal("-4")
        
        # Create mock event with empty SOLUSDT position (exit)
        mock_event = SimpleNamespace(
            pld={
                "positions": [],  # SOL position is gone
                "equity": "1000",
            },
            rid="test-rid-001",
        )
        
        # Before: No exit timestamp
        assert "SOLUSDT" not in decision_making._last_exit_mono_ts
        
        # Process portfolio update
        decision_making.on_portfolio(mock_event)
        
        # After: Exit timestamp should be set
        assert "SOLUSDT" in decision_making._last_exit_mono_ts
        assert decision_making._last_exit_mono_ts["SOLUSDT"] > 0
    
    def test_cooldown_blocks_entry_after_portfolio_exit(self, decision_making):
        """
        Entry should be blocked during cooldown after portfolio-detected exit.
        """
        # Setup cooldown
        decision_making._reentry_cooldown_sec = 60.0
        
        # Simulate exit happened 30 seconds ago
        decision_making._last_exit_mono_ts["BTCUSDT"] = time.monotonic() - 30
        
        # Check cooldown gate
        should_block, details = decision_making._check_reentry_cooldown_gate(
            symbol="BTCUSDT",
            reduce_only=False,
        )
        
        # Should block (30s < 60s cooldown)
        assert should_block is True
        assert details["result"] == "BLOCK"
        assert details["elapsed_sec"] < 60
        assert details["remaining_sec"] > 0
    
    def test_cooldown_allows_entry_after_cooldown_expires(self, decision_making):
        """
        Entry should be allowed after cooldown expires.
        """
        # Setup cooldown
        decision_making._reentry_cooldown_sec = 60.0
        
        # Simulate exit happened 90 seconds ago
        decision_making._last_exit_mono_ts["ETHUSDT"] = time.monotonic() - 90
        
        # Check cooldown gate
        should_block, details = decision_making._check_reentry_cooldown_gate(
            symbol="ETHUSDT",
            reduce_only=False,
        )
        
        # Should pass (90s >= 60s cooldown)
        assert should_block is False
        assert details["result"] == "PASS"
        assert details["elapsed_sec"] >= 60
    
    def test_reduce_only_bypasses_cooldown(self, decision_making):
        """
        Reduce-only orders (close) should bypass cooldown.
        """
        # Setup: Active cooldown
        decision_making._reentry_cooldown_sec = 60.0
        decision_making._last_exit_mono_ts["XRPUSDT"] = time.monotonic() - 10
        
        # Check cooldown gate for reduce_only
        should_block, details = decision_making._check_reentry_cooldown_gate(
            symbol="XRPUSDT",
            reduce_only=True,  # Close order
        )
        
        # Should pass
        assert should_block is False
        assert details["result"] == "PASS:reduce_only"
    
    def test_no_cooldown_if_no_prior_exit(self, decision_making):
        """
        No cooldown should apply if there was no prior exit.
        """
        # No exit timestamp for this symbol
        assert "DOGEUSDT" not in decision_making._last_exit_mono_ts
        
        # Check cooldown gate
        should_block, details = decision_making._check_reentry_cooldown_gate(
            symbol="DOGEUSDT",
            reduce_only=False,
        )
        
        # Should pass
        assert should_block is False
        assert details["result"] == "PASS:no_prior_exit"
    
    def test_partial_close_does_not_trigger_cooldown(self, decision_making):
        """
        Partial close (qty reduced but not to 0) should NOT trigger cooldown.
        """
        from types import SimpleNamespace
        # Setup: Previous position = -4
        decision_making._prev_position_qty["SOLUSDT"] = decimal.Decimal("-4")
        
        # Portfolio update: Partial close to -2 (not 0)
        mock_event = SimpleNamespace(
            pld={
                "positions": [
                    {"symbol": "SOLUSDT", "quantity": "-2"}
                ],
                "equity": "1000",
            },
            rid="test-rid-002",
        )
        
        # Process portfolio update
        decision_making.on_portfolio(mock_event)
        
        # Should NOT set exit timestamp (position still open)
        assert "SOLUSDT" not in decision_making._last_exit_mono_ts


class TestReentryCooldownMonotonic:
    """Verify cooldown uses monotonic time (not affected by wall clock changes)."""
    
    def test_monotonic_time_prevents_bypass(self, decision_making):
        """
        Cooldown uses monotonic time, so wall clock manipulation doesn't help.
        """
        decision_making._reentry_cooldown_sec = 60.0
        
        # Set exit timestamp using monotonic
        mono_now = time.monotonic()
        decision_making._last_exit_mono_ts["BTCUSDT"] = mono_now
        
        # Check immediately - should block
        should_block, details = decision_making._check_reentry_cooldown_gate(
            symbol="BTCUSDT",
            reduce_only=False,
        )
        
        assert should_block is True
        # Elapsed should be very small (< 1 second)
        assert details["elapsed_sec"] < 1


class TestReentryCooldownTelemetry:
    """Verify telemetry is emitted on cooldown blocks."""
    
    def test_details_include_all_fields(self, decision_making):
        """
        BLOCK details should include all required fields for forensics.
        """
        decision_making._reentry_cooldown_sec = 60.0
        decision_making._last_exit_mono_ts["SOLUSDT"] = time.monotonic() - 25
        
        should_block, details = decision_making._check_reentry_cooldown_gate(
            symbol="SOLUSDT",
            reduce_only=False,
        )
        
        assert should_block is True
        # Required fields
        assert "gate" in details
        assert "symbol" in details
        assert "last_exit_mono_ts" in details
        assert "elapsed_sec" in details
        assert "cooldown_sec" in details
        assert "remaining_sec" in details
        assert "result" in details
        
        assert details["gate"] == "REENTRY_COOLDOWN"
        assert details["cooldown_sec"] == 60.0
        assert details["remaining_sec"] > 0
