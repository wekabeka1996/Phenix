"""
Correlation Store for Order Lifecycle Tracing

Stores correlation data for order chains (entry + SL/TP) with TTL.
Maps order_id to correlation metadata for tracing EVT:FILL back to original RID.
"""

import time
from typing import Dict, Any, Optional
from threading import Lock


class CorrelationStore:
    """
    Thread-safe store for order correlation data with TTL.

    Stores mapping: order_id -> {
        'corr_id': str,
        'parent_client_order_id': str | None,
        'oco_group_id': str,
        'rid': str,
        'timestamp': float
    }
    """

    def __init__(self, ttl_hours: float = 24.0):
        self.ttl_seconds: int = int(ttl_hours * 3600)
        self.store: Dict[str, Dict[str, Any]] = {}
        self.lock = Lock()

    def put_entry_ack(self, order_id: str, data: Dict[str, Any]) -> None:
        """
        Store correlation data for entry order ACK.

        Args:
            order_id: Exchange order ID
            data: Dict with corr_id, oco_group_id, rid, etc.
        """
        with self.lock:
            self.store[str(order_id)] = {
                **data,
                'timestamp': time.time()
            }
            self._cleanup_expired()

    def put_sl_tp_ack(self, order_id: str, parent_client_order_id: str, corr_id: str, oco_group_id: str, rid: str) -> None:
        """
        Store correlation data for SL/TP order ACK.

        Args:
            order_id: Exchange order ID for SL/TP
            parent_client_order_id: Client order ID of entry order
            corr_id: Correlation ID
            oco_group_id: OCO group ID
            rid: Request ID
        """
        with self.lock:
            self.store[str(order_id)] = {
                'corr_id': corr_id,
                'parent_client_order_id': parent_client_order_id,
                'oco_group_id': oco_group_id,
                'rid': rid,
                'timestamp': time.time()
            }
            self._cleanup_expired()

    def get_by_order_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve correlation data by order_id.

        Returns None if not found or expired.
        """
        with self.lock:
            data = self.store.get(str(order_id))
            if data and self._is_expired(data):
                del self.store[str(order_id)]
                return None
            return data

    def _is_expired(self, data: Dict[str, Any]) -> bool:
        """Check if data entry is expired."""
        return time.time() - data['timestamp'] > self.ttl_seconds

    def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired_keys = [
            k for k, v in self.store.items()
            if now - v['timestamp'] > self.ttl_seconds
        ]
        for k in expired_keys:
            del self.store[k]

    def get_stats(self) -> Dict[str, int]:
        """Return store statistics."""
        with self.lock:
            self._cleanup_expired()
            return {
                'total_entries': len(self.store),
                'ttl_seconds': self.ttl_seconds
            }
