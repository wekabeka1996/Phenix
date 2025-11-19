"""
EP-STAB-LIVEPOS-FIX-AGG: Tests for entry_price guard in ManageFlowFSM.

Tests verify that _compute_aggregated_bracket_levels returns None (instead of raising
AggregatedOcoError) when position_entry_price is None or <= 0, preventing
DECISION_EXECUTION_FAILED errors from reaching the aggregator.
"""

from decimal import Decimal
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM


@pytest.fixture
def mock_manage_fsm():
    """Create ManageFlowFSM mock with minimal config."""
    config = {
        "execution": {
            "manage": {
                "mode": "aggregated_only",
                "auto": True,
                "brackets": {
                    "enable": True,
                    "aggregated_oco": {
                        "enabled": True,
                        "aggregated_only_mode": True,
                        "recalc_on_scale_in": True,
                        "recalc_on_partial_close": True,
                        "ttl_protect_new_bracket_ms": 0,
                        "sl": {"fixed_bps": 100},
                        "tp": {"fixed_bps": 200},
                    }
                },
                "guardian": {
                    "unified": True,
                    "poll_interval_ms": 1000,
                    "cleanup_ttl_ms": 60000,
                    "symbol_cooldown_ms": 5000,
                    "emit_tidy_event": False
                },
                "watchdog": {
                    "ack_ttl_ms": 5000,
                    "fill_ttl_ms": 30000,
                    "source": "config"
                }
            }
        },
        "trading": {
            "instruments": {
                "BTCUSDT": {"min_qty": "0.001", "tick_size": "0.01"}
            }
        },
        "binance_api": {
            "testnet": {
                "api_key": "fake_key",
                "api_secret": "fake_secret",
                "rest_url": "https://testnet.binance.vision/api"
            }
        }
    }

    fsm = ManageFlowFSM(config=config, symbol="BTCUSDT")

    # Mock parent FSM
    fsm.fsm = MagicMock()
    fsm.fsm.emit = MagicMock()

    return fsm


def test_entry_price_none_returns_none_instead_of_error(mock_manage_fsm):
    """
    Test that _compute_aggregated_bracket_levels returns None when entry_price is None.

    Before fix: Would raise AggregatedOcoError("position snapshot is incomplete")
    After fix: Returns None with AGG_OCO_ENTRY_PRICE_NOT_READY warning
    """
    fsm = mock_manage_fsm

    # Set position state: qty and side present, but entry_price is None
    fsm.position_qty = Decimal("0.5")
    fsm.position_side = "LONG"
    fsm.position_entry_price = None  # ❌ Invalid: None

    # Mock agg_oco_logger to capture warning
    with patch("apps.reference.domains.execution_position.fsm_manage.agg_oco_logger") as mock_logger:
        result = fsm._compute_aggregated_bracket_levels(reason="test_none")

        # Should return None (not raise AggregatedOcoError)
        assert result is None

        # Should log AGG_OCO_ENTRY_PRICE_NOT_READY warning
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args[0][0] == "AGG_OCO_ENTRY_PRICE_NOT_READY"
        assert call_args[1]["extra"]["symbol"] == "BTCUSDT"
        assert call_args[1]["extra"]["entry_price"] is None
        assert call_args[1]["extra"]["event_type"] == "AGG_OCO_ENTRY_PRICE_NOT_READY"


def test_entry_price_zero_returns_none_instead_of_error(mock_manage_fsm):
    """
    Test that _compute_aggregated_bracket_levels returns None when entry_price is 0.

    Before fix: Would call aggregator → AggregatedOcoError("avg_entry_price must be > 0")
    After fix: Returns None with AGG_OCO_ENTRY_PRICE_NOT_READY warning
    """
    fsm = mock_manage_fsm

    # Set position state: qty and side present, but entry_price is 0
    fsm.position_qty = Decimal("0.5")
    fsm.position_side = "LONG"
    fsm.position_entry_price = Decimal("0")  # ❌ Invalid: zero

    # Mock agg_oco_logger to capture warning
    with patch("apps.reference.domains.execution_position.fsm_manage.agg_oco_logger") as mock_logger:
        result = fsm._compute_aggregated_bracket_levels(reason="test_zero")

        # Should return None (not raise AggregatedOcoError)
        assert result is None

        # Should log AGG_OCO_ENTRY_PRICE_NOT_READY warning
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args[0][0] == "AGG_OCO_ENTRY_PRICE_NOT_READY"
        assert call_args[1]["extra"]["symbol"] == "BTCUSDT"
        assert call_args[1]["extra"]["entry_price"] == "0"


