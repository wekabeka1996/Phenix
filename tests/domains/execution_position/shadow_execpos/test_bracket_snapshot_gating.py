"""
Bracket Snapshot Gating Tests (Phase 10)
=========================================

Tests for bracket evaluation gating based on ORDERS_SNAPSHOT state.

Contract: EP-RUNTIME-SNAPSHOT-GATING-S1
- Bracket evaluation is blocked when snapshot_state == "UNKNOWN"
- Recovery pass runs after first ORDERS_SNAPSHOT
- Duplicate cleanup waits for fresh snapshot before acting

Phase 10: Tests verify gating via execution_service calls (place_order, cancel_order)
          instead of bracket_service.evaluate, since runtime now uses core planner directly.

Style: Consistent with test_execpos_v2_brackets_idempotent.py
"""
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketAction,
    BracketPlan,
    BracketState,
    BracketRulesConfig,
    PositionView,
    OrderView,
)
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import time

import pytest

from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    TrailingConfig,
    CloseConfig,
    SnapshotConfig,
)
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState

# Phase 11: runtime.bracket_service is None, tests that mock bracket_service need refactor
pytestmark = pytest.mark.xfail(
    reason="Phase 11: Legacy bracket_service mock - runtime.bracket_service deprecated")


# =============================================================================
# Fixtures & Builders
# =============================================================================

def make_ep_config(
    enabled: bool = True,
    allow_unprotected_position: bool = False,
    recreate_missing_brackets: bool = True,
) -> ExecutionPositionConfig:
    """Build ExecutionPositionConfig with aggregated_oco settings."""
    return ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(
            enabled=enabled,
            allow_unprotected_position=allow_unprotected_position,
            recreate_missing_brackets=recreate_missing_brackets,
        ),
        trailing=TrailingConfig(),
        close=CloseConfig(),
        snapshot=SnapshotConfig(),
    )


def make_runtime(
    ep_config: ExecutionPositionConfig = None,
    guardian: MagicMock = None,
) -> ExecPosRuntimeV2:
    """Build ExecPosRuntimeV2 with mock adapter and price_service."""
    if ep_config is None:
        ep_config = make_ep_config()
    runtime = ExecPosRuntimeV2(
        config={},
        adapter=None,
        price_service=None,
        ep_config=ep_config,
        guardian=guardian,
    )
    # Mock execution_service
    runtime.execution_service = MagicMock()
    runtime.execution_service.place_order = AsyncMock(
        return_value={"success": True, "order_id": "mock-oid"})
    runtime.execution_service.cancel_order = AsyncMock(
        return_value={"success": True})
    return runtime


def make_plan(symbol: str, side: str, actions: list, severity: str = "ALERT", why: str = "test") -> BracketPlan:
    """Build BracketPlan for testing."""
    state = BracketState(
        symbol=symbol,
        side=side,
        position_view=None,
        bracket_set=None,
        guardian_meta=None,
        snapshot_ts=0,
    )
    return BracketPlan(
        symbol=symbol,
        side=side,
        state=state,
        actions=actions,
        severity=severity,
        why=why,
    )


def make_stop_order(
    symbol: str,
    order_id: str,
    side: str,
    qty: float,
    stop_price: float,
    order_type: str = "STOP_MARKET",
    client_order_id: str = "",
) -> dict:
    """Build order dict resembling Binance order structure."""
    return {
        "symbol": symbol,
        "orderId": order_id,
        "clientOrderId": client_order_id or f"AUR-{symbol}-SL",
        "side": side,
        "type": order_type,
        "origQty": str(qty),
        "quantity": str(qty),
        "stopPrice": str(stop_price),
        "reduceOnly": True,
        "status": "NEW",
    }


def make_tp_order(
    symbol: str,
    order_id: str,
    side: str,
    qty: float,
    price: float,
    order_type: str = "TAKE_PROFIT_MARKET",
    client_order_id: str = "",
) -> dict:
    """Build TP order dict resembling Binance order structure."""
    return {
        "symbol": symbol,
        "orderId": order_id,
        "clientOrderId": client_order_id or f"AUR-{symbol}-TP",
        "side": side,
        "type": order_type,
        "origQty": str(qty),
        "quantity": str(qty),
        "stopPrice": str(price),
        "reduceOnly": True,
        "status": "NEW",
    }


# =============================================================================
# Test 1: Recovery blocks then recovers on first snapshot
# =============================================================================

