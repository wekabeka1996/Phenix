"""Phase 9.2: Reconstruction from order log.

This module proves that a CloseSubmissionPayload can be reconstructed
from order_log entries (rid, idempotent_key, symbol, position_amt).

Goal:
Show that when replaying from order_log on restart, we can deterministically
reconstruct what was submitted without re-executing decision logic.

Invariant:
The order_log is the source-of-truth for what was actually submitted.
Reconstruction is read-only and produces identical payloads.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from apps.reference.domains.execution_position.flows.close.close_submission_adapter import (
    CloseSubmissionPayload,
)


class OrderLogEntry:
    """Minimal order log entry for reconstruction."""

    def __init__(
        self,
        rid: str,
        symbol: str,
        idempotent_key: str,
        client_order_id: str,
        side: str,
        quantity: str,  # String representation from order_log
        partial_close: bool = False,
        source_fsm: str = "close_executor",
    ):
        self.rid = rid
        self.symbol = symbol
        self.idempotent_key = idempotent_key
        self.client_order_id = client_order_id
        self.side = side
        self.quantity = quantity  # Already string
        self.partial_close = partial_close
        self.source_fsm = source_fsm


def reconstruct_close_submission_from_order_log(
    order_log_entry: OrderLogEntry,
    position_amt: Decimal,
) -> tuple[Optional[CloseSubmissionPayload], Optional[str]]:
    """Reconstruct CloseSubmissionPayload from order_log entry.

    Args:
        order_log_entry: Entry from order_log (contains rid, symbol, idempotent_key, side, quantity, partial_close)
        position_amt: Position amount at the time of close (from restore envelope or position tracking)

    Returns:
        (CloseSubmissionPayload or None, error_reason or None)

    Semantics:
        - Side and quantity are EXACT (from order_log)
        - partial_close is EXACT (from order_log)
        - client_order_id is EXACT (from order_log)
        - position_amt is provided for context only (not used in reconstruction)
        - This is deterministic: same inputs → same output
    """
    try:
        payload = CloseSubmissionPayload(
            symbol=order_log_entry.symbol,
            side=order_log_entry.side,
            quantity=order_log_entry.quantity,
            client_order_id=order_log_entry.client_order_id,
            partial_close=order_log_entry.partial_close,
        )
        return payload, None
    except Exception as exc:
        return None, str(exc)


def reconstruct_partial_close_flag_from_side_and_position(
    position_amt: Decimal,
    quantity: str,
) -> bool:
    """Determine if this was a partial close based on position and quantity.

    Returns:
        True if quantity < |position_amt| (partial close)
        False if quantity == |position_amt| (full close)

    Note: This is a heuristic - we can't be 100% certain, but the order_log
    entry itself contains the authoritative partial_close flag.
    """
    try:
        qty = Decimal(quantity)
    except:
        return False

    if qty < abs(position_amt):
        return True
    return False
