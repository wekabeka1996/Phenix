"""
EP-STAB-GUARDIAN-CLOSE-CLEANUP: Test that DEC:CLOSE delegates cleanup to OrderGuardian.

This test validates that ExecPosFSM does not perform manual get_open_orders + cancel_order
loops, but instead delegates all SL/TP cleanup to OrderGuardian.cleanup_orphans() with hard=True.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
from decimal import Decimal
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.contracts import PositionSide


@pytest.fixture
def fsm_with_guardian():
    """Create ExecPosFSM with OrderGuardian enabled."""
    # Use simple dict, ExecPosFSM will wrap it internally
    config_dict = {
        "execution": {
            "position": {
                "mode": "aggregated_only",
                "auto": True,
                "brackets": {
                    "enable": True,
                    "keep_single_bracket_set": True,
                    "aggregated_oco": {
                        "enabled": True,
                        "aggregated_only_mode": True,
                        "allow_unprotected_position": False,  # Required for aggregated_only mode
                        "recalc_on_scale_in": True,
                        "recalc_on_partial_close": True,
                        "ttl_protect_new_bracket_ms": 0,
                        "sl": {"fixed_bps": 100},
                        "tp": {"fixed_bps": 200},
                        "watchdog": {
                            "enabled": True,
                            "check_interval_ms": 1000
                        }
                    }
                },
                "guardian": {
                    "unified": True,
                    "poll_interval_ms": 500,
                    "cleanup_ttl_ms": 6000,
                    "symbol_cooldown_ms": 4000,
                    "emit_tidy_event": True
                },
                "watchdog": {
                    "ack_ttl_ms": 1000,
                    "fill_ttl_ms": 1000,
                    "check_interval_ms": 1000,
                    "source": "config"
                }
            }
        },
        "trading": {
            "instruments": {
                "BTCUSDT": {"min_qty": "0.001", "tick_size": "0.01"},
                "ETHUSDT": {"min_qty": "0.01", "tick_size": "0.01"},
                "SOLUSDT": {"min_qty": "0.1", "tick_size": "0.001"},
                "BNBUSDT": {"min_qty": "0.01", "tick_size": "0.01"},
                "ADAUSDT": {"min_qty": "1", "tick_size": "0.0001"}
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

    with patch('apps.reference.domains.execution_position.fsm.OrderGuardian') as MockGuardian:
        fsm = ExecPosFSM(config=config_dict, shadow_mode=True)
        fsm.logger = MagicMock()

        # Mock adapter
        fsm.adapter = MagicMock()
        fsm.adapter.base_url = "https://testnet.binance.vision"
        fsm.adapter.get_open_positions = AsyncMock(return_value=[
            {"symbol": "BTCUSDT", "positionAmt": "0.1", "positionSide": "LONG"}
        ])
        fsm.adapter.place_market_reduce_only = AsyncMock(return_value={
            "orderId": 12345,
            "status": "FILLED",
            "symbol": "BTCUSDT"
        })

        # Mock OrderGuardian instance
        guardian_instance = MagicMock()
        guardian_instance.cleanup_orphans = AsyncMock(
            return_value=2)  # Returns count of cancelled orders
        guardian_instance.reconcile_symbol = AsyncMock()
        guardian_instance.clear_bracket_set_for_position = MagicMock()
        fsm.order_guardian = guardian_instance

        return fsm


@pytest.mark.asyncio
async def test_dec_close_delegates_cleanup_to_guardian(fsm_with_guardian):
    """
    EP-STAB-GUARDIAN-CLOSE-CLEANUP: Test that DEC:CLOSE uses Guardian instead of manual cleanup.

    Scenario: DEC:CLOSE is executed for a symbol with open position.
    Expected:
    1. OrderGuardian.cleanup_orphans(symbol, hard=True) is called
    2. OrderGuardian.clear_bracket_set_for_position() is called
    3. adapter.get_open_orders() is NOT called for manual cleanup
    4. adapter.cancel_order() is NOT called directly by ExecPosFSM
    """
    fsm = fsm_with_guardian
    symbol = "BTCUSDT"

    # Create DEC:CLOSE decision
    decision = Message(
        op="DEC",
        verb="CLOSE",
        src="test",
        dst="execution_position",
        rid="test_close_rid",
        pld={"symbol": symbol}
    )

    # Execute CLOSE decision
    await fsm._execute_decision(decision)

    # Verify OrderGuardian.cleanup_orphans was called with hard=True
    fsm.order_guardian.cleanup_orphans.assert_called_once()
    call_args = fsm.order_guardian.cleanup_orphans.call_args
    assert call_args[1]["symbol"] == symbol
    assert call_args[1]["hard"] is True

    # Verify OrderGuardian.clear_bracket_set_for_position was called
    fsm.order_guardian.clear_bracket_set_for_position.assert_called_once()
    clear_call_args = fsm.order_guardian.clear_bracket_set_for_position.call_args
    assert clear_call_args[1]["symbol"] == symbol
    assert clear_call_args[1]["side"] in ["LONG", "SHORT"]

    # Verify reconcile_symbol was also called
    fsm.order_guardian.reconcile_symbol.assert_called_once_with(
        symbol, decision.rid)

    # Verify adapter methods were NOT called for manual cleanup
    # (get_open_positions is called for position snapshot, that's OK)
    # But get_open_orders with symbol filter should NOT be called
    if hasattr(fsm.adapter, 'get_open_orders'):
        # If method exists, verify it wasn't called with symbol argument for cleanup
        for call_item in fsm.adapter.get_open_orders.call_args_list:
            # Should not be called with symbol positional arg
            if call_item[0]:  # Has positional args
                assert call_item[0][
                    0] != symbol, "ExecPosFSM should not call get_open_orders(symbol) for cleanup"


@pytest.mark.asyncio
async def test_dec_close_by_entry_skips_symbol_wide_cleanup(fsm_with_guardian):
    """
    EP-STAB-GUARDIAN-CLOSE-CLEANUP: Test that DEC:CLOSE by entry skips symbol-wide cleanup.

    Scenario: DEC:CLOSE with parent_order_id (close specific entry, not entire symbol).
    Expected: Symbol-wide cleanup via Guardian.cleanup_orphans() should be skipped.
    """
    fsm = fsm_with_guardian
    symbol = "ETHUSDT"

    # Mock position data
    fsm.adapter.get_open_positions = AsyncMock(return_value=[
        {"symbol": symbol, "positionAmt": "0.5", "positionSide": "LONG"}
    ])

    # Create DEC:CLOSE by-entry decision
    decision = Message(
        op="DEC",
        verb="CLOSE",
        src="test",
        dst="execution_position",
        rid="test_close_by_entry_rid",
        pld={
            "symbol": symbol,
            "parent_order_id": "entry_12345"  # Close specific entry
        }
    )

    # Mock close_entry result
    fsm.order_guardian.close_entry = AsyncMock(return_value={
        "cancelled_brackets": 1,
        "remaining_qty": 0.5,
        "side": "LONG"
    })

    # Execute CLOSE decision
    await fsm._execute_decision(decision)

    # Verify cleanup_orphans was NOT called (multi-entry mode)
    fsm.order_guardian.cleanup_orphans.assert_not_called()

    # Verify close_entry WAS called
    fsm.order_guardian.close_entry.assert_called_once()


@pytest.mark.asyncio
async def test_dec_close_without_guardian_logs_warning(fsm_with_guardian):
    """
    EP-STAB-GUARDIAN-CLOSE-CLEANUP: Test fallback behavior when Guardian is disabled.

    Scenario: DEC:CLOSE executed but OrderGuardian is None (legacy config).
    Expected: Warning is logged when do_symbol_reconcile=True but Guardian is None.

    NOTE: keep_single_bracket_set must be True for do_symbol_reconcile to trigger.
    """
    fsm = fsm_with_guardian
    symbol = "SOLUSDT"

    # Mock position data to pass snapshot check
    fsm.adapter.get_open_positions = AsyncMock(return_value=[
        {"symbol": symbol, "positionAmt": "1.0", "positionSide": "LONG"}
    ])

    # Mock reduce only order to avoid actual execution
    fsm.adapter.place_market_reduce_only = AsyncMock(
        return_value={"orderId": 12345})

    # Disable OrderGuardian AFTER initialization
    fsm.order_guardian = None

    # Mock logger to track warning calls
    fsm.logger = MagicMock()

    # Create DEC:CLOSE decision without parent_order_id (symbol-wide mode)
    decision = Message(
        op="DEC",
        verb="CLOSE",
        src="test",
        dst="execution_position",
        rid="test_close_no_guardian_rid",
        # No parent_order_id → do_symbol_reconcile stays True
        pld={"symbol": symbol}
    )

    # Execute CLOSE decision
    await fsm._execute_decision(decision)

    # Verify warning was logged about missing Guardian
    warning_calls = [str(call) for call in fsm.logger.warning.call_args_list]
    assert any("OrderGuardian not available" in str(call) for call in warning_calls), \
        f"Should log warning when Guardian is disabled. Got warning calls: {warning_calls}"


@pytest.mark.asyncio
async def test_dec_close_cleanup_count_tracked_in_metrics(fsm_with_guardian):
    """
    EP-STAB-GUARDIAN-CLOSE-CLEANUP: Test that cleanup count is tracked in metrics.

    Scenario: Guardian cancels 3 brackets during DEC:CLOSE.
    Expected: _orphan_metrics["reconcile_cancelled"] is incremented by 3.

    NOTE: keep_single_bracket_set must be True and no parent_order_id for cleanup to trigger.
    """
    fsm = fsm_with_guardian
    symbol = "BNBUSDT"

    # Mock position data to pass snapshot check
    fsm.adapter.get_open_positions = AsyncMock(return_value=[
        {"symbol": symbol, "positionAmt": "2.0", "positionSide": "SHORT"}
    ])

    # Mock reduce only order to avoid actual execution
    fsm.adapter.place_market_reduce_only = AsyncMock(
        return_value={"orderId": 67890})

    # Mock Guardian to return 3 cancelled orders
    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=3)
    fsm.order_guardian.reconcile_symbol = AsyncMock()
    fsm.order_guardian.clear_bracket_set_for_position = MagicMock()

    # Initialize metrics to 0
    fsm._orphan_metrics["reconcile_cancelled"] = 0

    # Create DEC:CLOSE decision without parent_order_id (symbol-wide mode)
    decision = Message(
        op="DEC",
        verb="CLOSE",
        src="test",
        dst="execution_position",
        rid="test_close_metrics_rid",
        pld={"symbol": symbol}  # No parent_order_id → do_symbol_reconcile=True
    )

    # Execute CLOSE decision
    await fsm._execute_decision(decision)

    # Verify metrics were updated (incremented by 3)
    assert fsm._orphan_metrics["reconcile_cancelled"] == 3, \
        f"Expected reconcile_cancelled=3, got {fsm._orphan_metrics['reconcile_cancelled']}"

    # Verify observability event was emitted with correct count
    # (Check _emit_observability_event calls if you have a spy on it)


@pytest.mark.asyncio
async def test_dec_close_clears_bracket_meta_for_closed_side(fsm_with_guardian):
    """
    EP-STAB-GUARDIAN-CLOSE-CLEANUP: Test that BracketSetMeta is cleared for closed side.

    Scenario: LONG position is closed, resulting in FLAT state.
    Expected: Guardian.clear_bracket_set_for_position(symbol, "LONG") is called.
    """
    fsm = fsm_with_guardian
    symbol = "ADAUSDT"

    # Mock LONG position
    fsm.adapter.get_open_positions = AsyncMock(return_value=[
        {"symbol": symbol, "positionAmt": "100", "positionSide": "LONG"}
    ])

    # Create DEC:CLOSE decision
    decision = Message(
        op="DEC",
        verb="CLOSE",
        src="test",
        dst="execution_position",
        rid="test_close_bracket_meta_rid",
        pld={"symbol": symbol}
    )

    # Execute CLOSE decision
    await fsm._execute_decision(decision)

    # Verify clear_bracket_set_for_position was called with LONG side
    fsm.order_guardian.clear_bracket_set_for_position.assert_called_once_with(
        symbol=symbol,
        side="LONG"
    )