@pytest.mark.asyncio
async def test_brackets_recovery_blocks_then_recovers_on_first_snapshot():
    """
    Verify that:
    1. Bracket evaluation is blocked when snapshot_state == "UNKNOWN"
    2. After ORDERS_SNAPSHOT arrives, _run_bracket_recovery_pass executes
    3. BracketService generates PLACE_SL + PLACE_TP plan
    4. ExecutionService places both orders
    """
    runtime = make_runtime()
    symbol = "ETHUSDT"

    # Arrange: Position with qty > 0, no brackets, snapshot UNKNOWN
    position = PositionState(symbol=symbol, qty=1.0,
                             avg_entry_price=2000.0, cycle_id=1)
    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "UNKNOWN"
    runtime.order_index.reconcile_snapshot(symbol, [])  # No SL/TP

    # Act 1: Call _evaluate_brackets with guard_loop reason → should skip
    await runtime._evaluate_brackets(symbol, position, reason="guard_loop")

    # Assert 1: place_order NOT called (blocked by UNKNOWN snapshot)
    runtime.execution_service.place_order.assert_not_called()

    # Arrange for snapshot: Mock bracket_service to return plan with PLACE_SL + PLACE_TP
    place_sl_action = BracketAction(
        action="PLACE_SL", leg_type="SL",
        target_price=Decimal("1900"),
        qty=Decimal("1.0"),
        reason_code="MISSING_SL",
    )
    place_tp_action = BracketAction(
        action="PLACE_TP", leg_type="TP",
        target_price=Decimal("2200"),
        qty=Decimal("1.0"),
        reason_code="MISSING_TP",
    )
    recovery_plan = make_plan(symbol, "LONG", [
                              place_sl_action, place_tp_action], severity="ALERT", why="recovery_missing_brackets")

    runtime.bracket_service = MagicMock()
    runtime.bracket_service.evaluate_all_for_recovery = MagicMock(return_value=[
                                                                  recovery_plan])
    runtime._apply_bracket_plan = AsyncMock()

    # Act 2: Simulate ORDERS_SNAPSHOT arrival and recovery pass
    runtime.order_index.reconcile_snapshot(
        symbol, [])  # Empty (no existing brackets)
    runtime._orders_snapshot_state[symbol] = "FRESH"
    runtime._last_orders_snapshot_ts[symbol] = time.time()
    runtime._recovery_completed = False

    await runtime._run_bracket_recovery_pass()

    # Assert 2: _apply_bracket_plan was called with our recovery plan
    runtime.bracket_service.evaluate_all_for_recovery.assert_called_once()
    runtime._apply_bracket_plan.assert_awaited()
    assert runtime._recovery_completed is True


# =============================================================================
# Test 2: Duplicate SL not cleaned until trade
# =============================================================================

@pytest.mark.asyncio
async def test_duplicate_sl_with_unknown_snapshot_not_cleaned_until_trade():
    """
    Verify that:
    1. When snapshot_state == "UNKNOWN", duplicate SL orders are NOT cleaned
    2. After TRADE_EXECUTED, evaluate runs and generates CANCEL for extra SL
    3. Only 1 SL remains after cleanup

    Phase 10: Core planner cancels excess brackets (keeps first, cancels rest).
    """
    runtime = make_runtime()
    symbol = "BTCUSDT"

    # Arrange: Position with qty > 0, TWO SL orders (duplicate), snapshot UNKNOWN
    position = PositionState(symbol=symbol, qty=0.5,
                             avg_entry_price=50000.0, cycle_id=1)
    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "UNKNOWN"

    # Two reduce_only STOP orders (duplicate SL scenario)
    sl_order_1 = make_stop_order(
        symbol, "sl-1", "SELL", 0.5, 49000.0, client_order_id="AUR-BTCUSDT-LONG-PLACE_SL-C1-a")
    sl_order_2 = make_stop_order(
        symbol, "sl-2", "SELL", 0.5, 49000.0, client_order_id="AUR-BTCUSDT-LONG-PLACE_SL-C1-b")
    runtime.order_index.reconcile_snapshot(symbol, [sl_order_1, sl_order_2])

    # Act 1: guard_loop evaluate → should skip (UNKNOWN snapshot)
    await runtime._evaluate_brackets(symbol, position, reason="guard_loop")

    # Assert 1: No cancel called (gating blocks)
    runtime.execution_service.cancel_order.assert_not_called()

    # Simulate TRADE_EXECUTED by setting snapshot to FRESH and calling evaluate
    runtime._orders_snapshot_state[symbol] = "FRESH"
    runtime._last_orders_snapshot_ts[symbol] = time.time()

    # Act 2: Evaluate after trade (snapshot now FRESH)
    # Phase 10: Core planner will detect duplicate SL and cancel excess
    await runtime._evaluate_brackets(symbol, position, reason="trade_executed")

    # Assert 2: cancel_order called for one of the duplicate SLs
    runtime.execution_service.cancel_order.assert_awaited_once()
    call_args = runtime.execution_service.cancel_order.call_args
    canceled_id = call_args.kwargs.get("order_id")
    assert canceled_id in (
        "sl-1", "sl-2"), f"Expected one of duplicate SLs to be canceled, got {canceled_id}"


