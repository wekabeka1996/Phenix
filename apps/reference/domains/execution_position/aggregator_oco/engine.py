"""
Aggregator OCO — Engine Entry Point (Phase 10)

Pure contract-level entrypoint for Aggregated OCO bracket computation.

Phase 10: bracket_service fully retired from production.
          - compute_bracket_plan() → _compute_bracket_plan_core() → core_math
          - compute_bracket_plan_from_views() → converts views → core planner (NO bracket_service)
          - Legacy adapters retained ONLY for shadow tests
          - bracket_service imports are DEPRECATED / TEST-ONLY

RID: EXEC-AGGREGATOR-OCO-PHASE10-BRACKET-SERVICE-TEST-ONLY

Usage:
    from aggregator_oco.engine import compute_bracket_plan
    from aggregator_oco.contracts import AggregatorInput, BracketConfig

    plan = compute_bracket_plan(agg_input, cfg)
"""

from __future__ import annotations
import time
from decimal import Decimal
from typing import List, Optional

from apps.reference.domains.execution_position.aggregator_oco.contracts import (
    AggregatorInput,
    BracketAction,
    BracketConfig,
    BracketPlan,
    OrderSnapshot,
    PositionSnapshot,
    SeverityType,
    cancel_action,
    noop_plan,
    place_sl_action,
    place_tp_action,
)

# Phase 8: Import core_math for SL/TP calculation (single source of truth)
from apps.reference.domains.execution_position.aggregator_oco.core_math import (
    compute_desired_levels as _core_compute_desired_levels,
    prices_match_with_tolerance,
)

# Phase 11: Import view types from contract layer (NO bracket_service dependency)
from apps.reference.domains.execution_position.aggregator_oco.view_types import (
    OrderView,
    PositionView,
)

# DEPRECATED (Phase 11): Legacy types retained ONLY for _build_bracket_state in shadow tests
# These are NOT used in production path - only for test compatibility
try:
    from apps.reference.domains.execution_position.shadow_execpos.bracket_service import (
        BracketLeg,
        BracketRulesConfig,
        BracketSet,
        BracketState,
    )
except ImportError:
    # If bracket_service is removed, these types won't be available
    # This is expected in future phases
    BracketLeg = None  # type: ignore
    BracketRulesConfig = None  # type: ignore
    BracketSet = None  # type: ignore
    BracketState = None  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════════
# ADAPTER FUNCTIONS (Legacy → Contract) - Phase 10
# ═══════════════════════════════════════════════════════════════════════════════

def _view_to_position_snapshot(view: PositionView) -> PositionSnapshot:
    """
    Adapt PositionView (legacy) → PositionSnapshot (contract).

    Phase 9: Enables compute_bracket_plan_from_views to use core planner.
    """
    return PositionSnapshot(
        symbol=view.symbol,
        side=view.side,  # type: ignore[arg-type]
        qty=view.qty,
        entry_price=view.avg_entry_price,
        unrealized_pnl=view.unrealized_pnl,
    )


