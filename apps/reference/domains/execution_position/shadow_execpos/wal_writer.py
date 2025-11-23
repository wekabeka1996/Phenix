"""
WAL Writer for ExecPos V2 Runtime
==================================

Writes structured execution events to WAL (write-ahead log) for audit trail,
disaster recovery, and downstream consumption by other domains.

Responsibilities:
- Write TRADE events (fills, partial fills)
- Write ORDER events (placements, cancellations, rejections)
- Write POSITION events (opens, closes, updates)
- Fail-closed: WAL write failures are logged but never crash the runtime
"""
from __future__ import annotations
import time
import logging
from typing import Any, Callable, Dict, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


class ExecPosWALWriter:
    """
    WAL writer for execution position events.
    
    Uses dependency injection for the WAL append function to enable testing
    and avoid tight coupling to vfoundation.dr.wal.
    """
    
    def __init__(self, wal_append_fn: Callable[[Dict[str, Any]], Optional[str]]):
        """
        Initialize WAL writer with dependency injection.
        
        Args:
            wal_append_fn: Function to append records to WAL (e.g., vfoundation.dr.wal.append)
        """
        self.wal_append_fn = wal_append_fn
        self._metrics = {
            "trades_written": 0,
            "orders_written": 0,
            "positions_written": 0,
            "write_errors": 0,
        }
    
    def write_trade_wal(
        self,
        trade: Dict[str, Any],
        position_ctx: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Write EXEC_TRADE record to WAL.
        
        Args:
            trade: Enriched trade event (from TRADE_EXECUTED)
            position_ctx: Optional position context (entry price, current size, etc.)
            extra: Optional extra metadata
            
        Returns:
            True if write succeeded, False if failed (failure is logged, never raises)
        """
        try:
            record = {
                "event_type": "EXEC_TRADE",
                "domain": "execution_position",
                "runtime": "v2",
                "ts": time.time(),
                "symbol": trade.get("symbol"),
                "side": trade.get("side"),
                "qty": str(trade.get("qty") or trade.get("quantity", 0)),
                "price": str(trade.get("price", 0)),
                "trade_id": trade.get("trade_id") or trade.get("tradeId"),
                "order_id": trade.get("order_id") or trade.get("orderId"),
                "role": self._infer_trade_role(trade, position_ctx),
                "source": trade.get("source", "adapter"),
            }
            
            # Add position context if available
            if position_ctx:
                record["position_id"] = position_ctx.get("position_id")
                record["realized_pnl"] = str(position_ctx.get("realized_pnl", 0))
                record["fee"] = str(position_ctx.get("fee", 0))
            
            # Add extra metadata
            if extra:
                record["extra"] = extra
            
            # Write to WAL (fail-closed)
            self.wal_append_fn(record)
            self._metrics["trades_written"] += 1
            logger.debug(f"WAL: wrote EXEC_TRADE for {record['symbol']}")
            return True
            
        except Exception as e:
            self._metrics["write_errors"] += 1
            logger.error(
                f"WAL write failed for EXEC_TRADE: {e}",
                exc_info=False,
                extra={"symbol": trade.get("symbol"), "error": str(e)}
            )
            return False
    
    def write_order_wal(
        self,
        order_event: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Write EXEC_ORDER record to WAL.
        
        Args:
            order_event: Order lifecycle event (PLACED/FILLED/CANCELLED/REJECTED)
            extra: Optional extra metadata
            
        Returns:
            True if write succeeded, False if failed
        """
        try:
            record = {
                "event_type": "EXEC_ORDER",
                "domain": "execution_position",
                "runtime": "v2",
                "ts": time.time(),
                "symbol": order_event.get("symbol"),
                "order_id": order_event.get("order_id") or order_event.get("orderId"),
                "client_order_id": order_event.get("client_order_id") or order_event.get("clientOrderId"),
                "side": order_event.get("side"),
                "type": order_event.get("type") or order_event.get("order_type"),
                "status": order_event.get("status"),
                "qty": str(order_event.get("qty") or order_event.get("quantity", 0)),
                "price": str(order_event.get("price", 0)),
                "role": order_event.get("role"),
                "reason": order_event.get("reason"),
            }
            
            if extra:
                record["extra"] = extra
            
            self.wal_append_fn(record)
            self._metrics["orders_written"] += 1
            logger.debug(f"WAL: wrote EXEC_ORDER for {record['symbol']}")
            return True
            
        except Exception as e:
            self._metrics["write_errors"] += 1
            logger.error(
                f"WAL write failed for EXEC_ORDER: {e}",
                exc_info=False,
                extra={"symbol": order_event.get("symbol"), "error": str(e)}
            )
            return False
    
    def write_position_wal(
        self,
        position: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Write EXEC_POSITION record to WAL.
        
        Args:
            position: Position state snapshot
            extra: Optional extra metadata
            
        Returns:
            True if write succeeded, False if failed
        """
        try:
            record = {
                "event_type": "EXEC_POSITION",
                "domain": "execution_position",
                "runtime": "v2",
                "ts": time.time(),
                "symbol": position.get("symbol"),
                "position_size": str(position.get("position_size") or position.get("qty", 0)),
                "entry_price": str(position.get("entry_price") or position.get("avg_price", 0)),
                "direction": position.get("direction") or position.get("side"),
                "realized_pnl": str(position.get("realized_pnl", 0)),
                "unrealized_pnl": str(position.get("unrealized_pnl", 0)),
                "exposure_usdt": str(position.get("exposure_usdt", 0)),
                "leverage": position.get("leverage", 1),
            }
            
            if extra:
                record["extra"] = extra
            
            self.wal_append_fn(record)
            self._metrics["positions_written"] += 1
            logger.debug(f"WAL: wrote EXEC_POSITION for {record['symbol']}")
            return True
            
        except Exception as e:
            self._metrics["write_errors"] += 1
            logger.error(
                f"WAL write failed for EXEC_POSITION: {e}",
                exc_info=False,
                extra={"symbol": position.get("symbol"), "error": str(e)}
            )
            return False
    
    def _infer_trade_role(
        self,
        trade: Dict[str, Any],
        position_ctx: Optional[Dict[str, Any]]
    ) -> str:
        """
        Infer trade role (ENTRY/SL/TP/CLOSE) from trade and position context.
        
        Args:
            trade: Trade event
            position_ctx: Position context
            
        Returns:
            Role string: ENTRY, SL, TP, CLOSE, or UNKNOWN
        """
        # Check if explicitly marked
        if "role" in trade:
            return trade["role"]
        
        # Check order type hints
        order_type = trade.get("type") or trade.get("order_type", "")
        if "STOP" in str(order_type).upper():
            return "SL"
        if "TAKE_PROFIT" in str(order_type).upper():
            return "TP"
        
        # Check reduce_only / closePosition flags
        if trade.get("reduceOnly") or trade.get("closePosition"):
            return "CLOSE"
        
        # Default to ENTRY for new positions
        if position_ctx and position_ctx.get("is_new_position"):
            return "ENTRY"
        
        return "UNKNOWN"
    
    def get_metrics(self) -> Dict[str, int]:
        """Get WAL writer metrics."""
        return dict(self._metrics)
