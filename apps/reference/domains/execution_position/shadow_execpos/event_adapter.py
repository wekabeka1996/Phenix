"""
Event adapter for bridging legacy vFoundation Messages to ExecPosRuntimeV2 RuntimeEvents.
"""
import logging
from typing import Any, Dict, Optional

from .types import RuntimeEvent

LOG = logging.getLogger(__name__)

class MessageToRuntimeEventAdapter:
    """
    Adapts legacy vFoundation Messages to RuntimeEvents.
    """
    
    def from_legacy_message(self, msg: Any) -> Optional[RuntimeEvent]:
        """
        Convert a legacy Message object to a RuntimeEvent.
        Returns None if the message is not relevant for V2 runtime.
        """
        try:
            # Extract basic fields
            # Message(op, verb, pld, ...)
            op = getattr(msg, "op", None)
            verb = getattr(msg, "verb", None)
            payload = getattr(msg, "pld", {}) or {}
            timestamp = getattr(msg, "ts", 0.0)
            
            # 1. Entry Intent (CMD:OPEN)
            if op == "CMD" and verb == "OPEN":
                return RuntimeEvent(
                    kind="ENTRY_INTENT",
                    symbol=payload.get("symbol"),
                    timestamp=timestamp,
                    payload={
                        "side": payload.get("side"),
                        "quantity": payload.get("qty"),
                        "price": payload.get("price"),
                        "order_type": payload.get("order_type", "MARKET"),
                        "tif": payload.get("tif"),
                        "idempotent_key": payload.get("idempotent_key"),
                        "strategy_id": payload.get("strategy_id"),
                        "client_order_id": payload.get("client_order_id"),
                    }
                )
                
            # 2. Cancel Intent (CMD:CANCEL or internal intent)
            if op == "CMD" and verb in ["CANCEL", "CANCEL_ORDER"]:
                return RuntimeEvent(
                    kind="CANCEL_INTENT",
                    symbol=payload.get("symbol"),
                    timestamp=timestamp,
                    payload={
                        "order_id": payload.get("order_id"),
                        "client_order_id": payload.get("client_order_id"),
                    }
                )
                
            # 3. Close Intent (CMD:CLOSE / CMD:FORCE_CLOSE)
            if op == "CMD" and verb in ["CLOSE", "FORCE_CLOSE"]:
                return RuntimeEvent(
                    kind="CLOSE_INTENT",
                    symbol=payload.get("symbol"),
                    timestamp=timestamp,
                    payload={
                        "quantity": payload.get("qty"), # Optional, full close if missing
                        "reason": payload.get("reason", "force_close" if verb == "FORCE_CLOSE" else "manual"),
                        "is_force": verb == "FORCE_CLOSE",
                    }
                )
                
            # 4. Trade Executed (EVT:TRADE_EXECUTED / EVT:FILL)
            if verb in ["TRADE_EXECUTED", "FILL", "PARTIAL_FILL"]:
                return RuntimeEvent(
                    kind="TRADE_EXECUTED",
                    symbol=payload.get("symbol"),
                    timestamp=timestamp,
                    payload={
                        "order_id": payload.get("order_id"),
                        "client_order_id": payload.get("client_order_id"),
                        "side": payload.get("side"),
                        "quantity": payload.get("last_qty") or payload.get("qty"),
                        "price": payload.get("last_price") or payload.get("price"),
                        "fee": payload.get("fee"),
                        "fee_asset": payload.get("fee_asset"),
                        "role": payload.get("role"), # MAKER/TAKER
                        "cum_qty": payload.get("cum_qty"),
                        "cum_quote": payload.get("cum_quote"),
                        "trade_id": payload.get("trade_id"),
                    }
                )
                
            # 5. Position Snapshot (EVT:PORTFOLIO_STATE_UPDATED / POSITION_SNAPSHOT / ACCOUNT_UPDATE)
            if verb in ["PORTFOLIO_STATE_UPDATED", "POSITION_SNAPSHOT", "ACCOUNT_UPDATE", "outboundAccountPosition"]:
                # Payload might be a list of positions or a wrapper
                raw_positions = payload.get("positions", [])
                if not raw_positions and "balances" in payload:
                     # Some account updates might be balances only, ignore for now unless we map balances to positions
                     pass
                
                normalized_positions = []
                for pos in raw_positions:
                    # Normalize Binance/Legacy fields to RuntimeV2 expected fields
                    # RuntimeV2 expects: symbol, qty, side (optional but good)
                    p_symbol = pos.get("symbol")
                    if not p_symbol:
                        continue
                        
                    p_amt = pos.get("positionAmt") or pos.get("position_amount") or pos.get("qty") or pos.get("amount")
                    p_entry = pos.get("entryPrice") or pos.get("avgPrice") or pos.get("avg_price") or pos.get("entry_price")
                    p_side = pos.get("positionSide") or pos.get("side") or pos.get("position_side")
                    
                    normalized_positions.append({
                        "symbol": p_symbol,
                        "qty": float(p_amt) if p_amt is not None else 0.0,
                        "entry_price": float(p_entry) if p_entry is not None else 0.0,
                        "side": p_side,
                        "unrealized_pnl": pos.get("unRealizedProfit") or pos.get("unrealized_pnl"),
                        "update_time": pos.get("updateTime") or timestamp
                    })

                return RuntimeEvent(
                    kind="POSITION_SNAPSHOT",
                    symbol=None, # Snapshot is often global or multi-symbol
                    timestamp=timestamp,
                    payload={
                        "positions": normalized_positions,
                        "source": payload.get("source", "portfolio")
                    }
                )
                
            # 6. Orders Snapshot (EVT:OPEN_ORDERS_UPDATED / ORDERS_SNAPSHOT)
            if verb in ["OPEN_ORDERS_UPDATED", "ORDERS_SNAPSHOT"]:
                raw_orders = payload.get("orders", [])
                normalized_orders = []
                for order in raw_orders:
                    o_symbol = order.get("symbol")
                    if not o_symbol:
                        continue
                    
                    normalized_orders.append({
                        "order_id": order.get("orderId") or order.get("order_id"),
                        "client_order_id": order.get("clientOrderId") or order.get("client_order_id"),
                        "symbol": o_symbol,
                        "side": order.get("side"),
                        "type": order.get("type") or order.get("order_type"),
                        "quantity": order.get("origQty") or order.get("qty") or order.get("quantity"),
                        "price": order.get("price"),
                        "stop_price": order.get("stopPrice") or order.get("stop_price"),
                        "reduce_only": order.get("reduceOnly") or order.get("reduce_only", False),
                        "status": order.get("status"),
                    })

                return RuntimeEvent(
                    kind="ORDERS_SNAPSHOT",
                    symbol=payload.get("symbol"), # Often per-symbol
                    timestamp=timestamp,
                    payload={
                        "orders": normalized_orders,
                        "source": payload.get("source", "adapter")
                    }
                )
                
            # Ignore other messages
            return None
            
        except Exception as e:
            LOG.error(f"Error adapting message {msg}: {e}")
            return None
