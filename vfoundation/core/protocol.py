from __future__ import annotations
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator
import time
import uuid

Op = Literal["ASK", "DEC", "CMD", "EVT", "UPD", "ERR"]


def truncate_why(why_text: Optional[str], max_len: int = 80) -> Optional[str]:
    """Truncate why field to max_len to comply with Message validation.

    Usage in bridge: why = truncate_why(long_why_string)
    """
    if why_text is None:
        return None
    if len(why_text) <= max_len:
        return why_text
    return why_text[:max_len]


class Message(BaseModel):
    v: int = 1
    op: Op
    verb: str
    src: str
    dst: str | Literal["any"]
    rid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    parent_span_id: Optional[str] = None
    parent_rid: Optional[str] = None  # Parent message RID for WHY-chain
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))
    ttl_ms: int = 2000
    key: Optional[str] = None
    idempotent_key: Optional[str] = None  # New field for TTL-based idempotency
    pld: Dict[str, Any] = Field(default_factory=dict)
    why: Optional[str] = None
    why_explain_ref: Optional[str] = None
    data_ref: List[str] = Field(default_factory=list)
    sig: Optional[str] = None
    mode: str = "live"  # Domain-level trading mode: live, backtest, paper
    # Mode-specific validation rule identifier
    mode_contract: Optional[str] = None
    corr_id: Optional[str] = None  # Correlation ID for order lifecycle tracing
    oco_group_id: Optional[str] = None  # OCO group ID for entry + SL/TP orders
    # Parent client order ID for SL/TP orders
    parent_client_order_id: Optional[str] = None
    link_ack_id: Optional[str] = None  # Link to exchange ACK order_id
    link_fill_id: Optional[str] = None  # Link to fill order_id for correlation

    @field_validator("ttl_ms")
    @classmethod
    def _ttl_positive(cls, v: int) -> int:
        if v <= 0 or v > 30000:
            raise ValueError("ttl_ms out of allowed range (1..30000)")
        return v

    @field_validator("why")
    @classmethod
    def _why_len(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 80:
            raise ValueError("why must be <=80 chars")
        return v

    def is_expired(self) -> bool:
        return (int(time.time() * 1000) - self.ts) > self.ttl_ms

    @classmethod
    def from_parent(cls, parent: "Message", **kwargs) -> "Message":
        """Створити повідомлення з автоматичним parent_rid."""
        return cls(
            parent_rid=parent.rid,
            parent_span_id=parent.span_id,
            data_ref=parent.data_ref + [parent.rid],  # WHY-chain
            **kwargs
        )
