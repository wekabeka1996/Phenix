"""
Order Lifecycle Correlation Index.

Provides in-memory TTL-based storage for correlating order identifiers:
rid ↔ idempotent_key ↔ clientOrderId ↔ exchangeOrderId
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from time import time
from typing import Optional, Dict, List, Set, Any


@dataclass
class OrderRef:
    """Order reference with all correlation identifiers."""

    rid: str
    idempotent_key: Optional[str]
    clientOrderId: Optional[str] = None
    exchangeOrderId: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    order_type: Optional[str] = None
    # Additional fields for runtime compatibility
    price: Optional[float] = None
    quantity: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = "NEW"
    reduce_only: bool = False

    created_ts: float = field(default_factory=time)
    update_ts: float = field(default_factory=time)
    terminal: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format expected by converters."""
        return {
            "orderId": self.exchangeOrderId,
            "order_id": self.exchangeOrderId,  # Alias for compatibility
            "clientOrderId": self.clientOrderId,
            "client_order_id": self.clientOrderId, # Alias for compatibility
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
            "order_type": self.order_type, # Alias
            "price": self.price,
            "quantity": self.quantity,
            "qty": self.quantity, # Alias
            "stopPrice": self.stop_price,
            "stop_price": self.stop_price, # Alias
            "status": self.status,
            "reduceOnly": self.reduce_only,
            "reduce_only": self.reduce_only, # Alias
            "time": self.created_ts * 1000,  # ms expected by some converters
            "updateTime": self.update_ts * 1000,
            # Internal fields
            "rid": self.rid,
            "idempotent_key": self.idempotent_key,
        }