def test_entry_price_negative_returns_none_instead_of_error(mock_manage_fsm):
    """
    Test that _compute_aggregated_bracket_levels returns None when entry_price is negative.

    Before fix: Would call aggregator → AggregatedOcoError("avg_entry_price must be > 0")
    After fix: Returns None with AGG_OCO_ENTRY_PRICE_NOT_READY warning
    """
    fsm = mock_manage_fsm

    # Set position state: qty and side present, but entry_price is negative
    fsm.position_qty = Decimal("0.5")
    fsm.position_side = "LONG"
    fsm.position_entry_price = Decimal("-50000")  # ❌ Invalid: negative

    # Mock agg_oco_logger to capture warning
    with patch("apps.reference.domains.execution_position.fsm_manage.agg_oco_logger") as mock_logger:
        result = fsm._compute_aggregated_bracket_levels(reason="test_negative")

        # Should return None (not raise AggregatedOcoError)
        assert result is None

        # Should log AGG_OCO_ENTRY_PRICE_NOT_READY warning
        mock_logger.warning.assert_called_once()


def test_entry_price_valid_proceeds_normally(mock_manage_fsm):
    """
    Test that _compute_aggregated_bracket_levels proceeds normally with valid entry_price.

    This verifies that the guard does NOT block valid data.
    """
    fsm = mock_manage_fsm

    # Set position state: all fields valid
    fsm.position_qty = Decimal("0.5")
    fsm.position_side = "LONG"
    fsm.position_entry_price = Decimal("50000.0")  # ✅ Valid: > 0

    # Mock compute_aggregated_brackets to avoid full execution
    with patch("apps.reference.domains.execution_position.fsm_manage.compute_aggregated_brackets") as mock_compute:
        mock_compute.return_value = MagicMock(
            sl_price=Decimal("49500"), tp_price=Decimal("51000"))

        result = fsm._compute_aggregated_bracket_levels(reason="test_valid")

        # Should call aggregator (not return None)
        assert result is not None
        mock_compute.assert_called_once()


def test_place_brackets_aggregated_handles_none_from_compute(mock_manage_fsm):
    """
    Test that _place_brackets_aggregated handles None from _compute_aggregated_bracket_levels.

    When _compute_aggregated_bracket_levels returns None (entry_price not ready),
    _place_brackets_aggregated should:
    1. Set state to TRACKING
    2. Return None (no bracket placement)
    3. NOT crash with AttributeError on levels.sl_price
    """
    fsm = mock_manage_fsm
    fsm.state = "FLAT"  # Initial state

    # Set position state: entry_price is None
    fsm.position_qty = Decimal("0.5")
    fsm.position_side = "LONG"
    fsm.position_entry_price = None  # ❌ Invalid

    # Mock _prepare_for_bracket_placement to return True (ready to place)
    with patch.object(fsm, "_prepare_for_bracket_placement", return_value=True):
        # Mock agg_oco_logger to suppress logs
        with patch("apps.reference.domains.execution_position.fsm_manage.agg_oco_logger"):
            msg = MagicMock(pld={"symbol": "BTCUSDT"})

            result = fsm._place_brackets_aggregated(
                msg, reason="test_handle_none")

            # Should return None (no bracket placement)
            assert result is None

            # State should be TRACKING (not BRACKETS_PENDING)
            assert fsm.state == "TRACKING"


def test_no_decision_execution_failed_on_entry_price_zero(mock_manage_fsm):
    """
    Integration test: verify that DECISION_EXECUTION_FAILED is NOT emitted when entry_price is 0.

    Before fix: AggregatedOcoError("avg_entry_price must be > 0") → caught → logged as error
    After fix: _compute_aggregated_bracket_levels returns None → _place_brackets_aggregated returns None → no DEC emitted
    """
    fsm = mock_manage_fsm
    fsm.state = "FLAT"

    # Set position state: entry_price is 0
    fsm.position_qty = Decimal("0.5")
    fsm.position_side = "LONG"
    fsm.position_entry_price = Decimal("0")  # ❌ Invalid: zero

    # Mock _prepare_for_bracket_placement to return True
    with patch.object(fsm, "_prepare_for_bracket_placement", return_value=True):
        # Mock agg_oco_logger to suppress logs
        with patch("apps.reference.domains.execution_position.fsm_manage.agg_oco_logger"):
            msg = MagicMock(pld={"symbol": "BTCUSDT"})

            # Call _place_brackets_aggregated
            result = fsm._place_brackets_aggregated(
                msg, reason="test_no_dec_failed")

            # Should return None (no bracket placement, no error raised)
            assert result is None

            # Verify fsm.fsm.emit was NOT called with DECISION_EXECUTION_FAILED
            # (Note: fsm.fsm is mocked, so we can check call_args_list)
            emit_calls = fsm.fsm.emit.call_args_list
            for call in emit_calls:
                if len(call[0]) > 0:
                    msg_arg = call[0][0]
                    if hasattr(msg_arg, "verb"):
                        # Verify no DECISION verb with EXECUTION_FAILED
                        assert msg_arg.verb != "DECISION" or "EXECUTION_FAILED" not in str(
                            msg_arg.pld)
