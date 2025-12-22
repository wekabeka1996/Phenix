"""
In-Flight Order Reconciler.

TASK51-C: TTL-based reconciliation for in-flight orders.
Prevents permanent "order in flight" blocks by reconciling via REST API.

Contract:
1. In-flight orders have TTL (configurable, default 60s)
2. On TTL expiry, reconcile via REST openOrders/orderStatus
3. If terminal or not found -> clear in-flight, allow new OPEN
4. No eternal in-flight blocks
"""

from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Protocol
from threading import RLock

from .config import InFlightConfig

LOG = logging.getLogger(__name__)


class InFlightStatus(Enum):
    """Status of an in-flight order after reconciliation."""
    PENDING = auto()       # Still in-flight (waiting for exchange)
    FILLED = auto()        # Order filled (terminal)
    CANCELED = auto()      # Order canceled (terminal)
    EXPIRED = auto()       # Order expired (terminal)
    NOT_FOUND = auto()     # Order not found on exchange (terminal)
    REJECTED = auto()      # Order rejected (terminal)
    ERROR = auto()         # Reconciliation failed (retry later)
    TTL_EXPIRED = auto()   # TTL expired, forced cleanup


# Terminal statuses that allow cleanup
TERMINAL_STATUSES = frozenset([
    InFlightStatus.FILLED,
    InFlightStatus.CANCELED,
    InFlightStatus.EXPIRED,
    InFlightStatus.NOT_FOUND,
    InFlightStatus.REJECTED,
    InFlightStatus.TTL_EXPIRED,
])


@dataclass
class InFlightEntry:
    """
    Represents an in-flight order being tracked.
    
    Attributes:
        rid: Request ID
        symbol: Trading symbol
        client_order_id: Client order ID (may be None initially)
        exchange_order_id: Exchange order ID (may be None initially)
        created_ts: Creation timestamp (epoch seconds)
        last_reconcile_ts: Last reconciliation attempt timestamp
        reconcile_attempts: Number of reconciliation attempts
        status: Current status
    """
    rid: str
    symbol: str
    client_order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    created_ts: float = field(default_factory=time.time)
    last_reconcile_ts: float = 0
    reconcile_attempts: int = 0
    status: InFlightStatus = InFlightStatus.PENDING
    
    @property
    def age_sec(self) -> float:
        """Age of this entry in seconds."""
        return time.time() - self.created_ts
    
    @property
    def is_terminal(self) -> bool:
        """True if status is terminal (can be cleaned up)."""
        return self.status in TERMINAL_STATUSES


@dataclass
class ReconcileResult:
    """Result of a reconciliation operation."""
    rid: str
    symbol: str
    old_status: InFlightStatus
    new_status: InFlightStatus
    reason: str
    cleared: bool  # True if entry was removed from in-flight
    
    def __str__(self) -> str:
        action = "CLEARED" if self.cleared else "KEPT"
        return f"[{self.symbol}] {self.rid}: {self.old_status.name} -> {self.new_status.name} ({action}: {self.reason})"


