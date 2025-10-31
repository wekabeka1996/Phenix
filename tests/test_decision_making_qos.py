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
