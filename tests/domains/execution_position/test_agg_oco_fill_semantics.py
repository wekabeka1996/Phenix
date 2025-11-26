"""
TEST-OCO-FILL — Aggregated OCO Fill Semantics Tests

Tests for OCO fill behavior using BracketService (Pure Computation Layer).
These tests verify the BracketPlan generation when fills occur:

- SL fill → position FLAT → BracketPlan CANCELS orphan TP
- TP fill → position FLAT → BracketPlan CANCELS orphan SL
- Partial fill → recalc brackets

RID: OCO-AUDIT-FILL-TESTS
"""
from decimal import Decimal
from typing import List, Any

import pytest

from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketLeg,
    BracketRulesConfig,
    BracketService,
    BracketSet,
    BracketState,
    OrderView,
    PositionView,
)


class StubAggregator:
    """Stub aggregator for testing (returns fixed levels)."""

    def __init__(self, sl_price: Decimal = Decimal("98.0"), tp_price: Decimal = Decimal("104.0")):
        self.sl_price = sl_price
        self.tp_price = tp_price

    def compute_aggregated_brackets(self, **kwargs) -> Any:
        class StubLevels:
            def __init__(self, sl: Decimal, tp: Decimal):
                self.sl_price = sl
                self.tp_price = tp
                self.why = "stub_aggregator"

        return StubLevels(self.sl_price, self.tp_price)


class StubGuardian:
    """Stub guardian for testing."""

    def get_active_bracket_set(self, symbol: str, side: str):
        return None

    def list_all_bracket_sets(self) -> List:
        return []


@pytest.fixture
def default_config() -> BracketRulesConfig:
    return BracketRulesConfig(
        enabled=True,
        allow_unprotected_position=False,
        recalc_on_partial_close=True,
        recalc_on_scale_in=True,
        ttl_protect_new_bracket_ms=5000,
        max_tp_legs=1,
        max_sl_legs=1,
        sl_pct=0.02,
        tp_rr=2.0,
    )


@pytest.fixture
def stub_aggregator() -> StubAggregator:
    return StubAggregator(sl_price=Decimal("98.0"), tp_price=Decimal("104.0"))


@pytest.fixture
def stub_guardian() -> StubGuardian:
    return StubGuardian()


@pytest.fixture
def bracket_service(stub_aggregator, stub_guardian) -> BracketService:
    return BracketService(aggregator=stub_aggregator, guardian=stub_guardian)


# ============================================================================
# TEST-OCO-FILL-001: SL fill closes position → orphan TP must be cancelled
# ============================================================================

