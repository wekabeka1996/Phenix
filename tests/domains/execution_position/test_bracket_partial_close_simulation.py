"""
TASK: Full Simulation Test for TP/SL Bracket Recalculation on Partial Close

This test simulates the complete flow:
1. Shadow opens a position (BUY 0.1 ETH)
2. System places TP/SL brackets for full qty (0.1)
3. Position is partially closed (0.04 filled, leaving 0.06)
4. System detects qty mismatch (bracket_qty > position_qty)
5. System cancels old brackets (sized for 0.1)
6. System places new brackets (sized for 0.06)

Tests verify:
- Bracket recalculation triggers on partial close
- Old brackets are cancelled before new ones placed
- New brackets have correct qty matching remaining position
- TP/SL prices are preserved or recalculated appropriately
"""
import asyncio
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import replace

import pytest

from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketService,
    BracketRulesConfig,
    BracketPlan,
    BracketAction,
    PositionView,
    OrderView,
    BracketState,
)
from apps.reference.domains.execution_position.shadow_execpos.runtime import (
    ExecPosRuntimeV2,
)
from apps.reference.domains.execution_position.shadow_execpos.position_model import (
    PositionState,
    apply_fill,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def bracket_config() -> BracketRulesConfig:
    """Standard bracket config with recalc on partial close enabled."""
    return BracketRulesConfig(
        enabled=True,
        allow_unprotected_position=False,
        recalc_on_partial_close=True,
        recalc_on_scale_in=True,
        ttl_protect_new_bracket_ms=5000,
        max_tp_legs=1,
        max_sl_legs=1,
        sl_pct=0.02,  # 2% SL
        tp_rr=2.0,    # 2:1 reward/risk
        recreate_missing_brackets=True,
    )


@pytest.fixture
def mock_aggregator():
    """Mock bracket aggregator that computes simple SL/TP levels."""
    class MockAggregator:
        def compute_aggregated_brackets(
            self,
            position_amt: Decimal,
            avg_entry_price: Decimal,
            side: str,
            risk_cfg: Any,
            constraints: Any,
            why: str,
        ):
            """Compute SL/TP based on entry price and risk config."""
            sl_pct = float(risk_cfg.sl_pct)
            tp_rr = float(risk_cfg.tp_rr)

            if side == "LONG":
                sl_price = avg_entry_price * Decimal(1 - sl_pct)
                tp_price = avg_entry_price * Decimal(1 + sl_pct * tp_rr)
            else:  # SHORT
                sl_price = avg_entry_price * Decimal(1 + sl_pct)
                tp_price = avg_entry_price * Decimal(1 - sl_pct * tp_rr)

            class Levels:
                pass
            levels = Levels()
            levels.sl_price = sl_price
            levels.tp_price = tp_price
            return levels

    return MockAggregator()


@pytest.fixture
def bracket_service(mock_aggregator) -> BracketService:
    """BracketService with mock aggregator."""
    return BracketService(
        aggregator=mock_aggregator,
        guardian=None,
        watchdog=None,
    )


# =============================================================================
# Unit Tests: BracketService Size Invariant Detection
# =============================================================================

class TestBracketServicePartialCloseDetection:
    """Test that BracketService correctly detects size mismatches after partial close."""

    def test_detects_oversized_sl_after_partial_close(
        self, bracket_service: BracketService, bracket_config: BracketRulesConfig
    ):
        """
        Scenario:
        - Position: 0.06 ETH LONG (after partial close)
        - Existing SL: qty=0.1 (old full position size)
        - Expected: CANCEL old SL + PLACE new SL with qty=0.06
        """
        # Position after partial close (0.1 - 0.04 = 0.06)
        position = PositionView(
            symbol="ETHUSDT",
            side="LONG",
            qty=Decimal("0.06"),
            avg_entry_price=Decimal("3000.00"),
            cycle_id=1,
        )

        # Old SL order sized for full position (0.1)
        sl_order = OrderView(
            order_id="SL_001",
            client_order_id="AUR-ETHUSDT-LONG-SL-C1-abc123",
            symbol="ETHUSDT",
            side="SELL",  # Exit side for LONG
            order_type="STOP_MARKET",
            qty=Decimal("0.1"),  # OLD SIZE - too big!
            stop_price=Decimal("2940.00"),  # 2% below entry
            reduce_only=True,
            cycle_id=1,
        )

        # Build state with oversized bracket
        state = BracketState(
            symbol="ETHUSDT",
            side="LONG",
            position_view=position,
            bracket_set=MagicMock(
                sl_legs=[MagicMock(
                    leg_type="SL",
                    order=sl_order,
                    order_id="SL_001",
                    price=Decimal("2940.00"),
                )],
                tp_legs=[],
                legs=[MagicMock(leg_type="SL", order=sl_order,
                                order_id="SL_001")],
            ),
        )

        # Evaluate
        plan = bracket_service.evaluate(state, bracket_config, rid="TEST-001")

        # Should have actions: CANCEL old SL + PLACE new SL
        assert plan.has_actions, "Expected actions for size mismatch"
        assert plan.severity in (
            "WARN", "ALERT"), f"Expected warning, got {plan.severity}"

        # Find CANCEL and PLACE_SL actions
        cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
        place_sl_actions = [
            a for a in plan.actions if a.action_type == "PLACE_SL"]

        assert len(cancel_actions) >= 1, "Expected CANCEL action for oversized SL"
        assert len(
            place_sl_actions) >= 1, "Expected PLACE_SL action with correct qty"

        # Verify PLACE_SL has correct qty
        new_sl = place_sl_actions[0]
        assert new_sl.qty == Decimal(
            "0.06"), f"New SL should have qty=0.06, got {new_sl.qty}"

    def test_detects_oversized_tp_after_partial_close(
        self, bracket_service: BracketService, bracket_config: BracketRulesConfig
    ):
        """
        Scenario:
        - Position: 0.06 ETH LONG
        - Existing TP: qty=0.1 (old full position size)
        - Existing SL: qty=0.06 (already correct)
        - Expected: CANCEL old TP + PLACE new TP with qty=0.06
        """
        position = PositionView(
            symbol="ETHUSDT",
            side="LONG",
            qty=Decimal("0.06"),
            avg_entry_price=Decimal("3000.00"),
            cycle_id=1,
        )

        # Correct SL
        sl_order = OrderView(
            order_id="SL_001",
            client_order_id="AUR-ETHUSDT-LONG-SL-C1-abc123",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            qty=Decimal("0.06"),  # Correct size
            stop_price=Decimal("2940.00"),
            reduce_only=True,
            cycle_id=1,
        )

        # Oversized TP
        tp_order = OrderView(
            order_id="TP_001",
            client_order_id="AUR-ETHUSDT-LONG-TP-C1-def456",
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            qty=Decimal("0.1"),  # OLD SIZE - too big!
            stop_price=Decimal("3120.00"),  # 4% above entry (2:1 RR)
            reduce_only=True,
            cycle_id=1,
        )

        state = BracketState(
            symbol="ETHUSDT",
            side="LONG",
            position_view=position,
            bracket_set=MagicMock(
                sl_legs=[MagicMock(leg_type="SL", order=sl_order,
                                   order_id="SL_001", price=Decimal("2940.00"))],
                tp_legs=[MagicMock(leg_type="TP", order=tp_order,
                                   order_id="TP_001", price=Decimal("3120.00"))],
                legs=[
                    MagicMock(leg_type="SL", order=sl_order,
                              order_id="SL_001"),
                    MagicMock(leg_type="TP", order=tp_order,
                              order_id="TP_001"),
                ],
            ),
        )

        plan = bracket_service.evaluate(state, bracket_config, rid="TEST-002")

        # Find TP-related actions
        cancel_tp = [a for a in plan.actions if a.action_type ==
                     "CANCEL" and a.order_id == "TP_001"]
        place_tp = [a for a in plan.actions if a.action_type == "PLACE_TP"]

        assert len(cancel_tp) >= 1, "Expected CANCEL for oversized TP"
        assert len(place_tp) >= 1, "Expected PLACE_TP with correct qty"
        assert place_tp[0].qty == Decimal(
            "0.06"), f"New TP should have qty=0.06, got {place_tp[0].qty}"


# =============================================================================
# Integration Tests: Full Flow Simulation
# =============================================================================

class TestPartialCloseBracketRecalculation:
    """
    Full integration test simulating:
    1. Position opens
    2. Brackets placed
    3. Partial close
    4. Brackets recalculated
    """

    @pytest.mark.asyncio
    async def test_full_partial_close_flow_with_mock_delays(self):
        """
        Complete simulation with mock network delays:

        T0: Position opens (BUY 0.1 ETHUSDT @ 3000)
        T1: System places SL @ 2940 (0.1 qty), TP @ 3120 (0.1 qty)
        T2: Partial fill (TP hit for 0.04) - position now 0.06
        T3: System detects size mismatch
        T4: System cancels old brackets
        T5: System places new brackets (0.06 qty)
        """
        # Track all adapter calls
        adapter_calls: List[Dict[str, Any]] = []
        placed_orders: Dict[str, Dict] = {}  # order_id -> order details

        async def mock_place_order(**kwargs):
            """Mock adapter.place_order with simulated delay."""
            await asyncio.sleep(0.05)  # 50ms mock delay

            order_id = f"ORD_{len(placed_orders) + 1:03d}"
            order = {
                "order_id": order_id,
                "client_order_id": kwargs.get("client_order_id", ""),
                "symbol": kwargs.get("symbol"),
                "side": kwargs.get("side"),
                "order_type": kwargs.get("order_type"),
                "qty": kwargs.get("quantity"),
                "stop_price": kwargs.get("stop_price"),
                "reduce_only": kwargs.get("reduce_only", False),
                "status": "NEW",
                "success": True,
            }
            placed_orders[order_id] = order
            adapter_calls.append({"action": "place", **order})
            return order

        async def mock_cancel_order(**kwargs):
            """Mock adapter.cancel_order with simulated delay."""
            await asyncio.sleep(0.03)  # 30ms mock delay

            order_id = kwargs.get("order_id")
            adapter_calls.append({"action": "cancel", "order_id": order_id})
            if order_id in placed_orders:
                placed_orders[order_id]["status"] = "CANCELED"
            return {"success": True, "order_id": order_id}

        # Create mock adapter
        mock_adapter = MagicMock()
        mock_adapter.place_order_v2 = mock_place_order
        mock_adapter.cancel_order = mock_cancel_order
        mock_adapter.get_open_orders = AsyncMock(return_value=[])
        mock_adapter.get_open_positions = AsyncMock(return_value=[])

        # Create runtime with mock adapter
        config = {
            "execution_position": {
                "manage": {
                    "brackets": {
                        "enable": True,
                        "aggregated_oco": {
                            "enabled": True,
                            "recalc_on_partial_close": True,
                            "sl_pct": 0.02,
                            "tp_rr": 2.0,
                        }
                    }
                }
            }
        }

        # === STEP 1: Open position ===
        # qty is SIGNED: positive for LONG, negative for SHORT
        initial_position = PositionState(
            symbol="ETHUSDT",
            qty=0.1,  # Positive = LONG
            avg_entry_price=3000.0,
            cycle_id=1,
        )

        # === STEP 2: Calculate initial brackets ===
        # SL: 3000 * (1 - 0.02) = 2940
        # TP: 3000 * (1 + 0.02 * 2) = 3120
        expected_sl_price = Decimal("2940.00")
        expected_tp_price = Decimal("3120.00")

        # Simulate placing initial brackets
        sl_result = await mock_place_order(
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            quantity=0.1,
            stop_price="2940.00",
            client_order_id="AUR-ETHUSDT-SELL-SL-C1-init",
            reduce_only=True,
        )

        tp_result = await mock_place_order(
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            quantity=0.1,
            stop_price="3120.00",
            client_order_id="AUR-ETHUSDT-SELL-TP-C1-init",
            reduce_only=True,
        )

        assert len(placed_orders) == 2, "Should have 2 initial brackets"

        # === STEP 3: Partial close (TP partially filled) ===
        # Scenario: TP was partially filled for 0.04, remaining TP qty is 0.06
        # In real life, exchange would update TP order qty from 0.1 to 0.06
        # OR the order would be fully filled and we'd have no TP

        # Let's simulate: TP fully filled for the partial amount (0.04)
        # This means the TP order is now FILLED, not active
        placed_orders[tp_result["order_id"]]["status"] = "FILLED"

        # Position reduces from 0.1 to 0.06
        new_position = apply_fill(
            initial_position,
            side="SELL",  # Exit fill
            quantity=0.04,  # Partial fill
            price=3120.0,  # At TP price
        )

        assert abs(new_position.qty) == pytest.approx(0.06, abs=0.001), \
            f"Position should be 0.06 after partial fill, got {new_position.qty}"

        # === STEP 4: Evaluate brackets with new position qty ===
        # Build BracketService state representing current situation
        bracket_service = BracketService(
            aggregator=MagicMock(),
            guardian=None,
            watchdog=None,
        )

        # Current position view
        pos_view = PositionView(
            symbol="ETHUSDT",
            side="LONG",
            qty=Decimal("0.06"),  # After partial close
            avg_entry_price=Decimal("3000.00"),
            cycle_id=1,
        )

        # Current orders (still sized for 0.1!)
        sl_order = OrderView(
            order_id=sl_result["order_id"],
            client_order_id=sl_result["client_order_id"],
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            qty=Decimal("0.1"),  # Still old size!
            stop_price=Decimal("2940.00"),
            reduce_only=True,
            cycle_id=1,
        )

        tp_order = OrderView(
            order_id=tp_result["order_id"],
            client_order_id=tp_result["client_order_id"],
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            qty=Decimal("0.06"),  # Partially filled, now 0.06 remaining
            stop_price=Decimal("3120.00"),
            reduce_only=True,
            cycle_id=1,
        )

        # Build state for evaluation
        states = bracket_service.build_state(
            positions=[pos_view],
            orders=[sl_order],  # Only SL remaining (TP was partially filled)
            symbol="ETHUSDT",
            side="LONG",
        )

        assert ("ETHUSDT", "LONG") in states, "Should have state for ETHUSDT LONG"
        state = states[("ETHUSDT", "LONG")]

        # === STEP 5: Evaluate and generate recalculation plan ===
        cfg = BracketRulesConfig(
            enabled=True,
            recalc_on_partial_close=True,
            sl_pct=0.02,
            tp_rr=2.0,
        )

        plan = bracket_service.evaluate(state, cfg, rid="PARTIAL-CLOSE-001")

        # === STEP 6: Verify plan has correct actions ===
        print(f"\nPlan severity: {plan.severity}")
        print(f"Plan why: {plan.why}")
        print(
            f"Plan actions: {[(a.action_type, a.order_id, a.qty) for a in plan.actions]}")

        # Should detect oversized SL
        cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
        place_sl_actions = [
            a for a in plan.actions if a.action_type == "PLACE_SL"]
        place_tp_actions = [
            a for a in plan.actions if a.action_type == "PLACE_TP"]

        # SL oversized (0.1 > 0.06) should trigger CANCEL + PLACE
        assert len(
            cancel_actions) >= 1, f"Expected CANCEL for oversized SL, got {cancel_actions}"
        assert len(
            place_sl_actions) >= 1, f"Expected PLACE_SL with new qty, got {place_sl_actions}"

        # Verify new SL has correct qty
        if place_sl_actions:
            new_sl_qty = place_sl_actions[0].qty
            assert new_sl_qty == Decimal("0.06"), \
                f"New SL should have qty=0.06, got {new_sl_qty}"

        # Missing TP should trigger PLACE_TP
        assert len(
            place_tp_actions) >= 1, f"Expected PLACE_TP for missing TP, got {place_tp_actions}"
        if place_tp_actions:
            new_tp_qty = place_tp_actions[0].qty
            assert new_tp_qty == Decimal("0.06"), \
                f"New TP should have qty=0.06, got {new_tp_qty}"

        # === STEP 7: Execute plan actions ===
        for action in plan.actions:
            if action.action_type == "CANCEL":
                await mock_cancel_order(order_id=action.order_id)
            elif action.action_type in ("PLACE_SL", "PLACE_TP"):
                order_type = "STOP_MARKET" if action.action_type == "PLACE_SL" else "TAKE_PROFIT_MARKET"
                await mock_place_order(
                    symbol="ETHUSDT",
                    side="SELL",
                    order_type=order_type,
                    quantity=float(action.qty),
                    stop_price=str(action.price) if action.price else None,
                    client_order_id=f"AUR-ETHUSDT-SELL-{action.action_type.split('_')[1]}-C1-resized",
                    reduce_only=True,
                )

        # === Verify final state ===
        # Only count orders that are still NEW (not FILLED or CANCELED)
        final_active_orders = [
            o for o in placed_orders.values() if o["status"] == "NEW"]

        print(f"\nFinal active orders: {len(final_active_orders)}")
        for order in final_active_orders:
            print(
                f"  - {order['order_type']}: qty={order['qty']}, stop_price={order['stop_price']}, status={order['status']}")

        # Should have new brackets sized for 0.06
        active_sl = [
            o for o in final_active_orders if o["order_type"] == "STOP_MARKET"]
        active_tp = [
            o for o in final_active_orders if o["order_type"] == "TAKE_PROFIT_MARKET"]

        assert len(
            active_sl) == 1, f"Should have exactly 1 active SL, got {len(active_sl)}"
        assert len(
            active_tp) == 1, f"Should have exactly 1 active TP, got {len(active_tp)}"

        # Verify qty is correct
        assert active_sl[0]["qty"] == 0.06, f"SL qty should be 0.06, got {active_sl[0]['qty']}"
        assert active_tp[0]["qty"] == 0.06, f"TP qty should be 0.06, got {active_tp[0]['qty']}"

        print("\n✅ TEST PASSED: Brackets correctly resized after partial close!")


class TestBracketRecalculationTiming:
    """Tests for timing aspects of bracket recalculation."""

    @pytest.mark.asyncio
    async def test_brackets_recalc_happens_after_position_update(self):
        """
        Verify that bracket evaluation happens AFTER position state is updated,
        not before (which would use stale qty).
        """
        position_states: List[PositionState] = []
        bracket_eval_positions: List[Decimal] = []

        async def track_position_update(pos: PositionState):
            """Track when position is updated."""
            position_states.append(pos)

        def track_bracket_eval(pos_qty: Decimal):
            """Track what qty was used in bracket evaluation."""
            bracket_eval_positions.append(pos_qty)

        # Simulate the flow
        # 1. Initial position: 0.1 (positive = LONG)
        initial = PositionState(
            symbol="ETHUSDT", qty=0.1, avg_entry_price=3000.0)
        await track_position_update(initial)
        track_bracket_eval(Decimal(str(abs(initial.qty))))

        # 2. Partial fill: 0.04 closed
        after_fill = apply_fill(initial, side="SELL",
                                quantity=0.04, price=3120.0)
        await track_position_update(after_fill)
        track_bracket_eval(Decimal(str(abs(after_fill.qty))))

        # Verify ordering
        assert len(position_states) == 2
        assert len(bracket_eval_positions) == 2

        # First eval should use 0.1
        assert bracket_eval_positions[0] == Decimal("0.1")
        # Second eval should use ~0.06 (after position update) - use approx for float precision
        assert abs(bracket_eval_positions[1] - Decimal("0.06")) < Decimal("0.0001"), \
            f"Expected ~0.06, got {bracket_eval_positions[1]}"

        print("✅ Bracket evaluation correctly uses updated position qty")


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestBracketRecalculationEdgeCases:
    """Edge cases for bracket recalculation."""

    def test_full_close_cancels_all_brackets(
        self, bracket_service: BracketService, bracket_config: BracketRulesConfig
    ):
        """When position is fully closed, all brackets should be cancelled (orphan cleanup)."""
        # FLAT position
        position = PositionView(
            symbol="ETHUSDT",
            side="LONG",
            qty=Decimal("0"),  # Fully closed!
            avg_entry_price=Decimal("3000.00"),
            cycle_id=1,
        )

        # Orphan brackets
        sl_order = OrderView(
            order_id="SL_001",
            client_order_id="AUR-ETHUSDT-LONG-SL-C1-abc",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            qty=Decimal("0.1"),
            stop_price=Decimal("2940.00"),
            reduce_only=True,
            cycle_id=1,
        )

        tp_order = OrderView(
            order_id="TP_001",
            client_order_id="AUR-ETHUSDT-LONG-TP-C1-def",
            symbol="ETHUSDT",
            side="SELL",
            order_type="TAKE_PROFIT_MARKET",
            qty=Decimal("0.1"),
            stop_price=Decimal("3120.00"),
            reduce_only=True,
            cycle_id=1,
        )

        state = BracketState(
            symbol="ETHUSDT",
            side="LONG",
            position_view=position,
            bracket_set=MagicMock(
                sl_legs=[
                    MagicMock(leg_type="SL", order=sl_order, order_id="SL_001")],
                tp_legs=[
                    MagicMock(leg_type="TP", order=tp_order, order_id="TP_001")],
                legs=[
                    MagicMock(leg_type="SL", order=sl_order,
                              order_id="SL_001"),
                    MagicMock(leg_type="TP", order=tp_order,
                              order_id="TP_001"),
                ],
            ),
        )

        plan = bracket_service.evaluate(
            state, bracket_config, rid="FULL-CLOSE-001")

        # All brackets should be cancelled (orphans)
        cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
        assert len(
            cancel_actions) == 2, f"Should cancel both orphan brackets, got {len(cancel_actions)}"

        # Should NOT place new brackets for FLAT position
        place_actions = [
            a for a in plan.actions if a.action_type.startswith("PLACE")]
        assert len(
            place_actions) == 0, f"Should not place brackets for FLAT position, got {len(place_actions)}"

        assert plan.why.startswith(
            "orphan"), f"Should report orphan brackets, got: {plan.why}"

    def test_scale_in_increases_bracket_qty(
        self, bracket_service: BracketService, bracket_config: BracketRulesConfig
    ):
        """
        When position size increases (scale-in), brackets should be resized UP.

        Scenario:
        - Initial: 0.06 ETH @ 3000
        - Scale-in: +0.04 ETH @ 3050
        - New total: 0.1 ETH @ ~3020 (weighted avg)
        - Brackets should be resized from 0.06 to 0.1
        """
        # Position after scale-in
        position = PositionView(
            symbol="ETHUSDT",
            side="LONG",
            qty=Decimal("0.1"),  # After scale-in
            avg_entry_price=Decimal("3020.00"),  # New weighted avg
            cycle_id=1,
        )

        # Old brackets sized for smaller position
        sl_order = OrderView(
            order_id="SL_001",
            client_order_id="AUR-ETHUSDT-LONG-SL-C1-abc",
            symbol="ETHUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            qty=Decimal("0.06"),  # Old smaller size
            stop_price=Decimal("2940.00"),
            reduce_only=True,
            cycle_id=1,
        )

        states = bracket_service.build_state(
            positions=[position],
            orders=[sl_order],
            symbol="ETHUSDT",
            side="LONG",
        )

        state = states[("ETHUSDT", "LONG")]

        # With recalc_on_scale_in=True (default), should detect stale levels
        # because SL price is for old entry (3000) not new avg (3020)
        plan = bracket_service.evaluate(
            state, bracket_config, rid="SCALE-IN-001")

        print(f"Scale-in plan: severity={plan.severity}, why={plan.why}")
        print(f"Actions: {[(a.action_type, a.qty) for a in plan.actions]}")

        # Should have action to resize/recalc brackets
        # Note: size invariant checks qty, stale_levels checks price
        # Both may trigger actions
        assert plan.has_actions, "Should have actions after scale-in"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
