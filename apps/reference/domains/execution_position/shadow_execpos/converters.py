"""
Data Converters for Execution Position Domain.
Shared logic for normalizing raw dictionary data into typed Views.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from .bracket_service import PositionView, OrderView, parse_cycle_id_from_client_order_id


def normalize_positions(raw_positions: List[Dict[str, Any]]) -> List[PositionView]:
    """
    Convert raw position dictionaries to PositionView objects.
    Filters out positions with negligible quantity (< 0.0001).
    """
    views: List[PositionView] = []
    for raw in raw_positions:
        if raw is None:
            continue
        symbol = str(raw.get("symbol", "")).upper()
        if not symbol:
            continue

        qty = None
        # Try various keys for quantity
        for key in ["positionAmt", "position_amt", "qty", "quantity", "position_size"]:
            if key in raw:
                try:
                    qty = Decimal(str(raw[key]))
                    break
                except Exception:
                    qty = None

        if qty is None:
            continue

        # Filter dust
        if abs(qty) < Decimal("0.0001"):
            continue

        side = "LONG" if qty > 0 else "SHORT"

        # Try various keys for entry price
        entry = raw.get("entryPrice") or raw.get("avg_price") or raw.get(
            "avg_entry_price") or raw.get("entry_price") or 0

        try:
            entry_price = Decimal(str(entry)) if entry else Decimal("0")
            # PositionView requires entry_price > 0 when qty > 0
            if entry_price <= 0:
                # Fallback to avoid validation error
                entry_price = Decimal("1")

            views.append(
                PositionView(
                    symbol=symbol,
                    side=side,
                    qty=abs(qty),
                    avg_entry_price=entry_price,
                )
            )
        except Exception:
            continue

    return views


def normalize_orders(raw_orders: List[Dict[str, Any]]) -> List[OrderView]:
    """
    Convert raw order dictionaries to OrderView objects.
    """
    views: List[OrderView] = []
    for raw in raw_orders:
        try:
            order_id = raw.get("orderId") or raw.get(
                "order_id") or raw.get("clientOrderId")
            if not order_id:
                continue

            symbol = str(raw.get("symbol", "")).upper()
            if not symbol:
                continue

            side = str(raw.get("side", "")).upper() or "BUY"
            order_type = raw.get("type") or raw.get(
                "order_type") or "LIMIT"

            qty = Decimal(str(raw.get("quantity") or raw.get(
                "origQty") or raw.get("qty") or 0))

            price = raw.get("price")
            stop_price = raw.get("stopPrice") or raw.get("stop_price")

            reduce_only = bool(raw.get("reduce_only")
                               or raw.get("reduceOnly", False))
            close_position = bool(
                raw.get("close_position") or raw.get("closePosition", False))

            status = str(raw.get("status") or "NEW")

            created_ts = float(raw.get("created_ts")
                               or raw.get("time") or 0)
            update_ts = float(raw.get("update_ts") or raw.get(
                "updateTime") or created_ts)

            client_order_id = str(raw.get("clientOrderId") or raw.get(
                        "client_order_id") or order_id)

            # Parse cycle_id from clientOrderId
            cycle_id = parse_cycle_id_from_client_order_id(client_order_id)

            views.append(
                OrderView(
                    order_id=str(order_id),
                    client_order_id=client_order_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    qty=qty,
                    price=Decimal(str(price)) if price not in (
                        None, "") else None,
                    stop_price=Decimal(str(stop_price)) if stop_price not in (
                        None, "") else None,
                    reduce_only=reduce_only,
                    close_position=close_position,
                    status=status,
                    created_ts=created_ts,
                    update_ts=update_ts,
                    cycle_id=cycle_id,
                )
            )
        except Exception:
            continue

    return views
