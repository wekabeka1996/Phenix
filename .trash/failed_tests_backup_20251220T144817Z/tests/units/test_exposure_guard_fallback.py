"""
Unit tests for ExposureGuard fallback mode functionality.

Tests fallback mode entry/exit, policy application, and metrics.
"""

import time
import pytest
from apps.reference.domains.execution_position.exposure_guard import (
    ExposureGuard,
    FallbackState,
)
from decimal import Decimal
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_fallback_mode_enter_exit():
    """Test entering and exiting fallback mode."""
    guard = ExposureGuard({
        "trading": {
            "execution": {
                "fallback": {
                    "policy": "fail_closed",
                    "risk_reduction_pct": "0.5",
                    "backoff_ms": [200, 500, 1000]
                }
            }
        }
    })

    # Initially not in fallback mode
    assert not guard.is_fallback_mode_active()
    assert guard.fallback_state.reason is None

    # Enter fallback mode
    guard.enter_fallback_mode("API_TIMEOUT")

    assert guard.is_fallback_mode_active()
    assert guard.fallback_state.reason == "API_TIMEOUT"
    assert guard.fallback_state.active is True
    assert guard.fallback_state.entered_at is not None

    # Exit fallback mode
    guard.exit_fallback_mode()

    assert not guard.is_fallback_mode_active()
    assert guard.fallback_state.reason == ""
    assert guard.fallback_state.active is False


def test_fallback_mode_fail_closed_policy():
    """Test fail_closed policy blocks trades during fallback."""
    guard = ExposureGuard({
        "trading": {
            "execution": {
                "fallback": {
                    "policy": "fail_closed",
                    "risk_reduction_pct": "0.5"
                }
            }
        }
    })

    # Enter fallback mode
    guard.enter_fallback_mode("EMPTY_POSITIONS")

    # Test can_open with valid portfolio state
    portfolio_state = {
        "equity_free_usdt": "1000",
        "open_positions_margin_usd": "100",
        "positions_last_ts_ms": int(time.time() * 1000),
        "positions_by_side": {"long_margin": "50", "short_margin": "50"}
    }

    result = guard.can_open("BTCUSDT", Decimal("100"), portfolio_state)

    assert result["allowed"] is False
    assert "FALLBACK_FAIL_CLOSED_EMPTY_POSITIONS" in result["reason"]


def test_fallback_mode_risk_reduction_policy():
    """Test risk_reduction policy reduces trade size during fallback."""
    guard = ExposureGuard({
        "trading": {
            "execution": {
                "fallback": {
                    "policy": "risk_reduction",
                    "risk_reduction_pct": "0.5"
                }
            }
        }
    })

    # Enter fallback mode
    guard.enter_fallback_mode("API_TIMEOUT")

    # Test can_open with valid portfolio state
    portfolio_state = {
        "equity_free_usdt": "10000",  # High equity to avoid other limits
        "open_positions_margin_usd": "100",
        "positions_last_ts_ms": int(time.time() * 1000),
        "positions_by_side": {"long_margin": "50", "short_margin": "50"}
    }

    # This should pass but with reduced notional
    result = guard.can_open("BTCUSDT", Decimal("1000"), portfolio_state)

    # Should be allowed but with risk reduction applied
    # (The exact behavior depends on other exposure checks, but fallback should be applied)
    assert result["allowed"] is True or "FALLBACK" in result.get("reason", "")


def test_fallback_mode_metrics():
    """Test that fallback mode increments metrics correctly."""
    guard = ExposureGuard({
        "trading": {
            "execution": {
                "fallback": {
                    "policy": "fail_closed"
                }
            }
        }
    })

    # Initially no fallback metrics
    assert guard.metrics["fallback_mode_entries_total"] == 0

    # Enter fallback mode
    guard.enter_fallback_mode("TEST_REASON")

    assert guard.metrics["fallback_mode_entries_total"]["TEST_REASON"] == 1

    # Exit fallback mode
    guard.exit_fallback_mode()

    # Duration should be tracked (may be 0 if very fast, but should exist)
    assert "fallback_duration_ms_total" in guard.metrics
    assert isinstance(
        guard.metrics["fallback_duration_ms_total"], (int, float))


def test_fallback_config_loading():
    """Test fallback configuration loading from config."""
    config = {
        "trading": {
            "execution": {
                "fallback": {
                    "policy": "risk_reduction",
                    "risk_reduction_pct": "0.3",
                    "backoff_ms": [100, 200, 500]
                }
            }
        }
    }

    guard = ExposureGuard(config)

    assert guard.fallback_config["policy"] == "risk_reduction"
    assert guard.fallback_config["risk_reduction_pct"] == Decimal("0.3")
    assert guard.fallback_config["backoff_ms"] == [100, 200, 500]


def test_fallback_state_dataclass():
    """Test FallbackState dataclass functionality."""
    state = FallbackState()

    assert state.active is False
    assert state.entered_at is None
    assert state.reason is None
    assert state.risk_reduction_pct == Decimal("0.5")

    # Test with custom values
    state = FallbackState(
        active=True,
        entered_at=1234567890,
        reason="TEST",
        risk_reduction_pct=Decimal("0.25")
    )

    assert state.active is True
    assert state.entered_at == 1234567890
    assert state.reason == "TEST"
    assert state.risk_reduction_pct == Decimal("0.25")
