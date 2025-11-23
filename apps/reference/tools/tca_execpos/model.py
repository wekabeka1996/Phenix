"""
TCA Data Models
===============

Defines the data structures for Transaction Cost Analysis records and summaries.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from decimal import Decimal

@dataclass
class ExecPosTCATradeRecord:
    """
    Represents the execution outcome of a single trade (fill).
    """
    trade_id: str
    order_id: str
    symbol: str
    side: str  # BUY or SELL
    role: str  # ENTRY, SL, TP, CLOSE
    qty: float
    exec_price: float
    notional: float
    fee: float
    ts: float
    
    # Execution Quality Metrics
    slippage_bps: Optional[float] = None  # Basis points relative to reference price
    ref_price: Optional[float] = None     # Reference price used for slippage
    time_to_fill_ms: Optional[float] = None # Time from placement to fill in ms
    
    # Metadata
    client_order_id: Optional[str] = None
    
    def to_dict(self):
        return {
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "role": self.role,
            "qty": self.qty,
            "exec_price": self.exec_price,
            "notional": self.notional,
            "fee": self.fee,
            "ts": self.ts,
            "slippage_bps": self.slippage_bps,
            "ref_price": self.ref_price,
            "time_to_fill_ms": self.time_to_fill_ms,
            "client_order_id": self.client_order_id
        }

@dataclass
class ExecPosTCASummary:
    """
    Aggregated TCA metrics for a specific scope (e.g., symbol, global).
    """
    scope: str  # e.g., "BTCUSDT", "GLOBAL", "SIDE:BUY"
    total_volume: float = 0.0
    total_fees: float = 0.0
    trade_count: int = 0
    
    # Slippage Statistics
    avg_slippage_bps: float = 0.0  # Volume-weighted
    p95_slippage_bps: float = 0.0
    min_slippage_bps: float = 0.0
    max_slippage_bps: float = 0.0
    
    # Timing Statistics
    avg_time_to_fill_ms: float = 0.0
    
    def to_dict(self):
        return {
            "scope": self.scope,
            "total_volume": self.total_volume,
            "total_fees": self.total_fees,
            "trade_count": self.trade_count,
            "avg_slippage_bps": self.avg_slippage_bps,
            "p95_slippage_bps": self.p95_slippage_bps,
            "min_slippage_bps": self.min_slippage_bps,
            "max_slippage_bps": self.max_slippage_bps,
            "avg_time_to_fill_ms": self.avg_time_to_fill_ms
        }
