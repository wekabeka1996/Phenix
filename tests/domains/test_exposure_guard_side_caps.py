"""
Comprehensive tests for ExposureGuard side-cap, ratio-gate, and shrink-to-fit logic.

EXP-DIRECTION: Tests for per-side limits and directional imbalance enforcement.
"""

import pytest
from decimal import Decimal
from typing import Dict, Any
from unittest.mock import MagicMock
import time

from apps.reference.domains.execution_position.exposure_guard import ExposureGuard


@pytest.fixture
def exposure_guard_config():
    """Fixture for exposure guard configuration with side-caps."""
    return {
        "trading": {
            "execution": {
                "exposure": {
                    "max_equity_utilization_pct": "0.20",  # 20% total
                    "max_side_utilization_pct": {
                        "long": "0.12",  # 12% max long
                        "short": "0.12"  # 12% max short
                    },
                    "max_directional_ratio": "2.0",  # Max 2:1 ratio
                    "per_symbol_cap_pct": "0.08",  # 8% per symbol
                    "leverage_defaults": {
                        "BTCUSDT": "20",
                        "ETHUSDT": "20",
                        "__default__": "15"
                    },
                    "pending_ttl_sec": "90",
                    "post_fill_hold_ttl_sec": "5"
                }
            }
        }
    }


@pytest.fixture
def exposure_guard(exposure_guard_config):
    """Fixture for ExposureGuard instance."""
    return ExposureGuard(exposure_guard_config, fsm=None)


def test_total_margin_cap(exposure_guard):
    """Test that total margin cap is enforced."""
    # Setup: Equity $1000, max total margin = $200
    now_ms = int(time.time() * 1000)
    portfolio_state = {
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "180",  # Already using $180
        "positions_last_ts_ms": now_ms,  # Current timestamp
        "positions_by_side": {
            "long_margin": "100",
            "short_margin": "80"
        }
    }

    # Try to add $30 more (would be $210 > $200 limit)
    result = exposure_guard.can_open(
        "ETHUSDT", Decimal("600"), portfolio_state)

    # Should be rejected or shrunk
    assert result.get("allowed") == False or result.get("reason") in [
        "SHRUNK_TO_FIT", "SHRUNK_TO_FIT_SIDE", "EXPOSURE_LIMIT_EXCEEDED"]


def test_side_cap_long(exposure_guard):
    """Test that per-side cap for long is enforced."""
    # Setup: $1000 equity, 12% long cap = $120
    now_ms = int(time.time() * 1000)
    portfolio_state = {
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "110",
        "positions_last_ts_ms": now_ms,
        "positions_by_side": {
            "long_margin": "110",  # Already at $110
            "short_margin": "0"
        }
    }

    # Try to add BUY (long) with $20 margin (would be $130 > $120 limit)
    result = exposure_guard.can_open(
        "BTCUSDT", Decimal("400"), portfolio_state)

    # Should be shrunk or rejected
    assert (result.get("allowed") == False or
            result.get("reason") in ["SHRUNK_TO_FIT_SIDE", "SIDE_EXPOSURE_EXCEEDED"])


def test_side_cap_short(exposure_guard):
    """Test that per-side cap for short is enforced."""
    # Setup: $1000 equity, 12% short cap = $120
    now_ms = int(time.time() * 1000)
    portfolio_state = {
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "105",
        "positions_last_ts_ms": now_ms,
        "positions_by_side": {
            "long_margin": "0",
            "short_margin": "105"  # Already at $105
        }
    }

    # Try to add SELL (short) with $20 margin
    result = exposure_guard.can_open(
        "ETHUSDT", Decimal("400"), portfolio_state)

    # Should be shrunk or rejected
    assert (result.get("allowed") == False or
            result.get("reason") in ["SHRUNK_TO_FIT_SIDE", "SIDE_EXPOSURE_EXCEEDED"])


def test_directional_ratio_enforcement(exposure_guard):
    """Test that directional ratio (2:1 max) is enforced."""
    # Setup: $1000 equity
    # Long: $80, Short: $30 (ratio = 2.67:1, exceeds 2:1 limit)
    now_ms = int(time.time() * 1000)
    portfolio_state = {
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "110",
        "positions_last_ts_ms": now_ms,
        "positions_by_side": {
            "long_margin": "80",
            "short_margin": "30"
        }
    }

    # Try to add more SELL (short) - would worsen imbalance
    result = exposure_guard.can_open(
        "BTCUSDT", Decimal("100"), portfolio_state)

    # Should be rejected or clipped due to ratio
    assert (result.get("reason") in ["DIRECTIONAL_RATIO_EXCEEDED", "CLIPPED_DIRECTIONAL"] or
            result.get("allowed") == False)


def test_shrink_to_fit_total(exposure_guard):
    """Test shrink-to-fit for total margin cap."""
    # Setup: $1000 equity, can use max $200 total margin
    now_ms = int(time.time() * 1000)
    portfolio_state = {
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "190",  # Using $190
        "positions_last_ts_ms": now_ms,
        "positions_by_side": {
            "long_margin": "100",
            "short_margin": "90"
        }
    }

    # Try to add $15 notional (= $15/20 = $0.75 margin)
    # Should fit within $10 remaining ($200 - $190)
    result = exposure_guard.can_open(
        "ETHUSDT", Decimal("150"), portfolio_state)

    # Should allow, possibly shrunk
    assert result.get("allowed") == True
    if "shrink_notional" in result:
        # Verify shrunk amount is reasonable
        assert result["shrink_notional"] > Decimal("0")
        assert result["shrink_notional"] <= Decimal("150")