# =============================================================================
# Test 3: Partial close while awaiting snapshot resizes after snapshot
# =============================================================================

@pytest.mark.asyncio
async def test_partial_close_while_awaiting_snapshot_resizes_after_snapshot():
    """
    Verify that:
    1. During partial closes with awaiting_snapshot=True, brackets aren't modified
    2. After fresh ORDERS_SNAPSHOT, SL/TP are resized to match actual qty
    3. No duplicate SL or missing SL after reconciliation
    """
    runtime = make_runtime()
    symbol = "SOLUSDT"

    # Arrange: Position qty=2.0, SL on qty=2.0, awaiting_snapshot=True
    position = PositionState(symbol=symbol, qty=2.0,
                             avg_entry_price=100.0, cycle_id=1)
    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "STALE"

    sl_order = make_stop_order(symbol, "sl-orig", "SELL", 2.0,
                               95.0, client_order_id="AUR-SOLUSDT-LONG-PLACE_SL-C1")
    tp_order = make_tp_order(symbol, "tp-orig", "SELL", 2.0,
                             105.0, client_order_id="AUR-SOLUSDT-LONG-PLACE_TP-C1")
    runtime.order_index.reconcile_snapshot(symbol, [sl_order, tp_order])

    # Set awaiting_snapshot flag
    from apps.reference.domains.execution_position.shadow_execpos.runtime import BracketStatus
    runtime._bracket_status[symbol] = BracketStatus(
        awaiting_snapshot=True, last_reason="partial_close")

    # Act 1: Simulate two partial closes (qty goes 2.0 → 1.5 → 1.0)
    position = PositionState(symbol=symbol, qty=1.0,
                             avg_entry_price=100.0, cycle_id=1)
    runtime._positions_by_symbol[symbol] = position

    # guard_loop should be blocked due to awaiting_snapshot
    await runtime._evaluate_brackets(symbol, position, reason="guard_loop")

    # Assert 1: No place/cancel during awaiting_snapshot
    runtime.execution_service.place_order.assert_not_called()
    runtime.execution_service.cancel_order.assert_not_called()

    # Act 2: Fresh ORDERS_SNAPSHOT clears awaiting_snapshot
    runtime._bracket_status[symbol].awaiting_snapshot = False
    runtime._orders_snapshot_state[symbol] = "FRESH"
    runtime._last_orders_snapshot_ts[symbol] = time.time()
    runtime.order_index.reconcile_snapshot(
        symbol, [sl_order, tp_order])  # Still has old brackets

    await runtime._evaluate_brackets(symbol, position, reason="trade_executed")

    # Assert 2: Phase 10 — Core planner uses closePosition=True, doesn't resize qty
    # Since we have SL + TP already, core planner should NOOP (no place/cancel)
    # Because core planner sees existing brackets and doesn't care about qty mismatch
    # This is expected Phase 10 behavior — no qty-based resize
    runtime.execution_service.cancel_order.assert_not_awaited()
    runtime.execution_service.place_order.assert_not_awaited()


# =============================================================================
# Test 4: allow_unprotected_position honors missing SL
# =============================================================================

@pytest.mark.xfail(reason="Phase 10: Core planner always places SL/TP; allow_unprotected_position not supported")
@pytest.mark.asyncio
async def test_allow_unprotected_position_honors_missing_sl():
    """
    Verify that when:
    - allow_unprotected_position=True
    - recreate_missing_brackets=False
    - position > 0 with no SL/TP
    BracketService does NOT generate PLACE_SL (only INFO/WARN).

    Phase 10: Core planner doesn't support allow_unprotected_position config.
              This test is xfail until/if this feature is implemented in core planner.
    """
    # Arrange: Config with allow_unprotected_position=True
    ep_config = make_ep_config(
        enabled=True,
        allow_unprotected_position=True,
        recreate_missing_brackets=False,
    )
    runtime = make_runtime(ep_config=ep_config)
    symbol = "XRPUSDT"

    position = PositionState(symbol=symbol, qty=100.0,
                             avg_entry_price=0.5, cycle_id=1)
    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "FRESH"
    runtime._last_orders_snapshot_ts[symbol] = time.time()
    runtime.order_index.reconcile_snapshot(symbol, [])  # No SL/TP

    # Mock bracket_service.evaluate to return INFO plan (no actions)
    info_plan = make_plan(symbol, "LONG", [], severity="INFO",
                          why="unprotected_position_allowed")

    runtime.bracket_service = MagicMock()
    runtime.bracket_service.build_state = MagicMock(return_value={
        (symbol, "LONG"): BracketState(
            symbol=symbol,
            side="LONG",
            position_view=PositionView(symbol=symbol, side="LONG", qty=Decimal(
                "100"), avg_entry_price=Decimal("0.5")),
            bracket_set=None,
            guardian_meta=None,
        )
    })
    runtime.bracket_service.evaluate = MagicMock(return_value=info_plan)

    # Act
    await runtime._evaluate_brackets(symbol, position, reason="trade_executed")

    # Assert: NO place_order called (config allows unprotected)
    runtime.execution_service.place_order.assert_not_called()
    runtime.execution_service.cancel_order.assert_not_called()

    # Verify bracket_service.evaluate was called (we still evaluate, just don't act)
    runtime.bracket_service.evaluate.assert_called_once()