class OrderIndex:
    """
    In-memory index for order lifecycle correlation with TTL expiration.

    Maintains lookup indexes:
    - by_rid: rid -> OrderRef
    - by_client: clientOrderId -> OrderRef
    - by_exchange: exchangeOrderId -> OrderRef
    - by_symbol: symbol -> Set[rid]
    """

    def __init__(self, ttl_sec: int = 3600):
        self.ttl = ttl_sec
        self._by_rid: Dict[str, OrderRef] = {}
        self._by_client: Dict[str, OrderRef] = {}
        self._by_exchange: Dict[str, OrderRef] = {}
        self._by_symbol: Dict[str, Set[str]] = {}

    def upsert_from_open(
        self,
        *,
        rid: str,
        idempotent_key: str,
        clientOrderId: Optional[str],
        symbol: str,
        side: str,
        order_type: str,
        price: Optional[float] = None,
        quantity: Optional[float] = None,
        stop_price: Optional[float] = None,
        reduce_only: bool = False,
    ) -> OrderRef:
        """
        Create or update order reference from OPEN operation.
        """
        ref = self._by_rid.get(rid) or OrderRef(rid=rid, idempotent_key=idempotent_key)

        # Update fields
        ref.clientOrderId = clientOrderId or ref.clientOrderId
        ref.symbol = symbol
        ref.side = side
        ref.order_type = order_type
        ref.price = price
        ref.quantity = quantity
        ref.stop_price = stop_price
        ref.reduce_only = reduce_only
        ref.update_ts = time()

        self._by_rid[rid] = ref

        if ref.clientOrderId:
            self._by_client[ref.clientOrderId] = ref

        if symbol:
            if symbol not in self._by_symbol:
                self._by_symbol[symbol] = set()
            self._by_symbol[symbol].add(rid)

        return ref

    def attach_exchange_id(
        self, *, clientOrderId: Optional[str], exchangeOrderId: Optional[str]
    ) -> Optional[OrderRef]:
        """
        Attach exchange order ID to existing order reference.
        """
        ref = (clientOrderId and self._by_client.get(clientOrderId)) or None
        if ref and exchangeOrderId:
            ref.exchangeOrderId = exchangeOrderId
            self._by_exchange[exchangeOrderId] = ref
            ref.update_ts = time()
        return ref

    def get(
        self, *, rid: str = None, clientOrderId: str = None, exchangeOrderId: str = None
    ) -> Optional[OrderRef]:
        """
        Get order reference by any identifier.
        """
        if rid:
            return self._by_rid.get(rid)
        if clientOrderId:
            return self._by_client.get(clientOrderId)
        if exchangeOrderId:
            return self._by_exchange.get(exchangeOrderId)
        return None

    def get_by_symbol(self, symbol: str) -> List[OrderRef]:
        """Get all active orders for a symbol."""
        rids = self._by_symbol.get(symbol, set())
        return [self._by_rid[rid] for rid in rids if rid in self._by_rid]

    def reconcile_snapshot(self, symbol: str, snapshot_orders: List[Dict[str, Any]]) -> None:
        """
        Reconcile local state with exchange snapshot.

        Strategy:
        1. Mark all local orders for symbol as 'potentially_stale'.
        2. Iterate snapshot:
           - If matches existing (by clientOrderId or exchangeOrderId), update it and unmark 'stale'.
           - If new, create new OrderRef (generate synthetic RID).
        3. Remove remaining 'stale' orders (they are not in snapshot).
        """
        current_rids = self._by_symbol.get(symbol, set()).copy()
        matched_rids = set()

        for order_data in snapshot_orders:
            client_oid = order_data.get("clientOrderId") or order_data.get("client_order_id")
            exchange_oid = str(order_data.get("orderId") or order_data.get("order_id") or "")

            # Try to find existing
            ref = None
            if client_oid:
                ref = self._by_client.get(client_oid)
            if not ref and exchange_oid:
                ref = self._by_exchange.get(exchange_oid)

            if ref:
                # Update existing
                matched_rids.add(ref.rid)
                ref.exchangeOrderId = exchange_oid or ref.exchangeOrderId
                ref.status = order_data.get("status", ref.status)
                ref.update_ts = time()

                # Ensure indexes are up to date
                if exchange_oid:
                    self._by_exchange[exchange_oid] = ref
            else:
                # Create new (Synthetic RID)
                # Use clientOrderId as RID if it looks like one, else generate
                synthetic_rid = client_oid if client_oid else f"synth_{exchange_oid}_{time()}"

                raw_time = order_data.get("time")
                if raw_time:
                    created_ts = float(raw_time) / 1000.0
                else:
                    created_ts = time()

                new_ref = OrderRef(
                    rid=synthetic_rid,
                    idempotent_key=None,
                    clientOrderId=client_oid,
                    exchangeOrderId=exchange_oid,
                    symbol=symbol,
                    side=order_data.get("side"),
                    order_type=order_data.get("type"),
                    price=float(order_data.get("price") or 0),
                    quantity=float(order_data.get("origQty") or order_data.get("quantity") or 0),
                    stop_price=float(order_data.get("stopPrice") or order_data.get("stop_price") or 0),
                    status=order_data.get("status", "NEW"),
                    reduce_only=order_data.get("reduceOnly", False),
                    created_ts=created_ts
                )

                self._by_rid[synthetic_rid] = new_ref
                if symbol not in self._by_symbol:
                    self._by_symbol[symbol] = set()
                self._by_symbol[symbol].add(synthetic_rid)

                if client_oid:
                    self._by_client[client_oid] = new_ref
                if exchange_oid:
                    self._by_exchange[exchange_oid] = new_ref

        # Remove stale orders (those in local index but not in snapshot)
        # EXCEPTION: Don't remove orders created very recently (in-flight race condition protection)
        # If we just sent an order, it might not be in the snapshot yet.
        now = time()
        IN_FLIGHT_GRACE_PERIOD = 2.0 # seconds

        for rid in current_rids:
            if rid not in matched_rids:
                ref = self._by_rid.get(rid)
                if ref:
                    if (now - ref.created_ts) > IN_FLIGHT_GRACE_PERIOD:
                        self._kill(ref)

    def mark_terminal(self, ref: OrderRef) -> None:
        """
        Mark order reference as terminal (completed/canceled/expired).
        """
        ref.terminal = True
        ref.status = "CANCELED" # Default to canceled if marked terminal explicitly
        ref.update_ts = time()

    def expire(self) -> int:
        """
        Remove expired order references based on TTL.
        """
        now = time()
        removed = 0

        for ref in list(self._by_rid.values()):
            if ref.terminal or (now - ref.created_ts) > self.ttl:
                self._kill(ref)
                removed += 1
        return removed

    def _kill(self, ref: OrderRef):
        """Internal removal logic."""
        self._by_rid.pop(ref.rid, None)
        if ref.clientOrderId:
            self._by_client.pop(ref.clientOrderId, None)
        if ref.exchangeOrderId:
            self._by_exchange.pop(ref.exchangeOrderId, None)
        if ref.symbol and ref.symbol in self._by_symbol:
            self._by_symbol[ref.symbol].discard(ref.rid)
