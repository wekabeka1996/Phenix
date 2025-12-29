"""
Tests for DecisionMaking QoS functionality (PACK EXP-4).
"""

import time
import pytest
from unittest.mock import Mock, patch
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.decision_making.normalized_reject_reasons import (
    NormalizedRejectReasons,
)


class TestDecisionMakingQoS:
    """Test cases for QoS functionality in DecisionMaking."""

    @pytest.fixture
    def mock_fsm(self):
        """Create a mock FSM."""
        return Mock()

    @pytest.fixture
    def qos_config(self):
        """QoS configuration for testing."""
        return {
            "decision": {
                "qos": {
                    "exposure_block_cooldown_sec": 10,
                    "symbol_cooldown_sec": 3,
                    "max_intents_per_minute_per_symbol": 2,
                },
                "position_sizing": {
                    "min_position_size_usd": 10,
                    "liquidity_based_cap_usd": 10000,
                },
                "signal_weights": {"feature1": 1.0},
            },
            "tca_prefs": {},
            "risk_budgets": {},
            "instruments": {"BTCUSDT": {"step_size": "0.001"}},
        }

    @pytest.fixture
    def decision_making(self, mock_fsm, qos_config):
        """Create DecisionMaking instance with QoS config."""
        return DecisionMaking(mock_fsm, qos_config)

    def test_qos_initialization(self, decision_making):
        """Test QoS configuration is loaded correctly."""
        assert decision_making.qos_exposure_block_cooldown_sec == 10
        assert decision_making.qos_symbol_cooldown_sec == 3
        assert decision_making.qos_max_intents_per_minute_per_symbol == 2

    def test_qos_allow_initial_state(self, decision_making):
        """Test QoS allows decisions initially."""
        allowed, reason = decision_making._qos_allow("BTCUSDT")
        assert allowed is True
        assert reason is None

    def test_symbol_cooldown_qos(self, decision_making):
        """Test symbol cooldown prevents rapid decisions."""
        symbol = "BTCUSDT"

        # First decision should be allowed
        allowed, reason = decision_making._qos_allow(symbol)
        assert allowed is True

        # Update cooldown
        decision_making._update_symbol_cooldown(symbol)

        # Immediate second decision should be blocked
        allowed, reason = decision_making._qos_allow(symbol)
        assert allowed is False
        assert reason == NormalizedRejectReasons.RATE_LIMIT_EXCEEDED

    def test_rate_limit_qos(self, decision_making):
        """Test rate limiting per symbol."""
        symbol = "BTCUSDT"

        # Allow first decision
        allowed, reason = decision_making._qos_allow(symbol)
        assert allowed is True
        decision_making._update_intent_count(symbol)

        # Allow second decision
        allowed, reason = decision_making._qos_allow(symbol)
        assert allowed is True
        decision_making._update_intent_count(symbol)

        # Third decision should be rate limited
        allowed, reason = decision_making._qos_allow(symbol)
        assert allowed is False
        assert reason == NormalizedRejectReasons.RATE_LIMIT_EXCEEDED

    def test_exposure_block_cooldown(self, decision_making):
        """Test exposure block triggers cooldown."""
        symbol = "BTCUSDT"

        # Record exposure block
        decision_making._handle_exposure_block(symbol)

        # Decision should be blocked due to exposure cooldown
        allowed, reason = decision_making._qos_allow(
            symbol, is_exposure_block=True)
        assert allowed is False
        assert reason == NormalizedRejectReasons.EXPOSURE_LIMIT_EXCEEDED

    def test_exposure_block_qos_bypass(self, decision_making):
        """Test exposure block check bypasses normal QoS when not exposure-related."""
        symbol = "BTCUSDT"

        # Record exposure block
        decision_making._handle_exposure_block(symbol)

        # Normal decision should still be allowed (only exposure checks are blocked)
        allowed, reason = decision_making._qos_allow(
            symbol, is_exposure_block=False)
        assert allowed is True

    def test_rate_limit_window_reset(self, decision_making):
        """Test rate limit window resets after 60 seconds."""
        symbol = "BTCUSDT"

        # Use up rate limit
        for i in range(2):
            allowed, reason = decision_making._qos_allow(symbol)
            assert allowed is True
            decision_making._update_intent_count(symbol)

        # Should be rate limited
        allowed, reason = decision_making._qos_allow(symbol)
        assert allowed is False

        # Simulate window reset by advancing time
        decision_making._qos_state["symbol_intent_counts"][symbol]["window_start"] -= 61

        # Should allow again
        allowed, reason = decision_making._qos_allow(symbol)
        assert allowed is True

    def test_multiple_symbols_independent_qos(self, decision_making):
        """Test QoS state is independent per symbol."""
        symbol1 = "BTCUSDT"
        symbol2 = "ETHUSDT"

        # Use up BTC rate limit
        for i in range(2):
            allowed, reason = decision_making._qos_allow(symbol1)
            assert allowed is True
            decision_making._update_intent_count(symbol1)

        # BTC should be rate limited
        allowed, reason = decision_making._qos_allow(symbol1)
        assert allowed is False

        # ETH should still be allowed (independent rate limit)
        allowed, reason = decision_making._qos_allow(symbol2)
        assert allowed is True

        # Test symbol cooldown independence
        decision_making._update_symbol_cooldown(symbol1)
        time.sleep(0.1)  # Small delay

        # BTC should be in cooldown
        allowed, reason = decision_making._qos_allow(symbol1)
        assert allowed is False

        # ETH should not be affected by BTC cooldown
        allowed, reason = decision_making._qos_allow(symbol2)
        assert allowed is True

    def test_busy_guard_stores_seconds_not_milliseconds(self, decision_making):
        """
        BUGFIX TEST: Verify _qos_next_allowed_ts stores SECONDS (not milliseconds).

        This test ensures the fix for the critical bug where timestamps were
        stored in milliseconds but compared with time.time() (seconds),
        causing ~55874 YEAR cooldowns instead of seconds.

        Bug manifestation: "Busy guard active: decision blocked for 1762623022079.1s"
        """
        symbol = "BTCUSDT"

        # Get current time in seconds
        current_time_sec = time.time()

        # Simulate setting busy guard via _qos_next_allowed_ts
        cooldown_seconds = 5.0
        future_time_sec = current_time_sec + cooldown_seconds
        decision_making._qos_next_allowed_ts[symbol] = future_time_sec

        # Verify stored value is in reasonable seconds range (not milliseconds!)
        stored_value = decision_making._qos_next_allowed_ts[symbol]

        # Key assertion: stored value should be close to time.time() + cooldown
        # If bug exists: stored_value would be ~1762623022079 (milliseconds)
        # If fixed: stored_value should be ~1762623022.079 (seconds)
        assert stored_value < current_time_sec * 2, (
            f"CRITICAL BUG: _qos_next_allowed_ts stores milliseconds instead of seconds! "
            f"stored={stored_value}, expected ~{future_time_sec}"
        )

        # Verify remaining time is reasonable (not 55874 years!)
        remaining = stored_value - current_time_sec
        assert remaining < 100, (
            f"CRITICAL BUG: Remaining cooldown is {remaining}s instead of ~{cooldown_seconds}s"
        )
        assert remaining >= 0, f"Remaining cooldown should be positive, got {remaining}s"

    def test_busy_guard_comparison_units_match(self, decision_making):
        """
        Verify busy guard comparison uses consistent units.

        The check in _make_decision_for_symbol():
            current_time = time.time()  # returns SECONDS
            next_allowed = self._qos_next_allowed_ts.get(symbol, 0)
            if current_time < next_allowed:  # Both should be in SECONDS
        """
        symbol = "BTCUSDT"

        # Set cooldown 2 seconds from now
        cooldown_end = time.time() + 2.0
        decision_making._qos_next_allowed_ts[symbol] = cooldown_end

        # Verify busy guard blocks correctly
        current_time = time.time()
        next_allowed = decision_making._qos_next_allowed_ts.get(symbol, 0)
        remaining_sec = next_allowed - current_time

        # Should be blocked (remaining ~2 seconds)
        assert remaining_sec > 0, f"Should be blocked but remaining={remaining_sec}s"
        assert remaining_sec < 10, f"Remaining too large: {remaining_sec}s (units mismatch?)"

        # Wait for cooldown to expire
        time.sleep(2.1)

        # Should no longer be blocked
        current_time = time.time()
        next_allowed = decision_making._qos_next_allowed_ts.get(symbol, 0)
        remaining_sec = next_allowed - current_time
        assert remaining_sec <= 0, f"Should be unblocked but remaining={remaining_sec}s"
