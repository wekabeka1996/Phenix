"""
Unit tests for risk_score null fix.

Ensures risk_score is always numeric (never null) in EVT:RISK_ASSESSMENT_COMPLETED.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from apps.reference.domains.risk_management.risk_management import RiskManagement


@pytest.mark.asyncio
async def test_risk_score_always_number():
    """Test that risk_score is always a float, never null."""
    # Mock FSM
    fsm = MagicMock()
    emitted_events = []
    fsm.emit = lambda *args, **kwargs: emitted_events.append((args, kwargs))

    # Create RiskManagement instance
    config = {
        "risk": {
            "max_daily_drawdown_limit": "0.10",
            "score_weights": {
                "delta_price": "0.1",
                "obi": "0.3",
                "tfi": "0.3",
                "absorption_inverse": "0.3"
            },
            "trading_allowed_thresholds": {
                "max_risk_score": "0.8"
            }
        }
    }
    risk_mgmt = RiskManagement(fsm, config)

    # Mock event with features
    event = MagicMock()
    event.pld = {
        "symbol": "BTCUSDT",
        "ts": 1234567890,
        "features": {
            "obi": "-0.5",
            "tfi": "-0.4",
            "delta_price": "100",  # $100 change
            "price": "50000",      # $50k current price
            "absorption": "0.7"
        }
    }

    # Call the handler
    risk_mgmt.on_features_calculated(event)

    # Verify event was emitted
    assert len(emitted_events) == 1
    args, kwargs = emitted_events[0]

    # Check that risk_score is present and is a float
    risk_params = kwargs["payload"]["risk_parameters"]
    assert "risk_score" in risk_params
    assert isinstance(risk_params["risk_score"], float)
    assert risk_params["risk_score"] >= 0.0
    assert risk_params["risk_score"] <= 1.0

    print(f"✅ risk_score = {risk_params['risk_score']} (type: {type(risk_params['risk_score'])})")


@pytest.mark.asyncio
async def test_risk_score_with_invalid_features():
    """Test risk_score calculation with invalid/missing feature values."""
    # Mock FSM
    fsm = MagicMock()
    emitted_events = []
    fsm.emit = lambda *args, **kwargs: emitted_events.append((args, kwargs))

    # Create RiskManagement instance
    config = {
        "risk": {
            "max_daily_drawdown_limit": "0.10",
            "score_weights": {
                "delta_price": "0.1",
                "obi": "0.3",
                "tfi": "0.3",
                "absorption_inverse": "0.3"
            },
            "trading_allowed_thresholds": {
                "max_risk_score": "0.8"
            }
        }
    }
    risk_mgmt = RiskManagement(fsm, config)

    # Mock event with invalid features
    event = MagicMock()
    event.pld = {
        "symbol": "BTCUSDT",
        "ts": 1234567890,
        "features": {
            "obi": None,           # Invalid
            "tfi": "invalid",      # Invalid string
            "delta_price": "",     # Empty string
            "price": 0,            # Zero price
            "absorption": "not_a_number"  # Invalid
        }
    }

    # Call the handler
    risk_mgmt.on_features_calculated(event)

    # Verify event was emitted and risk_score is still valid
    assert len(emitted_events) == 1
    args, kwargs = emitted_events[0]

    risk_params = kwargs["payload"]["risk_parameters"]
    assert "risk_score" in risk_params
    assert isinstance(risk_params["risk_score"], float)
    assert risk_params["risk_score"] >= 0.0
    assert risk_params["risk_score"] <= 1.0

    print(f"✅ risk_score with invalid features = {risk_params['risk_score']} (type: {type(risk_params['risk_score'])})")
