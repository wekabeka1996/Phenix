"""
Tests for BracketService — Pure Computation Layer
=================================================

Contract: EP-PORT-BRACKETS-S1-PH1 (v1.0)
Implementation: EP-PORT-BRACKETS-S1-PH2

Test Coverage:
- build_state(): flat positions, single position with brackets, multiple positions
- evaluate(): MISSING_SL, ORPHAN_SL, TOO_MANY_SL, STALE_LEVELS
- evaluate_all(): batch processing

All tests are pure (no network, no files, no global state).
"""
from decimal import Decimal
from typing import Any, List, Optional

import pytest

from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
    BracketAction,
    BracketLeg,
    BracketPlan,
    BracketRulesConfig,
    BracketService,
    BracketSet,
    BracketState,
    OrderView,
    PositionView,
)


# ============================================================================
# Test Fixtures & Stubs
# ============================================================================

class StubAggregator:
    """Stub aggregator for testing (returns fixed levels)."""

    def __init__(self, sl_price: Decimal, tp_price: Decimal):
        self.sl_price = sl_price
        self.tp_price = tp_price

    def compute_aggregated_brackets(self, **kwargs) -> Any:
        """Return stub bracket levels."""
        class StubLevels:
            def __init__(self, sl: Decimal, tp: Decimal):
                self.sl_price = sl
                self.tp_price = tp
                self.why = "stub_aggregator"

        return StubLevels(self.sl_price, self.tp_price)


class StubGuardian:
    """Stub guardian for testing (always returns None)."""

    def get_active_bracket_set(self, symbol: str, side: str) -> None:
        return None

    def list_all_bracket_sets(self) -> List:
        return []


@pytest.fixture
def default_config() -> BracketRulesConfig:
    """Default bracket rules config for testing."""
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
    """Stub aggregator with fixed SL/TP levels."""
    return StubAggregator(
        sl_price=Decimal("24.5"),  # 2% below entry of 25.0
        tp_price=Decimal("26.0"),  # 4% above entry (2% * RR=2.0)
    )


@pytest.fixture
def stub_guardian() -> StubGuardian:
    """Stub guardian (query-only)."""
    return StubGuardian()


@pytest.fixture
def bracket_service(stub_aggregator, stub_guardian) -> BracketService:
    """BracketService instance with stub dependencies."""
    return BracketService(
        aggregator=stub_aggregator,
        guardian=stub_guardian,
    )


# ============================================================================
# Tests: build_state()
# ============================================================================

def test_build_state_flat_no_orders(bracket_service):
    """Test build_state with no positions and no orders."""
    states = bracket_service.build_state(
        positions=[],
        orders=[],
    )

    assert states == {}


def test_build_state_single_long_position_with_sl_tp(bracket_service):
    """Test build_state with LONG position + SL + TP orders."""
    # Position: LONG 1.0 BTC @ 25.0
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("25.0"),
    )

    # SL order
    sl_order = OrderView(order_id="SL123",
        client_order_id="SL_CLIENT_123",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("24.5"),
        reduce_only=True,
    )

    # TP order
    tp_order = OrderView(order_id="TP456",
        client_order_id="TP_CLIENT_456",
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("26.0"),
        reduce_only=True,
    )

    states = bracket_service.build_state(
        positions=[position],
        orders=[sl_order, tp_order],
        symbol="BTCUSDT",
        side="LONG",
    )

    # Verify single state exists
    assert len(states) == 1
    key = ("BTCUSDT", "LONG")
    assert key in states

    state = states[key]

    # Verify position
    assert state.position_view is not None
    assert state.position_view.qty == Decimal("1.0")
    assert state.position_view.avg_entry_price == Decimal("25.0")

    # Verify brackets
    assert state.has_brackets
    assert state.sl_count == 1
    assert state.tp_count == 1

    # Verify leg classification
    sl_legs = state.bracket_set.sl_legs
    assert len(sl_legs) == 1
    assert sl_legs[0].order_id == "SL123"

    tp_legs = state.bracket_set.tp_legs
    assert len(tp_legs) == 1
    assert tp_legs[0].order_id == "TP456"


