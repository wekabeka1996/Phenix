"""
TCA Engine
==========

Core logic for computing Transaction Cost Analysis metrics from WAL events.
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import numpy as np

from .model import ExecPosTCATradeRecord, ExecPosTCASummary
from .loader import load_tca_events
from apps.reference.tools.order_trace.types import TraceEvent
from apps.reference.tools.execpos_metrics_aggregator import ExecPosMetricsAggregator

logger = logging.getLogger(__name__)

class TCAEngine:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
    def compute_metrics(self, events: List[TraceEvent]) -> Tuple[List[ExecPosTCATradeRecord], List[ExecPosTCASummary], Dict[str, Any]]:
        """
        Compute per-trade records and aggregated summaries from events.
        """
        # Index events for fast lookup
        orders_by_id = {}
        trades = []
        
        for e in events:
            if e.event_type == "EXEC_ORDER":
                order_id = e.payload.get("order_id")
                if order_id:
                    # Store the PLACED event or the first event seen for this order
                    if order_id not in orders_by_id or e.payload.get("status") == "PLACED":
                        orders_by_id[order_id] = e
            elif e.event_type == "EXEC_TRADE":
                trades.append(e)
                
        # Compute per-trade records
        records = []
        for t in trades:
            record = self._process_trade(t, orders_by_id)
            if record:
                records.append(record)
                
        # Compute summaries
        summaries = self._aggregate_metrics(records)

        canonical_metrics = self._build_canonical_metrics(records)

        return records, summaries, canonical_metrics
    
    def _process_trade(self, trade_event: TraceEvent, orders_map: Dict[str, TraceEvent]) -> ExecPosTCATradeRecord:
        """Process a single trade event into a TCA record."""
        p = trade_event.payload
        order_id = p.get("order_id")
        
        # Basic fields
        qty = float(p.get("qty", 0))
        price = float(p.get("price", 0))
        fee = float(p.get("fee", 0))
        
        record = ExecPosTCATradeRecord(
            trade_id=p.get("trade_id"),
            order_id=order_id,
            symbol=p.get("symbol"),
            side=p.get("side"),
            role=p.get("role", "UNKNOWN"),
            qty=qty,
            exec_price=price,
            notional=qty * price,
            fee=fee,
            ts=trade_event.ts
        )
        
        # Enrich with order info
        order_event = orders_map.get(order_id)
        if order_event:
            op = order_event.payload
            record.client_order_id = op.get("client_order_id")
            
            # Time to fill
            if order_event.ts > 0:
                record.time_to_fill_ms = (trade_event.ts - order_event.ts) * 1000.0
            
            # Reference Price & Slippage
            # For V1: Use order price for LIMIT, or mark price from metadata if available
            ref_price = None
            order_type = op.get("type", "").upper()
            
            if "LIMIT" in order_type:
                ref_price = float(op.get("price", 0))
            elif "MARKET" in order_type:
                # Try to find mark price in extra metadata (if logged)
                # Fallback: use exec_price (0 slippage) if no better ref
                ref_price = price 
            
            if ref_price and ref_price > 0:
                record.ref_price = ref_price
                
                # Slippage BPS calculation
                # (Exec - Ref) / Ref * 10000
                # For BUY: Positive if Exec < Ref (Better), Negative if Exec > Ref (Worse)
                # For SELL: Positive if Exec > Ref (Better), Negative if Exec < Ref (Worse)
                # Wait, standard convention is often:
                # Slippage = (Exec - Ref) for Buy? No, usually "Implementation Shortfall"
                # Let's stick to: Positive = Better for user, Negative = Worse for user
                
                diff = 0.0
                if record.side == "BUY":
                    diff = ref_price - price # Lower price is better
                else: # SELL
                    diff = price - ref_price # Higher price is better
                    
                record.slippage_bps = (diff / ref_price) * 10000.0

        return record

    def _aggregate_metrics(self, records: List[ExecPosTCATradeRecord]) -> List[ExecPosTCASummary]:
        """Aggregate records into summaries per symbol and global."""
        groups = defaultdict(list)
        global_records = []
        
        for r in records:
            groups[r.symbol].append(r)
            global_records.append(r)
            
        summaries = []
        
        # Per Symbol
        for symbol, recs in groups.items():
            summaries.append(self._compute_summary(symbol, recs))
            
        # Global
        if global_records:
            summaries.append(self._compute_summary("GLOBAL", global_records))
            
        return summaries
    
    def _compute_summary(self, scope: str, records: List[ExecPosTCATradeRecord]) -> ExecPosTCASummary:
        if not records:
            return ExecPosTCASummary(scope=scope)
            
        total_vol = sum(r.notional for r in records)
        total_fees = sum(r.fee for r in records)
        count = len(records)
        
        # Slippage stats (filter out None)
        slippage_values = [r.slippage_bps for r in records if r.slippage_bps is not None]
        
        avg_slip = 0.0
        p95_slip = 0.0
        min_slip = 0.0
        max_slip = 0.0
        
        if slippage_values:
            # Volume-weighted average would be better, but simple avg for V1
            avg_slip = float(np.mean(slippage_values))
            p95_slip = float(np.percentile(slippage_values, 5)) # 5th percentile is the "bad tail" for negative numbers (worse execution)
            # Wait, if Positive is Better, then the "Bad Tail" is the low numbers (negative).
            # So p95 of "badness" might be p05 of the value.
            # Let's just report p05 and p95? Or just p05 (worst execution)?
            # Let's report p05 as "Worst 5%"
            p95_slip = float(np.percentile(slippage_values, 5)) 
            min_slip = float(np.min(slippage_values))
            max_slip = float(np.max(slippage_values))
            
        # Timing stats
        times = [r.time_to_fill_ms for r in records if r.time_to_fill_ms is not None]
        avg_time = float(np.mean(times)) if times else 0.0
        
        return ExecPosTCASummary(
            scope=scope,
            total_volume=total_vol,
            total_fees=total_fees,
            trade_count=count,
            avg_slippage_bps=avg_slip,
            p95_slippage_bps=p95_slip,
            min_slippage_bps=min_slip,
            max_slippage_bps=max_slip,
            avg_time_to_fill_ms=avg_time
        )

    def _build_canonical_metrics(self, records: List[ExecPosTCATradeRecord]) -> Dict[str, Any]:
        """Convert TCA records into canonical execpos_* counters."""
        agg = ExecPosMetricsAggregator()
        agg.consume_tca_records(records)
        return {
            "counters": agg.to_dict(),
            "prometheus": agg.to_prometheus_text()
        }

def compute_tca_for_period(
    logs_root: str,
    from_ts: float,
    to_ts: float,
    symbol: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Main entry point: Compute TCA metrics for a period.
    Returns a dict with 'records' and 'summaries'.
    """
    events = load_tca_events(logs_root, from_ts, to_ts, symbol)
    engine = TCAEngine(config)
    records, summaries, canonical_metrics = engine.compute_metrics(events)
    
    return {
        "records": [r.to_dict() for r in records],
        "summaries": [s.to_dict() for s in summaries],
        "metrics": canonical_metrics,
    }
