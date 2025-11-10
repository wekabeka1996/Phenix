"""
FSMP-P1-T02: Order Ledger Repository
SQLite-based storage for order ownership tracking and cleanup coordination.

Schema:
- orders table: order_id (PK), client_order_id, symbol, side, order_type,
  status, role (ENTRY|SL|TP), entry_client_id (FK to ENTRY), created_at, updated_at
- Indexes: order_id, client_order_id, symbol+role, entry_client_id
"""

import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, List, Optional
from contextlib import contextmanager
import logging

LOG = logging.getLogger(__name__)


class OrderRole(str, Enum):
    """Order roles in the system"""
    ENTRY = "ENTRY"
    SL = "SL"
    TP = "TP"


class OrderStatus(str, Enum):
    """Order statuses"""
    PENDING = "PENDING"      # Placed but not yet ACKed
    ACTIVE = "ACTIVE"        # ACKed and active
    CANCELLED = "CANCELLED"  # Cancelled by system
    FILLED = "FILLED"        # Executed
    REJECTED = "REJECTED"    # Rejected by exchange
    EXPIRED = "EXPIRED"      # Expired
    UNKNOWN = "UNKNOWN"      # Status unknown


@dataclass
class OrderRecord:
    """Order record in ledger"""
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    status: OrderStatus
    role: OrderRole
    entry_client_id: Optional[str] = None  # For SL/TP brackets
    created_at: float = None
    updated_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.updated_at is None:
            self.updated_at = time.time()