def test_build_state_flat_position_with_orphan_sl(bracket_service):
    """Test build_state with FLAT position but orphan SL order."""
    # No position (FLAT)

    # Orphan SL order
    sl_order = OrderView(order_id="SL999",
        client_order_id="SL_CLIENT_999",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("24.5"),
        reduce_only=True,
    )

    states = bracket_service.build_state(
        positions=[],
        orders=[sl_order],
    )

    # State should exist for LONG (or SHORT, depending on classification)
    # Since we have SELL order, it could be LONG position exit
    assert len(states) >= 1

    # Find state with brackets
    state_with_brackets = None
    for state in states.values():
        if state.has_brackets:
            state_with_brackets = state
            break

    assert state_with_brackets is not None
    assert state_with_brackets.is_flat  # No position
    assert state_with_brackets.has_brackets  # Has orphan SL


# ============================================================================
# Tests: evaluate() — MISSING_SL
# ============================================================================

def test_evaluate_missing_sl_alert(bracket_service, default_config):
    """Test evaluate() detects missing SL with ALERT severity."""
    # Position LONG 1.0 BTC @ 25.0, no brackets
    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=PositionView(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("1.0"),
            avg_entry_price=Decimal("25.0"),
        ),
        bracket_set=None,  # No brackets
    )

    plan = bracket_service.evaluate(state, default_config, rid="TEST_RID")

    # Verify ALERT severity
    assert plan.severity == "ALERT"
    assert plan.is_critical
    assert "missing_sl" in plan.why

    # Verify PLACE_SL + PLACE_TP actions (both missing when no brackets)
    assert plan.has_actions
    # R2-B-FIX: Now generates both PLACE_SL and PLACE_TP when both missing
    assert len(plan.actions) == 2

    sl_action = next(a for a in plan.actions if a.action_type == "PLACE_SL")
    assert sl_action.reason_code == "MISSING_SL_RECREATED"
    assert sl_action.price == Decimal("24.5")  # From stub aggregator
    assert sl_action.qty == Decimal("1.0")
    assert sl_action.rid == "TEST_RID"

    tp_action = next(a for a in plan.actions if a.action_type == "PLACE_TP")
    assert tp_action.reason_code == "MISSING_TP_RECREATED"


def test_evaluate_missing_sl_allowed(bracket_service):
    """Test evaluate() allows missing SL when allow_unprotected_position=True."""
    config = BracketRulesConfig(
        enabled=True,
        allow_unprotected_position=True,  # Permissive mode
    )

    # Position LONG 1.0 BTC @ 25.0, no brackets
    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=PositionView(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("1.0"),
            avg_entry_price=Decimal("25.0"),
        ),
        bracket_set=None,
    )

    plan = bracket_service.evaluate(state, config)

    # Verify INFO severity (allowed)
    assert plan.severity == "INFO"
    assert not plan.is_critical
    assert not plan.has_actions


# ============================================================================
# Tests: evaluate() — ORPHAN_SL
# ============================================================================

def test_evaluate_orphan_sl_warn(bracket_service, default_config):
    """Test evaluate() detects orphan SL with WARN severity."""
    # FLAT position (no position_view), but has SL order
    sl_order = OrderView(order_id="SL999",
        client_order_id="SL_CLIENT_999",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("24.5"),
        reduce_only=True,
    )

    sl_leg = BracketLeg(
        leg_type="SL",
        order=sl_order,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("0"),
        avg_entry_price=Decimal("0"),
        legs=[sl_leg],
        created_ts=1234567890.0,
        updated_ts=1234567890.0,
    )

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=None,  # FLAT
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    # Verify WARN severity
    assert plan.severity == "WARN"
    assert "orphan" in plan.why.lower()

    # Verify CANCEL action
    assert plan.has_actions
    assert len(plan.actions) == 1

    action = plan.actions[0]
    assert action.action_type == "CANCEL"
    assert action.reason_code == "ORPHAN_SL"
    assert action.order_id == "SL999"


