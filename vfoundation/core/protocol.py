from __future__ import annotations
import warnings
from typing import List, Optional, Literal, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
import time
from decimal import Decimal
import uuid

from vfoundation.core.data_ref import DataRef, coerce_data_ref

Op = Literal["ASK", "DEC", "CMD", "EVT", "UPD", "ERR"]
IntentType = Literal["INQUIRY", "COMMAND", "PROPOSAL", "OBSERVATION", "DECLARATION"]


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
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_encoders={
            Decimal: float  # Automatically serialize Decimals in pld/etc to float (JSON compliant)
        }
    )

    v: int = 1
    op: Op
    verb: str
    src: str
    dst: str | Literal["any"]
    rid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    parent_span_id: Optional[str] = None
    ts: int = Field(default_factory=lambda: int(time.time() * 1000))
    ttl_ms: int = 2000
    key: Optional[str] = None
    idempotent_key: Optional[str] = None  # New field for TTL-based idempotency
    pld: Dict[str, Any] = Field(default_factory=dict)
    why: Optional[str] = None
    why_explain_ref: Optional[str] = None
    intent: Optional[IntentType] = None  # Message intent classification (v2.2)
    data_ref: List[Any] = Field(default_factory=list)  # Union[str, DataRef] per §5.2
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

    @field_validator("data_ref", mode="before")
    @classmethod
    def _coerce_data_ref(cls, v: Any) -> Any:
        """Coerce data_ref elements: str passthrough, dict → DataRef."""
        if not isinstance(v, list):
            return v
        return [coerce_data_ref(item) for item in v]

    # Phase 14.3: Deprecation warnings for trading-specific envelope fields
    _DEPRECATED_ENVELOPE_FIELDS = ("oco_group_id", "parent_client_order_id", "link_ack_id", "link_fill_id")

    @model_validator(mode="after")
    def _warn_deprecated_envelope_fields(self) -> "Message":
        """Emit DeprecationWarning when trading-specific top-level fields are set."""
        for field_name in self._DEPRECATED_ENVELOPE_FIELDS:
            val = getattr(self, field_name, None)
            if val is not None:
                warnings.warn(
                    f"Message.{field_name} is deprecated at top-level. "
                    f"Migrate to pld['{field_name}']. Removal target: v2.0.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                break  # Warn once per Message, not per field
        return self

    def is_expired(self) -> bool:
        return (int(time.time() * 1000) - self.ts) > self.ttl_ms

    def typed_payload(self, schema_cls: type) -> Any:
        """
        Parse pld as typed Pydantic schema.

        Args:
            schema_cls: Pydantic BaseModel subclass from vfoundation.core.payloads

        Returns:
            Validated schema_cls instance.

        Raises:
            pydantic.ValidationError: if pld doesn't match schema.
        """
        return schema_cls(**self.pld)

    def validate_pld(self) -> Any:
        """Validate pld against VERB_PAYLOAD_MAP. Returns Payload or None.

        Looks up the Payload class for (self.op, self.verb) in the
        discriminated union map.  Returns a validated Payload instance,
        or ``None`` when the (op, verb) pair has no registered schema.

        Raises:
            pydantic.ValidationError: if pld doesn't match the resolved schema.
        """
        from vfoundation.core.payloads import resolve_payload_cls
        cls = resolve_payload_cls(self.op, self.verb)
        if cls is None:
            return None
        return cls(**self.pld)
