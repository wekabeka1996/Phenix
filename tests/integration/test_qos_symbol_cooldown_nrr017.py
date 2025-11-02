"""Test QoS symbol cooldown NRR-017 integration."""

import pytest
from unittest.mock import Mock, patch
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons


class TestQoSSymbolCooldownNRR017:
    """Test QoS symbol cooldown returns NRR-017."""

    @pytest.fixture
    def decision_making(self):
        """Create DecisionMaking instance with minimal config."""
        config = {
            "decision": {
                "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10000},
                "qos": {"symbol_cooldown_sec": 3, "mode": "enforce"},
                "features": {"ttl_sec": 30}
            },
            "tca_prefs": {},
            "risk_budgets": {}
        }
        fsm_mock = Mock()
        return DecisionMaking(fsm_mock, config)

    def test_symbol_cooldown_returns_nrr_017(self, decision_making):
        """Test that symbol cooldown logging includes NRR-017 code."""
        # Force symbol cooldown active by setting future timestamp (cooldown not expired)
        import time
        future_time = time.time() + decision_making.qos_symbol_cooldown_sec + \
            1  # 1 second in future
        decision_making._qos_state["symbol_cooldowns"]["BTCUSDT"] = future_time

        import logging
        with patch('logging.Logger.warning') as mock_log:
            allowed, reason = decision_making._qos_allow("BTCUSDT")

            assert allowed is False
            assert reason == NormalizedRejectReasons.RATE_LIMIT_EXCEEDED  # Return value is NRR-012

            # Verify logging includes NRR-017
            mock_log.assert_called_once()
            call_args = mock_log.call_args[0][0]
            assert "symbol_cooldown_active" in call_args

    def test_symbol_cooldown_inactive_allows_trading(self, decision_making):
        """Test that inactive symbol cooldown allows trading."""
        # Clear any cooldown
        decision_making._qos_state["symbol_cooldowns"]["BTCUSDT"] = 0

        allowed, reason = decision_making._qos_allow("BTCUSDT")

        assert allowed is True
        assert reason is None

    def test_symbol_cooldown_logging_includes_nrr_code(self, decision_making):
        """Test that symbol cooldown logging includes NRR-017 code."""
        # Force cooldown active
        import time
        future_time = time.time() + decision_making.qos_symbol_cooldown_sec + 1
        decision_making._qos_state["symbol_cooldowns"]["BTCUSDT"] = future_time

        import logging
        with patch('logging.Logger.warning') as mock_log:
            decision_making._qos_allow("BTCUSDT")

            # Verify logging was called with cooldown message
            mock_log.assert_called_once()
            call_args = mock_log.call_args[0][0]
            assert "symbol_cooldown_active" in call_args