def test_evaluate_orphan_sl_and_tp_warn(bracket_service, default_config):
    """Test evaluate() detects orphan SL + TP with WARN severity."""
    # FLAT position, but has SL + TP orders
    sl_order = OrderView(order_id="SL999",
        client_order_id="SL_CLIENT_999",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("24.5"),
        reduce_only=True,
    )

    tp_order = OrderView(order_id="TP888",
        client_order_id="TP_CLIENT_888",
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("26.0"),
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
        position_view=None,  # FLAT
        bracket_set=bracket_set,
    )

    plan = bracket_service.evaluate(state, default_config)

    # Verify WARN severity
    assert plan.severity == "WARN"

    # Verify 2 CANCEL actions (SL + TP)
    assert plan.has_actions
    assert len(plan.actions) == 2

    cancel_order_ids = {action.order_id for action in plan.actions}
    assert "SL999" in cancel_order_ids
    assert "TP888" in cancel_order_ids


# ============================================================================
# Tests: evaluate() — TOO_MANY_SL
# ============================================================================

def test_evaluate_too_many_sl_warn(bracket_service, default_config):
    """Test evaluate() detects too many SL orders with WARN severity."""
    # Position LONG 3.0 BTC @ 25.0, with 3 SL orders (qty matches but count > max_sl_legs)
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        # R2-B: Match total SL qty to avoid SIZE_INVARIANT overlap
        qty=Decimal("3.0"),
        avg_entry_price=Decimal("25.0"),
    )

    # Create 3 SL orders (each 1.0, total 3.0 = position qty)
    sl_legs = [
        BracketLeg(
            leg_type="SL",
            order=OrderView(order_id=f"SL{i}",
                client_order_id=f"SL_CLIENT_{i}",
                symbol="BTCUSDT",
                side="SELL",
                order_type="STOP_MARKET",
                qty=Decimal("1.0"),
                stop_price=Decimal("24.5"),
                reduce_only=True,
            ),
        )
        for i in range(3)
    ]

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("3.0"),  # Match position
        avg_entry_price=Decimal("25.0"),
        legs=sl_legs,
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

    # Verify WARN severity
    assert plan.severity == "WARN"
    assert "too_many_sl" in plan.why.lower() or "missing_tp" in plan.why.lower()

    # Should have actions (at least CANCEL for extra SL and/or PLACE_TP for missing TP)
    assert plan.has_actions

    # At least 2 CANCEL actions for extra SL legs (keep 1, cancel 2)
    cancel_actions = [a for a in plan.actions if a.action_type == "CANCEL"]
    assert len(cancel_actions) >= 2

    for action in cancel_actions:
        assert action.reason_code == "TOO_MANY_SL"


# ============================================================================
# Tests: evaluate() — STALE_LEVELS
# ============================================================================

