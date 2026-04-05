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
    # EP-01.6: Explicit order kind for robust entry detection (no string-hacks)
    order_kind: Optional[str] = None  # "ENTRY", "TP", "SL", "EXIT", etc.
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

    def __init__(self, ttl_sec: int = 3600, *, entry_guard_ttl_sec: int = 120):
        """
        Initialize Order Index.

        Args:
            ttl_sec: Time-to-live for order references in seconds
            entry_guard_ttl_sec: Max age for treating ENTRY refs as “in-flight” for one-open-order guard
        """
        self.ttl = ttl_sec
        self.entry_guard_ttl_sec = int(entry_guard_ttl_sec)
        self._lock = threading.RLock()
        self._by_rid: Dict[str, OrderRef] = {}
        self._by_client: Dict[str, OrderRef] = {}
        self._by_exchange: Dict[str, OrderRef] = {}
        self._shadow_journal: Optional[Any] = None

    def attach_shadow_journal(self, journal: Any) -> None:
        self._shadow_journal = journal

    def _record_shadow_transition(
        self,
        *,
        event_name: str,
        rid: Optional[str],
        payload: Dict[str, Any],
        before: Dict[str, Any],
        after: Dict[str, Any],
        notes: Optional[list[str]] = None,
    ) -> None:
        if self._shadow_journal is None:
            return
        try:
            self._shadow_journal.record_transition(
                event_name=event_name,
                source_component="execution_position.order_index",
                source_path="execution:order_index",
                event_origin_type="execution",
                truth_owner="OrderIndex",
                payload=payload,
                rid=rid,
                before=before,
                after=after,
                notes=notes,
            )
        except Exception:
            return

    @staticmethod
    def _is_entry_ref(ref: OrderRef) -> bool:
        # EP-01.6: Prefer order_kind (SSOT) if set
        if ref.order_kind:
            return str(ref.order_kind).upper() == "ENTRY"
        # Legacy fallback: clientOrderId starts with "ENTRY-"
        if ref.clientOrderId and str(ref.clientOrderId).startswith("ENTRY-"):
            return True
        if str(ref.order_type or "").upper() == "ENTRY_INTENT":
            return True
        return False

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
            before = {
                "size_by_rid": len(self._by_rid),
                "size_by_client": len(self._by_client),
                "size_by_exchange": len(self._by_exchange),
            }
            ref = self._by_rid.get(rid) or OrderRef(
                rid=rid, idempotent_key=idempotent_key)
            ref.clientOrderId = clientOrderId or ref.clientOrderId
            ref.symbol, ref.side, ref.order_type = symbol, side, order_type
            self._by_rid[rid] = ref
            if ref.clientOrderId:
                self._by_client[ref.clientOrderId] = ref
            after = {
                "size_by_rid": len(self._by_rid),
                "size_by_client": len(self._by_client),
                "size_by_exchange": len(self._by_exchange),
                "rid_ref": ref,
            }
        self._record_shadow_transition(
            event_name="ORDER_INDEX:UPSERT_OPEN",
            rid=rid,
            payload={
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "clientOrderId": clientOrderId,
                "idempotent_key": idempotent_key,
            },
            before=before,
            after=after,
        )
        return ref

    def register_bracket_child(
        self,
        *,
        rid: str,
        idempotent_key: str,
        clientOrderId: str,
        exchangeOrderId: str,
        symbol: str,
        side: str,
        order_type: str,
        order_kind: str,
    ) -> OrderRef:
        """
        Canonical registration for bracket child orders (SL/TP).

        Unlike upsert_from_open, this requires BOTH clientOrderId AND
        exchangeOrderId up-front (both are known at bracket placement time)
        and sets order_kind explicitly.

        Args:
            rid: Parent request ID (from the entry decision)
            idempotent_key: Idempotency key for the bracket child
            clientOrderId: Client-assigned order ID (SL-xxx / TP-xxx)
            exchangeOrderId: Exchange-assigned order ID from placement response
            symbol: Trading symbol
            side: Order side (the bracket side, opposite of entry)
            order_type: Order type (STOP_MARKET / TAKE_PROFIT_MARKET / LIMIT)
            order_kind: Bracket role — "SL" or "TP"

        Returns:
            OrderRef instance
        """
        if not clientOrderId or not exchangeOrderId:
            raise ValueError(
                "register_bracket_child requires both clientOrderId and exchangeOrderId"
            )
        if order_kind not in ("SL", "TP"):
            raise ValueError(
                f"register_bracket_child order_kind must be 'SL' or 'TP', got {order_kind!r}"
            )

        with self._lock:
            before = {
                "size_by_rid": len(self._by_rid),
                "size_by_client": len(self._by_client),
                "size_by_exchange": len(self._by_exchange),
            }
            # Bracket children use clientOrderId as the primary key (not rid),
            # because multiple bracket children share the same parent rid.
            # We use a synthetic rid to avoid collisions in _by_rid.
            bracket_rid = f"{rid}:{order_kind}"
            ref = OrderRef(
                rid=bracket_rid,
                idempotent_key=idempotent_key,
                clientOrderId=clientOrderId,
                exchangeOrderId=exchangeOrderId,
                symbol=symbol,
                side=side,
                order_type=order_type,
                order_kind=order_kind,
            )
            self._by_rid[bracket_rid] = ref
            self._by_client[clientOrderId] = ref
            self._by_exchange[exchangeOrderId] = ref
            after = {
                "size_by_rid": len(self._by_rid),
                "size_by_client": len(self._by_client),
                "size_by_exchange": len(self._by_exchange),
                "rid_ref": ref,
            }
        self._record_shadow_transition(
            event_name="ORDER_INDEX:REGISTER_BRACKET_CHILD",
            rid=bracket_rid,
            payload={
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "order_kind": order_kind,
                "clientOrderId": clientOrderId,
                "exchangeOrderId": exchangeOrderId,
                "parent_rid": rid,
                "idempotent_key": idempotent_key,
            },
            before=before,
            after=after,
        )
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
            before = {
                "size_by_rid": len(self._by_rid),
                "size_by_client": len(self._by_client),
                "size_by_exchange": len(self._by_exchange),
            }
            ref = (clientOrderId and self._by_client.get(clientOrderId)) or None
            if ref and exchangeOrderId:
                ref.exchangeOrderId = exchangeOrderId
                self._by_exchange[exchangeOrderId] = ref
            after = {
                "size_by_rid": len(self._by_rid),
                "size_by_client": len(self._by_client),
                "size_by_exchange": len(self._by_exchange),
                "rid_ref": ref,
            }
        self._record_shadow_transition(
            event_name="ORDER_INDEX:ATTACH_EXCHANGE_ID",
            rid=str(ref.rid) if ref else None,
            payload={
                "clientOrderId": clientOrderId,
                "orderId": exchangeOrderId,
                "symbol": ref.symbol if ref else None,
            },
            before=before,
            after=after,
        )
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
            before = {
                "rid_ref": ref,
                "size_by_rid": len(self._by_rid),
            }
            ref.terminal = True
            after = {
                "rid_ref": ref,
                "size_by_rid": len(self._by_rid),
            }
        self._record_shadow_transition(
            event_name="ORDER_INDEX:MARK_TERMINAL",
            rid=ref.rid,
            payload={
                "symbol": ref.symbol,
                "clientOrderId": ref.clientOrderId,
                "orderId": ref.exchangeOrderId,
                "side": ref.side,
            },
            before=before,
            after=after,
        )

    def has_in_flight_entry(self, symbol: str) -> bool:
        """Return True if there's a non-terminal ENTRY order for this symbol.

        Used by DecisionMaking to enforce "one open order per symbol" (TASK40).
        """
        if not symbol:
            return False
        symbol = str(symbol)
        with self._lock:
            now = time()
            for ref in self._by_rid.values():
                if ref.terminal:
                    continue
                if ref.symbol != symbol:
                    continue
                if not self._is_entry_ref(ref):
                    continue

                age_sec = now - ref.created_ts
                if age_sec > self.entry_guard_ttl_sec:
                    # Guard is best-effort; never block indefinitely due to missing terminal updates.
                    continue

                return True
            return False

    def try_reserve_entry(self, symbol: str, rid: str) -> bool:
        """
        Atomic CAS (Compare-And-Swap) reserve for ENTRY intent.

        TASK49: Fixes TOCTOU race condition by combining check + reserve into single
        atomic operation. Must be called from DecisionMaking BEFORE emitting
        TRADE_INTENT_PROPOSED.

        Args:
            symbol: Trading symbol to reserve entry for
            rid: Request ID for tracking

        Returns:
            True if reservation succeeded (no in-flight entry existed),
            False if another entry is already in-flight (reservation denied).

        Thread-safe: Uses RLock to guarantee atomicity.
        """
        if not symbol or not rid:
            return False
        symbol = str(symbol)
        rid = str(rid)

        with self._lock:
            now = time()
            before = {
                "size_by_rid": len(self._by_rid),
                "size_by_client": len(self._by_client),
                "size_by_exchange": len(self._by_exchange),
            }
            # Check: Is there already an in-flight ENTRY for this symbol?
            for ref in self._by_rid.values():
                if ref.terminal:
                    continue
                if ref.symbol != symbol:
                    continue
                if not self._is_entry_ref(ref):
                    continue

                age_sec = now - ref.created_ts
                if age_sec > self.entry_guard_ttl_sec:
                    # Guard is best-effort; never block indefinitely due to missing terminal updates.
                    continue

                self._record_shadow_transition(
                    event_name="ORDER_INDEX:RESERVE_ENTRY",
                    rid=rid,
                    payload={"symbol": symbol,
                             "reason": "reservation_denied_existing_entry"},
                    before=before,
                    after={
                        "size_by_rid": len(self._by_rid),
                        "size_by_client": len(self._by_client),
                        "size_by_exchange": len(self._by_exchange),
                    },
                    notes=["reservation_denied"],
                )
                return False  # Deny: another ENTRY in-flight

            # Reserve: Create ENTRY_INTENT placeholder immediately
            ref = OrderRef(
                rid=rid,
                idempotent_key=rid,  # Use rid as idempotent_key for early reserve
                symbol=symbol,
                side="",  # Will be filled by upsert_from_open later
                order_type="ENTRY_INTENT",
            )
            self._by_rid[rid] = ref
            after = {
                "size_by_rid": len(self._by_rid),
                "size_by_client": len(self._by_client),
                "size_by_exchange": len(self._by_exchange),
                "rid_ref": ref,
            }
        self._record_shadow_transition(
            event_name="ORDER_INDEX:RESERVE_ENTRY",
            rid=rid,
            payload={"symbol": symbol, "order_type": "ENTRY_INTENT"},
            before=before,
            after=after,
        )
        return True  # Grant: reservation successful

    def cancel_reservation(self, rid: str) -> bool:
        """
        Cancel a previously made reservation (e.g., if trade intent is blocked downstream).

        TASK49: Called when trade intent fails arbitration or other checks after
        try_reserve_entry succeeded but before actual order placement.

        Args:
            rid: Request ID used in try_reserve_entry

        Returns:
            True if reservation was found and cancelled, False otherwise.
        """
        if not rid:
            return False
        rid = str(rid)

        with self._lock:
            before = {
                "size_by_rid": len(self._by_rid),
                "size_by_client": len(self._by_client),
                "size_by_exchange": len(self._by_exchange),
            }
            ref = self._by_rid.get(rid)
            if ref and str(ref.order_type or "").upper() == "ENTRY_INTENT" and not ref.clientOrderId:
                # Only cancel if it's an uncommitted reservation (no clientOrderId yet)
                self._by_rid.pop(rid, None)
                cancelled = True
            else:
                cancelled = False
            after = {
                "size_by_rid": len(self._by_rid),
                "size_by_client": len(self._by_client),
                "size_by_exchange": len(self._by_exchange),
            }
        self._record_shadow_transition(
            event_name="ORDER_INDEX:CANCEL_RESERVATION",
            rid=rid,
            payload={"rid": rid},
            before=before,
            after=after,
            notes=["reservation_cancelled"] if cancelled else [
                "reservation_cancel_noop"],
        )
        return cancelled

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
