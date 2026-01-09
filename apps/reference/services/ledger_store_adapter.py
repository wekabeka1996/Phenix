"""
Ledger-backed StoreProtocol adapter for OrderGuardian.

Maps OrderGuardian's key-value access pattern onto OrderLedger (SQLite).

Supported keys:
- "order:{order_id}" -> order metadata dict (symbol, type, reduce_only/close_position, parent_entry_id, client_order_id, kind)
- "client:{client_order_id}" -> mapped order_id (str) or None
- "entry:{entry_order_id}" -> entry data dict with "brackets" mapping {sl|tp}

Notes:
- We infer bracket-ness from OrderRole (SL/TP) and expose reduce_only/close_position=True for compatibility.
- Parent linkage is reconstructed via entry_client_id -> entry order_id.
"""

from __future__ import annotations

from typing import Any, Optional

from apps.reference.domains.execution_position.infra.order_ledger import (
    OrderLedger,
    OrderRecord,
    OrderRole,
    OrderStatus,
)


class LedgerStoreAdapter:
    """Adapter implementing StoreProtocol over OrderLedger."""

    def __init__(self, ledger: OrderLedger):
        self.ledger = ledger

    # --- StoreProtocol API ---
    def get(self, key: str) -> Any:
        if key.startswith("order:"):
            order_id = key.split(":", 1)[1]
            return self._get_order_meta(order_id)
        if key.startswith("client:"):
            client_id = key.split(":", 1)[1]
            rec = self.ledger.get_order_by_client_id(client_id)
            return rec.order_id if rec else None
        if key.startswith("entry:"):
            entry_order_id = key.split(":", 1)[1]
            return self._get_entry_data(entry_order_id)
        return None

    def put(self, key: str, value: Any) -> None:
        # We only persist meaningful keys; others are no-ops for compatibility.
        if key.startswith("order:"):
            order_id = key.split(":", 1)[1]
            self._upsert_order(order_id, value)
        else:
            # "client:" and "entry:" keys are derived from order rows; ignore.
            return

    def delete(self, key: str) -> None:
        # Not required for current Guardian usage; keep no-op for idempotency.
        return

    # --- Helpers ---
    def _get_order_meta(self, order_id: str) -> Optional[dict[str, Any]]:
        rec = self.ledger.get_order_by_order_id(order_id)
        if not rec:
            return None

        # Determine parent entry order_id from entry_client_id
        parent_entry_id = None
        if rec.entry_client_id:
            entry_rec = self.ledger.get_order_by_client_id(rec.entry_client_id)
            parent_entry_id = entry_rec.order_id if entry_rec else None

        kind = None
        if rec.role == OrderRole.SL:
            kind = "SL"
        elif rec.role == OrderRole.TP:
            kind = "TP"

        # Expose reduce_only/close_position for Guardian compatibility
        is_bracket = rec.role in (OrderRole.SL, OrderRole.TP)
        meta = {
            "symbol": rec.symbol,
            "type": rec.order_type,
            "reduce_only": True if is_bracket else False,
            "close_position": True if is_bracket else False,
            "parent_entry_id": parent_entry_id,
            "client_order_id": rec.client_order_id,
        }
        if kind:
            meta["kind"] = kind
        return meta

    def _get_entry_data(self, entry_order_id: str) -> Optional[dict[str, Any]]:
        entry_rec = self.ledger.get_order_by_order_id(entry_order_id)
        if not entry_rec:
            return None

        # Fetch brackets linked by entry_client_id
        brackets: dict[str, dict[str, Any]] = {}
        if entry_rec.client_order_id:
            for br in self.ledger.get_brackets_for_entry(entry_rec.client_order_id):
                if br.role == OrderRole.SL:
                    brackets["sl"] = {
                        "order_id": br.order_id,
                        "client_order_id": br.client_order_id,
                        "ts": br.created_at,
                    }
                elif br.role == OrderRole.TP:
                    brackets["tp"] = {
                        "order_id": br.order_id,
                        "client_order_id": br.client_order_id,
                        "ts": br.created_at,
                    }

        return {
            "symbol": entry_rec.symbol,
            "side": entry_rec.side,
            "qty": None,  # Not tracked in current ledger; optional for Guardian
            "ts": entry_rec.created_at,
            "brackets": brackets,
        }

    def _upsert_order(self, order_id: str, meta: dict[str, Any]) -> None:
        symbol = meta.get("symbol") or ""
        side = meta.get("side") or ""
        order_type = meta.get("type") or meta.get("order_type") or "MARKET"
        client_order_id = meta.get("client_order_id") or ""
        parent_entry_id = meta.get("parent_entry_id")

        # Determine role
        kind = (meta.get("kind") or "").upper()
        if kind == "SL":
            role = OrderRole.SL
        elif kind == "TP":
            role = OrderRole.TP
        else:
            role = OrderRole.ENTRY

        # For brackets, we prefer linking by entry_client_id. If we only have parent_entry_id,
        # try to resolve its client_order_id from ledger.
        entry_client_id = meta.get("entry_client_id")
        if not entry_client_id and parent_entry_id:
            parent_rec = self.ledger.get_order_by_order_id(str(parent_entry_id))
            entry_client_id = parent_rec.client_order_id if parent_rec else None

        record = OrderRecord(
            order_id=str(order_id),
            client_order_id=str(client_order_id) if client_order_id else str(order_id),
            symbol=symbol,
            side=side,
            order_type=str(order_type),
            status=OrderStatus.ACTIVE,
            role=role,
            entry_client_id=entry_client_id,
        )
        self.ledger.register_order(record)

