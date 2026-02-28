"""
Typed payload schemas — Phase 14C.

Pydantic models for opt-in type-safe access to Message.pld.
Does NOT change Message.pld (Dict[str, Any]) — backward compatible.

Usage:
    payload = msg.typed_payload(OpenPayload)
    assert payload.symbol == "BTCUSDT"

Registry-first: every verb here must exist in verb_registry_v1.yaml.
"""
from __future__ import annotations

from typing import Dict, Literal, Optional, Tuple, Type
from pydantic import BaseModel, Field


class OpenPayload(BaseModel):
    """DEC:OPEN / CMD:OPEN — initiate a new position."""

    symbol: str
    side: Literal["BUY", "SELL"]
    qty: float = Field(gt=0)
    price: Optional[float] = Field(default=None, gt=0)
    reduce_only: bool = False
    model_config = {"extra": "ignore"}


class ClosePayload(BaseModel):
    """DEC:CLOSE / CMD:CLOSE — close an existing position."""

    symbol: str
    reason: str
    reduce_only: bool = True
    model_config = {"extra": "ignore"}


class FillPayload(BaseModel):
    """EVT:FILL — exchange fill notification."""

    order_id: str
    symbol: str
    qty: float = Field(gt=0)
    price: float = Field(gt=0)
    ts_fill: int
    side: Optional[Literal["BUY", "SELL"]] = None
    model_config = {"extra": "ignore"}


class CancelPayload(BaseModel):
    """CMD:CANCEL — cancel a pending order."""

    order_id: str
    symbol: str
    reason: str = "user_request"
    model_config = {"extra": "ignore"}


class RejectPayload(BaseModel):
    """ERR:REJECT — decision or execution rejection."""

    reason_code: str
    message: str
    symbol: Optional[str] = None
    model_config = {"extra": "ignore"}


class ReconcilePayload(BaseModel):
    """EVT:RECONCILE — position reconciliation result."""

    symbol: str
    internal_qty: Optional[float] = None
    external_qty: Optional[float] = None
    status: Literal["MATCH", "DIVERGED", "MISSING_LOCAL", "MISSING_EXTERNAL"]
    model_config = {"extra": "ignore"}


# Phase 14.4: Discriminated union — maps (op, verb) to Payload class.
# Registry-first: verbs here map to entries in verb_registry_v1.yaml.
VERB_PAYLOAD_MAP: Dict[Tuple[str, str], Type[BaseModel]] = {
    ("DEC", "OPEN"): OpenPayload,
    ("CMD", "OPEN"): OpenPayload,
    ("DEC", "CLOSE"): ClosePayload,
    ("CMD", "CLOSE"): ClosePayload,
    ("EVT", "FILL"): FillPayload,
    ("EVT", "ORDER_FILL"): FillPayload,
    ("CMD", "CANCEL"): CancelPayload,
    ("DEC", "CANCEL"): CancelPayload,
    ("ERR", "REJECT"): RejectPayload,
    ("EVT", "REJECTED"): RejectPayload,
    ("EVT", "RECONCILE"): ReconcilePayload,
}


def resolve_payload_cls(op: str, verb: str) -> Optional[Type[BaseModel]]:
    """Look up Payload class for (op, verb). Returns None if unmapped."""
    return VERB_PAYLOAD_MAP.get((op, verb))
