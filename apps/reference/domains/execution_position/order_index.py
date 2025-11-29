"""
Order Lifecycle Correlation Index.

Provides in-memory TTL-based storage for correlating order identifiers:
rid ↔ idempotent_key ↔ clientOrderId ↔ exchangeOrderId
"""

from __future__ import annotations
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from time import time
from typing import Optional, Dict, Any


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
    created_ts: float = field(default_factory=time)
    terminal: bool = False


class OrderIndex:
    """
    In-memory index for order lifecycle correlation with TTL expiration.

    Maintains three lookup indexes:
    - by_rid: rid -> OrderRef
    - by_client: clientOrderId -> OrderRef
    - by_exchange: exchangeOrderId -> OrderRef
    """

    def __init__(self, ttl_sec: int = 3600):
        """
        Initialize Order Index.

        Args:
            ttl_sec: Time-to-live for order references in seconds
        """
        self.ttl = ttl_sec
        self._lock = threading.RLock()
        self._by_rid: Dict[str, OrderRef] = {}
        self._by_client: Dict[str, OrderRef] = {}
        self._by_exchange: Dict[str, OrderRef] = {}

    def upsert_from_open(
        self,
        *,
        rid: str,
        idempotent_key: str,
        clientOrderId: Optional[str],
        symbol: str,
        side: str,
        order_type: str,
    ) -> OrderRef:
        """
        Create or update order reference from OPEN operation.

        Args:
            rid: Request ID
            idempotent_key: Idempotency key
            clientOrderId: Client order ID (may be None initially)
            symbol: Trading symbol
            side: Order side (BUY/SELL)
            order_type: Order type (MARKET/LIMIT)

        Returns:
            OrderRef instance
        """
        with self._lock:
            ref = self._by_rid.get(rid) or OrderRef(rid=rid, idempotent_key=idempotent_key)
            ref.clientOrderId = clientOrderId or ref.clientOrderId
            ref.symbol, ref.side, ref.order_type = symbol, side, order_type
            self._by_rid[rid] = ref
            if ref.clientOrderId:
                self._by_client[ref.clientOrderId] = ref
            return ref

    def attach_exchange_id(
        self, *, clientOrderId: Optional[str], exchangeOrderId: Optional[str]
    ) -> Optional[OrderRef]:
        """
        Attach exchange order ID to existing order reference.

        Args:
            clientOrderId: Client order ID to lookup
            exchangeOrderId: Exchange order ID to attach

        Returns:
            OrderRef if found and updated, None otherwise
        """
        with self._lock:
            ref = (clientOrderId and self._by_client.get(clientOrderId)) or None
            if ref and exchangeOrderId:
                ref.exchangeOrderId = exchangeOrderId
                self._by_exchange[exchangeOrderId] = ref
            return ref

    def get(
        self, *, rid: str = None, clientOrderId: str = None, exchangeOrderId: str = None
    ) -> Optional[OrderRef]:
        """
        Get order reference by any identifier.

        Args:
            rid: Request ID
            clientOrderId: Client order ID
            exchangeOrderId: Exchange order ID

        Returns:
            OrderRef if found, None otherwise
        """
        with self._lock:
            if rid:
                return self._by_rid.get(rid)
            if clientOrderId:
                return self._by_client.get(clientOrderId)
            if exchangeOrderId:
                return self._by_exchange.get(exchangeOrderId)
            return None

    def mark_terminal(self, ref: OrderRef) -> None:
        """
        Mark order reference as terminal (completed/canceled/expired).

        Args:
            ref: OrderRef to mark as terminal
        """
        with self._lock:
            ref.terminal = True

    def expire(self) -> int:
        """
        Remove expired order references based on TTL.

        Returns:
            Number of references removed
        """
        now = time()
        removed = 0

        def _kill(ref: OrderRef):
            nonlocal removed
            self._by_rid.pop(ref.rid, None)
            removed += 1
            if ref.clientOrderId:
                self._by_client.pop(ref.clientOrderId, None)
            if ref.exchangeOrderId:
                self._by_exchange.pop(ref.exchangeOrderId, None)

        with self._lock:
            for ref in list(self._by_rid.values()):
                if ref.terminal or (now - ref.created_ts) > self.ttl:
                    _kill(ref)
            return removed