class ExchangeOrderChecker(Protocol):
    """Protocol for checking order status on exchange."""
    
    async def get_order_status(
        self,
        symbol: str,
        client_order_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get order status from exchange.
        
        Returns:
            Order info dict or None if not found
        """
        ...
    
    async def get_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Get list of open orders for a symbol."""
        ...


class InFlightReconciler:
    """
    Manages in-flight order TTL and reconciliation.
    
    TASK51-C Contract:
    - Track in-flight orders with creation timestamp
    - After TTL, reconcile via REST API
    - Clear in-flight on terminal status or not-found
    - Never block forever on "order in flight"
    
    Thread-safe via RLock.
    """
    
    def __init__(
        self,
        config: Optional[InFlightConfig] = None,
        exchange_checker: Optional[ExchangeOrderChecker] = None,
    ):
        """
        Initialize reconciler.
        
        Args:
            config: In-flight configuration
            exchange_checker: Protocol for checking orders on exchange
        """
        self.config = config or InFlightConfig()
        self._checker = exchange_checker
        self._lock = RLock()
        self._entries: Dict[str, InFlightEntry] = {}  # rid -> entry
        self._by_symbol: Dict[str, set] = {}  # symbol -> set of rids
    
    def set_exchange_checker(self, checker: ExchangeOrderChecker) -> None:
        """Set exchange checker (for late binding after adapter init)."""
        self._checker = checker
    
    def register(
        self,
        rid: str,
        symbol: str,
        client_order_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
    ) -> InFlightEntry:
        """
        Register a new in-flight order.
        
        Args:
            rid: Request ID
            symbol: Trading symbol
            client_order_id: Client order ID (may be None initially)
            exchange_order_id: Exchange order ID (may be None initially)
            
        Returns:
            Created InFlightEntry
        """
        with self._lock:
            entry = InFlightEntry(
                rid=rid,
                symbol=symbol,
                client_order_id=client_order_id,
                exchange_order_id=exchange_order_id,
            )
            self._entries[rid] = entry
            
            if symbol not in self._by_symbol:
                self._by_symbol[symbol] = set()
            self._by_symbol[symbol].add(rid)
            
            if self.config.verbose_logging:
                LOG.info(f"[{symbol}] Registered in-flight: rid={rid}, coid={client_order_id}")
            
            return entry
    
    def update_order_id(
        self,
        rid: str,
        client_order_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
    ) -> bool:
        """
        Update order IDs for an in-flight entry.
        
        Args:
            rid: Request ID
            client_order_id: Client order ID
            exchange_order_id: Exchange order ID
            
        Returns:
            True if entry was found and updated
        """
        with self._lock:
            entry = self._entries.get(rid)
            if not entry:
                return False
            
            if client_order_id:
                entry.client_order_id = client_order_id
            if exchange_order_id:
                entry.exchange_order_id = exchange_order_id
            
            return True
    
    def has_in_flight(self, symbol: str) -> bool:
        """
        Check if symbol has any non-expired in-flight orders.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            True if there's at least one in-flight order
        """
        with self._lock:
            rids = self._by_symbol.get(symbol, set())
            for rid in rids:
                entry = self._entries.get(rid)
                if entry and not entry.is_terminal:
                    return True
            return False
    
    def get_in_flight(self, symbol: str) -> List[InFlightEntry]:
        """
        Get all in-flight entries for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            List of in-flight entries
        """
        with self._lock:
            rids = self._by_symbol.get(symbol, set())
            return [
                self._entries[rid]
                for rid in rids
                if rid in self._entries and not self._entries[rid].is_terminal
            ]
    
    def mark_terminal(
        self,
        rid: str,
        status: InFlightStatus,
        reason: str = "",
    ) -> bool:
        """
        Mark an in-flight entry as terminal.
        
        Args:
            rid: Request ID
            status: Terminal status
            reason: Reason for terminal status
            
        Returns:
            True if entry was found and marked
        """
        with self._lock:
            entry = self._entries.get(rid)
            if not entry:
                return False
            
            old_status = entry.status
            entry.status = status
            
            if self.config.verbose_logging:
                LOG.info(
                    f"[{entry.symbol}] Marked terminal: rid={rid}, "
                    f"{old_status.name} -> {status.name} ({reason})"
                )
            
            return True
    
    def clear(self, rid: str) -> bool:
        """
        Clear an in-flight entry.
        
        Args:
            rid: Request ID
            
        Returns:
            True if entry was found and cleared
        """
        with self._lock:
            entry = self._entries.pop(rid, None)
            if not entry:
                return False
            
            if entry.symbol in self._by_symbol:
                self._by_symbol[entry.symbol].discard(rid)
            
            if self.config.verbose_logging:
                LOG.info(f"[{entry.symbol}] Cleared in-flight: rid={rid}")
            
            return True
    
    def get_expired_entries(self) -> List[InFlightEntry]:
        """
        Get entries that have exceeded TTL and need reconciliation.
        
        Returns:
            List of expired entries
        """
        now = time.time()
        expired = []
        
        with self._lock:
            for entry in self._entries.values():
                if entry.is_terminal:
                    continue
                
                age = now - entry.created_ts
                
                # Check if TTL expired
                if age >= self.config.inflight_ttl_sec:
                    # Check if reconciliation is due
                    time_since_reconcile = now - entry.last_reconcile_ts
                    if time_since_reconcile >= self.config.reconcile_interval_sec:
                        expired.append(entry)
        
        return expired
    
    async def reconcile_entry(self, entry: InFlightEntry) -> ReconcileResult:
        """
        Reconcile a single in-flight entry via REST API.
        
        Args:
            entry: Entry to reconcile
            
        Returns:
            ReconcileResult
        """
        old_status = entry.status
        entry.last_reconcile_ts = time.time()
        entry.reconcile_attempts += 1
        
        # Check if max TTL exceeded (force cleanup)
        if entry.age_sec >= self.config.max_ttl_sec:
            entry.status = InFlightStatus.TTL_EXPIRED
            self.clear(entry.rid)
            
            LOG.warning(
                f"[{entry.symbol}] FORCE_CLEAR: rid={entry.rid} exceeded max TTL "
                f"({entry.age_sec:.1f}s > {self.config.max_ttl_sec}s)"
            )
            
            return ReconcileResult(
                rid=entry.rid,
                symbol=entry.symbol,
                old_status=old_status,
                new_status=InFlightStatus.TTL_EXPIRED,
                reason=f"Max TTL exceeded ({self.config.max_ttl_sec}s)",
                cleared=True,
            )
        
        # Try to check order status via REST
        if not self._checker:
            LOG.warning(f"[{entry.symbol}] No exchange checker configured for reconciliation")
            return ReconcileResult(
                rid=entry.rid,
                symbol=entry.symbol,
                old_status=old_status,
                new_status=InFlightStatus.ERROR,
                reason="No exchange checker configured",
                cleared=False,
            )
        
        try:
            order_info = await self._checker.get_order_status(
                symbol=entry.symbol,
                client_order_id=entry.client_order_id,
                exchange_order_id=entry.exchange_order_id,
            )
            
            if order_info is None:
                # Order not found on exchange
                entry.status = InFlightStatus.NOT_FOUND
                self.clear(entry.rid)
                
                LOG.info(
                    f"[{entry.symbol}] Order not found on exchange: rid={entry.rid}, "
                    f"coid={entry.client_order_id} - clearing in-flight"
                )
                
                return ReconcileResult(
                    rid=entry.rid,
                    symbol=entry.symbol,
                    old_status=old_status,
                    new_status=InFlightStatus.NOT_FOUND,
                    reason="Order not found on exchange",
                    cleared=True,
                )
            
            # Parse exchange status
            exchange_status = str(order_info.get("status", "")).upper()
            new_status = self._map_exchange_status(exchange_status)
            
            entry.status = new_status
            cleared = new_status in TERMINAL_STATUSES
            
            if cleared:
                self.clear(entry.rid)
                LOG.info(
                    f"[{entry.symbol}] Reconciled to terminal: rid={entry.rid}, "
                    f"exchange_status={exchange_status} -> {new_status.name}"
                )
            else:
                LOG.debug(
                    f"[{entry.symbol}] Reconciled (still pending): rid={entry.rid}, "
                    f"exchange_status={exchange_status}"
                )
            
            return ReconcileResult(
                rid=entry.rid,
                symbol=entry.symbol,
                old_status=old_status,
                new_status=new_status,
                reason=f"Exchange status: {exchange_status}",
                cleared=cleared,
            )
            
        except Exception as e:
            LOG.warning(
                f"[{entry.symbol}] Reconciliation failed for rid={entry.rid}: {e}"
            )
            
            return ReconcileResult(
                rid=entry.rid,
                symbol=entry.symbol,
                old_status=old_status,
                new_status=InFlightStatus.ERROR,
                reason=f"Reconciliation error: {e}",
                cleared=False,
            )
    
    async def reconcile_all_expired(self) -> List[ReconcileResult]:
        """
        Reconcile all expired in-flight entries.
        
        Returns:
            List of reconciliation results
        """
        expired = self.get_expired_entries()
        
        if not expired:
            return []
        
        LOG.info(f"Reconciling {len(expired)} expired in-flight entries...")
        
        results = []
        for entry in expired:
            result = await self.reconcile_entry(entry)
            results.append(result)
        
        return results
    
    def _map_exchange_status(self, status: str) -> InFlightStatus:
        """Map Binance order status to InFlightStatus."""
        status = status.upper()
        
        if status == "FILLED":
            return InFlightStatus.FILLED
        elif status in ("CANCELED", "CANCELLED"):
            return InFlightStatus.CANCELED
        elif status == "EXPIRED":
            return InFlightStatus.EXPIRED
        elif status == "REJECTED":
            return InFlightStatus.REJECTED
        elif status in ("NEW", "PARTIALLY_FILLED", "PENDING_CANCEL"):
            return InFlightStatus.PENDING
        else:
            LOG.warning(f"Unknown exchange status: {status}")
            return InFlightStatus.PENDING
    
    def cleanup_terminal(self) -> int:
        """
        Clean up all terminal entries.
        
        Returns:
            Number of entries cleaned up
        """
        cleaned = 0
        
        with self._lock:
            terminal_rids = [
                rid for rid, entry in self._entries.items()
                if entry.is_terminal
            ]
            
            for rid in terminal_rids:
                if self.clear(rid):
                    cleaned += 1
        
        if cleaned:
            LOG.info(f"Cleaned up {cleaned} terminal in-flight entries")
        
        return cleaned
    
    def stats(self) -> Dict[str, Any]:
        """Get reconciler statistics."""
        with self._lock:
            total = len(self._entries)
            pending = sum(1 for e in self._entries.values() if e.status == InFlightStatus.PENDING)
            terminal = sum(1 for e in self._entries.values() if e.is_terminal)
            by_symbol = {
                symbol: len(rids)
                for symbol, rids in self._by_symbol.items()
            }
            
            return {
                "total": total,
                "pending": pending,
                "terminal": terminal,
                "by_symbol": by_symbol,
            }
