"""
TASK R3-D1 — Guard-loop vs Trade-executed anti-double-apply
=============================================================

Test Coverage:
- test_guard_loop_vs_trade_executed_no_double_apply: Verify guard_loop doesn't place duplicate brackets when trade_executed already applied plan without snapshot confirmation

Scenario:
1. Initial: BNBUSDT SHORT 0.11, no brackets, mirror empty
2. _evaluate_brackets(reason="trade_executed") → expect 2 PLACE (SL + TP)
3. Without updating snapshot (simulate exchange delay), call _evaluate_brackets(reason="guard_loop")
4. Expect: 0 new PLACE (protected by in_flight/awaiting_snapshot), log SKIP_BRACKETS_GUARD_LOOP_IN_FLIGHT
5. After ORDERS_SNAPSHOT confirms SL/TP → guard_loop should work normally

RID: OCO-R3-D1-GUARD-LOOP-ANTI-DOUBLE-APPLY
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2, BracketStatus
from apps.reference.domains.execution_position.shadow_execpos.position_model import PositionState
from apps.reference.domains.execution_position.config import ExecutionPositionConfig


@pytest.fixture
def runtime_config():
    """Minimal config for ExecPosRuntimeV2."""
    return {
        "symbols": {
            "BNBUSDT": {
                "leverage": 10,
                "tp_bps": 150,
                "sl_bps": 50,
            }
        },
        "brackets": {
            "enabled": True,
            "tp_bps": 150,
            "sl_bps": 50,
        },
    }


@pytest.fixture
def ep_config():
    """ExecutionPositionConfig with brackets enabled."""
    from apps.reference.domains.execution_position.config import (
        AggregatedOcoConfig,
        TrailingConfig,
        CloseConfig,
        SnapshotConfig,
    )
    return ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(
            enabled=True,
            sl_pct=0.005,  # 50 bps
            tp_rr=3.0,     # 150 bps (3x SL)
            allow_unprotected_position=False,
        ),
        trailing=TrailingConfig(),
        close=CloseConfig(),
        snapshot=SnapshotConfig(orders_ttl_sec=30.0, position_ttl_sec=30.0),
    )


@pytest.fixture
def mock_adapter():
    """Mock adapter with place_order that returns success."""
    adapter = AsyncMock()
    adapter.place_order = AsyncMock(return_value={
        "success": True,
        "order_id": "12345",
        "client_order_id": "AUR-BNBUSDT-SHORT-PLACE_SL-C0-0.xxx",
    })
    adapter.cancel_order = AsyncMock(return_value={"success": True})
    return adapter


@pytest.fixture
def mock_price_service():
    """Mock price service."""
    service = MagicMock()
    service.get_price = MagicMock(return_value=Decimal("650.0"))
    return service


@pytest.fixture
def mock_guardian():
    """Mock guardian."""
    guardian = MagicMock()
    guardian.register_bracket_set = MagicMock()
    guardian.clear_bracket_set = MagicMock()
    return guardian


@pytest.mark.asyncio
async def test_guard_loop_vs_trade_executed_no_double_apply(
    runtime_config,
    ep_config,
    mock_adapter,
    mock_price_service,
    mock_guardian,
    caplog
):
    """
    RED → GREEN test: Verify guard_loop doesn't duplicate PLACE when trade_executed already applied plan.

    Scenario:
    1. Initial position: BNBUSDT SHORT 0.11, no brackets
    2. _evaluate_brackets(reason="trade_executed") → 2 PLACE (SL + TP)
    3. Without ORDERS_SNAPSHOT update, _evaluate_brackets(reason="guard_loop") → 0 PLACE (blocked)
    4. After ORDERS_SNAPSHOT confirms brackets → guard_loop works normally

    Expected:
    - First call (trade_executed): 2 place_order calls (SL + TP)
    - Second call (guard_loop): 0 place_order calls (SKIP_BRACKETS_GUARD_LOOP_IN_FLIGHT log)
    - Metric brackets_skipped_guard_loop_in_flight incremented
    - After snapshot: awaiting_snapshot=False, guard_loop can proceed
    """
    # Setup runtime
    runtime = ExecPosRuntimeV2(
        config=runtime_config,
        adapter=mock_adapter,
        price_service=mock_price_service,
        guardian=mock_guardian,
        ep_config=ep_config,
    )

    # Initial position: BNBUSDT SHORT 0.11 (qty=-0.11 → side property returns "SHORT")
    position = PositionState(
        symbol="BNBUSDT",
        qty=-0.11,  # Negative qty → SHORT side
        avg_entry_price=650.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        last_update_time=1732560000.0,
        cycle_id=0,
    )
    runtime._positions_by_symbol["BNBUSDT"] = position

    # Mirror empty (no brackets yet)
    runtime._open_orders_by_symbol["BNBUSDT"] = []
    runtime._orders_snapshot_state["BNBUSDT"] = "FRESH"

    # Reset adapter call count
    mock_adapter.place_order.reset_mock()
    caplog.clear()

    # Step 1: trade_executed → call _apply_bracket_plan directly with fake BracketPlan
    from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
        BracketPlan,
        BracketAction,
        BracketState,
        PositionView,
    )
    from decimal import Decimal

    fake_state = BracketState(
        symbol="BNBUSDT",
        side="SHORT",
        position_view=PositionView(
            symbol="BNBUSDT",
            side="SHORT",
            qty=Decimal("0.11"),
            avg_entry_price=Decimal("650.0"),
            realized_pnl=Decimal("0.0"),
            unrealized_pnl=Decimal("0.0"),
            update_ts=1732560000.0,
            cycle_id=0,
        ),
        bracket_set=None,  # No existing brackets
    )

    fake_plan = BracketPlan(
        symbol="BNBUSDT",
        side="SHORT",
        state=fake_state,
        severity="INFO",
        why="test_plan",
        rid="TEST-001",
        actions=[
            BracketAction(action_type="PLACE_SL", qty=Decimal(
                "0.11"), price=Decimal("653.25"), why="test_sl"),
            BracketAction(action_type="PLACE_TP", qty=Decimal(
                "0.11"), price=Decimal("640.25"), why="test_tp"),
        ]
    )

    await runtime._apply_bracket_plan("BNBUSDT", position, fake_plan, reason="trade_executed")

    # Verify: 2 place_order calls
    assert mock_adapter.place_order.call_count == 2, \
        f"Expected 2 PLACE calls from trade_executed, got {mock_adapter.place_order.call_count}"

    # Verify: BracketStatus shows in_flight=False, awaiting_snapshot=True
    status = runtime._bracket_status.get("BNBUSDT")
    assert status is not None, "BracketStatus should be created"
    assert status.in_flight is False, "in_flight should be False after _apply_bracket_plan completes"
    assert status.awaiting_snapshot is True, "awaiting_snapshot should be True after brackets applied"
    assert status.last_reason == "trade_executed"

    # Step 2: guard_loop WITHOUT snapshot update → expect 0 PLACE (blocked)
    mock_adapter.place_order.reset_mock()
    caplog.clear()

    # Call _apply_bracket_plan directly with same plan (simulating guard_loop trying to apply same brackets)
    await runtime._apply_bracket_plan("BNBUSDT", position, fake_plan, reason="guard_loop")

    # Verify: 0 place_order calls (blocked by awaiting_snapshot)
    assert mock_adapter.place_order.call_count == 0, \
        f"Expected 0 PLACE calls from guard_loop (blocked), got {mock_adapter.place_order.call_count}"

    # Verify: SKIP metric incremented (more reliable than caplog)
    skip_metric = runtime._metrics.get(
        "brackets_skipped_guard_loop_in_flight", 0)
    assert skip_metric == 1, \
        f"Expected brackets_skipped_guard_loop_in_flight metric = 1, got {skip_metric}. awaiting_snapshot={runtime._bracket_status.get('BNBUSDT').awaiting_snapshot if 'BNBUSDT' in runtime._bracket_status else 'NO STATUS'}"

    # Step 3: Simulate ORDERS_SNAPSHOT confirms brackets
    # Disable recovery to avoid it re-setting awaiting_snapshot
    runtime._recovery_completed = True

    snapshot_orders = [
        {
            "symbol": "BNBUSDT",
            "order_id": "1001",
            "client_order_id": "AUR-BNBUSDT-SHORT-PLACE_SL-C0-0.xxx",
            "side": "BUY",
            "type": "STOP_MARKET",
            "quantity": 0.11,
            "stop_price": 682.5,  # SL price
            "reduce_only": True,
        },
        {
            "symbol": "BNBUSDT",
            "order_id": "1002",
            "client_order_id": "AUR-BNBUSDT-SHORT-PLACE_TP-C0-0.xxx",
            "side": "BUY",
            "type": "TAKE_PROFIT_MARKET",
            "quantity": 0.11,
            "stop_price": 617.5,  # TP price
            "reduce_only": True,
        }
    ]

    await runtime._handle_orders_snapshot({"orders": snapshot_orders})

    # Verify: awaiting_snapshot cleared
    status_after = runtime._bracket_status.get("BNBUSDT")
    assert status_after.awaiting_snapshot is False, \
        "awaiting_snapshot should be False after ORDERS_SNAPSHOT confirms brackets"

    # Step 4: guard_loop after snapshot → should work normally (no blocking)
    mock_adapter.place_order.reset_mock()
    caplog.clear()

    # Call _apply_bracket_plan again with guard_loop (should NOT be blocked now)
    fake_plan_new = BracketPlan(
        symbol="BNBUSDT",
        side="SHORT",
        state=fake_state,
        severity="INFO",
        why="test_plan_after_snapshot",
        rid="TEST-002",
        actions=[
            BracketAction(action_type="ADJUST", qty=Decimal("0.11"), price=Decimal(
                "655.0"), why="test_adjust", order_id="1001"),
        ]
    )
    await runtime._apply_bracket_plan("BNBUSDT", position, fake_plan_new, reason="guard_loop")

    # Verify: No SKIP log (guard_loop not blocked anymore)
    skip_logs_after = [
        rec for rec in caplog.records if "SKIP_BRACKETS_GUARD_LOOP_IN_FLIGHT" in rec.message]
    assert len(skip_logs_after) == 0, \
        "Expected no SKIP log after snapshot confirmation (guard_loop should proceed)"

    # Verify: metric unchanged (no additional skips)
    assert runtime._metrics.get("brackets_skipped_guard_loop_in_flight", 0) == 1, \
        "Expected brackets_skipped_guard_loop_in_flight metric still = 1 (no new skips)"


@pytest.mark.asyncio
async def test_guard_loop_vs_trade_executed_in_flight_blocks(
    runtime_config,
    ep_config,
    mock_adapter,
    mock_price_service,
    mock_guardian,
    caplog
):
    """
    Verify guard_loop is blocked when in_flight=True (during _apply_bracket_plan execution).

    Scenario:
    1. trade_executed starts _apply_bracket_plan (in_flight=True)
    2. guard_loop arrives during execution → blocked
    3. After trade_executed completes (in_flight=False, awaiting_snapshot=True) → guard_loop still blocked
    """
    runtime = ExecPosRuntimeV2(
        config=runtime_config,
        adapter=mock_adapter,
        price_service=mock_price_service,
        guardian=mock_guardian,
        ep_config=ep_config,
    )

    position = PositionState(
        symbol="BNBUSDT",
        qty=-0.11,
        avg_entry_price=650.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        last_update_time=1732560000.0,
        cycle_id=0,
    )
    runtime._positions_by_symbol["BNBUSDT"] = position
    runtime._open_orders_by_symbol["BNBUSDT"] = []
    runtime._orders_snapshot_state["BNBUSDT"] = "FRESH"

    # Manually set in_flight=True (simulate ongoing execution)
    runtime._bracket_status["BNBUSDT"] = BracketStatus(
        last_reason="trade_executed",
        last_started_ts=1732560001.0,
        in_flight=True,
        awaiting_snapshot=False,
    )

    # guard_loop arrives → should be blocked
    caplog.clear()
    mock_adapter.place_order.reset_mock()

    # Call _apply_bracket_plan with guard_loop reason (should be blocked by in_flight)
    from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
        BracketPlan,
        BracketAction,
        BracketState,
        PositionView,
    )
    from decimal import Decimal

    fake_state = BracketState(
        symbol="BNBUSDT",
        side="SHORT",
        position_view=PositionView(
            symbol="BNBUSDT",
            side="SHORT",
            qty=Decimal("0.11"),
            avg_entry_price=Decimal("650.0"),
            realized_pnl=Decimal("0.0"),
            unrealized_pnl=Decimal("0.0"),
            update_ts=1732560000.0,
            cycle_id=0,
        ),
        bracket_set=None,
    )

    fake_plan = BracketPlan(
        symbol="BNBUSDT",
        side="SHORT",
        state=fake_state,
        severity="INFO",
        why="test_plan",
        rid="TEST-001",
        actions=[
            BracketAction(action_type="PLACE_SL", qty=Decimal(
                "0.11"), price=Decimal("653.25"), why="test_sl"),
        ]
    )

    await runtime._apply_bracket_plan("BNBUSDT", position, fake_plan, reason="guard_loop")

    # Verify: 0 PLACE calls (blocked by in_flight)
    assert mock_adapter.place_order.call_count == 0, \
        "Expected 0 PLACE calls (guard_loop blocked by in_flight)"

    # Verify: metric incremented (more reliable than caplog)
    skip_metric = runtime._metrics.get(
        "brackets_skipped_guard_loop_in_flight", 0)
    assert skip_metric == 1, f"Expected brackets_skipped_guard_loop_in_flight metric = 1, got {skip_metric}"


@pytest.mark.asyncio
async def test_non_guard_loop_not_blocked_by_awaiting_snapshot(
    runtime_config,
    ep_config,
    mock_adapter,
    mock_price_service,
    mock_guardian
):
    """
    Verify that non-guard_loop reasons (e.g., account_update_sync) are NOT blocked by awaiting_snapshot.

    Only guard_loop should be blocked to prevent double-apply race. Other reasons proceed normally.
    """
    runtime = ExecPosRuntimeV2(
        config=runtime_config,
        adapter=mock_adapter,
        price_service=mock_price_service,
        guardian=mock_guardian,
        ep_config=ep_config,
    )

    position = PositionState(
        symbol="BNBUSDT",
        qty=-0.11,
        avg_entry_price=650.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        last_update_time=1732560000.0,
        cycle_id=0,
    )
    runtime._positions_by_symbol["BNBUSDT"] = position
    runtime._open_orders_by_symbol["BNBUSDT"] = []
    runtime._orders_snapshot_state["BNBUSDT"] = "FRESH"

    # Simulate awaiting_snapshot=True (trade_executed just applied plan)
    runtime._bracket_status["BNBUSDT"] = BracketStatus(
        last_reason="trade_executed",
        last_started_ts=1732560001.0,
        in_flight=False,
        awaiting_snapshot=True,
    )

    # account_update_sync arrives → should NOT be blocked (only guard_loop is blocked)
    mock_adapter.place_order.reset_mock()

    await runtime._evaluate_brackets("BNBUSDT", position, reason="account_update_sync")

    # Verify: PLACE calls made (NOT blocked)
    # Note: Depending on bracket logic, may skip due to throttling or existing brackets
    # Here we verify NO SKIP_BRACKETS_GUARD_LOOP_IN_FLIGHT log (protection not triggered)
    assert runtime._metrics.get("brackets_skipped_guard_loop_in_flight", 0) == 0, \
        "account_update_sync should NOT trigger guard_loop protection"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
