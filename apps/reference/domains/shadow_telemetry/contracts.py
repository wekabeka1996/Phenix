from __future__ import annotations

import hashlib
import json
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LLMOrderV1(BaseModel):
    """External LLM order block (policy-enforced, Stage A allows LIMIT only)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["LIMIT", "MARKET"] = Field(default="LIMIT")
    limit_price: str = Field(description="Limit price as decimal string")
    qty: str = Field(description="Order quantity as decimal string")
    time_in_force: Literal["GTC", "IOC", "FOK"] = Field(default="GTC")

    @field_validator("limit_price", "qty")
    @classmethod
    def _validate_decimal_positive(cls, v: str) -> str:
        d = Decimal(str(v))
        if not d.is_finite() or d <= 0:
            raise ValueError("must be a positive finite decimal")
        return str(v)


class LLMBracketsV1(BaseModel):
    """Optional TP/SL block."""

    model_config = ConfigDict(extra="forbid")

    tp_price: Optional[str] = None
    sl_price: Optional[str] = None

    @field_validator("tp_price", "sl_price")
    @classmethod
    def _validate_optional_decimal(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        d = Decimal(str(v))
        if not d.is_finite() or d <= 0:
            raise ValueError("must be a positive finite decimal")
        return str(v)


class LLMSnapshotRefV1(BaseModel):
    """Reference to snapshot used by LLM for this decision."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    inputs_digest: str = Field(min_length=8, max_length=128)


class LLMModelMetaV1(BaseModel):
    """Metadata about model/prompt used for decision."""

    model_config = ConfigDict(extra="forbid")

    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    prompt_hash: Optional[str] = Field(default=None, min_length=8, max_length=128)


class LLMPolicyHintsV1(BaseModel):
    """Optional policy hints from caller."""

    model_config = ConfigDict(extra="forbid")

    max_slippage_bps: Optional[int] = Field(default=None, ge=0)
    expiry_ts_ms: Optional[int] = None
    risk_tag: Optional[str] = None


class LLMIntentRequestV1(BaseModel):
    """HTTP POST /intents/llm/v1 request schema."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    symbol: str = Field(min_length=2, max_length=20)
    side: Literal["BUY", "SELL"]
    order: LLMOrderV1
    brackets: LLMBracketsV1 = Field(default_factory=LLMBracketsV1)
    snapshot_ref: Optional[LLMSnapshotRefV1] = None
    model_meta: Optional[LLMModelMetaV1] = None
    why_short: str = Field(min_length=1, max_length=80)
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=256)
    policy_hints: Optional[LLMPolicyHintsV1] = None

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, v: str) -> str:
        return str(v).upper().strip()

    @field_validator("side")
    @classmethod
    def _normalize_side(cls, v: str) -> str:
        return str(v).upper().strip()

    @model_validator(mode="after")
    def _validate_brackets_consistency(self) -> "LLMIntentRequestV1":
        tp = self.brackets.tp_price
        sl = self.brackets.sl_price
        if tp is not None and sl is not None:
            tp_d = Decimal(str(tp))
            sl_d = Decimal(str(sl))
            entry_d = Decimal(str(self.order.limit_price))
            if self.side == "BUY" and not (sl_d < entry_d < tp_d):
                raise ValueError("BUY brackets must satisfy sl < entry < tp")
            if self.side == "SELL" and not (tp_d < entry_d < sl_d):
                raise ValueError("SELL brackets must satisfy tp < entry < sl")
        return self


class CmdLlmIntentSubmitV1(BaseModel):
    """Internal command payload delivered over IPC to main process."""

    model_config = ConfigDict(extra="forbid")

    request_id: Optional[str] = None
    intent_id: str
    ts_ms: int
    symbol: str
    side: Literal["BUY", "SELL"]
    order: LLMOrderV1
    brackets: LLMBracketsV1 = Field(default_factory=LLMBracketsV1)
    snapshot_ref: Optional[LLMSnapshotRefV1] = None
    model_meta: Optional[LLMModelMetaV1] = None
    why_short: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=256)
    policy_hints: Optional[LLMPolicyHintsV1] = None


class IntentAcceptedResponseV1(BaseModel):
    """Accepted response for POST /intents/llm/v1."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    request_id: str
    state: Literal["queued"] = "queued"


def canonical_payload_hash(payload: Dict[str, Any]) -> str:
    """Return stable sha256 hash for payload dedupe."""

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_idempotency_key(req: LLMIntentRequestV1) -> str:
    """Generate deterministic idempotency key from stable fields."""

    stable = {
        "v": "v1",
        "symbol": req.symbol,
        "side": req.side,
        "type": req.order.type,
        "limit_price": req.order.limit_price,
        "qty": req.order.qty,
        "tp": req.brackets.tp_price,
        "sl": req.brackets.sl_price,
        "snapshot_id": req.snapshot_ref.snapshot_id if req.snapshot_ref else None,
        "inputs_digest": req.snapshot_ref.inputs_digest if req.snapshot_ref else None,
        "expiry_ts_ms": req.policy_hints.expiry_ts_ms if req.policy_hints else None,
    }
    digest = canonical_payload_hash(stable)
    return f"llm:v1:{req.symbol}:{digest}"
