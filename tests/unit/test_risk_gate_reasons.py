"""
Unit tests for risk gate reasons.

Tests that budget conflicts and daily limits are properly marked.
"""

import pytest
from unittest.mock import Mock
from apps.reference.domains.risk_management.risk_management import RiskManagement


def test_daily_drawdown_gate_blocks_trading():
    """Test that daily drawdown breaches block all trading."""

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
        "risk": {
            "max_daily_drawdown_limit": "0.05",  # 5% limit
            "score_weights": {"delta_price": 0.1, "obi": 0.3, "tfi": 0.3, "absorption_inverse": 0.3},
            "trading_allowed_thresholds": {"max_risk_score": 0.8},
        }
    }

    rm = RiskManagement(fsm, cfg)

    # Set drawdown above limit
    rm.current_daily_drawdown = 0.08  # 8% > 5% limit

    # Calculate risk parameters
    features = {
        "obi": 0.1,
        "tfi": 0.1,
        "delta_price": 0.0,
        "absorption": 0.5,
        "price": 50000
    }

    result = rm._calculate_risk_parameters(features)

    # Should be blocked
    assert result["is_trading_allowed"] == False
    # Note: We can't easily test the logging output in unit tests,
    # but the logic ensures drawdown breaches disable trading


def test_risk_score_gate_blocks_high_risk():
    """Test that high risk scores block trading."""

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
        "risk": {
            "max_daily_drawdown_limit": "0.10",
            "score_weights": {"delta_price": 0.1, "obi": 0.3, "tfi": 0.3, "absorption_inverse": 0.3},
            "trading_allowed_thresholds": {"max_risk_score": 0.5},  # Restrictive threshold
        }
    }

    rm = RiskManagement(fsm, cfg)

    # Create high-risk features
    features = {
        "obi": -0.8,  # Very bearish
        "tfi": -0.8,  # Very bearish
        "delta_price": -0.05,  # 5% price drop
        "absorption": 0.1,  # Low absorption = high risk
        "price": 50000
    }

    result = rm._calculate_risk_parameters(features)

    # Should be blocked due to high risk score
    assert result["is_trading_allowed"] == False
    assert result["risk_score"] > 0.5  # Above threshold


def test_budget_exposure_limits():
    """Test exposure limit handling (placeholder for future budget logic)."""

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
        "risk": {
            "max_daily_drawdown_limit": "0.10",
            "score_weights": {"delta_price": 0.1, "obi": 0.3, "tfi": 0.3, "absorption_inverse": 0.3},
            "trading_allowed_thresholds": {"max_risk_score": 0.8},
        }
    }

    rm = RiskManagement(fsm, cfg)

    # Normal features
    features = {
        "obi": 0.2,
        "tfi": 0.2,
        "delta_price": 0.0,
        "absorption": 0.5,
        "price": 50000
    }

    result = rm._calculate_risk_parameters(features)

    # Should allow trading (baseline test)
    assert result["is_trading_allowed"] == True
    assert result["risk_score"] <= 0.8

    # Note: Full budget logic would require portfolio state integration
    # This test establishes the baseline for future budget checks


def test_portfolio_state_integration():
    """Test that portfolio drawdown calculations work correctly."""

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
        "risk": {
            "max_daily_drawdown_limit": "0.10",  # 10%
        }
    }

    rm = RiskManagement(fsm, cfg)

    # Set initial equity
    rm.peak_equity = 10000
    rm.current_daily_drawdown = 0.0

    # Simulate portfolio update with loss
    portfolio_event = Mock()
    portfolio_event.pld = {
        "equity": "8500",  # Lost 15%
        "positions": []
    }

    rm.on_portfolio_state_updated(portfolio_event)

    # Drawdown should be calculated: (10000 - 8500) / 10000 = 0.15
    from decimal import Decimal
    assert rm.current_daily_drawdown == Decimal('0.15')

    # Test risk calculation with this drawdown
    features = {
        "obi": 0.1,
        "tfi": 0.1,
        "delta_price": 0.0,
        "absorption": 0.5,
        "price": 50000
    }

    result = rm._calculate_risk_parameters(features)

    # Should be blocked due to drawdown > 10%
    assert result['is_trading_allowed'] == False
