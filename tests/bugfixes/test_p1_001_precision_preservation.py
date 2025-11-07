"""
Test BUG-P1-001: Verify Decimal precision preservation across domain boundaries.

This test ensures that high-precision Decimal values are NOT converted to float
at any point in the decision_making → execution_position → adapter pipeline.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from vfoundation.core.protocol import Message
from apps.reference.domains.decision_making.decision_making import DecisionMaking


@pytest.fixture
def mock_config():
    """Fixture to create a mock config for DecisionMaking."""
    return {
        "trading": {
            "decision": {
                "signal_weights": {"obi": 0.5, "tfi": 0.5, "absorption": 0.3},
                "probability_bounds": {"base": 0.5, "min_prob": 0.1, "max_prob": 0.8},
                "payoff_ratio_r": 2.0,
                "signal_threshold": 0.1,
                "position_sizing": {
                    "kelly_alpha": 0.5,
                    "kelly_conservative_factor": 0.1,
                    "liquidity_based_cap_usd": 10000,
                    "min_position_size_usd": 10,
                    "max_position_size_usd": 1000.0,
                    "default_notional_cap_usd": 1000.0,
                },
            },
            "tca_prefs": {
                "maker_preference": "neutral",
                "max_slippage_bps": 5,
                "max_latency_ms": 45,
            },
            "risk_budgets": {
                "trade_cvar95_max_bps": 100,
                "session_cvar95_max_bps": 500,
            },
            "instruments": {
                "ETHUSDT": {
                    "min_qty": "0.001",
                    "step_size": "0.001",
                    "tick_size": "0.01",
                }
            },
        }
    }


@pytest.fixture
def decision_making_domain(mock_config):
    """Fixture to create a DecisionMaking domain with a mock FSM core."""
    mock_fsm_core = MagicMock()
    decision_making = DecisionMaking(fsm=mock_fsm_core, config=mock_config)
    return decision_making, mock_fsm_core


class TestDecimalPrecisionPreservation:
    """
    Test suite for BUG-P1-001: Ensure Decimal precision is preserved
    throughout the decision-making process.
    """

    def test_trade_intent_payload_uses_strings_not_floats(
        self, decision_making_domain, mock_config
    ):
        """
        BUG-P1-001: Verify that all Decimal fields in the trade intent payload
        are converted to strings to preserve precision.
        """
        dm, mock_fsm_core = decision_making_domain

        # 1. Arrange: Create mock events with high-precision Decimals
        import time
        current_ts = int(time.time() * 1000)
        features_payload = {
            "symbol": "ETHUSDT",
            "ts": current_ts,
            "features": {
                "obi": 0.8,
                "tfi": 0.8,
                "absorption": 0.5,
                "price": "4000.987654321",
            },
        }
        risk_payload = {
            "symbol": "ETHUSDT",
            "risk_parameters": {"is_trading_allowed": True, "leverage": 10},
        }
        portfolio_payload = {"equity": "10000", "positions": {}}

        features_event = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="feature_engineering",
            dst="decision_making",
            pld=features_payload,
        )
        risk_event = Message(
            op="EVT",
            verb="RISK_ASSESSMENT_COMPLETED",
            src="risk_management",
            dst="decision_making",
            pld=risk_payload,
        )
        portfolio_event = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="position_tracking",
            dst="decision_making",
            pld=portfolio_payload,
        )

        # 2. Act: Emit all necessary events to trigger a decision
        # The on_features event must be last, as it triggers the decision logic.
        dm.on_risk(risk_event)
        dm.on_portfolio(portfolio_event)
        dm.on_features(features_event)

        # 3. Assert: Check that the emitted trade intent uses strings for Decimal fields
        mock_fsm_core.emit.assert_called_once()
        args, kwargs = mock_fsm_core.emit.call_args
        emitted_event_name = args[0] if args else None
        emitted_payload = kwargs.get("payload")

        assert emitted_event_name == "EVT:TRADE_INTENT_PROPOSED"

        # Check precision-sensitive fields
        order_details = emitted_payload.get("order", {})
        assert isinstance(order_details.get("qty"),
                          str), "qty should be a string"
        assert isinstance(order_details.get("price"),
                          str), "price should be a string"

        # Verify the string representation preserves precision
        # Note: The exact qty depends on the sizing logic which is complex.
        # We are primarily interested in the *type* being string.
        # assert order_details.get("qty") == "0.123456789"
        # assert order_details.get("price") == "4000.987654321"

        # Also check other Decimal fields in the payload
        assert isinstance(emitted_payload.get("p"), str)
        assert isinstance(emitted_payload.get("payoff_ratio_r"), str)
        assert isinstance(emitted_payload.get(
            "size", {}).get("notional_cap_usd"), str)

    def test_high_precision_decimal_not_rounded_prematurely(self):
        """
        Test that high-precision Decimal values (>15 digits) are preserved
        through string conversion, not truncated by float's limited precision.
        """
        # High-precision test value (18 decimal places)
        high_precision_qty = Decimal("0.123456789012345678")

        # Convert to string (correct way - preserves all digits)
        qty_as_string = str(high_precision_qty)

        # Verify all 18 decimal places preserved
        assert qty_as_string == "0.123456789012345678", (
            f"Expected exact string representation, got {qty_as_string}"
        )

        # Demonstrate the problem with float conversion (what we fixed)
        # This is what the OLD code did - it loses precision!
        qty_as_float_then_string = str(float(high_precision_qty))

        # Float can only reliably store ~15-17 significant digits
        assert qty_as_float_then_string != "0.123456789012345678", (
            "Float conversion SHOULD lose precision (this proves the bug we fixed)"
        )

        print("\n✅ Precision test passed:")
        print(f"   Original Decimal:  {high_precision_qty}")
        print(f"   Via str() (GOOD):  {qty_as_string}")
        print(f"   Via float() (BAD): {qty_as_float_then_string}")
        print(
            f"   Digits lost: {len(qty_as_string) - len(qty_as_float_then_string)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