def _view_to_order_snapshot(view: OrderView) -> OrderSnapshot:
    """
    Adapt OrderView (legacy) → OrderSnapshot (contract).

    Phase 9: Enables compute_bracket_plan_from_views to use core planner.
    """
    # Map legacy order_type to contract OrderType
    order_type = view.order_type
    if order_type not in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "LIMIT", "MARKET"):
        # Default unknown types to STOP_MARKET (safe fallback)
        order_type = "STOP_MARKET"

    # Map legacy status to contract OrderStatus
    status_map = {
        "NEW": "NEW",
        "PARTIALLY_FILLED": "PARTIALLY_FILLED",
        "FILLED": "FILLED",
        "CANCELED": "CANCELED",
    }
    status = status_map.get(view.status, "NEW")

    return OrderSnapshot(
        symbol=view.symbol,
        order_id=view.order_id,
        client_order_id=view.client_order_id,
        side=view.side,  # type: ignore[arg-type]
        type=order_type,  # type: ignore[arg-type]
        stop_price=view.stop_price,
        status=status,  # type: ignore[arg-type]
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ADAPTER FUNCTIONS (Contract → Legacy) - For shadow tests
# ═══════════════════════════════════════════════════════════════════════════════

def _position_snapshot_to_view(pos: PositionSnapshot) -> PositionView:
    """
    Adapt PositionSnapshot (contract) → PositionView (legacy).

    Maps contract fields to legacy structure expected by bracket_service.
    """
    return PositionView(
        symbol=pos.symbol,
        side=pos.side,
        qty=pos.qty,
        avg_entry_price=pos.entry_price,
        unrealized_pnl=pos.unrealized_pnl,
        cycle_id=0,  # Phase 3: no cycle tracking in contract yet
    )


def _order_snapshot_to_view(order: OrderSnapshot) -> OrderView:
    """
    Adapt OrderSnapshot (contract) → OrderView (legacy).

    Maps contract fields to legacy structure expected by bracket_service.
    """
    return OrderView(
        order_id=order.order_id or "",
        client_order_id=order.client_order_id or "",
        symbol=order.symbol,
        side=order.side,
        order_type=order.type,
        # Bracket orders use closePosition=true, qty is nominal
        qty=Decimal("1"),
        stop_price=order.stop_price,
        reduce_only=True,  # Bracket orders are always reduce_only
        status=order.status if order.status in (
            "NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED") else "NEW",
    )


def _classify_order_leg(order: OrderView, position_side: str) -> Optional[BracketLeg]:
    """
    Classify an OrderView as BracketLeg (SL/TP).

    Args:
        order: Legacy OrderView to classify.
        position_side: "LONG" or "SHORT" to determine leg type.

    Returns:
        BracketLeg if order is SL/TP, None otherwise.
    """
    # SL: STOP_MARKET order, opposite side to position
    # TP: TAKE_PROFIT_MARKET order, opposite side to position
    expected_order_side = "SELL" if position_side == "LONG" else "BUY"

    if order.side != expected_order_side:
        return None  # Not a bracket order for this position

    if order.order_type == "STOP_MARKET":
        return BracketLeg(
            leg_type="SL",
            order=order,
            source="exchange",
            confidence=1.0,
        )
    elif order.order_type == "TAKE_PROFIT_MARKET":
        return BracketLeg(
            leg_type="TP",
            order=order,
            source="exchange",
            confidence=1.0,
        )

    return None


def _build_bracket_set(
    symbol: str,
    side: str,
    position_view: Optional[PositionView],
    order_views: List[OrderView],
) -> Optional[BracketSet]:
    """
    Build BracketSet from position and orders.

    Args:
        symbol: Trading symbol.
        side: Position side ("LONG" or "SHORT").
        position_view: Position data (None if flat).
        order_views: List of orders to classify.

    Returns:
        BracketSet if any legs found, None otherwise.
    """
    legs: List[BracketLeg] = []

    for order in order_views:
        if order.symbol != symbol:
            continue
        leg = _classify_order_leg(order, side)
        if leg:
            legs.append(leg)

    if not legs and not position_view:
        return None

    now = time.time()
    return BracketSet(
        symbol=symbol,
        side=side,
        position_qty=position_view.qty if position_view else Decimal(0),
        avg_entry_price=position_view.avg_entry_price if position_view else Decimal(
            0),
        legs=legs,
        created_ts=now,
        updated_ts=now,
        meta=None,
    )


def _build_bracket_state(
    agg_input: AggregatorInput,
) -> BracketState:
    """
    Adapt AggregatorInput (contract) → BracketState (legacy).

    Central adaptation function that converts contract input to legacy state.

    Args:
        agg_input: Contract input snapshot.

    Returns:
        BracketState ready for bracket_service.evaluate().
    """
    # Convert position if exists
    position_view: Optional[PositionView] = None
    side = "LONG"  # Default, will be overridden

    if agg_input.position:
        position_view = _position_snapshot_to_view(agg_input.position)
        side = agg_input.position.side

    # Convert orders
    order_views: List[OrderView] = [
        _order_snapshot_to_view(o) for o in agg_input.orders
    ]

    # Build bracket set
    bracket_set = _build_bracket_set(
        symbol=agg_input.symbol,
        side=side,
        position_view=position_view,
        order_views=order_views,
    )

    return BracketState(
        symbol=agg_input.symbol,
        side=side,
        position_view=position_view,
        bracket_set=bracket_set,
        snapshot_ts=agg_input.ts,
    )


def _bracket_config_to_rules_config(cfg: BracketConfig) -> BracketRulesConfig:
    """
    Adapt BracketConfig (contract) → BracketRulesConfig (legacy).

    Maps contract configuration to legacy config structure.

    Args:
        cfg: Contract configuration.

    Returns:
        BracketRulesConfig ready for bracket_service.evaluate().
    """
    return BracketRulesConfig(
        enabled=True,
        sl_pct=float(cfg.sl_pct),
        tp_rr=float(cfg.tp_rr),
        # Default values for fields not in contract config
        allow_unprotected_position=False,
        recalc_on_partial_close=True,
        recalc_on_scale_in=True,
        ttl_protect_new_bracket_ms=5000,
        max_tp_legs=1,
        max_sl_legs=1,
        recreate_missing_brackets=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 8: CORE PLANNER (no bracket_service.evaluate dependency)
# ═══════════════════════════════════════════════════════════════════════════════

def _compute_bracket_plan_core(
    agg_input: AggregatorInput,
    cfg: BracketConfig,
    *,
    rid: Optional[str] = None,
) -> BracketPlan:
    """
    Pure core planner for bracket computation (Phase 8).

    Computes BracketPlan using:
    - AggregatorInput (position, orders)
    - BracketConfig (sl_pct, tp_rr)
    - core_math.compute_desired_levels() for SL/TP prices

    NO calls to bracket_service.evaluate().

    Implements behavior documented in AGGREGATOR_OCO_BEHAVIOR.md:
    - INV-1: Max 1 SL, 1 TP per symbol/side
    - INV-2: Flat position → no PLACE actions (only CANCEL orphans)
    - INV-4: LONG → SL < entry < TP
    - INV-5: SHORT → TP < entry < SL

    Args:
        agg_input: Complete input snapshot.
        cfg: Bracket configuration.
        rid: Optional request ID for tracing.

    Returns:
        BracketPlan with recommended actions.
    """
    symbol = agg_input.symbol
    position = agg_input.position
    now = time.time()

    actions: List[BracketAction] = []
    severity: SeverityType = "INFO"
    why_parts: List[str] = []

    # ─────────────────────────────────────────────────────────────────────────
    # CASE 1: FLAT POSITION (INV-2)
    # ─────────────────────────────────────────────────────────────────────────
    if agg_input.is_flat():
        # Check for orphan brackets to cancel
        active_sl = agg_input.get_active_sl()
        active_tp = agg_input.get_active_tp()

        if active_sl:
            actions.append(cancel_action(
                order_ref=active_sl.order_id or "",
                why="orphan_sl|pos_flat",
            ))
            why_parts.append("cancel_orphan_sl")
            severity = "WARN"

        if active_tp:
            actions.append(cancel_action(
                order_ref=active_tp.order_id or "",
                why="orphan_tp|pos_flat",
            ))
            why_parts.append("cancel_orphan_tp")
            severity = "WARN"

        if not actions:
            why_parts.append("flat_no_brackets")

        return BracketPlan(
            symbol=symbol,
            side="",
            actions=actions,
            severity=severity,
            why="|".join(why_parts)[:80] if why_parts else "flat_ok",
            rid=rid,
            evaluated_ts=now,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # CASE 2: POSITION EXISTS - Compute desired levels
    # ─────────────────────────────────────────────────────────────────────────
    assert position is not None  # Covered by is_flat() check above

    side = position.side
    entry_price = position.entry_price

    # Compute desired SL/TP prices via core_math (single source of truth)
    desired = _core_compute_desired_levels(
        side=side,
        entry_price=entry_price,
        sl_pct=cfg.sl_pct,
        tp_rr=cfg.tp_rr,
    )

    desired_sl = desired.sl_price
    desired_tp = desired.tp_price

    # ─────────────────────────────────────────────────────────────────────────
    # Check existing brackets
    # ─────────────────────────────────────────────────────────────────────────
    active_sl = agg_input.get_active_sl()
    active_tp = agg_input.get_active_tp()

    # Count excess brackets (INV-1: max 1 SL, 1 TP)
    sl_orders = [o for o in agg_input.orders if o.is_stop_loss()
                 and o.is_active()]
    tp_orders = [o for o in agg_input.orders if o.is_take_profit()
                 and o.is_active()]

    # Cancel excess SL orders (keep first, cancel rest)
    if len(sl_orders) > 1:
        for excess_sl in sl_orders[1:]:
            actions.append(cancel_action(
                order_ref=excess_sl.order_id or "",
                why="excess_sl|max_1",
            ))
            why_parts.append("cancel_excess_sl")
            severity = "WARN"

    # Cancel excess TP orders (keep first, cancel rest)
    if len(tp_orders) > 1:
        for excess_tp in tp_orders[1:]:
            actions.append(cancel_action(
                order_ref=excess_tp.order_id or "",
                why="excess_tp|max_1",
            ))
            why_parts.append("cancel_excess_tp")
            severity = "WARN"

    # ─────────────────────────────────────────────────────────────────────────
    # Place missing SL (Scenario A1, A2, B3)
    # ─────────────────────────────────────────────────────────────────────────
    if not active_sl:
        actions.append(place_sl_action(
            target_price=desired_sl,
            why=f"missing_sl|{side}|@{desired_sl}",
        ))
        why_parts.append("place_sl")
        severity = "ALERT"  # Missing bracket is critical

    # ─────────────────────────────────────────────────────────────────────────
    # Place missing TP (Scenario A1, A2, B2)
    # ─────────────────────────────────────────────────────────────────────────
    if not active_tp:
        actions.append(place_tp_action(
            target_price=desired_tp,
            why=f"missing_tp|{side}|@{desired_tp}",
        ))
        why_parts.append("place_tp")
        severity = "ALERT"  # Missing bracket is critical

    # ─────────────────────────────────────────────────────────────────────────
    # CASE 3: Check for stale levels (after placing missing brackets)
    # ─────────────────────────────────────────────────────────────────────────
    # NOTE: This runs regardless of whether both brackets exist
    # We check stale levels for any existing brackets

    stale_actions_needed = False
    stale_parts = []

    # Check SL staleness
    if active_sl:
        current_sl_price = active_sl.stop_price
        sl_stale = current_sl_price is None or not prices_match_with_tolerance(
            current_sl_price, desired_sl
        )
        if sl_stale:
            stale_actions_needed = True
            stale_parts.append(f"sl_{current_sl_price}→{desired_sl}")
            # Cancel stale SL and place new one
            actions.append(cancel_action(
                order_ref=active_sl.order_id or "",
                why="stale_sl|recalc",
            ))
            actions.append(place_sl_action(
                target_price=desired_sl,
                why=f"recalc_sl|{side}|@{desired_sl}",
            ))

    # Check TP staleness
    if active_tp:
        current_tp_price = active_tp.stop_price
        tp_stale = current_tp_price is None or not prices_match_with_tolerance(
            current_tp_price, desired_tp
        )
        if tp_stale:
            stale_actions_needed = True
            stale_parts.append(f"tp_{current_tp_price}→{desired_tp}")
            # Cancel stale TP and place new one
            actions.append(cancel_action(
                order_ref=active_tp.order_id or "",
                why="stale_tp|recalc",
            ))
            actions.append(place_tp_action(
                target_price=desired_tp,
                why=f"recalc_tp|{side}|@{desired_tp}",
            ))

    if stale_actions_needed:
        severity = "WARN"
        why_parts.append(f"stale_levels|{'_'.join(stale_parts)}")
    elif active_sl and active_tp and not stale_actions_needed:
        # Perfect state - both brackets exist and are fresh
        why_parts.append("brackets_ok")
        severity = "INFO"

    return BracketPlan(
        symbol=symbol,
        side=side,
        actions=actions,
        severity=severity,
        why="|".join(why_parts)[:80] if why_parts else "ok",
        rid=rid,
        evaluated_ts=now,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENGINE ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════════

def compute_bracket_plan(
    agg_input: AggregatorInput,
    cfg: BracketConfig,
    *,
    rid: Optional[str] = None,
) -> BracketPlan:
    """
    Pure contract-level entrypoint for Aggregated OCO bracket computation.

    Phase 8 Implementation:
    - Uses core planner (_compute_bracket_plan_core) directly.
    - NO calls to bracket_service.evaluate().
    - Zero-diff behavior verified by test_engine_scenarios.py.

    Args:
        agg_input: Complete input snapshot (symbol, position, orders, mark_price).
        cfg: Bracket calculation configuration (sl_pct, tp_rr, etc.).
        rid: Optional request ID for tracing.

    Returns:
        BracketPlan with recommended actions, severity, and XAI metadata.

    Example:
        >>> from aggregator_oco.contracts import AggregatorInput, BracketConfig, PositionSnapshot
        >>> pos = PositionSnapshot(symbol="BTCUSDT", side="LONG", qty=Decimal("0.1"), entry_price=Decimal("50000"))
        >>> agg_input = AggregatorInput(symbol="BTCUSDT", position=pos, orders=[])
        >>> cfg = BracketConfig(sl_pct=Decimal("0.02"), tp_rr=Decimal("2.0"))
        >>> plan = compute_bracket_plan(agg_input, cfg)
        >>> plan.symbol
        'BTCUSDT'
    """
    # Phase 8: Use core planner directly (no bracket_service.evaluate)
    return _compute_bracket_plan_core(agg_input, cfg, rid=rid)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def compute_bracket_plan_from_views(
    pos_view: Optional[PositionView],
    order_views: List[OrderView],
    cfg: BracketRulesConfig,
    symbol: str,
    side: str = "LONG",
    rid: Optional[str] = None,
) -> BracketPlan:
    """
    Compute bracket plan from legacy views (Phase 10: core planner only).

    This function enables runtime.py to call through the contract engine
    while still using its existing PositionView/OrderView types.

    Phase 10: ALWAYS uses core planner (_compute_bracket_plan_core).
              bracket_service parameter removed — no legacy path.

    Args:
        pos_view: Legacy PositionView (from runtime._get_order_views).
        order_views: List of legacy OrderView objects.
        cfg: Legacy BracketRulesConfig.
        symbol: Trading symbol.
        side: Position side ("LONG" or "SHORT").
        rid: Optional request ID for tracing.

    Returns:
        BracketPlan with recommended actions.
    """
    # Phase 10: Core planner path (production)
    # Step 1: Convert legacy views → contract snapshots
    position: Optional[PositionSnapshot] = None
    if pos_view is not None and pos_view.qty > 0:
        position = _view_to_position_snapshot(pos_view)

    orders: List[OrderSnapshot] = [
        _view_to_order_snapshot(ov) for ov in order_views
        if ov.symbol == symbol and  # Filter to relevant symbol
        # Filter to current position cycle
        (pos_view is None or ov.cycle_id == pos_view.cycle_id)
    ]

    # Step 2: Build AggregatorInput
    agg_input = AggregatorInput(
        symbol=symbol,
        position=position,
        orders=orders,
        mark_price=None,  # Not available from legacy views
    )

    # Step 3: Build BracketConfig from legacy config
    bracket_cfg = BracketConfig(
        sl_pct=Decimal(str(cfg.sl_pct)),
        tp_rr=Decimal(str(cfg.tp_rr)),
    )

    # Step 4: Delegate to core planner
    return _compute_bracket_plan_core(agg_input, bracket_cfg, rid=rid)


def compute_bracket_plan_from_raw(
    symbol: str,
    position_side: Optional[str],
    position_qty: Decimal,
    entry_price: Decimal,
    orders: List[dict],
    sl_pct: Decimal = Decimal("0.02"),
    tp_rr: Decimal = Decimal("2.0"),
    mark_price: Optional[Decimal] = None,
    rid: Optional[str] = None,
) -> BracketPlan:
    """
    Convenience wrapper for compute_bracket_plan with raw Python types.

    Useful for quick testing or integration without constructing full contract objects.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT").
        position_side: "LONG", "SHORT", or None for flat.
        position_qty: Position quantity (Decimal).
        entry_price: Average entry price (Decimal).
        orders: List of order dicts with keys: order_id, side, type, stop_price, status.
        sl_pct: Stop loss percentage (default 2%).
        tp_rr: Risk:reward ratio (default 2:1).
        mark_price: Current mark price (optional).
        rid: Request ID for tracing.

    Returns:
        BracketPlan with recommended actions.
    """
    from apps.reference.domains.execution_position.aggregator_oco.contracts import (
        OrderSnapshot,
        PositionSnapshot,
    )

    # Build position snapshot
    position: Optional[PositionSnapshot] = None
    if position_side and position_qty > 0:
        position = PositionSnapshot(
            symbol=symbol,
            side=position_side,  # type: ignore
            qty=position_qty,
            entry_price=entry_price,
        )

    # Build order snapshots
    order_snapshots: List[OrderSnapshot] = []
    for o in orders:
        order_snapshots.append(OrderSnapshot(
            symbol=symbol,
            order_id=o.get("order_id"),
            client_order_id=o.get("client_order_id"),
            side=o.get("side", "SELL"),  # type: ignore
            type=o.get("type", "STOP_MARKET"),  # type: ignore
            stop_price=Decimal(str(o["stop_price"])) if o.get(
                "stop_price") else None,
            status=o.get("status", "NEW"),  # type: ignore
        ))

    # Build input and config
    agg_input = AggregatorInput(
        symbol=symbol,
        position=position,
        orders=order_snapshots,
        mark_price=mark_price,
    )
    cfg = BracketConfig(sl_pct=sl_pct, tp_rr=tp_rr)

    return compute_bracket_plan(agg_input, cfg, rid=rid)