def test_shrink_to_fit_side_cap(exposure_guard):
    """Test shrink-to-fit for side cap."""
    # Setup: $1000 equity, 12% long cap = $120
    now_ms = int(time.time() * 1000)
    portfolio_state = {
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "115",
        "positions_last_ts_ms": now_ms,
        "positions_by_side": {
            "long_margin": "115",  # Using $115 of $120 allowed
            "short_margin": "0"
        }
    }

    # Try to add BUY (long) with $10 margin
    # Should shrink to fit within $5 remaining
    result = exposure_guard.can_open(
        "BTCUSDT", Decimal("100"), portfolio_state)

    # Should allow with shrink
    if result.get("allowed") == True:
        assert "shrink_notional" in result
        assert result["shrink_notional"] > Decimal("0")


def test_balanced_positions_allowed(exposure_guard):
    """Test that balanced positions are allowed even near limits."""
    # Setup: $1000 equity
    # Long: $60, Short: $60 (balanced, ratio = 1:1)
    now_ms = int(time.time() * 1000)
    portfolio_state = {
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "120",
        "positions_last_ts_ms": now_ms,
        "positions_by_side": {
            "long_margin": "60",
            "short_margin": "60"
        }
    }

    # Try to add $10 BUY (would be Long=$70, Short=$60, ratio=1.17:1)
    # Should be allowed since ratio < 2:1 and both sides < 12%
    result = exposure_guard.can_open(
        "ETHUSDT", Decimal("200"), portfolio_state)

    # Should be allowed
    assert result.get("allowed") == True


def test_zero_positions_startup(exposure_guard):
    """Test that trades are allowed when starting from zero positions."""
    # Setup: Fresh account
    now_ms = int(time.time() * 1000)
    portfolio_state = {
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "0",
        "positions_last_ts_ms": now_ms,
        "positions_by_side": {
            "long_margin": "0",
            "short_margin": "0"
        }
    }

    # Try to add $50 BUY
    result = exposure_guard.can_open(
        "BTCUSDT", Decimal("1000"), portfolio_state)

    # Should be allowed
    assert result.get("allowed") == True


def test_reject_when_all_caps_exceeded(exposure_guard):
    """Test that order is rejected (not shrunk) when well over limits."""
    # Setup: $1000 equity, requesting $500 notional (= $25 margin)
    # with already $198 used (near $200 total limit)
    portfolio_state = {
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "198",
        "positions_last_ts_ms": 1000,
        "positions_by_side": {
            "long_margin": "100",
            "short_margin": "98"
        }
    }

    # Try to add huge SELL order
    result = exposure_guard.can_open(
        "ETHUSDT", Decimal("10000"), portfolio_state)

    # Should be rejected (no room to shrink)
    assert result.get("allowed") == False


def test_reserve_and_release(exposure_guard):
    """Test reserve and release of exposure."""
    # Reserve $30 margin
    exposure_guard.reserve("order_1", Decimal(
        "600"), symbol="BTCUSDT", side="BUY")

    # Check that it's tracked
    assert "order_1" in exposure_guard.state.reservations
    assert exposure_guard.state.reservations["order_1"] == Decimal("600")

    # Release it
    exposure_guard.release("order_1")

    # Check that it's removed
    assert "order_1" not in exposure_guard.state.reservations


def test_on_fill_moves_to_postfill(exposure_guard):
    """Test that on_fill moves reservation to post-fill hold."""
    # Reserve first
    exposure_guard.reserve("order_1", Decimal(
        "600"), symbol="BTCUSDT", side="BUY")

    # Simulate fill
    exposure_guard.on_fill("order_1", Decimal(
        "600"), symbol="BTCUSDT", side="BUY")

    # Should be moved from reservations to postfill_reservations
    assert "order_1" not in exposure_guard.state.reservations
    assert "order_1" in exposure_guard.state.postfill_reservations


def test_nrr_codes_in_rejection(exposure_guard):
    """Test that appropriate NRR codes are logged when rejecting or shrinking."""
    from apps.reference.telemetry.order_logger import order_logger
    from unittest.mock import patch

    now_ms = int(time.time() * 1000)
    portfolio_state = {
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "199",
        "positions_last_ts_ms": now_ms,
        "positions_by_side": {
            "long_margin": "100",
            "short_margin": "99"
        }
    }

    # Try to add trade that violates total cap
    result = exposure_guard.can_open(
        "ETHUSDT", Decimal("5000"), portfolio_state)

    # Should either shrink or reject (both are valid handling)
    assert result.get("allowed") in [True, False]
    if result.get("allowed") == True:
        # Shrunk to fit
        assert result.get("reason") == "SHRUNK_TO_FIT"
        assert result.get("shrink_notional") > Decimal("0")
    else:
        # Rejected
        assert result.get("reason") in [
            "EXPOSURE_LIMIT_EXCEEDED", "SIDE_EXPOSURE_EXCEEDED"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
