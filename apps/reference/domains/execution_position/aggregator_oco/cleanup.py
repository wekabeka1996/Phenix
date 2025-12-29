"""
Cleanup Module for Aggregator OCO — Core Logic
===============================================

Phase 11: Extracted from bracket_service.py to remove production dependency.

This module provides cleanup plan generation for:
- Orphan cleanup: Cancel brackets when position is FLAT
- Reverse cleanup: Cancel old side brackets after position reversal

Uses contract types (AggregatorInput, BracketConfig, BracketPlan) exclusively.
NO imports from bracket_service.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, List, Optional

from .contracts import (
    AggregatorInput,
    BracketAction,
    BracketConfig,
    BracketPlan,
    OrderSnapshot,
    PositionSnapshot,
)
from .view_types import OrderView


# ============================================================================
# Orphan Cleanup (FLAT position with lingering brackets)
# ============================================================================

def plan_orphan_cleanup(
    symbol: str,
    orders: Iterable[OrderView],
    *,
    rid: Optional[str] = None,
) -> BracketPlan:
    """
    Generate plan to cancel all orphan brackets (e.g., when position is FLAT).

    Orphan = reduce_only or close_position order that should not exist
    when there is no position to protect.

    Args:
        symbol: Trading symbol.
        orders: All open orders for the symbol.
        rid: Optional request ID.

    Returns:
        BracketPlan with CANCEL actions for all reduce-only orders.
    """
    actions: List[BracketAction] = []

    for order in orders:
        if order.symbol != symbol:
            continue

        # Check if order is a bracket (reduce_only SL/TP)
        is_bracket = order.reduce_only or order.close_position
        if not is_bracket:
            continue

        # Check order type compatibility
        order_type_upper = order.order_type.upper()
        is_sl = "STOP" in order_type_upper
        is_tp = "TAKE_PROFIT" in order_type_upper or (
            "LIMIT" in order_type_upper and order.reduce_only
        )

        if is_sl or is_tp:
            leg_type = "SL" if is_sl else "TP"
            actions.append(BracketAction(
                action="CANCEL",
                leg_type=leg_type,
                order_ref=order.order_id,
                client_order_id=order.client_order_id,
                reason_code="ORPHAN_CLEANUP",
                why="orphan_cleanup|position_flat",
                rid=rid,
            ))

    return BracketPlan(
        symbol=symbol,
        side="FLAT",  # Virtual side for orphan cleanup
        actions=actions,
        severity="WARN" if actions else "INFO",
        why="orphan_cleanup_plan",
        rid=rid,
    )


def plan_orphan_cleanup_from_input(
    agg_input: AggregatorInput,
    cfg: BracketConfig,
    *,
    rid: Optional[str] = None,
) -> BracketPlan:
    """
    Generate orphan cleanup plan from AggregatorInput.

    If position is FLAT (None or qty=0), returns plan to cancel all brackets.
    If position exists, returns NOOP.

    Args:
        agg_input: Aggregator input with position and orders.
        cfg: Bracket configuration (not used for cleanup logic).
        rid: Optional request ID.

    Returns:
        BracketPlan with CANCEL actions if position is FLAT, else empty plan.
    """
    # Check if position is FLAT
    has_position = (
        agg_input.position is not None and
        agg_input.position.qty > 0
    )

    if has_position:
        # Position exists, no orphan cleanup needed
        return BracketPlan(
            symbol=agg_input.symbol,
            side=agg_input.position.side if agg_input.position else "FLAT",
            actions=[],
            severity="INFO",
            why="orphan_cleanup_skipped|position_exists",
            rid=rid,
        )

    # Position is FLAT — cancel all bracket orders
    actions: List[BracketAction] = []

    for order in agg_input.orders:
        # Check if order is a bracket-like order
        order_type_upper = order.order_type.upper()
        is_sl = "STOP" in order_type_upper and order_type_upper != "STOP_LIMIT"
        is_tp = "TAKE_PROFIT" in order_type_upper

        if is_sl or is_tp:
            leg_type = "SL" if is_sl else "TP"
            actions.append(BracketAction(
                action="CANCEL",
                leg_type=leg_type,
                order_ref=order.order_id,
                client_order_id=order.client_order_id,
                reason_code="ORPHAN_CLEANUP",
                why="orphan_cleanup|position_flat",
                rid=rid,
            ))

    return BracketPlan(
        symbol=agg_input.symbol,
        side="FLAT",
        actions=actions,
        severity="WARN" if actions else "INFO",
        why="orphan_cleanup_plan",
        rid=rid,
    )


# ============================================================================
# Reverse Cleanup (Position flip LONG↔SHORT)
# ============================================================================

def plan_reverse_cleanup(
    symbol: str,
    prev_side: str,
    new_side: str,
    orders: Iterable[OrderView],
    *,
    rid: Optional[str] = None,
) -> BracketPlan:
    """
    Generate plan to cancel brackets from previous side after a reversal.

    When position flips (LONG→SHORT or SHORT→LONG), old side brackets
    must be cancelled before new brackets can be placed.

    Args:
        symbol: Trading symbol.
        prev_side: Previous position side ("LONG" or "SHORT").
        new_side: New position side ("LONG" or "SHORT").
        orders: All open orders for the symbol.
        rid: Optional request ID.

    Returns:
        BracketPlan with CANCEL actions for old side brackets.
    """
    actions: List[BracketAction] = []

    # Determine old exit side
    # LONG position -> SL/TP are SELL
    # SHORT position -> SL/TP are BUY
    old_exit_side = "SELL" if prev_side == "LONG" else "BUY"

    for order in orders:
        if order.symbol != symbol:
            continue

        # Check if order is a bracket (reduce_only)
        is_bracket = order.reduce_only or order.close_position
        if not is_bracket:
            continue

        # Check if order side matches old exit side
        if order.side != old_exit_side:
            continue

        # Check order type compatibility
        order_type_upper = order.order_type.upper()
        is_sl = "STOP" in order_type_upper
        is_tp = "TAKE_PROFIT" in order_type_upper or (
            "LIMIT" in order_type_upper and order.reduce_only
        )

        if is_sl or is_tp:
            leg_type = "SL" if is_sl else "TP"
            actions.append(BracketAction(
                action="CANCEL",
                leg_type=leg_type,
                order_ref=order.order_id,
                client_order_id=order.client_order_id,
                reason_code="REVERSE_CLEANUP",
                why=f"reverse_cleanup|{prev_side}->{new_side}",
                rid=rid,
            ))

    return BracketPlan(
        symbol=symbol,
        side=new_side,
        actions=actions,
        severity="WARN" if actions else "INFO",
        why="reverse_cleanup_plan",
        rid=rid,
    )


def plan_reverse_cleanup_from_input(
    symbol: str,
    prev_side: str,
    new_side: str,
    agg_input: AggregatorInput,
    cfg: BracketConfig,
    *,
    rid: Optional[str] = None,
) -> BracketPlan:
    """
    Generate reverse cleanup plan from AggregatorInput.

    Args:
        symbol: Trading symbol.
        prev_side: Previous position side ("LONG" or "SHORT").
        new_side: New position side ("LONG" or "SHORT").
        agg_input: Aggregator input with orders.
        cfg: Bracket configuration (not used for cleanup logic).
        rid: Optional request ID.

    Returns:
        BracketPlan with CANCEL actions for old side brackets.
    """
    # Same logic but using OrderSnapshot from agg_input
    actions: List[BracketAction] = []

    # Determine old exit side
    old_exit_side = "SELL" if prev_side == "LONG" else "BUY"

    for order in agg_input.orders:
        # Check if order side matches old exit side
        if order.side != old_exit_side:
            continue

        # Check order type compatibility
        order_type_upper = order.order_type.upper()
        is_sl = "STOP" in order_type_upper and order_type_upper != "STOP_LIMIT"
        is_tp = "TAKE_PROFIT" in order_type_upper

        if is_sl or is_tp:
            leg_type = "SL" if is_sl else "TP"
            actions.append(BracketAction(
                action="CANCEL",
                leg_type=leg_type,
                order_ref=order.order_id,
                client_order_id=order.client_order_id,
                reason_code="REVERSE_CLEANUP",
                why=f"reverse_cleanup|{prev_side}->{new_side}",
                rid=rid,
            ))

    return BracketPlan(
        symbol=symbol,
        side=new_side,
        actions=actions,
        severity="WARN" if actions else "INFO",
        why="reverse_cleanup_plan",
        rid=rid,
    )


def plan_position_size_cleanup(
    symbol: str,
    orders: Iterable[OrderView],
    position_qty: Decimal,
    entry_price: Decimal,
    cfg: BracketConfig,
    *,
    rid: Optional[str] = None,
) -> BracketPlan:
    """
    Generate plan to cancel brackets that become inappropriate due to position size changes.

    This handles cases where position size changes significantly, making current TP/SL
    levels no longer suitable for risk management.

    Args:
        symbol: Trading symbol.
        orders: All open orders for the symbol.
        position_qty: Current position quantity.
        entry_price: Current entry price.
        cfg: Bracket configuration for calculating desired levels.
        rid: Optional request ID.

    Returns:
        BracketPlan with CANCEL actions for inappropriate brackets.
    """
    from .core_math import compute_desired_levels

    actions: List[BracketAction] = []

    # Skip if position is too small
    if abs(position_qty) < Decimal('0.0001'):
        return BracketPlan(
            symbol=symbol,
            side='FLAT',
            actions=[],
            severity='INFO',
            why='position_size_cleanup_skip|too_small',
            rid=rid,
        )

    # Calculate desired SL/TP levels for current position
    side = 'LONG' if position_qty > 0 else 'SHORT'
    desired = compute_desired_levels(
        side=side,
        entry_price=entry_price,
        sl_pct=cfg.sl_pct,
        tp_rr=cfg.tp_rr,
    )

    desired_sl = desired.sl_price
    desired_tp = desired.tp_price

    for order in orders:
        if order.symbol != symbol:
            continue

        # Check if order is a bracket (reduce_only SL/TP)
        is_bracket = order.reduce_only or order.close_position
        if not is_bracket:
            continue

        # Check order type compatibility
        order_type_upper = order.order_type.upper()
        is_sl = 'STOP' in order_type_upper
        is_tp = 'TAKE_PROFIT' in order_type_upper or (
            'LIMIT' in order_type_upper and order.reduce_only
        )

        if is_sl and order.stop_price:
            # Check if SL level is significantly different from desired
            current_sl = Decimal(str(order.stop_price))
            sl_diff_pct = abs(current_sl - desired_sl) / desired_sl
            if sl_diff_pct > Decimal('0.05'):  # 5% tolerance
                actions.append(BracketAction(
                    action='CANCEL',
                    leg_type='SL',
                    order_ref=order.order_id,
                    client_order_id=order.client_order_id,
                    reason_code='POSITION_SIZE_CLEANUP',
                    why=f'position_size_cleanup|sl_{current_sl}->{desired_sl}',
                    rid=rid,
                ))

        elif is_tp and order.stop_price:
            # Check if TP level is significantly different from desired
            current_tp = Decimal(str(order.stop_price))
            tp_diff_pct = abs(current_tp - desired_tp) / desired_tp
            if tp_diff_pct > Decimal('0.05'):  # 5% tolerance
                actions.append(BracketAction(
                    action='CANCEL',
                    leg_type='TP',
                    order_ref=order.order_id,
                    client_order_id=order.client_order_id,
                    reason_code='POSITION_SIZE_CLEANUP',
                    why=f'position_size_cleanup|tp_{current_tp}->{desired_tp}',
                    rid=rid,
                ))

    return BracketPlan(
        symbol=symbol,
        side=side,
        actions=actions,
        severity='WARN' if actions else 'INFO',
        why='position_size_cleanup_plan',
        rid=rid,
    )