def test_sl_fill_position_flat_cancels_orphan_tp(bracket_service, default_config):
    """
    TEST-OCO-FILL-001: When SL fills and position becomes FLAT,
    the remaining TP order is orphaned and must be cancelled.

    State AFTER SL fill:
    - Position: FLAT (qty=0)
    - Orders: TP still exists (orphan)

    Expected BracketPlan:
    - CANCEL TP (reason: ORPHAN_TP)
    """
    # After SL fill, position is FLAT but TP still exists
    tp_order = OrderView(
        order_id="TP_001",
        client_order_id="AUR-BTCUSDT-LONG-TP-C1",
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("104.0"),
        reduce_only=True,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("0"),  # FLAT after SL fill
        avg_entry_price=Decimal("0"),
        legs=[BracketLeg(leg_type="TP", order=tp_order)],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=None,  # FLAT position
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    # Verify severity
    assert plan.severity == "WARN"
    assert "orphan" in plan.why.lower()

    # Verify CANCEL action for orphan TP
    assert plan.has_actions
    cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
    assert len(cancel_actions) == 1

    cancel_action = cancel_actions[0]
    assert cancel_action.order_id == "TP_001"
    assert cancel_action.reason_code == "ORPHAN_TP"


# ============================================================================
# TEST-OCO-FILL-002: TP fill closes position → orphan SL must be cancelled
# ============================================================================

def test_tp_fill_position_flat_cancels_orphan_sl(bracket_service, default_config):
    """
    TEST-OCO-FILL-002: When TP fills and position becomes FLAT,
    the remaining SL order is orphaned and must be cancelled.
    """
    # After TP fill, position is FLAT but SL still exists
    sl_order = OrderView(
        order_id="SL_001",
        client_order_id="AUR-BTCUSDT-LONG-SL-C1",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("98.0"),
        reduce_only=True,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("0"),  # FLAT after TP fill
        avg_entry_price=Decimal("0"),
        legs=[BracketLeg(leg_type="SL", order=sl_order)],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=None,
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    assert plan.severity == "WARN"
    cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
    assert len(cancel_actions) == 1
    assert cancel_actions[0].order_id == "SL_001"
    assert cancel_actions[0].reason_code == "ORPHAN_SL"


# ============================================================================
# TEST-OCO-FILL-003: Both SL and TP orphaned after position close
# ============================================================================

def test_full_close_cancels_both_orphan_brackets(bracket_service, default_config):
    """
    TEST-OCO-FILL-003: When position becomes FLAT (via manual close or other),
    both SL and TP are orphaned and must be cancelled.
    """
    sl_order = OrderView(
        order_id="SL_001",
        client_order_id="AUR-BTCUSDT-LONG-SL-C1",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("98.0"),
        reduce_only=True,
    )

    tp_order = OrderView(
        order_id="TP_001",
        client_order_id="AUR-BTCUSDT-LONG-TP-C1",
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("104.0"),
        reduce_only=True,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("0"),
        avg_entry_price=Decimal("0"),
        legs=[
            BracketLeg(leg_type="SL", order=sl_order),
            BracketLeg(leg_type="TP", order=tp_order),
        ],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=None,
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    assert plan.severity == "WARN"
    cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
    assert len(cancel_actions) == 2

    cancelled_ids = {a.order_id for a in cancel_actions}
    assert "SL_001" in cancelled_ids
    assert "TP_001" in cancelled_ids


# ============================================================================
# TEST-OCO-FILL-004: Partial SL fill reduces position → recalc brackets
# ============================================================================

def test_partial_fill_triggers_bracket_recalc(bracket_service, default_config):
    """
    TEST-OCO-FILL-004: When partial fill reduces position,
    brackets must be recalculated to match new position size.

    Before: qty=2.0, brackets for 2.0
    After partial SL: qty=1.0, brackets should be adjusted to 1.0
    """
    # Position reduced to 1.0 after partial SL fill
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
    )

    # Existing brackets still have qty=2.0 (stale)
    sl_order = OrderView(
        order_id="SL_001",
        client_order_id="AUR-BTCUSDT-LONG-SL-C1",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("2.0"),  # Oversized!
        stop_price=Decimal("98.0"),
        reduce_only=True,
    )

    tp_order = OrderView(
        order_id="TP_001",
        client_order_id="AUR-BTCUSDT-LONG-TP-C1",
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("2.0"),  # Oversized!
        stop_price=Decimal("104.0"),
        reduce_only=True,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        legs=[
            BracketLeg(leg_type="SL", order=sl_order),
            BracketLeg(leg_type="TP", order=tp_order),
        ],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=position,
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    # Should have actions to recalculate/resize brackets
    assert plan.has_actions

    # Looking for ADJUST or CANCEL+PLACE pattern
    action_types = [a.action_type for a in plan.actions]
    has_resize = "ADJUST" in action_types or (
        "CANCEL" in action_types and "PLACE_SL" in action_types)
    assert has_resize, f"Expected resize actions, got: {action_types}"


# ============================================================================
# TEST-OCO-FILL-005: Position with no brackets triggers ALERT
# ============================================================================

def test_position_without_brackets_alert(bracket_service, default_config):
    """
    TEST-OCO-FILL-005: Position exists without any brackets → ALERT.
    This simulates state after fill when brackets not yet placed.
    """
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=position,
        bracket_set=None,  # No brackets!
    )

    plan = bracket_service.evaluate(state, default_config)

    # Must be ALERT severity
    assert plan.severity == "ALERT"
    assert plan.is_critical

    # Must have PLACE_SL and PLACE_TP actions
    action_types = {a.action_type for a in plan.actions}
    assert "PLACE_SL" in action_types
    assert "PLACE_TP" in action_types


# ============================================================================
# TEST-OCO-FILL-006: SHORT position fill semantics
# ============================================================================

def test_short_position_sl_fill_cancels_tp(bracket_service, default_config):
    """
    TEST-OCO-FILL-006: SHORT position SL fill → orphan TP cancelled.
    """
    tp_order = OrderView(
        order_id="TP_SHORT",
        client_order_id="AUR-ETHUSDT-SHORT-TP-C1",
        symbol="ETHUSDT",
        side="BUY",  # SHORT exit is BUY
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("2.0"),
        stop_price=Decimal("2880.0"),
        reduce_only=True,
    )

    bracket_set = BracketSet(
        symbol="ETHUSDT",
        side="SHORT",
        position_qty=Decimal("0"),  # FLAT after SL fill
        avg_entry_price=Decimal("0"),
        legs=[BracketLeg(leg_type="TP", order=tp_order)],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="ETHUSDT",
        side="SHORT",
        position_view=None,
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    assert plan.severity == "WARN"
    cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
    assert len(cancel_actions) == 1
    assert cancel_actions[0].order_id == "TP_SHORT"


# ============================================================================
# TEST-OCO-FILL-007: Multiple brackets scenario
# ============================================================================

def test_multiple_sl_legs_excess_cancelled(bracket_service, default_config):
    """
    TEST-OCO-FILL-007: Too many SL legs → excess cancelled.
    """
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
    )

    # 3 SL orders (max is 1)
    sl_orders = [
        OrderView(
            order_id=f"SL_{i}",
            client_order_id=f"AUR-SL-{i}",
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            qty=Decimal("0.5"),
            stop_price=Decimal("98.0"),
            reduce_only=True,
        )
        for i in range(3)
    ]

    tp_order = OrderView(
        order_id="TP_001",
        client_order_id="AUR-TP-1",
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("104.0"),
        reduce_only=True,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("1.0"),
        avg_entry_price=Decimal("100.0"),
        legs=[BracketLeg(leg_type="SL", order=o) for o in sl_orders] +
        [BracketLeg(leg_type="TP", order=tp_order)],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=position,
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    # Should have CANCEL actions for excess SL
    cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
    # At least 2 excess SL should be cancelled
    assert len(cancel_actions) >= 2


# ============================================================================
# TEST-OCO-FILL-008: Bracket qty exceeds position qty
# ============================================================================

def test_bracket_qty_exceeds_position_triggers_resize(bracket_service, default_config):
    """
    TEST-OCO-FILL-008: Bracket qty > position qty → must resize.

    Invariant R1-B: sum(bracket_qty) ≤ position_qty
    """
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("0.5"),  # Reduced position
        avg_entry_price=Decimal("100.0"),
    )

    # SL qty exceeds position
    sl_order = OrderView(
        order_id="SL_001",
        client_order_id="AUR-SL-1",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),  # Exceeds position of 0.5!
        stop_price=Decimal("98.0"),
        reduce_only=True,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("0.5"),
        avg_entry_price=Decimal("100.0"),
        legs=[BracketLeg(leg_type="SL", order=sl_order)],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=position,
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    # Must have actions to resize
    assert plan.has_actions

    action_types = [a.action_type for a in plan.actions]
    # Should have ADJUST or CANCEL+PLACE
    has_resize = "ADJUST" in action_types or "CANCEL" in action_types
    assert has_resize, f"Expected resize action, got: {action_types}"


# ============================================================================
# TEST-OCO-FILL-009: Zero quantity bracket - test skipped
# ============================================================================

def test_zero_qty_bracket_skipped():
    """
    TEST-OCO-FILL-009: Zero quantity bracket validation.

    Note: OrderView validates qty > 0 in __post_init__, so zero-qty
    orders cannot be created. This is a validation test.
    """
    with pytest.raises(ValueError, match="must be > 0"):
        OrderView(
            order_id="SL_ZERO",
            client_order_id="AUR-SL-ZERO",
            symbol="BTCUSDT",
            side="SELL",
            order_type="STOP_MARKET",
            qty=Decimal("0"),  # Invalid!
            stop_price=Decimal("98.0"),
            reduce_only=True,
        )
