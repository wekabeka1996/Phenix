"""Aggregator OCO package — contract types and engine for bracket evaluation."""

from .contracts import (
    # Type aliases
    Side,
    OrderSide,
    OrderType,
    OrderStatus,
    BracketLegType,
    ActionType,
    ActionTypeFull,
    SeverityType,
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

# Phase 11: View types for runtime/adapters (no bracket_service dependency)
from .view_types import (
    PositionView,
    OrderView,
    BracketRulesConfig,
    parse_cycle_id_from_client_order_id,
    make_bracket_client_order_id,
    build_position_id,
)

# Phase 11: Cleanup functions (no bracket_service dependency)
from .cleanup import (
    plan_orphan_cleanup,
    plan_orphan_cleanup_from_input,
    plan_reverse_cleanup,
    plan_reverse_cleanup_from_input,
)

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
    # Phase 11: View types
    "PositionView",
    "OrderView",
    "BracketRulesConfig",
    "parse_cycle_id_from_client_order_id",
    "make_bracket_client_order_id",
    "build_position_id",
    # Phase 11: Cleanup
    "plan_orphan_cleanup",
    "plan_orphan_cleanup_from_input",
    "plan_reverse_cleanup",
    "plan_reverse_cleanup_from_input",
    # Engine (Phase 3) - import from .engine directly
    "compute_bracket_plan",
    "compute_bracket_plan_from_raw",
    # Phase 4 runtime adapter
    "compute_bracket_plan_from_views",
]


def __getattr__(name: str):
    """Lazy import for engine functions to avoid circular import."""
    if name in ("compute_bracket_plan", "compute_bracket_plan_from_raw", "compute_bracket_plan_from_views"):
        from . import engine
        return getattr(engine, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