def test_evaluate_stale_sl_level_warn(bracket_service, default_config):
    """Test evaluate() detects stale SL level with WARN severity."""
    # Position LONG 1.0 BTC @ 25.0
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("25.0"),
    )

    # SL at wrong price (should be 24.5, but is 24.0)
    sl_order = OrderView(order_id="SL123",
        client_order_id="SL_CLIENT_123",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("24.0"),  # Wrong price
        reduce_only=True,
    )

    # R2-B-FIX: Also include TP to avoid MISSING_TP taking precedence
    tp_order = OrderView(order_id="TP123",
        client_order_id="TP_CLIENT_123",
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("26.0"),  # Correct TP price
        reduce_only=True,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("1.0"),
        avg_entry_price=Decimal("25.0"),
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

    # Verify WARN severity (stale SL level detected)
    assert plan.severity == "WARN"
    assert "stale" in plan.why.lower()

    # Verify 2 actions: CANCEL old SL + PLACE new SL
    assert plan.has_actions
    sl_actions = [a for a in plan.actions if "SL" in (
        a.action_type or "") or a.order_id == "SL123"]
    assert len(
        sl_actions) >= 2, f"Expected at least CANCEL + PLACE_SL, got {plan.actions}"

    cancel_action = next(a for a in plan.actions if a.action_type == "CANCEL")
    assert cancel_action.order_id == "SL123"

    place_action = next(a for a in plan.actions if a.action_type == "PLACE_SL")
    assert place_action.price == Decimal(
        "24.5")  # Correct price from aggregator
    # Correct price from stub aggregator
    assert place_action.price == Decimal("24.5")


def test_evaluate_stale_sl_and_tp_levels_warn(bracket_service, default_config):
    """Test evaluate() detects stale SL + TP levels with WARN severity."""
    # Position LONG 1.0 BTC @ 25.0
    position = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("25.0"),
    )

    # SL at wrong price
    sl_order = OrderView(order_id="SL123",
        client_order_id="SL_CLIENT_123",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("24.0"),  # Should be 24.5
        reduce_only=True,
    )

    # TP at wrong price
    tp_order = OrderView(order_id="TP456",
        client_order_id="TP_CLIENT_456",
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("25.5"),  # Should be 26.0
        reduce_only=True,
    )

    bracket_set = BracketSet(
        symbol="BTCUSDT",
        side="LONG",
        position_qty=Decimal("1.0"),
        avg_entry_price=Decimal("25.0"),
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

    # Verify WARN severity
    assert plan.severity == "WARN"

    # Verify 4 actions: CANCEL old SL, PLACE new SL, CANCEL old TP, PLACE new TP
    assert plan.has_actions
    assert len(plan.actions) == 4

    # Verify order: CANCEL before PLACE
    action_types = [action.action_type for action in plan.actions]
    assert action_types.count("CANCEL") == 2
    assert action_types.count("PLACE_SL") == 1
    assert action_types.count("PLACE_TP") == 1


# ============================================================================
# Tests: evaluate_all()
# ============================================================================

def test_evaluate_all_multiple_positions(bracket_service, default_config):
    """Test evaluate_all() with multiple positions."""
    # Position 1: LONG 1.0 BTC @ 25.0 (no brackets → ALERT)
    pos1 = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("25.0"),
    )

    # Position 2: SHORT 0.5 ETH @ 1500.0 (no brackets → ALERT)
    pos2 = PositionView(
        symbol="ETHUSDT",
        side="SHORT",
        qty=Decimal("0.5"),
        avg_entry_price=Decimal("1500.0"),
    )

    plans = bracket_service.evaluate_all(
        positions=[pos1, pos2],
        orders=[],
        cfg=default_config,
        rid="TEST_BATCH",
    )

    # Verify 2 plans
    assert len(plans) == 2

    # Both should be ALERT (missing SL)
    alert_plans = [p for p in plans if p.is_critical]
    assert len(alert_plans) == 2

    # Verify RID propagation
    for plan in plans:
        assert plan.rid == "TEST_BATCH"


def test_evaluate_all_mixed_severities(bracket_service, default_config):
    """Test evaluate_all() with mixed severity levels."""
    # Position 1: LONG 1.0 BTC @ 25.0 with correct SL and TP (INFO)
    pos1 = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("25.0"),
    )

    sl1 = OrderView(order_id="SL1",
        client_order_id="SL_CLIENT_1",
        symbol="BTCUSDT",
        side="SELL",
        order_type="STOP_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("24.5"),  # Correct price
        reduce_only=True,
    )

    # R2-B-FIX: Add TP order to get INFO severity (no missing brackets)
    tp1 = OrderView(order_id="TP1",
        client_order_id="TP_CLIENT_1",
        symbol="BTCUSDT",
        side="SELL",
        order_type="TAKE_PROFIT_MARKET",
        qty=Decimal("1.0"),
        stop_price=Decimal("26.0"),  # Correct TP price
        reduce_only=True,
    )

    # Position 2: SHORT 0.5 ETH @ 1500.0 (no brackets → ALERT)
    pos2 = PositionView(
        symbol="ETHUSDT",
        side="SHORT",
        qty=Decimal("0.5"),
        avg_entry_price=Decimal("1500.0"),
    )

    plans = bracket_service.evaluate_all(
        positions=[pos1, pos2],
        orders=[sl1, tp1],  # Include TP order
        cfg=default_config,
    )

    # Verify 2 plans
    assert len(plans) == 2

    # Count by severity
    info_plans = [p for p in plans if p.severity == "INFO"]
    alert_plans = [p for p in plans if p.severity == "ALERT"]

    # BTCUSDT with correct SL+TP
    assert len(
        info_plans) == 1, f"Expected 1 INFO plan (BTCUSDT), got {info_plans}"
    # ETHUSDT missing SL
    assert len(
        alert_plans) == 1, f"Expected 1 ALERT plan (ETHUSDT), got {alert_plans}"


