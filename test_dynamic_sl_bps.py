#!/usr/bin/env python3
"""
Test for dynamic SL_bps multiplier based on volatility_state.
Tests the adaptive position sizing feature from TODO.md Phase 1.
"""

import decimal
import pytest
from unittest.mock import Mock, patch
from apps.reference.domains.decision_making.decision_making import DecisionMaking


class MockFSM:
    def __init__(self):
        self.listeners = {}

    def listen(self, event, handler):
        if event not in self.listeners:
            self.listeners[event] = []
        self.listeners[event].append(handler)

    def emit(self, event_name, payload=None, why=None, data_ref=None):
        pass


class TestDynamicSLBps:
    """Test dynamic SL_bps multiplier functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = {
            "trading": {
                "decision": {
                    "position_sizing": {
                        "min_position_size_usd": 10,
                        "liquidity_based_cap_usd": 10000,
                        "risk_fraction_q": 0.01  # Enable SL_bps sizing
                    }
                },
                "execution": {
                    "brackets": {
                        "sl": {
                            "fixed_bps": 50
                        }
                    }
                },
                "tca_prefs": {"max_slippage_bps": 10},
                "risk_budgets": {"trade_cvar95_max_bps": 100},
                "instruments": {
                    "BTCUSDT": {"step_size": "0.001"}
                }
            }
        }

        self.fsm = MockFSM()
        self.decision_making = DecisionMaking(
            fsm=self.fsm,
            config=self.config
        )

    def test_sl_bps_high_vol_multiplier(self):
        """Test HIGH_VOL volatility state applies 1.4x multiplier."""
        context = {
            "_sizing_meta": {
                "volatility_state": "HIGH_VOL"
            },
            "portfolio": {
                "equity": "1000"
            }
        }

        # Mock logger to capture debug calls
        with patch.object(self.decision_making, 'logger') as mock_logger:
            # Call the position size calculation
            result = self.decision_making._calculate_position_size(
                symbol="BTCUSDT",
                price=decimal.Decimal("50000"),
                side="BUY",
                context=context
            )

            # Verify the multiplier was applied (50 * 1.4 = 70)
            # Check that debug log was called with correct values
            mock_logger.debug.assert_called_with(
                "[BTCUSDT] SL_BPS_ADJUSTED: base=50, multiplier=1.4, final=70.0"
            )

    def test_sl_bps_low_vol_multiplier(self):
        """Test LOW_VOL volatility state applies 0.8x multiplier."""
        context = {
            "_sizing_meta": {
                "volatility_state": "LOW_VOL"
            },
            "portfolio": {
                "equity": "1000"
            }
        }

        with patch.object(self.decision_making, 'logger') as mock_logger:
            result = self.decision_making._calculate_position_size(
                symbol="BTCUSDT",
                price=decimal.Decimal("50000"),
                side="BUY",
                context=context
            )

            # Verify the multiplier was applied (50 * 0.8 = 40)
            mock_logger.debug.assert_called_with(
                "[BTCUSDT] SL_BPS_ADJUSTED: base=50, multiplier=0.8, final=40.0"
            )

    def test_sl_bps_normal_vol_multiplier(self):
        """Test normal volatility state applies 1.0x multiplier."""
        context = {
            "_sizing_meta": {
                "volatility_state": "NORMAL_VOL"
            },
            "portfolio": {
                "equity": "1000"
            }
        }

        with patch.object(self.decision_making, 'logger') as mock_logger:
            result = self.decision_making._calculate_position_size(
                symbol="BTCUSDT",
                price=decimal.Decimal("50000"),
                side="BUY",
                context=context
            )

            # Verify the multiplier was applied (50 * 1.0 = 50)
            mock_logger.debug.assert_called_with(
                "[BTCUSDT] SL_BPS_ADJUSTED: base=50, multiplier=1.0, final=50.0"
            )

    def test_sl_bps_no_volatility_state(self):
        """Test missing volatility_state defaults to 1.0x multiplier."""
        context = {
            "_sizing_meta": {},
            "portfolio": {
                "equity": "1000"
            }
        }

        with patch.object(self.decision_making, 'logger') as mock_logger:
            result = self.decision_making._calculate_position_size(
                symbol="BTCUSDT",
                price=decimal.Decimal("50000"),
                side="BUY",
                context=context
            )

            # Verify default multiplier was applied (50 * 1.0 = 50)
            mock_logger.debug.assert_called_with(
                "[BTCUSDT] SL_BPS_ADJUSTED: base=50, multiplier=1.0, final=50.0"
            )


if __name__ == "__main__":
    pytest.main([__file__])