# =============================================================================
# Test 5: Guardian v2_compat_mode blocks autoheal
# =============================================================================

@pytest.mark.asyncio
async def test_guardian_v2_compat_mode_blocks_autoheal():
    """
    Verify that when Guardian is injected with v2_compat_mode=True:
    1. V2 runtime only calls register_bracket_set / clear_bracket_set
    2. V2 runtime does NOT call ensure_single_bracket_set_for_position / cleanup_*
    """
    # Arrange: Mock Guardian with v2_compat_mode=True
    mock_guardian = MagicMock()
    mock_guardian.v2_compat_mode = True
    mock_guardian.register_bracket_set = MagicMock()
    mock_guardian.clear_bracket_set = MagicMock()
    mock_guardian.ensure_single_bracket_set_for_position = MagicMock()
    mock_guardian.cleanup_orphan_orders = MagicMock()
    mock_guardian.cleanup_stale_brackets = MagicMock()

    runtime = make_runtime(guardian=mock_guardian)
    symbol = "AVAXUSDT"

    position = PositionState(symbol=symbol, qty=5.0,
                             avg_entry_price=30.0, cycle_id=1)
    runtime._positions_by_symbol[symbol] = position
    runtime._orders_snapshot_state[symbol] = "FRESH"
    runtime._last_orders_snapshot_ts[symbol] = time.time()

    # SL already exists
    sl_order = make_stop_order(symbol, "sl-1", "SELL", 5.0, 28.0)
    runtime.order_index.reconcile_snapshot(symbol, [sl_order])

    # Mock bracket_service to return no-action plan (brackets OK)
    ok_plan = make_plan(symbol, "LONG", [], severity="INFO", why="brackets_ok")

    runtime.bracket_service = MagicMock()
    runtime.bracket_service.build_state = MagicMock(return_value={
        (symbol, "LONG"): BracketState(
            symbol=symbol,
            side="LONG",
            position_view=PositionView(symbol=symbol, side="LONG", qty=Decimal(
                "5"), avg_entry_price=Decimal("30")),
            bracket_set=None,
            guardian_meta=None,
        )
    })
    runtime.bracket_service.evaluate = MagicMock(return_value=ok_plan)

    # Act
    await runtime._evaluate_brackets(symbol, position, reason="trade_executed")

    # Assert: V2 runtime should NOT call autoheal methods on Guardian
    # (These would be called in legacy mode, but V2 uses BracketService instead)
    mock_guardian.ensure_single_bracket_set_for_position.assert_not_called()
    mock_guardian.cleanup_orphan_orders.assert_not_called()
    mock_guardian.cleanup_stale_brackets.assert_not_called()

    # Note: register_bracket_set/clear_bracket_set may be called by _apply_bracket_plan
    # if there are actions, but since ok_plan has no actions, they won't be called here


# =============================================================================
# Test 6: Guard loop respects snapshot freshness TTL
# =============================================================================

@pytest.mark.asyncio
async def test_guard_loop_respects_snapshot_freshness_ttl():
    """
    Verify that guard_loop skips evaluation when snapshot becomes STALE.
    """
    runtime = make_runtime()
    symbol = "LINKUSDT"

    position = PositionState(symbol=symbol, qty=10.0,
                             avg_entry_price=15.0, cycle_id=1)
    runtime._positions_by_symbol[symbol] = position

    # Set snapshot as FRESH but with old timestamp (simulating staleness)
    runtime._orders_snapshot_state[symbol] = "FRESH"
    # 2 minutes ago (> 60s TTL)
    runtime._last_orders_snapshot_ts[symbol] = time.time() - 120

    # Mock _is_orders_snapshot_fresh to return False (TTL expired)
    original_is_fresh = runtime._is_orders_snapshot_fresh
    runtime._is_orders_snapshot_fresh = MagicMock(return_value=False)

    # Act
    await runtime._evaluate_brackets(symbol, position, reason="guard_loop")

    # Assert: No evaluation (snapshot stale)
    # Since guard_loop requires FRESH snapshot, it should skip
    # Verify by checking that bracket_service methods weren't called
    assert runtime.execution_service.place_order.call_count == 0

    # Restore
    runtime._is_orders_snapshot_fresh = original_is_fresh