class OrderLedger:
    """
    SQLite-based order ledger for tracking order ownership and relationships.

    Thread-safe with connection pooling and proper transaction handling.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._local = threading.local()  # Thread-local storage for connections
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Get thread-local database connection"""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        try:
            yield self._local.conn
        except Exception:
            if hasattr(self._local, 'conn'):
                self._local.conn.rollback()
            raise
        finally:
            # Don't close - keep connection alive for thread
            pass

    def _init_db(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    client_order_id TEXT UNIQUE NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    role TEXT NOT NULL,
                    entry_client_id TEXT,  -- FK to ENTRY order's client_order_id
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)

            # Indexes for performance
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_client_order_id ON orders(client_order_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbol_role ON orders(symbol, role)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entry_client_id ON orders(entry_client_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_status ON orders(status)")
            conn.commit()

    def register_order(self, record: OrderRecord) -> None:
        """Register or update order in ledger"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO orders
                (order_id, client_order_id, symbol, side, order_type, status, role, entry_client_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.order_id,
                record.client_order_id,
                record.symbol,
                record.side,
                record.order_type,
                record.status.value,
                record.role.value,
                record.entry_client_id,
                record.created_at,
                record.updated_at
            ))
            conn.commit()

        LOG.debug(
            f"[LEDGER] Registered order: {record.client_order_id} -> {record.order_id} ({record.role.value})")

    def get_order_by_client_id(self, client_order_id: str) -> Optional[OrderRecord]:
        """Get order by client order ID"""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE client_order_id = ?",
                (client_order_id,)
            ).fetchone()

        if row:
            return OrderRecord(
                order_id=row['order_id'],
                client_order_id=row['client_order_id'],
                symbol=row['symbol'],
                side=row['side'],
                order_type=row['order_type'],
                status=OrderStatus(row['status']),
                role=OrderRole(row['role']),
                entry_client_id=row['entry_client_id'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
        return None

    def get_order_by_order_id(self, order_id: str) -> Optional[OrderRecord]:
        """Get order by exchange order ID"""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ?",
                (order_id,)
            ).fetchone()

        if row:
            return OrderRecord(
                order_id=row['order_id'],
                client_order_id=row['client_order_id'],
                symbol=row['symbol'],
                side=row['side'],
                order_type=row['order_type'],
                status=OrderStatus(row['status']),
                role=OrderRole(row['role']),
                entry_client_id=row['entry_client_id'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
        return None

    def get_brackets_for_entry(self, entry_client_id: str) -> List[OrderRecord]:
        """Get all bracket orders (SL/TP) for a given entry order"""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE entry_client_id = ? AND role IN ('SL', 'TP')",
                (entry_client_id,)
            ).fetchall()

        return [
            OrderRecord(
                order_id=row['order_id'],
                client_order_id=row['client_order_id'],
                symbol=row['symbol'],
                side=row['side'],
                order_type=row['order_type'],
                status=OrderStatus(row['status']),
                role=OrderRole(row['role']),
                entry_client_id=row['entry_client_id'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            for row in rows
        ]

    def get_active_orders_for_symbol(self, symbol: str) -> List[OrderRecord]:
        """Get all active (non-terminal) orders for a symbol"""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE symbol = ? AND status NOT IN ('CANCELLED', 'FILLED', 'REJECTED', 'EXPIRED')",
                (symbol,)
            ).fetchall()

        return [
            OrderRecord(
                order_id=row['order_id'],
                client_order_id=row['client_order_id'],
                symbol=row['symbol'],
                side=row['side'],
                order_type=row['order_type'],
                status=OrderStatus(row['status']),
                role=OrderRole(row['role']),
                entry_client_id=row['entry_client_id'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            for row in rows
        ]

    def update_order_status(self, order_id: str, new_status: OrderStatus) -> bool:
        """Update order status"""
        with self._get_connection() as conn:
            result = conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?",
                (new_status.value, time.time(), order_id)
            )
            conn.commit()
            return result.rowcount > 0

    def update_order_status_by_client_id(self, client_order_id: str, new_status: OrderStatus) -> bool:
        """Update order status by client order ID"""
        with self._get_connection() as conn:
            result = conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE client_order_id = ?",
                (new_status.value, time.time(), client_order_id)
            )
            conn.commit()
            return result.rowcount > 0

    def get_orphaned_brackets(self, symbol: str) -> List[OrderRecord]:
        """Get bracket orders that may be orphaned (no active entry)"""
        with self._get_connection() as conn:
            # Find brackets where entry order is terminal or missing
            rows = conn.execute("""
                SELECT b.* FROM orders b
                LEFT JOIN orders e ON b.entry_client_id = e.client_order_id
                WHERE b.symbol = ? AND b.role IN ('SL', 'TP')
                  AND (e.client_order_id IS NULL OR e.status IN ('CANCELLED', 'FILLED', 'REJECTED', 'EXPIRED'))
            """, (symbol,)).fetchall()

        return [
            OrderRecord(
                order_id=row['order_id'],
                client_order_id=row['client_order_id'],
                symbol=row['symbol'],
                side=row['side'],
                order_type=row['order_type'],
                status=OrderStatus(row['status']),
                role=OrderRole(row['role']),
                entry_client_id=row['entry_client_id'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            for row in rows
        ]

    def cleanup_old_records(self, max_age_days: int = 30) -> int:
        """Clean up old terminal records"""
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        with self._get_connection() as conn:
            result = conn.execute(
                "DELETE FROM orders WHERE status IN ('CANCELLED', 'FILLED', 'REJECTED', 'EXPIRED') AND updated_at < ?",
                (cutoff_time,)
            )
            conn.commit()
            return result.rowcount

    def get_stats(self) -> Dict[str, Any]:
        """Get ledger statistics"""
        with self._get_connection() as conn:
            stats = {}
            # Count by status
            rows = conn.execute(
                "SELECT status, COUNT(*) as count FROM orders GROUP BY status"
            ).fetchall()
            stats['by_status'] = {row['status']: row['count'] for row in rows}

            # Count by role
            rows = conn.execute(
                "SELECT role, COUNT(*) as count FROM orders GROUP BY role"
            ).fetchall()
            stats['by_role'] = {row['role']: row['count'] for row in rows}

            # Total count
            row = conn.execute(
                "SELECT COUNT(*) as total FROM orders").fetchone()
            stats['total'] = row['total']

            return stats
