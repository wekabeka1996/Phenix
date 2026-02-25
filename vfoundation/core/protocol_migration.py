"""
Protocol migration helpers — Phase 14C.

Allows transparent migration of Message.pld from V1 (flat, informal)
to V2 (structured, schemas).

Constitution v2.2 §9: all protocol upgrades must be backward compatible.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from vfoundation.core.protocol import Message


def is_v2_message(msg: Message) -> bool:
    """Return True if message payload is already V2."""
    return msg.pld.get("v") == 2


def migrate_pld_v1_to_v2(msg: Message) -> None:
    """
    In-place migration of msg.pld to V2 format.
    
    If already V2 or unsupported verb, does nothing.
    """
    if is_v2_message(msg):
        return

    # Mappings based on Phase 14 requirements and legacy usage
    if msg.verb == "OPEN":
        # sym -> symbol, q -> qty
        if "sym" in msg.pld:
            msg.pld["symbol"] = msg.pld.pop("sym")
        if "q" in msg.pld:
            msg.pld["qty"] = msg.pld.pop("q")
        msg.pld["v"] = 2

    elif msg.verb == "FILL":
        # oid -> order_id, p -> price
        if "oid" in msg.pld:
            msg.pld["order_id"] = msg.pld.pop("oid")
        if "p" in msg.pld:
            msg.pld["price"] = msg.pld.pop("p")
        msg.pld["v"] = 2
        
    # Add other verbs as needed during decomposition
