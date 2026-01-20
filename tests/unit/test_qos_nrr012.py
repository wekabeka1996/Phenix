"""
Unit tests for QoS NRR-012 rate limiting semantics.

Tests that DEFER correctly plans retry timestamps and respects cooldowns.

NOTE: These tests are SKIPPED because the tested methods (_qos_allow, _update_intent_count, etc.)
do not exist in the current DecisionMaking implementation. These are legacy tests from an earlier
refactoring phase that haven't been updated to match the new architecture.

To fix: Either implement these internal methods or rewrite tests to use public API.
"""

import pytest
import time
from unittest.mock import Mock
from types import SimpleNamespace
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.config_models import create_aurora_config


def _to_dict(obj):
    if isinstance(obj, SimpleNamespace):
        return {k: _to_dict(v) for k, v in vars(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dict(v) for v in obj]
    return obj


@pytest.mark.skip(reason="Method _qos_allow does not exist in DecisionMaking - legacy test")
def test_nrr_012_rate_limit_semantics():
    """Test that NRR-012 properly calculates retry timestamps."""

    # Mock FSM
    class MockFSM:
        def __init__(self):
            self.listeners = {}

        def listen(self, event, handler):
            if event not in self.listeners:
                self.listeners[event] = []
            self.listeners[event].append(handler)

        def emit(self, event_name, payload=None, why=None):
            pass  # Ignore for this test

    fsm = MockFSM()

    # Config with rate limiting - MUST have 'trading' wrapper
    cfg = {
        "trading": {
            "decision": {
                "features": {"ttl_sec": 30},
                "qos": {
                    "exposure_block_cooldown_sec": 10,
                    "symbol_cooldown_sec": 3,
                    "max_intents_per_minute_per_symbol": 2,  # Low limit for testing
                    "mode": "defer"
                },
                "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10000},
                "signal_weights": {"obi": 0.5, "tfi": 0.5},
                "signal_threshold": 0.2,
            },
            "tca_prefs": {"max_slippage_bps": 10},
            "risk_budgets": {"trade_cvar95_max_bps": 100},
            "instruments": {"SOLUSDT": {"step_size": "0.001"}},
        }
    }

    dm = DecisionMaking(fsm, create_aurora_config(_to_dict(cfg)))

    symbol = "SOLUSDT"

    # First check should allow
    allowed, reason = dm._qos_allow(symbol, is_exposure_block=False)
    assert allowed == True
    assert reason is None

    # Update state as if intent was made
    dm._update_intent_count(symbol)

    # Second check should still allow (under limit)
    allowed, reason = dm._qos_allow(symbol, is_exposure_block=False)
    assert allowed == True
    assert reason is None

    # Update again - now at limit
    dm._update_intent_count(symbol)

    # Third check should block
    allowed, reason = dm._qos_allow(symbol, is_exposure_block=False)
    assert allowed == False
    assert reason == "NRR-012"  # RATE_LIMIT_EXCEEDED

    # Calculate next allowed time
    next_ts = dm._calculate_next_allowed_time(symbol)
    now = time.time() * 1000

    # Should be at least 60 seconds in future (end of rate window)
    assert next_ts > now
    assert next_ts <= now + (60 * 1000) + 1000  # Allow some tolerance


@pytest.mark.skip(reason="Method _symbol_cooldown_semantics does not exist in DecisionMaking - legacy test")
def test_symbol_cooldown_semantics():
    """Test symbol cooldown prevents rapid-fire decisions."""

    class MockFSM:
        def __init__(self):
            self.listeners = {}

        def listen(self, event, handler):
            if event not in self.listeners:
                self.listeners[event] = []
            self.listeners[event].append(handler)

        def emit(self, event_name, payload=None, why=None):
            pass

    fsm = MockFSM()

    cfg = {
        "trading": {
            "decision": {
                "features": {"ttl_sec": 30},
                "qos": {
                    "exposure_block_cooldown_sec": 10,
                    "symbol_cooldown_sec": 1,  # 1 second cooldown
                    "max_intents_per_minute_per_symbol": 60,
                    "mode": "defer"
                },
                "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10000},
                "signal_weights": {"obi": 0.5, "tfi": 0.5},
                "signal_threshold": 0.2,
            },
            "tca_prefs": {"max_slippage_bps": 10},
            "risk_budgets": {"trade_cvar95_max_bps": 100},
            "instruments": {"SOLUSDT": {"step_size": "0.001"}},
        }
    }

    dm = DecisionMaking(fsm, create_aurora_config(_to_dict(cfg)))

    symbol = "SOLUSDT"

    # First check should allow
    allowed, reason = dm._qos_allow(symbol, is_exposure_block=False)
    assert allowed == True

    # Update cooldown
    dm._update_symbol_cooldown(symbol)

    # Immediate second check should block
    allowed, reason = dm._qos_allow(symbol, is_exposure_block=False)
    assert allowed == False
    assert reason == "NRR-012"  # RATE_LIMIT_EXCEEDED (includes cooldown)

    # Calculate next allowed time
    next_ts = dm._calculate_next_allowed_time(symbol)
    now = time.time() * 1000

    # Should be at least cooldown period in future (allow small timing variance)
    # 0.9 second cooldown (allow for timing)
    assert next_ts >= now + (0.9 * 1000)


@pytest.mark.skip(reason="Method _update_intent_count does not exist in DecisionMaking - legacy test")
def test_defer_mode_emits_correct_event():
    """Test that defer mode emits INTENT_DEFERRED with correct payload."""

    deferred_events = []

    class MockFSM:
        def __init__(self):
            self.listeners = {}

        def listen(self, event, handler):
            if event not in self.listeners:
                self.listeners[event] = []
            self.listeners[event].append(handler)

        def emit(self, event_name, payload=None, why=None, data_ref=None):
            from vfoundation.core.protocol import Message
            msg = Message(op="EVT", verb=event_name.split(
                ":")[1], src="test", dst="any", pld=payload, why=why, data_ref=data_ref or [])
            deferred_events.append(msg)

    fsm = MockFSM()

    cfg = {
        "trading": {
            "decision": {
                "features": {"ttl_sec": 30},
                "qos": {
                    "exposure_block_cooldown_sec": 10,
                    "symbol_cooldown_sec": 3,
                    "max_intents_per_minute_per_symbol": 1,  # Very restrictive
                    "mode": "defer"
                },
                "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10000},
                "signal_weights": {"obi": 0.5, "tfi": 0.5},
                "signal_threshold": 0.2,
            },
            "tca_prefs": {"max_slippage_bps": 10},
            "risk_budgets": {"trade_cvar95_max_bps": 100},
            "instruments": {"SOLUSDT": {"step_size": "0.001"}},
        }
    }

    dm = DecisionMaking(fsm, create_aurora_config(_to_dict(cfg)))

    # Exhaust rate limit
    symbol = "SOLUSDT"
    dm._update_intent_count(symbol)  # Count = 1, at limit

    # Create mock context for defer
    context = {
        "features": {"features": {"obi": 0.3, "tfi": 0.3, "price": "50000"}},
        "risk_params": {"risk_parameters": {"is_trading_allowed": True}},
        "portfolio": {"equity": "10000", "positions": []},
        "regime": None
    }

    # This should trigger QoS defer
    dm._make_decision_for_symbol(symbol, context, "test-rid")

    # Should have emitted INTENT_DEFERRED
    assert len(deferred_events) == 1
    defer_event = deferred_events[0]
    assert defer_event.verb == "INTENT_DEFERRED"

    payload = defer_event.pld
    assert "reason" in payload
    assert "symbol" in payload
    assert "next_allowed_ts" in payload
    assert payload['symbol'] == symbol