# ============================================================================
# Tests: Data Model Invariants
# ============================================================================

def test_position_view_invariants():
    """Test PositionView validates invariants."""
    # Valid position
    pos = PositionView(
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1.0"),
        avg_entry_price=Decimal("25.0"),
    )
    assert pos.qty == Decimal("1.0")

    # Invalid: negative qty
    with pytest.raises(ValueError, match="qty must be >= 0"):
        PositionView(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("-1.0"),
            avg_entry_price=Decimal("25.0"),
        )

    # Invalid: wrong side
    with pytest.raises(ValueError, match="side must be LONG or SHORT"):
        PositionView(
            symbol="BTCUSDT",
            side="FLAT",  # type: ignore
            qty=Decimal("1.0"),
            avg_entry_price=Decimal("25.0"),
        )

    # Invalid: qty > 0 but avg_entry <= 0
    with pytest.raises(ValueError, match="avg_entry_price must be > 0"):
        PositionView(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("1.0"),
            avg_entry_price=Decimal("0"),
        )


def test_order_view_invariants():
    """Test OrderView validates invariants."""
    # Valid order
    order = OrderView(order_id="123",
        client_order_id="CLIENT_123",
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        qty=Decimal("1.0"),
        price=Decimal("25.0"),
    )
    assert order.order_id == "123"

    # Invalid: empty order_id
    with pytest.raises(ValueError, match="order_id cannot be empty"):
        OrderView(order_id="",
            client_order_id="CLIENT_123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            qty=Decimal("1.0"),
        )

    # Invalid: qty <= 0
    with pytest.raises(ValueError, match="qty must be > 0"):
        OrderView(order_id="123",
            client_order_id="CLIENT_123",
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            qty=Decimal("0"),
        )


def test_bracket_action_why_truncation():
    """Test BracketAction truncates why field to 80 chars."""
    long_why = "a" * 100  # 100 chars

    action = BracketAction(
        action="CANCEL",
        order_ref="123",
        reason_code="TEST",
        why=long_why,
    )

    # Verify truncation
    assert len(action.why) == 80


# ============================================================================
# Tests: Edge Cases
# ============================================================================

def test_evaluate_disabled_config(bracket_service):
    """Test evaluate() returns INFO no-op when config disabled."""
    config = BracketRulesConfig(enabled=False)

    state = BracketState(
        symbol="BTCUSDT",
        side="LONG",
        position_view=PositionView(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("1.0"),
            avg_entry_price=Decimal("25.0"),
        ),
        bracket_set=None,
    )

    plan = bracket_service.evaluate(state, config)

    assert plan.severity == "INFO"
    assert not plan.has_actions
    assert "disabled" in plan.why.lower()


def test_evaluate_invalid_state_raises_error(bracket_service, default_config):
    """Test evaluate() raises ValueError for invalid state."""
    # Empty symbol
    state = BracketState(
        symbol="",
        side="LONG",
        position_view=None,
        bracket_set=None,
    )

    with pytest.raises(ValueError, match="symbol cannot be empty"):
        bracket_service.evaluate(state, default_config)

    # Invalid side
    state = BracketState(
        symbol="BTCUSDT",
        side="INVALID",  # type: ignore
        position_view=None,
        bracket_set=None,
    )

    with pytest.raises(ValueError, match="side must be LONG or SHORT"):
        bracket_service.evaluate(state, default_config)
