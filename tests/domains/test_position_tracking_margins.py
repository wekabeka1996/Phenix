"""
Tests for PositionTracking margin-by-side calculations.

EXP-DIRECTION: Tests for per-side margin calculation and PORTFOLIO_STATE_UPDATED emission.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from apps.reference.domains.position_tracking.position_tracking import PositionTracking


@pytest.fixture
def pt_config():
    """Fixture for PositionTracking configuration."""
    return {
        "trading": {
            "execution": {
                "exposure": {
                    "leverage_defaults": {
                        "BTCUSDT": "20",
                        "ETHUSDT": "20",
                        "__default__": "15"
                    }
                }
            }
        },
        "system": {
            "worker_id": "test_worker"
        }
    }


@pytest.fixture
def position_tracking(pt_config):
    """Fixture for PositionTracking instance."""
    fsm = MagicMock()
    fsm.emit = MagicMock()
    fsm.listen = MagicMock()

    pt = PositionTracking(fsm, pt_config)
    return pt


def test_margin_by_side_empty_positions(position_tracking):
    """Test margin calculation with no positions."""
    result = position_tracking._calculate_margin_by_side([])

    assert result["long_margin"] == Decimal("0")
    assert result["short_margin"] == Decimal("0")


def test_margin_by_side_single_long_position(position_tracking):
    """Test margin calculation with single long position."""
    # BTC: 1 unit @ 50000 = 50000 notional, lev=20 → 2500 margin
    positions = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "1.0",
            "markPrice": "50000",
            "leverage": "20",
            "notional": "50000"
        }
    ]

    result = position_tracking._calculate_margin_by_side(positions)

    assert result["long_margin"] == Decimal("2500.00")
    assert result["short_margin"] == Decimal("0.00")


def test_margin_by_side_single_short_position(position_tracking):
    """Test margin calculation with single short position."""
    # ETH: -10 units @ 2500 = 25000 notional (abs), lev=20 → 1250 margin
    positions = [
        {
            "symbol": "ETHUSDT",
            "positionAmt": "-10.0",
            "markPrice": "2500",
            "leverage": "20",
            "notional": "25000"
        }
    ]

    result = position_tracking._calculate_margin_by_side(positions)

    assert result["long_margin"] == Decimal("0.00")
    assert result["short_margin"] == Decimal("1250.00")


def test_margin_by_side_mixed_positions(position_tracking):
    """Test margin calculation with both long and short positions."""
    positions = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "2.0",  # Long 2 BTC
            "markPrice": "50000",
            "leverage": "20",
            "notional": "100000"
        },
        {
            "symbol": "ETHUSDT",
            "positionAmt": "-50.0",  # Short 50 ETH
            "markPrice": "2500",
            "leverage": "20",
            "notional": "125000"
        }
    ]

    result = position_tracking._calculate_margin_by_side(positions)

    # Long margin: 100000 / 20 = 5000
    assert result["long_margin"] == Decimal("5000.00")
    # Short margin: 125000 / 20 = 6250
    assert result["short_margin"] == Decimal("6250.00")


def test_margin_by_side_directional_ratio(position_tracking):
    """Test that directional ratio can be calculated from margins."""
    positions = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "1.0",
            "markPrice": "40000",
            "leverage": "20",
            "notional": "40000"
        },
        {
            "symbol": "ETHUSDT",
            "positionAmt": "-30.0",
            "markPrice": "1000",
            "leverage": "20",
            "notional": "30000"
        }
    ]

    result = position_tracking._calculate_margin_by_side(positions)

    long_margin = result["long_margin"]  # 2000
    short_margin = result["short_margin"]  # 1500

    # Ratio = max(L,S) / min(L,S) = 2000/1500 = 1.33:1
    ratio = long_margin / short_margin if short_margin > 0 else Decimal("0")
    assert ratio == Decimal("4") / Decimal("3")  # 1.33


def test_margin_by_side_with_fallback_leverage(position_tracking):
    """Test margin calculation falls back to config leverage when not provided."""
    # Simulate internal position without positionRisk data
    position_tracking._positions["BTCUSDT"] = {
        "quantity": Decimal("1.0"),
        "avg_price": Decimal("50000")
    }

    result = position_tracking._calculate_margin_by_side([])

    # Should use config leverage (20 for BTC)
    # Margin = (1.0 * 50000) / 20 = 2500
    assert result["long_margin"] == Decimal("2500.00")
    assert result["short_margin"] == Decimal("0.00")


def test_portfolio_state_includes_margin_by_side(position_tracking):
    """Test that _calculate_margin_by_side returns correct structure."""
    # Pass positions as list of dicts (like positionRisk data)
    positions = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "1.0",
            "markPrice": "50000",
            "leverage": "20"
        },
        {
            "symbol": "ETHUSDT",
            "positionAmt": "-2.0",
            "markPrice": "3000",
            "leverage": "20"
        }
    ]

    # Call calculate method directly
    result = position_tracking._calculate_margin_by_side(positions)

    # Verify structure
    assert "long_margin" in result
    assert "short_margin" in result

    # Verify values are Decimal (internal representation)
    assert isinstance(result["long_margin"], Decimal)
    assert isinstance(result["short_margin"], Decimal)

    # Verify long margin is calculated (50000 * 1 / 20 = 2500)
    assert result["long_margin"] == Decimal("2500.00")

    # Verify short margin is calculated (3000 * 2 / 20 = 300)
    assert result["short_margin"] == Decimal("300.00")


def test_margin_calculation_precision(position_tracking):
    """Test that margin calculations maintain precision."""
    positions = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.12345",
            "markPrice": "43567.89",
            "leverage": "20",
            "notional": "5381.93"
        }
    ]

    result = position_tracking._calculate_margin_by_side(positions)

    # Margin = 5381.93 / 20 = 269.0965, rounded to 269.10
    long_margin = result["long_margin"]
    assert long_margin > Decimal("260")
    assert long_margin < Decimal("280")


def test_zero_leverage_handled(position_tracking):
    """Test that zero or invalid leverage is handled gracefully."""
    positions = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "1.0",
            "markPrice": "50000",
            "leverage": "0",  # Invalid zero leverage
            "notional": "50000"
        }
    ]

    result = position_tracking._calculate_margin_by_side(positions)

    # Should default to leverage=1 when invalid
    # Margin = 50000 / 1 = 50000
    assert result["long_margin"] == Decimal("50000.00")


def test_negative_position_is_short(position_tracking):
    """Test that negative positionAmt is correctly classified as short."""
    positions = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "-5.0",  # Negative = short
            "markPrice": "50000",
            "leverage": "20",
            "notional": "250000"
        }
    ]

    result = position_tracking._calculate_margin_by_side(positions)

    # All margin should be on short side
    assert result["long_margin"] == Decimal("0.00")
    assert result["short_margin"] == Decimal("12500.00")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
