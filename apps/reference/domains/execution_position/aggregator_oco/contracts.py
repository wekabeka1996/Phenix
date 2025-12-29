"""
Aggregator OCO — Contract Types (Phase 1 + Phase 2 extensions)

Pure dataclass definitions for the Aggregator OCO subdomain.
NO imports from runtime, adapter, or bracket_service.

RID: EXEC-AGGREGATOR-OCO-PHASE1-CONTRACT-AND-TYPES
     EXEC-AGGREGATOR-OCO-PHASE2-BRACKET-SERVICE-OUTPUT-TYPES
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, List, Literal, Optional
import time

# ═══════════════════════════════════════════════════════════════════════════════
# TYPE ALIASES
# ═══════════════════════════════════════════════════════════════════════════════

Side = Literal["LONG", "SHORT"]
OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT", "MARKET"]
OrderStatus = Literal["NEW", "WORKING", "FILLED",
                      "PARTIALLY_FILLED", "CANCELED", "REJECTED"]
BracketLegType = Literal["SL", "TP"]
ActionType = Literal["PLACE_SL", "PLACE_TP", "CANCEL", "ADJUST", "NOOP"]

# Valid values for runtime validation
VALID_SIDES: frozenset[str] = frozenset({"LONG", "SHORT"})
VALID_ORDER_SIDES: frozenset[str] = frozenset({"BUY", "SELL"})
VALID_ORDER_TYPES: frozenset[str] = frozenset(
    {"STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT", "MARKET"})
VALID_ORDER_STATUSES: frozenset[str] = frozenset(
    {"NEW", "WORKING", "FILLED", "PARTIALLY_FILLED", "CANCELED", "REJECTED"})
VALID_LEG_TYPES: frozenset[str] = frozenset({"SL", "TP"})
VALID_ACTION_TYPES: frozenset[str] = frozenset(
    {"PLACE_SL", "PLACE_TP", "CANCEL", "ADJUST", "NOOP"})


# ═══════════════════════════════════════════════════════════════════════════════
# INPUT TYPES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class OrderSnapshot:
    """
    Point-in-time snapshot of an order.

    Used to represent current bracket orders (SL/TP) for evaluation.
    Frozen for hashability and safety.
    """
    symbol: str
    order_id: Optional[str]
    client_order_id: Optional[str]
    side: OrderSide
    type: OrderType
    stop_price: Optional[Decimal]
    status: OrderStatus

    def is_stop_loss(self) -> bool:
        """Check if this is a stop loss order."""
        return self.type == "STOP_MARKET"

    def is_take_profit(self) -> bool:
        """Check if this is a take profit order."""
        return self.type == "TAKE_PROFIT_MARKET"

    def is_active(self) -> bool:
        """Check if order is still active (can be canceled)."""
        return self.status in ("NEW", "WORKING", "PARTIALLY_FILLED")


@dataclass(frozen=True)
class PositionSnapshot:
    """
    Point-in-time snapshot of a position.

    Represents current position state for bracket evaluation.
    Frozen for hashability and safety.
    """
    symbol: str
    side: Side
    qty: Decimal
    entry_price: Decimal
    unrealized_pnl: Optional[Decimal] = None

    def is_long(self) -> bool:
        """Check if position is long."""
        return self.side == "LONG"

    def is_short(self) -> bool:
        """Check if position is short."""
        return self.side == "SHORT"

    def bracket_side(self) -> OrderSide:
        """Get the order side for bracket orders (opposite of position)."""
        return "SELL" if self.is_long() else "BUY"


@dataclass
class AggregatorInput:
    """
    Complete input snapshot for bracket evaluation.

    Contains all data needed to compute a BracketPlan.
    Not frozen because ts has a default factory.
    """
    symbol: str
    position: Optional[PositionSnapshot]
    orders: List[OrderSnapshot]
    mark_price: Optional[Decimal] = None
    ts: float = field(default_factory=lambda: time.time())

    def is_flat(self) -> bool:
        """Check if position is flat (no position or zero qty)."""
        return self.position is None or self.position.qty == Decimal("0")

    def get_bracket_orders(self) -> List[OrderSnapshot]:
        """Get only bracket orders (SL/TP) from order list."""
        return [o for o in self.orders if o.is_stop_loss() or o.is_take_profit()]

    def get_active_sl(self) -> Optional[OrderSnapshot]:
        """Get active stop loss order if exists."""
        for order in self.orders:
            if order.is_stop_loss() and order.is_active():
                return order
        return None

    def get_active_tp(self) -> Optional[OrderSnapshot]:
        """Get active take profit order if exists."""
        for order in self.orders:
            if order.is_take_profit() and order.is_active():
                return order
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG TYPES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BracketConfig:
    """
    Configuration for bracket calculation.

    Subset of AggregatedOcoConfig relevant to price computation.
    """
    sl_pct: Decimal = Decimal("0.02")           # 2% stop loss
    tp_rr: Decimal = Decimal("2.0")             # 1:2 risk:reward
    trailing_enabled: bool = False
    trailing_step_pct: Decimal = Decimal("0.005")
    tolerance_pct: Decimal = Decimal("0.001")   # 0.1% price drift tolerance


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT TYPES
# ═══════════════════════════════════════════════════════════════════════════════

# Action type includes NOOP for minimal plans
ActionTypeFull = Literal["CANCEL", "PLACE_SL", "PLACE_TP", "ADJUST", "NOOP"]

# Severity levels for bracket evaluation results
SeverityType = Literal["INFO", "WARN", "ALERT"]


@dataclass
class BracketAction:
    """
    Single action in a bracket plan.

    Represents one operation to bring bracket state into alignment.
    Every action MUST have a `why` for XAI traceability.

    Compatible with both:
    - contracts.py minimal interface (action, leg_type, target_price, order_ref, why)
    - bracket_service.py full interface (action_type, order_id, client_order_id, price, qty, etc.)
    """
    # Core action field - use 'action' as canonical name
    action: ActionType

    # Leg type for PLACE_SL/PLACE_TP/ADJUST
    leg_type: Optional[BracketLegType] = None

    # Target/stop price for PLACE_*/ADJUST actions
    target_price: Optional[Decimal] = None

    # Order reference for CANCEL/ADJUST (alias: order_ref or order_id)
    order_ref: Optional[str] = None

    # Client order ID (for tracking)
    client_order_id: Optional[str] = None

    # Order quantity (for PLACE_* actions)
    qty: Optional[Decimal] = None

    # XAI metadata
    reason_code: str = ""               # "MISSING_SL" | "ORPHAN_SL" | etc.
    why: str = ""                       # Structured why (≤80 chars)

    # Tracing
    rid: Optional[str] = None           # Request ID for tracing
    parent_why: Optional[str] = None    # Parent event trigger

    def __post_init__(self) -> None:
        """Validate action constraints and truncate why if needed."""
        # Truncate why to 80 chars (graceful degradation)
        if len(self.why) > 80:
            object.__setattr__(self, 'why', self.why[:80])

        # Validation for required fields by action type
        if self.action in ("PLACE_SL", "PLACE_TP"):
            if self.target_price is None:
                raise ValueError(f"{self.action} requires target_price")
            if self.leg_type is None:
                raise ValueError(f"{self.action} requires leg_type")
        elif self.action == "CANCEL":
            if self.order_ref is None:
                raise ValueError("CANCEL requires order_ref")
        elif self.action == "ADJUST":
            if self.order_ref is None or self.target_price is None:
                raise ValueError("ADJUST requires order_ref and target_price")

    # ─────────────────────────────────────────────────────────────────────────
    # Compatibility properties for bracket_service.py interface
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def action_type(self) -> ActionType:
        """Alias for action (bracket_service.py compatibility)."""
        return self.action

    @property
    def order_id(self) -> Optional[str]:
        """Alias for order_ref (bracket_service.py compatibility)."""
        return self.order_ref

    @property
    def price(self) -> Optional[Decimal]:
        """Alias for target_price (bracket_service.py compatibility)."""
        return self.target_price

    def is_placement(self) -> bool:
        """Check if this is a placement action."""
        return self.action in ("PLACE_SL", "PLACE_TP")

    def is_cancel(self) -> bool:
        """Check if this is a cancel action."""
        return self.action == "CANCEL"


@dataclass
class BracketPlan:
    """
    Complete bracket plan for a symbol.

    Result of evaluating an AggregatorInput or BracketState.
    Contains ordered list of actions to execute.

    Compatible with both:
    - contracts.py minimal interface (symbol, actions, suppressed, why)
    - bracket_service.py full interface (side, state, severity, rid, evaluated_ts)
    """
    symbol: str
    actions: List[BracketAction]

    # Position side ("LONG" or "SHORT") - required for bracket_service.py
    side: str = ""

    # Evaluation state reference (Any to avoid circular import with BracketState)
    state: Optional[Any] = None

    # Violation severity level
    severity: SeverityType = "INFO"

    # Suppression flag
    suppressed: bool = False

    # XAI: High-level reason (≤80 chars)
    why: str = ""

    # Tracing
    rid: Optional[str] = None

    # Timestamp of evaluation
    evaluated_ts: float = field(default_factory=lambda: time.time())

    def is_noop(self) -> bool:
        """Check if plan has no actions (state is correct)."""
        return len(self.actions) == 0 or all(a.action == "NOOP" for a in self.actions)

    def has_placements(self) -> bool:
        """Check if plan includes any placement actions."""
        return any(a.is_placement() for a in self.actions)

    def has_cancels(self) -> bool:
        """Check if plan includes any cancel actions."""
        return any(a.is_cancel() for a in self.actions)

    def action_count(self) -> int:
        """Get count of non-NOOP actions."""
        return sum(1 for a in self.actions if a.action != "NOOP")

    @property
    def has_actions(self) -> bool:
        """Plan contains actionable recommendations (bracket_service.py compatibility)."""
        return len(self.actions) > 0

    @property
    def is_critical(self) -> bool:
        """Plan severity is ALERT (critical violation)."""
        return self.severity == "ALERT"


# ═══════════════════════════════════════════════════════════════════════════════
# FACTORY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def noop_plan(symbol: str, why: str = "noop") -> BracketPlan:
    """Create a NOOP plan (no actions needed)."""
    return BracketPlan(symbol=symbol, actions=[], suppressed=False, why=why)


def suppressed_plan(symbol: str, why: str) -> BracketPlan:
    """Create a suppressed plan (skip execution)."""
    return BracketPlan(symbol=symbol, actions=[], suppressed=True, why=why)


def place_sl_action(target_price: Decimal, why: str = "missing_sl") -> BracketAction:
    """Create a PLACE_SL action."""
    return BracketAction(
        action="PLACE_SL",
        leg_type="SL",
        target_price=target_price,
        why=why,
    )


def place_tp_action(target_price: Decimal, why: str = "missing_tp") -> BracketAction:
    """Create a PLACE_TP action."""
    return BracketAction(
        action="PLACE_TP",
        leg_type="TP",
        target_price=target_price,
        why=why,
    )


def cancel_action(order_ref: str, why: str = "cancel_bracket") -> BracketAction:
    """Create a CANCEL action."""
    return BracketAction(
        action="CANCEL",
        order_ref=order_ref,
        why=why,
    )


def adjust_action(
    order_ref: str,
    target_price: Decimal,
    leg_type: BracketLegType,
    why: str = "price_drift",
) -> BracketAction:
    """Create an ADJUST action."""
    return BracketAction(
        action="ADJUST",
        leg_type=leg_type,
        target_price=target_price,
        order_ref=order_ref,
        why=why,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Type aliases
    "Side",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "BracketLegType",
    "ActionType",
    "ActionTypeFull",
    "SeverityType",
    # Valid value sets
    "VALID_SIDES",
    "VALID_ORDER_SIDES",
    "VALID_ORDER_TYPES",
    "VALID_ORDER_STATUSES",
    "VALID_LEG_TYPES",
    "VALID_ACTION_TYPES",
    # Input types
    "OrderSnapshot",
    "PositionSnapshot",
    "AggregatorInput",
    # Config types
    "BracketConfig",
    # Output types
    "BracketAction",
    "BracketPlan",
    # Factory helpers
    "noop_plan",
    "suppressed_plan",
    "place_sl_action",
    "place_tp_action",
    "cancel_action",
    "adjust_action",
]
