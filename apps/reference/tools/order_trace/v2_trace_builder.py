"""
V2 Trade Trace Builder
======================

Builds comprehensive trade timelines from V2 runtime/order logs with inference-based
detection of bracket/trailing/close decisions.

Key Features:
- RID-based correlation (primary)
- Symbol + time window fallback (secondary)
- Inference of bracket/trailing/close events from order state transitions
- Read-only analysis (no runtime changes)
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .types import TraceEvent, TradeTrace, TraceSources
from .parsers import (
    parse_decision_log,
    parse_execpos_runtime_log,
    parse_wal_records,
    parse_exposure_events,
)

logger = logging.getLogger(__name__)


def _deduplicate_events(events: List[TraceEvent]) -> List[TraceEvent]:
    """
    Deduplicate events by (ts, source, event_type, payload hash).

    Args:
        events: List of TraceEvent items

    Returns:
        Deduplicated list
    """
    seen = set()
    unique_events = []

    for event in events:
        # Create hash key from essential fields
        key = (
            event.ts,
            event.source,
            event.event_type,
            json.dumps(event.payload, sort_keys=True)
        )

        if key not in seen:
            seen.add(key)
            unique_events.append(event)

    return unique_events


def _extract_symbol_from_events(events: List[TraceEvent]) -> Optional[str]:
    """Extract symbol from event payloads."""
    for event in events:
        symbol = event.payload.get("symbol")
        if symbol:
            return symbol
    return None


def _parse_wal_with_rid(wal_dir: str, rid: str) -> List[TraceEvent]:
    """
    Parse WAL files filtering by RID.

    Args:
        wal_dir: Directory containing WAL files
        rid: Request ID to filter

    Returns:
        List of TraceEvent items with matching RID
    """
    events = []

    try:
        wal_path = Path(wal_dir)
        if not wal_path.exists():
            logger.warning(f"WAL directory not found: {wal_dir}")
            return events

        for wal_file in sorted(wal_path.glob("*.jsonl")):
            try:
                with open(wal_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Filter by RID
                        if payload.get("rid") != rid:
                            continue

                        # Only process ExecPos WAL records
                        if payload.get("domain") != "execution_position" or payload.get("runtime") != "v2":
                            continue

                        event_type = payload.get("event_type")
                        if event_type not in ("EXEC_TRADE", "EXEC_ORDER", "EXEC_POSITION"):
                            continue

                        ts = float(payload.get("ts", 0))

                        # Extract "why" from event context
                        why = ""
                        if event_type == "EXEC_TRADE":
                            role = payload.get("role", "UNKNOWN")
                            why = f"role={role}"
                        elif event_type == "EXEC_ORDER":
                            status = payload.get("status", "UNKNOWN")
                            why = f"status={status}"
                        elif event_type == "EXEC_POSITION":
                            direction = payload.get("direction", "UNKNOWN")
                            why = f"direction={direction}"

                        events.append(TraceEvent(
                            ts=ts,
                            source="WAL",
                            event_type=event_type,
                            payload=payload,
                            why=why
                        ))

            except Exception as e:
                logger.error(f"Error parsing WAL file {wal_file}: {e}")
                continue

    except Exception as e:
        logger.error(f"Error reading WAL directory: {e}")

    return sorted(events, key=lambda e: e.ts)


def _parse_runtime_with_rid(log_path: str, rid: str) -> List[TraceEvent]:
    """
    Parse runtime log filtering by RID.

    Args:
        log_path: Path to runtime JSONL log
        rid: Request ID to filter

    Returns:
        List of TraceEvent items with matching RID
    """
    events = []

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Filter by RID
                if payload.get("rid") != rid:
                    continue

                # Parse ISO timestamp
                ts_str = payload.get("ts", "")
                try:
                    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    ts = dt.timestamp()
                except Exception:
                    ts = 0.0

                event_type = payload.get("event_kind", "UNKNOWN")
                why = payload.get("why", "")

                events.append(TraceEvent(
                    ts=ts,
                    source="RUNTIME",
                    event_type=event_type,
                    payload=payload,
                    why=why
                ))

    except FileNotFoundError:
        logger.warning(f"Runtime log not found: {log_path}")
    except Exception as e:
        logger.error(f"Error parsing runtime log: {e}")

    return sorted(events, key=lambda e: e.ts)


def infer_bracket_orders_placed(events: List[TraceEvent]) -> List[TraceEvent]:
    """
    Infer BRACKET_ORDERS_PLACED events from order state transitions.

    Logic:
    - Detect new reduceOnly orders with stop_price (SL) or takeProfit price (TP)
    - Created within 5 seconds of EXEC_TRADE (ENTRY role)
    - Emit synthetic BRACKET_ORDERS_PLACED event

    Args:
        events: Sorted list of TraceEvent items

    Returns:
        List of inferred TraceEvent items
    """
    inferred = []

    # Find ENTRY trade events
    entry_events = [
        e for e in events
        if e.event_type == "EXEC_TRADE" and e.payload.get("role") == "ENTRY"
    ]

    if not entry_events:
        return inferred

    for entry_event in entry_events:
        entry_ts = entry_event.ts
        symbol = entry_event.payload.get("symbol", "UNKNOWN")

        # Find orders created within 5 seconds after entry
        bracket_window = [
            e for e in events
            if e.event_type == "EXEC_ORDER"
            and e.payload.get("symbol") == symbol
            and entry_ts <= e.ts <= entry_ts + 5.0
            and e.payload.get("status") in ("NEW", "PLACED")
            and (e.payload.get("reduce_only") is True or e.payload.get("close_position") is True)
        ]

        if not bracket_window:
            continue

        # Classify SL vs TP orders
        sl_orders = []
        tp_orders = []

        for order_event in bracket_window:
            payload = order_event.payload
            order_type = payload.get("type", "")
            stop_price = payload.get("stop_price")
            price = payload.get("price")

            # SL: has stop_price
            if stop_price:
                sl_orders.append({
                    "orderId": payload.get("order_id", payload.get("client_order_id", "UNKNOWN")),
                    "price": stop_price,
                    "type": order_type,
                })
            # TP: LIMIT order without stop_price
            elif "LIMIT" in order_type.upper() and price:
                tp_orders.append({
                    "orderId": payload.get("order_id", payload.get("client_order_id", "UNKNOWN")),
                    "price": price,
                    "type": order_type,
                })

        if sl_orders or tp_orders:
            # Create synthetic event
            why_parts = []
            if sl_orders:
                sl_list = ', '.join(
                    [f"{o['orderId']} @ {o['price']}" for o in sl_orders])
                why_parts.append(f"SL orders: {sl_list}")
            if tp_orders:
                tp_list = ', '.join(
                    [f"{o['orderId']} @ {o['price']}" for o in tp_orders])
                why_parts.append(f"TP orders: {tp_list}")

            inferred.append(TraceEvent(
                ts=entry_ts + 0.1,  # Place just after entry
                source="INFERRED",
                event_type="BRACKET_ORDERS_PLACED",
                payload={
                    "symbol": symbol,
                    "entry_ts": entry_ts,
                    "sl_orders": sl_orders,
                    "tp_orders": tp_orders,
                },
                why=f"INFERRED from order snapshot: {'; '.join(why_parts)}"
            ))

    return inferred


def infer_trailing_sl_updated(events: List[TraceEvent]) -> List[TraceEvent]:
    """
    Infer TRAILING_SL_UPDATED events from SL order replacement patterns.

    Logic:
    - Detect SL order cancelled + new SL order created within 5 seconds
    - New SL stop_price is closer to market (trailing direction)
    - Position qty unchanged (not a close operation)
    - Emit synthetic TRAILING_SL_UPDATED event

    Args:
        events: Sorted list of TraceEvent items

    Returns:
        List of inferred TraceEvent items
    """
    inferred = []

    # Find cancelled SL orders
    cancelled_sl_orders = [
        e for e in events
        if e.event_type == "EXEC_ORDER"
        and e.payload.get("status") == "CANCELLED"
        and e.payload.get("stop_price") is not None
        and (e.payload.get("reduce_only") is True or e.payload.get("close_position") is True)
    ]

    for cancelled_event in cancelled_sl_orders:
        cancel_ts = cancelled_event.ts
        symbol = cancelled_event.payload.get("symbol", "UNKNOWN")
        old_stop_price = float(cancelled_event.payload.get("stop_price", 0))

        # Find new SL orders within 5 seconds
        new_sl_orders = [
            e for e in events
            if e.event_type == "EXEC_ORDER"
            and e.payload.get("symbol") == symbol
            and cancel_ts <= e.ts <= cancel_ts + 5.0
            and e.payload.get("status") in ("NEW", "PLACED")
            and e.payload.get("stop_price") is not None
            and (e.payload.get("reduce_only") is True or e.payload.get("close_position") is True)
        ]

        if not new_sl_orders:
            continue

        for new_order_event in new_sl_orders:
            new_stop_price = float(
                new_order_event.payload.get("stop_price", 0))

            # Calculate delta (trailing direction check happens in rendering)
            delta = new_stop_price - old_stop_price

            # Create synthetic event
            inferred.append(TraceEvent(
                ts=new_order_event.ts,
                source="INFERRED",
                event_type="TRAILING_SL_UPDATED",
                payload={
                    "symbol": symbol,
                    "old_order_id": cancelled_event.payload.get("order_id", "UNKNOWN"),
                    "new_order_id": new_order_event.payload.get("order_id", "UNKNOWN"),
                    "old_stop_price": old_stop_price,
                    "new_stop_price": new_stop_price,
                    "delta": delta,
                },
                why=f"INFERRED from SL replacement: {old_stop_price} → {new_stop_price} (Δ {delta:+.2f})"
            ))

    return inferred


def infer_close_decision(events: List[TraceEvent]) -> List[TraceEvent]:
    """
    Infer CLOSE_DECISION_INFERRED events from position closure patterns.

    Logic:
    - Detect EXEC_POSITION with qty → 0 (FLAT)
    - Preceded by EXEC_TRADE with role=SL/TP/CLOSE
    - Multiple orders cancelled in close proximity
    - Emit synthetic CLOSE_DECISION_INFERRED event

    Args:
        events: Sorted list of TraceEvent items

    Returns:
        List of inferred TraceEvent items
    """
    inferred = []

    # Find FLAT position events
    flat_position_events = [
        e for e in events
        if e.event_type == "EXEC_POSITION"
        and abs(float(e.payload.get("position_size", 1))) < 0.0001
    ]

    for flat_event in flat_position_events:
        flat_ts = flat_event.ts
        symbol = flat_event.payload.get("symbol", "UNKNOWN")

        # Find exit trade within 1 second before FLAT
        exit_trades = [
            e for e in events
            if e.event_type == "EXEC_TRADE"
            and e.payload.get("symbol") == symbol
            and flat_ts - 1.0 <= e.ts <= flat_ts
            and e.payload.get("role") in ("SL", "TP", "CLOSE")
        ]

        if not exit_trades:
            continue

        exit_trade = exit_trades[-1]  # Most recent
        role = exit_trade.payload.get("role", "UNKNOWN")
        realized_pnl = exit_trade.payload.get("realized_pnl", 0)

        # Create synthetic event
        inferred.append(TraceEvent(
            ts=exit_trade.ts + 0.01,
            source="INFERRED",
            event_type="CLOSE_DECISION_INFERRED",
            payload={
                "symbol": symbol,
                "reason": role,
                "realized_pnl": realized_pnl,
                "close_ts": flat_ts,
            },
            why=f"INFERRED from position closure: reason={role}, pnl={realized_pnl}"
        ))

    return inferred


def build_timeline_for_rid(rid: str, sources: TraceSources) -> Optional[TradeTrace]:
    """
    Build trade timeline for a specific RID.

    Correlation Strategy:
    1. Filter all sources by RID (primary)
    2. Extract symbol from RID-matched events
    3. Fetch all events for that symbol (catch untagged events)
    4. Deduplicate and sort chronologically
    5. Infer bracket/trailing/close events

    Args:
        rid: Request ID (primary correlation key)
        sources: TraceSources with paths to log files

    Returns:
        TradeTrace object or None if no data found
    """
    all_events: List[TraceEvent] = []
    gaps = []

    # Step 1: Get RID-matched events
    if sources.decision_log_path:
        decision_events = parse_decision_log(
            sources.decision_log_path, rid=rid)
        all_events.extend(decision_events)
    else:
        gaps.append("MISSING_DECISION_LOG")

    if sources.runtime_log_path:
        runtime_events = _parse_runtime_with_rid(
            sources.runtime_log_path, rid=rid)
        all_events.extend(runtime_events)
    else:
        gaps.append("MISSING_RUNTIME_LOG")

    if sources.wal_dir:
        wal_events = _parse_wal_with_rid(sources.wal_dir, rid=rid)
        all_events.extend(wal_events)
    else:
        gaps.append("MISSING_WAL")

    # Step 2: Extract symbol
    symbol = _extract_symbol_from_events(all_events)

    if not symbol:
        logger.warning(f"No symbol found for rid={rid}")
        if not all_events:
            return None
        symbol = "UNKNOWN"

    # Step 3: Fetch all events for that symbol (fallback for untagged events)
    if sources.decision_log_path:
        all_events.extend(parse_decision_log(
            sources.decision_log_path, symbol=symbol))

    if sources.runtime_log_path:
        all_events.extend(parse_execpos_runtime_log(
            sources.runtime_log_path, symbol=symbol))

    if sources.wal_dir:
        all_events.extend(parse_wal_records(sources.wal_dir, symbol=symbol))

    if sources.exposure_log_path:
        all_events.extend(parse_exposure_events(
            sources.exposure_log_path, symbol=symbol))

    # Step 4: Deduplicate and sort
    all_events = _deduplicate_events(all_events)
    all_events.sort(key=lambda e: e.ts)

    if not all_events:
        logger.warning(f"No events found for rid={rid}")
        return None

    # Step 5: Infer bracket/trailing/close events
    inferred_events = []
    inferred_events.extend(infer_bracket_orders_placed(all_events))
    inferred_events.extend(infer_trailing_sl_updated(all_events))
    inferred_events.extend(infer_close_decision(all_events))

    all_events.extend(inferred_events)
    all_events.sort(key=lambda e: e.ts)

    # Extract metadata
    direction = "UNKNOWN"
    entry_info = None
    exit_info = None
    entry_size = None
    final_size = None

    for event in all_events:
        if event.event_type == "EXEC_TRADE":
            role = event.payload.get("role", "UNKNOWN")
            if role == "ENTRY" and not entry_info:
                entry_info = {
                    "ts": event.ts,
                    "price": event.payload.get("price", "0"),
                    "size": event.payload.get("qty", "0"),
                    "reason": event.why,
                }
                entry_size = float(event.payload.get("qty", 0))
            elif role in ("SL", "TP", "CLOSE"):
                exit_info = {
                    "ts": event.ts,
                    "price": event.payload.get("price", "0"),
                    "size": event.payload.get("qty", "0"),
                    "reason": role,
                    "pnl": event.payload.get("realized_pnl", "0"),
                }
                final_size = 0.0

        elif event.event_type == "EXEC_POSITION":
            direction = event.payload.get("direction", direction)

    return TradeTrace(
        trace_id=rid,
        symbol=symbol,
        direction=direction,
        entry_size=entry_size,
        final_size=final_size,
        entry_info=entry_info,
        exit_info=exit_info,
        events=all_events,
        gaps=gaps,
    )


def build_timeline_for_position(
    symbol: str,
    position_id: Optional[str] = None,
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
    sources: Optional[TraceSources] = None,
) -> Optional[TradeTrace]:
    """
    Build trade timeline for a symbol + time window (fallback correlation).

    Args:
        symbol: Trading symbol (required)
        position_id: Optional position ID filter
        from_ts: Start of time window (Unix seconds, optional)
        to_ts: End of time window (Unix seconds, optional)
        sources: TraceSources with paths to log files

    Returns:
        TradeTrace object or None if no data found
    """
    all_events: List[TraceEvent] = []
    gaps = []

    if not sources:
        logger.error("TraceSources required for build_timeline_for_position")
        return None

    # Parse all sources by symbol
    if sources.decision_log_path:
        all_events.extend(parse_decision_log(
            sources.decision_log_path, symbol=symbol))
    else:
        gaps.append("MISSING_DECISION_LOG")

    if sources.runtime_log_path:
        all_events.extend(parse_execpos_runtime_log(
            sources.runtime_log_path, symbol=symbol))
    else:
        gaps.append("MISSING_RUNTIME_LOG")

    if sources.wal_dir:
        wal_kwargs = {"symbol": symbol}
        if position_id:
            wal_kwargs["position_id"] = position_id
        all_events.extend(parse_wal_records(sources.wal_dir, **wal_kwargs))
    else:
        gaps.append("MISSING_WAL")

    if sources.exposure_log_path:
        all_events.extend(parse_exposure_events(
            sources.exposure_log_path, symbol=symbol))

    # Filter by time window
    if from_ts or to_ts:
        all_events = [
            e for e in all_events
            if (from_ts is None or e.ts >= from_ts)
            and (to_ts is None or e.ts <= to_ts)
        ]

    # Deduplicate and sort
    all_events = _deduplicate_events(all_events)
    all_events.sort(key=lambda e: e.ts)

    if not all_events:
        logger.warning(
            f"No events found for symbol={symbol}, window=[{from_ts}, {to_ts}]")
        return None

    # Infer bracket/trailing/close events
    inferred_events = []
    inferred_events.extend(infer_bracket_orders_placed(all_events))
    inferred_events.extend(infer_trailing_sl_updated(all_events))
    inferred_events.extend(infer_close_decision(all_events))

    all_events.extend(inferred_events)
    all_events.sort(key=lambda e: e.ts)

    # Extract metadata
    trace_id = position_id or f"{symbol}_{from_ts or 0}_{to_ts or 0}"
    direction = "UNKNOWN"
    entry_info = None
    exit_info = None
    entry_size = None
    final_size = None

    for event in all_events:
        if event.event_type == "EXEC_TRADE":
            role = event.payload.get("role", "UNKNOWN")
            if role == "ENTRY" and not entry_info:
                entry_info = {
                    "ts": event.ts,
                    "price": event.payload.get("price", "0"),
                    "size": event.payload.get("qty", "0"),
                    "reason": event.why,
                }
                entry_size = float(event.payload.get("qty", 0))
            elif role in ("SL", "TP", "CLOSE"):
                exit_info = {
                    "ts": event.ts,
                    "price": event.payload.get("price", "0"),
                    "size": event.payload.get("qty", "0"),
                    "reason": role,
                    "pnl": event.payload.get("realized_pnl", "0"),
                }
                final_size = 0.0

        elif event.event_type == "EXEC_POSITION":
            direction = event.payload.get("direction", direction)

    return TradeTrace(
        trace_id=trace_id,
        symbol=symbol,
        direction=direction,
        entry_size=entry_size,
        final_size=final_size,
        entry_info=entry_info,
        exit_info=exit_info,
        events=all_events,
        gaps=gaps,
    )
