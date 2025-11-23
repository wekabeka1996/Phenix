"""
OrderTrace V2 Tests
===================

Test suite for V2 trace builder with inference logic.

Scenarios:
1. Basic trade timeline (ENTRY → TP/SL creation → EXIT)
2. Bracket recalculation (SL/TP cancelled + new created)
3. Trailing stop updates (SL replaced with closer stop)
4. Position closure (FLAT + exit trade)
"""
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pytest

from apps.reference.tools.order_trace import (
    TraceSources,
    TraceEvent,
    build_timeline_for_rid,
    infer_bracket_orders_placed,
    infer_trailing_sl_updated,
    infer_close_decision,
)


def _create_jsonl_log(lines: List[Dict[str, Any]]) -> Path:
    """Create temporary JSONL log file."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
    for line in lines:
        tmp.write(json.dumps(line) + "\n")
    tmp.close()
    return Path(tmp.name)


def _create_wal_dir(files: Dict[str, List[Dict[str, Any]]]) -> Path:
    """Create temporary WAL directory with multiple JSONL files."""
    wal_dir = Path(tempfile.mkdtemp())
    for filename, lines in files.items():
        wal_file = wal_dir / filename
        with open(wal_file, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")
    return wal_dir


def _ts(offset_sec: float = 0.0) -> float:
    """Generate Unix timestamp (base: 2025-11-21 10:00:00)."""
    base = 1732183200.0  # 2025-11-21 10:00:00 UTC
    return base + offset_sec


def _iso_ts(offset_sec: float = 0.0) -> str:
    """Generate ISO 8601 timestamp."""
    ts = _ts(offset_sec)
    dt = datetime.fromtimestamp(ts)
    return dt.isoformat() + "Z"


# =======================
# Scenario 1: Basic Trade
# =======================

def test_basic_trade_timeline():
    """
    Test basic trade flow:
    1. ENTRY trade
    2. SL/TP orders placed (bracket)
    3. TP filled (exit)
    """
    rid = "TEST-BASIC-001"
    symbol = "BTCUSDT"

    # Create WAL with ENTRY trade + SL/TP orders + TP exit
    wal_records = [
        # ENTRY trade
        {
            "ts": _ts(0.0),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_TRADE",
            "rid": rid,
            "symbol": symbol,
            "trade_id": "t1",
            "role": "ENTRY",
            "qty": 0.5,
            "price": 45000.0,
            "realized_pnl": 0.0,
        },
        # SL order placed
        {
            "ts": _ts(1.0),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_ORDER",
            "rid": rid,
            "symbol": symbol,
            "order_id": "ord_sl_1",
            "status": "NEW",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "stop_price": 44100.0,
            "side": "SELL",
        },
        # TP order placed
        {
            "ts": _ts(1.5),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_ORDER",
            "rid": rid,
            "symbol": symbol,
            "order_id": "ord_tp_1",
            "status": "NEW",
            "type": "LIMIT",
            "reduce_only": True,
            "price": 46800.0,
            "side": "SELL",
        },
        # TP filled
        {
            "ts": _ts(60.0),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_TRADE",
            "rid": rid,
            "symbol": symbol,
            "trade_id": "t1",
            "role": "TP",
            "qty": -0.5,
            "price": 46800.0,
            "realized_pnl": 900.0,
        },
        # Position FLAT
        {
            "ts": _ts(60.5),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_POSITION",
            "rid": rid,
            "symbol": symbol,
            "position_id": "pos_1",
            "position_size": 0.0,
            "direction": "FLAT",
        },
    ]

    wal_dir = _create_wal_dir({"2025-11-21.jsonl": wal_records})

    sources = TraceSources(
        wal_dir=str(wal_dir),
    )

    # Build trace
    trace = build_timeline_for_rid(rid, sources)

    assert trace is not None, "Trace should be found"
    assert trace.symbol == symbol
    assert trace.trace_id == rid
    assert len(trace.events) >= 5, "Should have at least 5 explicit events"

    # Verify ENTRY trade
    entry_events = [e for e in trace.events if e.event_type ==
                    "EXEC_TRADE" and e.payload.get("role") == "ENTRY"]
    assert len(entry_events) == 1, "Should have 1 ENTRY trade"
    assert entry_events[0].payload["qty"] == 0.5

    # Verify inferred BRACKET_ORDERS_PLACED
    bracket_events = [
        e for e in trace.events if e.event_type == "BRACKET_ORDERS_PLACED"]
    assert len(bracket_events) >= 1, "Should infer bracket orders placed"
    bracket_payload = bracket_events[0].payload
    assert len(bracket_payload["sl_orders"]) >= 1, "Should detect SL order"
    assert len(bracket_payload["tp_orders"]) >= 1, "Should detect TP order"

    # Verify TP exit
    exit_events = [e for e in trace.events if e.event_type ==
                   "EXEC_TRADE" and e.payload.get("role") == "TP"]
    assert len(exit_events) == 1, "Should have 1 TP exit"
    assert exit_events[0].payload["realized_pnl"] == 900.0

    # Verify inferred CLOSE_DECISION
    close_events = [e for e in trace.events if e.event_type ==
                    "CLOSE_DECISION_INFERRED"]
    assert len(close_events) >= 1, "Should infer close decision"
    assert close_events[0].payload["reason"] == "TP"


# ===================================
# Scenario 2: Bracket Recalculation
# ===================================

def test_infer_bracket_orders_placed():
    """
    Test inference of bracket orders from order snapshot.
    """
    symbol = "BTCUSDT"

    events = [
        # ENTRY trade at ts=0
        TraceEvent(
            ts=_ts(0.0),
            source="WAL",
            event_type="EXEC_TRADE",
            payload={
                "symbol": symbol,
                "role": "ENTRY",
                "qty": 0.5,
                "price": 45000.0,
            },
            why="role=ENTRY",
        ),
        # SL order at ts=1
        TraceEvent(
            ts=_ts(1.0),
            source="WAL",
            event_type="EXEC_ORDER",
            payload={
                "symbol": symbol,
                "order_id": "ord_sl_1",
                "status": "NEW",
                "type": "STOP_MARKET",
                "reduce_only": True,
                "stop_price": 44100.0,
            },
            why="status=NEW",
        ),
        # TP order at ts=1.5
        TraceEvent(
            ts=_ts(1.5),
            source="WAL",
            event_type="EXEC_ORDER",
            payload={
                "symbol": symbol,
                "order_id": "ord_tp_1",
                "status": "NEW",
                "type": "LIMIT",
                "reduce_only": True,
                "price": 46800.0,
            },
            why="status=NEW",
        ),
    ]

    inferred = infer_bracket_orders_placed(events)

    assert len(inferred) == 1, "Should infer 1 bracket event"
    bracket_event = inferred[0]
    assert bracket_event.event_type == "BRACKET_ORDERS_PLACED"
    assert bracket_event.source == "INFERRED"
    assert len(bracket_event.payload["sl_orders"]) == 1
    assert len(bracket_event.payload["tp_orders"]) == 1
    assert bracket_event.payload["sl_orders"][0]["orderId"] == "ord_sl_1"
    assert bracket_event.payload["tp_orders"][0]["orderId"] == "ord_tp_1"


# ==============================
# Scenario 3: Trailing Updates
# ==============================

def test_infer_trailing_sl_updated():
    """
    Test inference of trailing stop updates from SL replacement pattern.
    """
    symbol = "BTCUSDT"

    events = [
        # Old SL cancelled at ts=10
        TraceEvent(
            ts=_ts(10.0),
            source="WAL",
            event_type="EXEC_ORDER",
            payload={
                "symbol": symbol,
                "order_id": "ord_sl_old",
                "status": "CANCELLED",
                "type": "STOP_MARKET",
                "reduce_only": True,
                "stop_price": 44100.0,
            },
            why="status=CANCELLED",
        ),
        # New SL placed at ts=11
        TraceEvent(
            ts=_ts(11.0),
            source="WAL",
            event_type="EXEC_ORDER",
            payload={
                "symbol": symbol,
                "order_id": "ord_sl_new",
                "status": "NEW",
                "type": "STOP_MARKET",
                "reduce_only": True,
                "stop_price": 44500.0,  # Trailed +400
            },
            why="status=NEW",
        ),
    ]

    inferred = infer_trailing_sl_updated(events)

    assert len(inferred) == 1, "Should infer 1 trailing event"
    trailing_event = inferred[0]
    assert trailing_event.event_type == "TRAILING_SL_UPDATED"
    assert trailing_event.source == "INFERRED"
    assert trailing_event.payload["old_stop_price"] == 44100.0
    assert trailing_event.payload["new_stop_price"] == 44500.0
    assert trailing_event.payload["delta"] == 400.0


# ==============================
# Scenario 4: Position Closure
# ==============================

def test_infer_close_decision():
    """
    Test inference of close decision from position FLAT + exit trade.
    """
    symbol = "BTCUSDT"

    events = [
        # SL exit trade at ts=20
        TraceEvent(
            ts=_ts(20.0),
            source="WAL",
            event_type="EXEC_TRADE",
            payload={
                "symbol": symbol,
                "role": "SL",
                "qty": -0.5,
                "price": 44100.0,
                "realized_pnl": -450.0,
            },
            why="role=SL",
        ),
        # Position FLAT at ts=20.5
        TraceEvent(
            ts=_ts(20.5),
            source="WAL",
            event_type="EXEC_POSITION",
            payload={
                "symbol": symbol,
                "position_id": "pos_1",
                "position_size": 0.0,
                "direction": "FLAT",
            },
            why="direction=FLAT",
        ),
    ]

    inferred = infer_close_decision(events)

    assert len(inferred) == 1, "Should infer 1 close decision"
    close_event = inferred[0]
    assert close_event.event_type == "CLOSE_DECISION_INFERRED"
    assert close_event.source == "INFERRED"
    assert close_event.payload["reason"] == "SL"
    assert close_event.payload["realized_pnl"] == -450.0


# ==========================
# Scenario 5: RID Correlation
# ==========================

def test_correlate_by_rid():
    """
    Test RID-based correlation with runtime log + WAL.
    """
    rid = "TEST-RID-002"
    symbol = "ETHUSDT"

    # Runtime log with RID
    runtime_records = [
        {
            "ts": _iso_ts(0.0),
            "rid": rid,
            "event_kind": "ENTRY_INTENT",
            "symbol": symbol,
            "side": "BUY",
            "quantity": 1.0,
            "why": "signal=STRONG_BUY",
        },
    ]

    # WAL with RID
    wal_records = [
        {
            "ts": _ts(1.0),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_TRADE",
            "rid": rid,
            "symbol": symbol,
            "trade_id": "t2",
            "role": "ENTRY",
            "qty": 1.0,
            "price": 3000.0,
            "realized_pnl": 0.0,
        },
    ]

    runtime_log = _create_jsonl_log(runtime_records)
    wal_dir = _create_wal_dir({"2025-11-21.jsonl": wal_records})

    sources = TraceSources(
        runtime_log_path=str(runtime_log),
        wal_dir=str(wal_dir),
    )

    trace = build_timeline_for_rid(rid, sources)

    assert trace is not None
    assert trace.trace_id == rid
    assert trace.symbol == symbol

    # Verify runtime event
    runtime_events = [e for e in trace.events if e.source == "RUNTIME"]
    assert len(runtime_events) >= 1, "Should have runtime events"
    assert runtime_events[0].event_type == "ENTRY_INTENT"

    # Verify WAL event
    wal_events = [e for e in trace.events if e.source == "WAL"]
    assert len(wal_events) >= 1, "Should have WAL events"
    assert wal_events[0].event_type == "EXEC_TRADE"


# ====================================
# Scenario 6: Symbol Fallback (No RID)
# ====================================

def test_correlate_by_symbol_fallback():
    """
    Test symbol-based fallback when RID is missing.
    """
    symbol = "BTCUSDT"
    from_ts = _ts(-10.0)
    to_ts = _ts(100.0)

    # WAL without RID
    wal_records = [
        {
            "ts": _ts(0.0),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_TRADE",
            "symbol": symbol,
            "trade_id": "t3",
            "role": "ENTRY",
            "qty": 0.5,
            "price": 45000.0,
            "realized_pnl": 0.0,
        },
    ]

    wal_dir = _create_wal_dir({"2025-11-21.jsonl": wal_records})

    sources = TraceSources(wal_dir=str(wal_dir))

    from apps.reference.tools.order_trace.v2_trace_builder import build_timeline_for_position

    trace = build_timeline_for_position(
        symbol=symbol,
        from_ts=from_ts,
        to_ts=to_ts,
        sources=sources,
    )

    assert trace is not None
    assert trace.symbol == symbol
    assert len(trace.events) >= 1

    entry_events = [e for e in trace.events if e.event_type == "EXEC_TRADE"]
    assert len(entry_events) == 1


# ====================================
# Scenario 7: Complex Trade (Multiple Brackets + Trailing)
# ====================================

def test_complex_trade_with_trailing():
    """
    Test complex scenario:
    1. ENTRY
    2. Initial brackets
    3. Multiple trailing updates
    4. Final exit
    """
    rid = "TEST-COMPLEX-003"
    symbol = "BTCUSDT"

    wal_records = [
        # ENTRY
        {
            "ts": _ts(0.0),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_TRADE",
            "rid": rid,
            "symbol": symbol,
            "trade_id": "t4",
            "role": "ENTRY",
            "qty": 1.0,
            "price": 45000.0,
            "realized_pnl": 0.0,
        },
        # Initial SL
        {
            "ts": _ts(1.0),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_ORDER",
            "rid": rid,
            "symbol": symbol,
            "order_id": "ord_sl_v1",
            "status": "NEW",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "stop_price": 44100.0,
        },
        # First trailing: cancel old SL
        {
            "ts": _ts(10.0),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_ORDER",
            "rid": rid,
            "symbol": symbol,
            "order_id": "ord_sl_v1",
            "status": "CANCELLED",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "stop_price": 44100.0,
        },
        # First trailing: new SL
        {
            "ts": _ts(10.5),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_ORDER",
            "rid": rid,
            "symbol": symbol,
            "order_id": "ord_sl_v2",
            "status": "NEW",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "stop_price": 44500.0,
        },
        # Second trailing: cancel v2
        {
            "ts": _ts(20.0),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_ORDER",
            "rid": rid,
            "symbol": symbol,
            "order_id": "ord_sl_v2",
            "status": "CANCELLED",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "stop_price": 44500.0,
        },
        # Second trailing: new SL v3
        {
            "ts": _ts(20.5),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_ORDER",
            "rid": rid,
            "symbol": symbol,
            "order_id": "ord_sl_v3",
            "status": "NEW",
            "type": "STOP_MARKET",
            "reduce_only": True,
            "stop_price": 44900.0,
        },
        # SL v3 filled
        {
            "ts": _ts(30.0),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_TRADE",
            "rid": rid,
            "symbol": symbol,
            "trade_id": "t4",
            "role": "SL",
            "qty": -1.0,
            "price": 44900.0,
            "realized_pnl": -100.0,
        },
        # Position FLAT
        {
            "ts": _ts(30.5),
            "domain": "execution_position",
            "runtime": "v2",
            "event_type": "EXEC_POSITION",
            "rid": rid,
            "symbol": symbol,
            "position_id": "pos_4",
            "position_size": 0.0,
            "direction": "FLAT",
        },
    ]

    wal_dir = _create_wal_dir({"2025-11-21.jsonl": wal_records})
    sources = TraceSources(wal_dir=str(wal_dir))

    trace = build_timeline_for_rid(rid, sources)

    assert trace is not None
    assert len(trace.events) >= 8

    # Verify 2 trailing updates
    trailing_events = [
        e for e in trace.events if e.event_type == "TRAILING_SL_UPDATED"]
    assert len(trailing_events) == 2, "Should infer 2 trailing updates"

    # Verify first trailing: 44100 → 44500 (+400)
    assert trailing_events[0].payload["old_stop_price"] == 44100.0
    assert trailing_events[0].payload["new_stop_price"] == 44500.0
    assert trailing_events[0].payload["delta"] == 400.0

    # Verify second trailing: 44500 → 44900 (+400)
    assert trailing_events[1].payload["old_stop_price"] == 44500.0
    assert trailing_events[1].payload["new_stop_price"] == 44900.0
    assert trailing_events[1].payload["delta"] == 400.0

    # Verify close decision
    close_events = [e for e in trace.events if e.event_type ==
                    "CLOSE_DECISION_INFERRED"]
    assert len(close_events) == 1
    assert close_events[0].payload["reason"] == "SL"
    assert close_events[0].payload["realized_pnl"] == -100.0
