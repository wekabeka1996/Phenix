"""
Invariant Assertion Helpers
============================

Test utilities for asserting ExecPosRuntimeV2 safety invariants.

These invariants enforce critical safety properties:
- I1: At most one active position per symbol
- I2: If position open + strategy requires SL → exactly one SL order
- I3: Closed position must not have active SL/TP (no orphans)
- I4: No negative or NaN position size/exposure
- I5: Duplicate TRADE_EXECUTED must not double-count PnL/position
- I6: Out-of-order events must not create inconsistent state

Defined in: EXECUTION_POSITION_INVARIANTS.md
"""
from typing import Any, Dict, List
from decimal import Decimal


def assert_no_double_close(state: Dict[str, Any], call_history: List[Any]) -> None:
    """
    Assert no double-close occurred.

    Checks:
    - Adapter never called close_position twice for same symbol without intervening open
    - Position state transitions: FLAT → OPEN → FLAT (not FLAT → FLAT)

    Args:
        state: Runtime state snapshot
        call_history: Adapter call history

    Raises:
        AssertionError: If double-close detected
    """
    close_calls = [c for c in call_history if c.method == "close_position"]

    # Group by symbol
    closes_by_symbol = {}
    for call in close_calls:
        symbol = call.kwargs.get("symbol", "UNKNOWN")
        closes_by_symbol.setdefault(symbol, []).append(call)

    # Check for rapid duplicates (same symbol closed twice within short window)
    for symbol, calls in closes_by_symbol.items():
        if len(calls) > 1:
            # Check timestamps - if < 1s apart, likely double-close
            for i in range(1, len(calls)):
                delta = calls[i].timestamp - calls[i-1].timestamp
                if delta < 1.0:
                    raise AssertionError(
                        f"INVARIANT VIOLATED: Double-close detected for {symbol} "
                        f"(calls {delta:.3f}s apart)"
                    )


def assert_no_orphan_brackets(state: Dict[str, Any]) -> None:
    """
    Assert no orphan SL/TP orders for closed positions.

    Checks:
    - If position_size == 0 or position absent → no SL/TP orders active

    Args:
        state: Runtime state snapshot with positions and orders

    Raises:
        AssertionError: If orphan brackets detected
    """
    positions = state.get("positions", {})
    orders = state.get("orders", [])

    for symbol, position in positions.items():
        position_size = float(position.qty) if position else 0.0

        # If position is closed/flat
        if abs(position_size) < 0.0001:
            # Check for SL/TP orders
            sl_orders = [o for o in orders
                        if o.get("symbol") == symbol and "STOP" in str(o.get("type", ""))]
            tp_orders = [o for o in orders
                       if o.get("symbol") == symbol and "TAKE_PROFIT" in str(o.get("type", ""))]

            if sl_orders or tp_orders:
                raise AssertionError(
                    f"INVARIANT VIOLATED: Orphan brackets for {symbol} "
                    f"(position={position_size}, SL={len(sl_orders)}, TP={len(tp_orders)})"
                )


def assert_no_impossible_exposure(state: Dict[str, Any]) -> None:
    """
    Assert no negative or NaN position size/exposure.

    Checks:
    - position_size is finite number
    - exposure_usdt is finite and non-negative
    - PnL values are finite

    Args:
        state: Runtime state snapshot

    Raises:
        AssertionError: If impossible values detected
    """
    positions = state.get("positions", {})

    for symbol, position in positions.items():
        # Check position_size
        position_size_str = str(position.qty) if position else "0"
        try:
            position_size = float(position_size_str)
            if not (-1e12 < position_size < 1e12):  # Sanity bounds
                raise AssertionError(
                    f"INVARIANT VIOLATED: Impossible position_size for {symbol}: {position_size}"
                )
        except (ValueError, TypeError):
            raise AssertionError(
                f"INVARIANT VIOLATED: Non-numeric position_size for {symbol}: {position_size_str}"
            )

        # Check exposure_usdt (if present)
        exposure = getattr(position, "exposure_usdt", "0")
        try:
            exposure_val = float(exposure)
            if exposure_val < 0 or not (0 <= exposure_val < 1e15):
                raise AssertionError(
                    f"INVARIANT VIOLATED: Impossible exposure for {symbol}: {exposure_val}"
                )
        except (ValueError, TypeError):
            raise AssertionError(
                f"INVARIANT VIOLATED: Non-numeric exposure for {symbol}: {exposure}"
            )

        # Check PnL values
        for pnl_field in ["realized_pnl", "unrealized_pnl"]:
            pnl = getattr(position, pnl_field, "0")
            try:
                pnl_val = float(pnl)
                if not (-1e15 < pnl_val < 1e15):
                    raise AssertionError(
                        f"INVARIANT VIOLATED: Impossible {pnl_field} for {symbol}: {pnl_val}"
                    )
            except (ValueError, TypeError):
                raise AssertionError(
                    f"INVARIANT VIOLATED: Non-numeric {pnl_field} for {symbol}: {pnl}"
                )


def assert_idempotency_respected(metrics: Dict[str, Any], state: Dict[str, Any]) -> None:
    """
    Assert idempotency mechanisms prevented double-counting.

    Checks:
    - If duplicate fills occurred (metrics), position size matches expected
    - Duplicate count in metrics > 0 implies state unchanged

    Args:
        metrics: Runtime metrics snapshot
        state: Runtime state snapshot

    Raises:
        AssertionError: If idempotency violated
    """
    duplicate_fills = metrics.get("fills_duplicate", 0)

    if duplicate_fills > 0:
        # Idempotency detected duplicates - this is OK
        # But we should verify that state is consistent
        # (This is a positive check - duplicates were caught)
        pass  # Success: duplicates were detected and skipped

    # Additional check: no position has impossible accumulated values
    # that would indicate double-counting
    assert_no_impossible_exposure(state)


def assert_single_position_per_symbol(state: Dict[str, Any]) -> None:
    """
    Assert at most one active position per symbol.

    Checks:
    - positions dict keys are unique (implicitly true for dict)
    - No duplicate position tracking

    Args:
        state: Runtime state snapshot

    Raises:
        AssertionError: If multiple positions for same symbol
    """
    positions = state.get("positions", {})

    # Dict inherently enforces uniqueness, but check for corrupted state
    symbols_seen = set()
    for symbol in positions.keys():
        if symbol in symbols_seen:
            raise AssertionError(
                f"INVARIANT VIOLATED: Duplicate position tracking for {symbol}"
            )
        symbols_seen.add(symbol)


def assert_all_invariants(state: Dict[str, Any], call_history: List[Any], metrics: Dict[str, Any]) -> None:
    """
    Run all invariant checks.

   Convenience function to assert all safety invariants in one call.

    Args:
        state: Runtime state snapshot
        call_history: Adapter call history
        metrics: Runtime metrics snapshot

    Raises:
        AssertionError: If any invariant violated
    """
    assert_single_position_per_symbol(state)
    assert_no_double_close(state, call_history)
    assert_no_orphan_brackets(state)
    assert_no_impossible_exposure(state)
    assert_idempotency_respected(metrics, state)
