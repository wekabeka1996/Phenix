"""
Order Trace - Trade Narrative Layer
====================================

Tools for correlating decision logs, execution events, WAL records, and exposure updates
into coherent trade narratives for debugging and post-mortem analysis.

V2 Features:
- RID-based correlation (primary)
- Inference of bracket/trailing/close events from order state transitions
- CLI with multiple output formats (timeline, JSON, table)
"""

__version__ = "2.0.0"

from .types import TradeTrace, TraceEvent, TraceSources
from .parsers import (
    parse_decision_log,
    parse_execpos_runtime_log,
    parse_wal_records,
    parse_exposure_events,
)
from .engine import build_trace_for_trade, build_trace_for_position
from .v2_trace_builder import (
    build_timeline_for_rid,
    build_timeline_for_position as build_timeline_for_position_v2,
    infer_bracket_orders_placed,
    infer_trailing_sl_updated,
    infer_close_decision,
)

__all__ = [
    "TradeTrace",
    "TraceEvent",
    "TraceSources",
    "parse_decision_log",
    "parse_execpos_runtime_log",
    "parse_wal_records",
    "parse_exposure_events",
    "build_trace_for_trade",
    "build_trace_for_position",
    "build_timeline_for_rid",
    "build_timeline_for_position_v2",
    "infer_bracket_orders_placed",
    "infer_trailing_sl_updated",
    "infer_close_decision",
]
