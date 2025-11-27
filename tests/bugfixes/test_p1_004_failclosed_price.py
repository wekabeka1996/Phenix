"""
Test BUG-P1-004: Verify fail-closed pattern when price reference unavailable.

This test ensures that decision_making does NOT use hardcoded fallback prices,
which could cause catastrophic losses if market data is unavailable.
"""

import pytest
import time
from unittest.mock import Mock, MagicMock
from vfoundation.core.protocol import Message
from apps.reference.domains.decision_making.decision_making import DecisionMaking


class TestFailClosedPricePattern:
    """Test suite for BUG-P1-004: Fail-closed on missing price data."""

    def test_decision_rejected_when_no_price_available(self):
        """
        Verify that decision_making REJECTS decisions (fail-closed)
        when no valid price reference is available, instead of using
        a hardcoded fallback.
        """
        # Arrange: Create DecisionMaking with mock FSM
        mock_fsm = Mock()
        emitted_events = []

        def capture_emit(verb, payload, why):
            emitted_events.append(
                {"verb": verb, "payload": payload, "why": why})

        mock_fsm.emit = capture_emit

        config = {
            "trading": {
                "instruments": {
                    "ETHUSDT": {
                        "symbol": "ETHUSDT",
                        "lot_step": "0.001",
                        "tick_size": "0.01",
                        "min_qty": "0.001",
                    }
                },
                "tca_prefs": {
                    "max_slippage_bps": 5,
                    "max_latency_ms": 45,
                    "maker_preference": "prefer",
                },
                "risk_budgets": {
                    "trade_cvar95_max_bps": 150,
                    "session_cvar95_max_bps": 500,
                },
                "decision": {
                    "payoff_ratio_r": 2.5,
                    "prob_calibration": {"version": "v1.0", "source": "test"},
                    "sizing": {"min_position_size_usd": 10},
                },
            },
            "system": {"trade_intent_validity_ms": 30000},
        }

        dm = DecisionMaking(fsm=mock_fsm, config=config)

        # Feed data WITHOUT valid price
        # Features without price field
        features_payload = {
            "features": {
                # NO 'price' field
                "obi": "0.5",
                "tfi": "0.3",
                "absorption": "1.2",
                # NO 'bid' or 'ask' fields either
            }
        }

        risk_payload = {
            "trading_allowed": True,
            "cvar_trade_usd": "125.0",
            "cvar_session_usd": "450.0",
            "risk_parameters": {
                "signal_score": "0.75",
                "p_raw": "0.60",
                "p_calibrated": "0.58",
                "p": "0.58",
                "p_ceiling": "0.80",
                "ev_raw": "0.45",
                "full_kelly": "0.30",
                "kelly_used": "0.15",
                "quality_grade": "A",
                "p_calibration_metrics": "v1.0",
            },
        }

        portfolio_payload = {
            "equity_free_usdt": "10000.0",
            "equity_total_usdt": "10000.0",
            "realized_pnl": "50.0",
            "unrealized_pnl": "25.0",
            "positions": {},
            # NO 'last_price' field
        }

        # Feed data to trigger decision logic
        dm.on_features(Message(op="EVT", verb="FEATURES_CALCULATED",
                       src="test", dst="test", pld=features_payload))
        dm.on_risk(Message(op="EVT", verb="RISK_ASSESSMENT_COMPLETED",
                   src="test", dst="test", pld=risk_payload))
        dm.on_portfolio(Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED",
                        src="test", dst="test", pld=portfolio_payload))

        # Assert: NO event should be emitted (fail-closed)
        assert len(emitted_events) == 0, (
            f"Expected NO events (fail-closed), but got {len(emitted_events)} events"
        )

        print("\n✅ BUG-P1-004 VERIFIED: Decision rejected when price unavailable")
        print("   No TRADE_INTENT_PROPOSED event emitted (fail-closed)")

    def test_decision_proceeds_when_price_available_in_features(self):
        """
        Verify that decision proceeds normally when valid price is available.
        """
        # Arrange
        mock_fsm_core = MagicMock()
        emitted_events = []
        mock_fsm_core.emit.side_effect = (
            lambda name, payload=None, why=None, data_ref=None: emitted_events.append(
                name)
        )

        config = {
            "trading": {
                "instruments": {
                    "ETHUSDT": {
                        "lot_step": 0.001,
                        "tick_size": 0.01,
                        "min_qty": 0.001,
                        "step_size": "0.001",
                    }
                },
                "decision": {
                    "signal_weights": {"obi": 0.3, "tfi": 0.4, "absorption": 0.3},
                    "probability_bounds": {"base": 0.5, "max_prob": 0.8},
                    "payoff_ratio_r": 2.0,
                    "position_sizing": {
                        "kelly_conservative_factor": 0.1,
                        "kelly_alpha": 0.5,
                        "min_position_size_usd": 10.0,
                        "max_position_size_usd": 1000.0,
                        "default_notional_cap_usd": 1000.0,
                        "liquidity_based_cap_usd": 10000.0,
                    },
                },
                "tca_prefs": {
                    "max_slippage_bps": 50.0,
                    "max_latency_ms": 5000,
                    "maker_preference": "allow",
                },
                "risk_budgets": {
                    "trade_cvar95_max_bps": 100.0,
                    "session_cvar95_max_bps": 200.0,
                },
            }
        }
        decision_domain = DecisionMaking(fsm=mock_fsm_core, config=config)

        features_msg = Message(
            op="EVT",
            verb="FEATURES_CALCULATED",
            src="test",
            dst="test",
            pld={
                "symbol": "ETHUSDT",
                "ts": int(time.time() * 1000),
                "features": {
                    "price": "3850.50",
                    "obi": "0.5",
                    "tfi": "0.3",
                    "absorption": "1.2",
                    "delta_price": "10.0",
                },
            },
        )
        risk_msg = Message(
            op="EVT",
            verb="RISK_ASSESSMENT_COMPLETED",
            src="test",
            dst="test",
            pld={
                "symbol": "ETHUSDT",
                "ts": "2025-01-01T12:00:00Z",
                "risk_parameters": {"is_trading_allowed": True},
            },
        )
        portfolio_msg = Message(
            op="EVT",
            verb="PORTFOLIO_STATE_UPDATED",
            src="test",
            dst="test",
            pld={"equity_free_usdt": "10000.0",
                 "equity_total_usdt": "10000.0"},
        )

        # Act: Feed events in the correct order (features is the trigger)
        decision_domain.on_risk(risk_msg)
        decision_domain.on_portfolio(portfolio_msg)
        decision_domain.on_features(features_msg)

        # Assert: A trade intent should be emitted
        assert len(emitted_events) == 1, (
            "Expected TRADE_INTENT_PROPOSED when price available"
        )
        assert "EVT:TRADE_INTENT_PROPOSED" in emitted_events
        print("\n✅ Decision proceeds normally when price available")

    def test_no_hardcoded_fallback_price_in_code(self):
        """
        Meta-test: Verify that the hardcoded fallback price literal
        has been removed from the source code.
        """
        import inspect
        from apps.reference.domains.decision_making import decision_making

        # Get source code of the module
        source = inspect.getsource(decision_making)

        # Check that the dangerous hardcoded price is NOT in the code
        # OLD CODE HAD: price_ref = decimal.Decimal('3850')
        assert "Decimal('3850')" not in source, (
            "CRITICAL: Hardcoded fallback price '3850' found in source code!"
        )

        # Also check for any suspicious numeric fallbacks
        # (this is a heuristic check - might need adjustment)
        assert (
            "fallback price" not in source.lower() or "fail-closed" in source.lower()
        ), "Found 'fallback price' mention without 'fail-closed' - check implementation"

        print("\n✅ Code inspection passed: No hardcoded fallback price found")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
