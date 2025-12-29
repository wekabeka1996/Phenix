"""
Shape tests for Aggregator OCO contract types.

These tests validate:
1. Dataclass serialization (asdict)
2. Valid Literal values
3. Factory helpers
4. Type invariants

NO imports from runtime, adapter, or bracket_service.

RID: EXEC-AGGREGATOR-OCO-PHASE1-CONTRACT-AND-TYPES
"""

from dataclasses import asdict
from decimal import Decimal
from typing import get_args

import pytest

from apps.reference.domains.execution_position.aggregator_oco.contracts import (
    # Type aliases
    Side,
    OrderSide,
    OrderType,
    OrderStatus,
    BracketLegType,
    ActionType,
    # Valid value sets
    VALID_SIDES,
    VALID_ORDER_SIDES,
    VALID_ORDER_TYPES,
    VALID_ORDER_STATUSES,
    VALID_LEG_TYPES,
    VALID_ACTION_TYPES,
    # Input types
    OrderSnapshot,
    PositionSnapshot,
    AggregatorInput,
    # Config types
    BracketConfig,
    # Output types
    BracketAction,
    BracketPlan,
    # Factory helpers
    noop_plan,
    suppressed_plan,
    place_sl_action,
    place_tp_action,
    cancel_action,
    adjust_action,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SERIALIZATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestSerializationToDict:
    """Test that all dataclasses can be serialized to dict via asdict."""

    def test_order_snapshot_serializable(self) -> None:
        """OrderSnapshot can be converted to dict."""
        order = OrderSnapshot(
            symbol="BTCUSDT",
            order_id="123",
            client_order_id="cli-123",
            side="SELL",
            type="STOP_MARKET",
            stop_price=Decimal("29000"),
            status="NEW",
        )
        data = asdict(order)
        assert data["symbol"] == "BTCUSDT"
        assert data["order_id"] == "123"
        assert data["type"] == "STOP_MARKET"
        assert data["stop_price"] == Decimal("29000")

    def test_position_snapshot_serializable(self) -> None:
        """PositionSnapshot can be converted to dict."""
        pos = PositionSnapshot(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("0.01"),
            entry_price=Decimal("30000"),
            unrealized_pnl=Decimal("50"),
        )
        data = asdict(pos)
        assert data["symbol"] == "BTCUSDT"
        assert data["side"] == "LONG"
        assert data["qty"] == Decimal("0.01")

    def test_aggregator_input_serializable(self) -> None:
        """AggregatorInput can be converted to dict."""
        pos = PositionSnapshot(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("0.01"),
            entry_price=Decimal("30000"),
        )
        order = OrderSnapshot(
            symbol="BTCUSDT",
            order_id="sl-123",
            client_order_id="cli-sl",
            side="SELL",
            type="STOP_MARKET",
            stop_price=Decimal("29400"),
            status="NEW",
        )
        inp = AggregatorInput(
            symbol="BTCUSDT",
            position=pos,
            orders=[order],
            mark_price=Decimal("30100"),
        )
        data = asdict(inp)
        assert data["symbol"] == "BTCUSDT"
        assert data["position"]["side"] == "LONG"
        assert len(data["orders"]) == 1
        assert data["orders"][0]["type"] == "STOP_MARKET"

    def test_bracket_action_serializable(self) -> None:
        """BracketAction can be converted to dict."""
        action = BracketAction(
            action="PLACE_SL",
            leg_type="SL",
            target_price=Decimal("29000"),
            order_ref=None,
            why="missing_sl",
        )
        data = asdict(action)
        assert data["action"] == "PLACE_SL"
        assert data["leg_type"] == "SL"
        assert data["why"] == "missing_sl"

    def test_bracket_plan_serializable(self) -> None:
        """BracketPlan can be converted to dict with nested actions."""
        plan = BracketPlan(
            symbol="BTCUSDT",
            actions=[
                BracketAction(
                    action="PLACE_SL",
                    leg_type="SL",
                    target_price=Decimal("29000"),
                    why="initial_sl",
                ),
                BracketAction(
                    action="PLACE_TP",
                    leg_type="TP",
                    target_price=Decimal("31200"),
                    why="initial_tp",
                ),
            ],
            suppressed=False,
            why="new_position",
        )
        data = asdict(plan)
        assert data["symbol"] == "BTCUSDT"
        assert len(data["actions"]) == 2
        assert data["actions"][0]["leg_type"] == "SL"
        assert data["actions"][1]["leg_type"] == "TP"
        assert data["why"] == "new_position"

    def test_bracket_config_serializable(self) -> None:
        """BracketConfig can be converted to dict."""
        cfg = BracketConfig(
            sl_pct=Decimal("0.03"),
            tp_rr=Decimal("3.0"),
        )
        data = asdict(cfg)
        assert data["sl_pct"] == Decimal("0.03")
        assert data["tp_rr"] == Decimal("3.0")


# ═══════════════════════════════════════════════════════════════════════════════
# LITERAL VALUES TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestLiteralValueSets:
    """Test that Literal type annotations match VALID_* frozensets."""

    def test_side_values_match(self) -> None:
        """Side Literal matches VALID_SIDES."""
        literal_values = set(get_args(Side))
        assert literal_values == VALID_SIDES

    def test_order_side_values_match(self) -> None:
        """OrderSide Literal matches VALID_ORDER_SIDES."""
        literal_values = set(get_args(OrderSide))
        assert literal_values == VALID_ORDER_SIDES

    def test_order_type_values_match(self) -> None:
        """OrderType Literal matches VALID_ORDER_TYPES."""
        literal_values = set(get_args(OrderType))
        assert literal_values == VALID_ORDER_TYPES

    def test_order_status_values_match(self) -> None:
        """OrderStatus Literal matches VALID_ORDER_STATUSES."""
        literal_values = set(get_args(OrderStatus))
        assert literal_values == VALID_ORDER_STATUSES

    def test_leg_type_values_match(self) -> None:
        """BracketLegType Literal matches VALID_LEG_TYPES."""
        literal_values = set(get_args(BracketLegType))
        assert literal_values == VALID_LEG_TYPES

    def test_action_type_values_match(self) -> None:
        """ActionType Literal matches VALID_ACTION_TYPES."""
        literal_values = set(get_args(ActionType))
        assert literal_values == VALID_ACTION_TYPES


class TestBracketActionValidValues:
    """Test BracketAction with valid action values."""

    @pytest.mark.parametrize("action_val", ["PLACE_SL", "PLACE_TP", "CANCEL", "ADJUST", "NOOP"])
    def test_action_values_accepted(self, action_val: str) -> None:
        """All valid action values can be used."""
        if action_val in ("PLACE_SL", "PLACE_TP"):
            action = BracketAction(
                action=action_val,
                leg_type="SL",
                target_price=Decimal("29000"),
            )
        elif action_val == "CANCEL":
            action = BracketAction(action=action_val, order_ref="ord-123")
        elif action_val == "ADJUST":
            action = BracketAction(
                action=action_val,
                order_ref="ord-123",
                target_price=Decimal("29000"),
            )
        else:  # NOOP
            action = BracketAction(action=action_val)

        assert action.action == action_val
        assert action.action in VALID_ACTION_TYPES


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY HELPERS TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestFactoryHelpers:
    """Test factory helper functions."""

    def test_noop_plan(self) -> None:
        """noop_plan creates empty plan."""
        plan = noop_plan("BTCUSDT", "all_correct")
        assert plan.symbol == "BTCUSDT"
        assert plan.actions == []
        assert plan.suppressed is False
        assert plan.why == "all_correct"
        assert plan.is_noop()

    def test_suppressed_plan(self) -> None:
        """suppressed_plan creates suppressed plan."""
        plan = suppressed_plan("BTCUSDT", "throttled")
        assert plan.symbol == "BTCUSDT"
        assert plan.suppressed is True
        assert plan.why == "throttled"

    def test_place_sl_action(self) -> None:
        """place_sl_action creates correct action."""
        action = place_sl_action(Decimal("29000"), "initial_sl")
        assert action.action == "PLACE_SL"
        assert action.leg_type == "SL"
        assert action.target_price == Decimal("29000")
        assert action.why == "initial_sl"

    def test_place_tp_action(self) -> None:
        """place_tp_action creates correct action."""
        action = place_tp_action(Decimal("31200"), "initial_tp")
        assert action.action == "PLACE_TP"
        assert action.leg_type == "TP"
        assert action.target_price == Decimal("31200")
        assert action.why == "initial_tp"

    def test_cancel_action(self) -> None:
        """cancel_action creates correct action."""
        action = cancel_action("ord-123", "orphan_cleanup")
        assert action.action == "CANCEL"
        assert action.order_ref == "ord-123"
        assert action.why == "orphan_cleanup"

    def test_adjust_action(self) -> None:
        """adjust_action creates correct action."""
        action = adjust_action("ord-123", Decimal("29500"),
                               "SL", "price_drift_0.5pct")
        assert action.action == "ADJUST"
        assert action.order_ref == "ord-123"
        assert action.target_price == Decimal("29500")
        assert action.leg_type == "SL"
        assert action.why == "price_drift_0.5pct"


# ═══════════════════════════════════════════════════════════════════════════════
# INVARIANT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvariants:
    """Test type invariants and validation."""

    def test_place_sl_requires_target_price(self) -> None:
        """PLACE_SL without target_price raises ValueError."""
        with pytest.raises(ValueError, match="PLACE_SL requires target_price"):
            BracketAction(action="PLACE_SL", leg_type="SL")

    def test_place_tp_requires_leg_type(self) -> None:
        """PLACE_TP without leg_type raises ValueError."""
        with pytest.raises(ValueError, match="PLACE_TP requires leg_type"):
            BracketAction(action="PLACE_TP", target_price=Decimal("31200"))

    def test_cancel_requires_order_ref(self) -> None:
        """CANCEL without order_ref raises ValueError."""
        with pytest.raises(ValueError, match="CANCEL requires order_ref"):
            BracketAction(action="CANCEL")

    def test_adjust_requires_both_fields(self) -> None:
        """ADJUST without order_ref and target_price raises ValueError."""
        with pytest.raises(ValueError, match="ADJUST requires order_ref and target_price"):
            BracketAction(action="ADJUST", order_ref="ord-123")
        with pytest.raises(ValueError, match="ADJUST requires order_ref and target_price"):
            BracketAction(action="ADJUST", target_price=Decimal("29000"))

    def test_noop_requires_nothing(self) -> None:
        """NOOP can be created with minimal fields."""
        action = BracketAction(action="NOOP")
        assert action.action == "NOOP"


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER METHOD TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelperMethods:
    """Test helper methods on types."""

    def test_order_snapshot_is_stop_loss(self) -> None:
        """OrderSnapshot.is_stop_loss() works correctly."""
        sl = OrderSnapshot(
            symbol="BTCUSDT",
            order_id="123",
            client_order_id="cli",
            side="SELL",
            type="STOP_MARKET",
            stop_price=Decimal("29000"),
            status="NEW",
        )
        tp = OrderSnapshot(
            symbol="BTCUSDT",
            order_id="456",
            client_order_id="cli2",
            side="SELL",
            type="TAKE_PROFIT_MARKET",
            stop_price=Decimal("31000"),
            status="NEW",
        )
        assert sl.is_stop_loss() is True
        assert sl.is_take_profit() is False
        assert tp.is_stop_loss() is False
        assert tp.is_take_profit() is True

    def test_order_snapshot_is_active(self) -> None:
        """OrderSnapshot.is_active() works correctly."""
        active = OrderSnapshot(
            symbol="BTCUSDT",
            order_id="123",
            client_order_id="cli",
            side="SELL",
            type="STOP_MARKET",
            stop_price=Decimal("29000"),
            status="NEW",
        )
        filled = OrderSnapshot(
            symbol="BTCUSDT",
            order_id="456",
            client_order_id="cli2",
            side="SELL",
            type="STOP_MARKET",
            stop_price=Decimal("29000"),
            status="FILLED",
        )
        assert active.is_active() is True
        assert filled.is_active() is False

    def test_position_snapshot_bracket_side(self) -> None:
        """PositionSnapshot.bracket_side() returns opposite side."""
        long_pos = PositionSnapshot(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("0.01"),
            entry_price=Decimal("30000"),
        )
        short_pos = PositionSnapshot(
            symbol="BTCUSDT",
            side="SHORT",
            qty=Decimal("0.01"),
            entry_price=Decimal("30000"),
        )
        assert long_pos.bracket_side() == "SELL"
        assert short_pos.bracket_side() == "BUY"

    def test_aggregator_input_is_flat(self) -> None:
        """AggregatorInput.is_flat() works correctly."""
        flat_none = AggregatorInput(symbol="BTCUSDT", position=None, orders=[])
        assert flat_none.is_flat() is True

        flat_zero = AggregatorInput(
            symbol="BTCUSDT",
            position=PositionSnapshot(
                symbol="BTCUSDT",
                side="LONG",
                qty=Decimal("0"),
                entry_price=Decimal("30000"),
            ),
            orders=[],
        )
        assert flat_zero.is_flat() is True

        has_pos = AggregatorInput(
            symbol="BTCUSDT",
            position=PositionSnapshot(
                symbol="BTCUSDT",
                side="LONG",
                qty=Decimal("0.01"),
                entry_price=Decimal("30000"),
            ),
            orders=[],
        )
        assert has_pos.is_flat() is False

    def test_bracket_plan_is_noop(self) -> None:
        """BracketPlan.is_noop() works correctly."""
        empty = BracketPlan(symbol="BTCUSDT", actions=[], why="all_ok")
        assert empty.is_noop() is True

        noop_action = BracketPlan(
            symbol="BTCUSDT",
            actions=[BracketAction(action="NOOP")],
            why="all_ok",
        )
        assert noop_action.is_noop() is True

        has_action = BracketPlan(
            symbol="BTCUSDT",
            actions=[place_sl_action(Decimal("29000"))],
            why="needs_sl",
        )
        assert has_action.is_noop() is False

    def test_bracket_plan_has_placements(self) -> None:
        """BracketPlan.has_placements() works correctly."""
        with_place = BracketPlan(
            symbol="BTCUSDT",
            actions=[place_sl_action(Decimal("29000"))],
            why="needs_sl",
        )
        assert with_place.has_placements() is True

        with_cancel = BracketPlan(
            symbol="BTCUSDT",
            actions=[cancel_action("ord-123")],
            why="cleanup",
        )
        assert with_cancel.has_placements() is False


# ═══════════════════════════════════════════════════════════════════════════════
# FROZEN DATACLASS TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestFrozenDataclasses:
    """Test that frozen dataclasses are immutable."""

    def test_order_snapshot_is_frozen(self) -> None:
        """OrderSnapshot is immutable."""
        order = OrderSnapshot(
            symbol="BTCUSDT",
            order_id="123",
            client_order_id="cli",
            side="SELL",
            type="STOP_MARKET",
            stop_price=Decimal("29000"),
            status="NEW",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            order.symbol = "ETHUSDT"  # type: ignore

    def test_position_snapshot_is_frozen(self) -> None:
        """PositionSnapshot is immutable."""
        pos = PositionSnapshot(
            symbol="BTCUSDT",
            side="LONG",
            qty=Decimal("0.01"),
            entry_price=Decimal("30000"),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            pos.qty = Decimal("0.02")  # type: ignore

    def test_bracket_config_is_frozen(self) -> None:
        """BracketConfig is immutable."""
        cfg = BracketConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            cfg.sl_pct = Decimal("0.05")  # type: ignore
