from __future__ import annotations

import hashlib
import json
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

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


class LLMCloseRequestV1(BaseModel):
    """HTTP POST /positions/{lifecycle_id}/close request schema."""

    model_config = ConfigDict(extra="forbid")

    request_kind: Literal["close_position"] = "close_position"
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    lifecycle_id: str = Field(min_length=1)
    symbol: str = Field(min_length=2, max_length=20)
    reason: str = Field(min_length=1, max_length=120)
    qty: Optional[str] = None
    model_meta: Optional[LLMModelMetaV1] = None
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=256)

    @field_validator("symbol")
    @classmethod
    def _normalize_close_symbol(cls, v: str) -> str:
        return str(v).upper().strip()

    @field_validator("qty")
    @classmethod
    def _validate_close_qty(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        d = Decimal(str(v))
        if not d.is_finite() or d <= 0:
            raise ValueError("qty must be a positive finite decimal")
        return str(v)


class LLMBracketAmendV1(BaseModel):
    """New TP/SL values for live bracket amend."""

    model_config = ConfigDict(extra="forbid")

    tp_price: str
    sl_price: str

    @field_validator("tp_price", "sl_price")
    @classmethod
    def _validate_decimal_positive_required(cls, v: str) -> str:
        d = Decimal(str(v))
        if not d.is_finite() or d <= 0:
            raise ValueError("must be a positive finite decimal")
        return str(v)


class LLMBracketAmendRequestV1(BaseModel):
    """HTTP PATCH /positions/{lifecycle_id}/brackets request schema."""

    model_config = ConfigDict(extra="forbid")

    request_kind: Literal["amend_brackets"] = "amend_brackets"
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    lifecycle_id: str = Field(min_length=1)
    symbol: str = Field(min_length=2, max_length=20)
    side: Literal["BUY", "SELL"]
    brackets: LLMBracketAmendV1
    reason: str = Field(min_length=1, max_length=120)
    entry_price: Optional[str] = None
    model_meta: Optional[LLMModelMetaV1] = None
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=256)

    @field_validator("symbol")
    @classmethod
    def _normalize_amend_symbol(cls, v: str) -> str:
        return str(v).upper().strip()

    @field_validator("side")
    @classmethod
    def _normalize_amend_side(cls, v: str) -> str:
        return str(v).upper().strip()

    @field_validator("entry_price")
    @classmethod
    def _validate_optional_entry_price(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        d = Decimal(str(v))
        if not d.is_finite() or d <= 0:
            raise ValueError("entry_price must be a positive finite decimal")
        return str(v)

    @model_validator(mode="after")
    def _validate_amend_brackets_consistency(self) -> "LLMBracketAmendRequestV1":
        tp_d = Decimal(str(self.brackets.tp_price))
        sl_d = Decimal(str(self.brackets.sl_price))
        if self.entry_price is None:
            return self
        entry_d = Decimal(str(self.entry_price))
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


class CmdLlmPositionCloseV1(BaseModel):
    """Internal command payload for external LLM close requests."""

    model_config = ConfigDict(extra="forbid")

    request_kind: Literal["close_position"] = "close_position"
    request_id: Optional[str] = None
    action_id: str
    ts_ms: int
    lifecycle_id: str
    symbol: str
    reason: str
    qty: Optional[str] = None
    model_meta: Optional[LLMModelMetaV1] = None
    idempotency_key: str = Field(min_length=8, max_length=256)


class CmdLlmBracketAmendV1(BaseModel):
    """Internal command payload for external LLM bracket amend requests."""

    model_config = ConfigDict(extra="forbid")

    request_kind: Literal["amend_brackets"] = "amend_brackets"
    request_id: Optional[str] = None
    action_id: str
    ts_ms: int
    lifecycle_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    brackets: LLMBracketAmendV1
    reason: str
    entry_price: Optional[str] = None
    model_meta: Optional[LLMModelMetaV1] = None
    idempotency_key: str = Field(min_length=8, max_length=256)


class IntentAcceptedResponseV1(BaseModel):
    """Accepted response for POST /intents/llm/v1."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    request_id: str
    state: Literal["queued"] = "queued"


class PositionActionAcceptedResponseV1(BaseModel):
    """Accepted response for close and bracket amend actions."""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    request_id: str
    lifecycle_id: str
    action: Literal["close_position", "amend_brackets"]
    state: Literal["queued"] = "queued"


class ActivePositionView(BaseModel):
    """Normalized active-position view for operator and agent surfaces."""

    model_config = ConfigDict(extra="allow")

    symbol: str
    lifecycle_id: Optional[str] = None
    state: Optional[str] = None
    side: Optional[str] = None
    qty: Optional[str] = None
    entry_price: Optional[str] = None
    sl_price: Optional[str] = None
    tp_price: Optional[str] = None
    sl_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None
    closing_position: Optional[bool] = None
    last_close_reason: Optional[str] = None


class BracketStateView(BaseModel):
    """Normalized bracket-state view for an active lifecycle."""

    model_config = ConfigDict(extra="allow")

    lifecycle_id: str
    symbol: str
    sl_price: Optional[str] = None
    tp_price: Optional[str] = None
    sl_order_id: Optional[str] = None
    tp_order_id: Optional[str] = None
    entry_order_id: Optional[str] = None
    entry_client_order_id: Optional[str] = None


class RecentRejectionView(BaseModel):
    """Recent rejection record surfaced to UI and agents."""

    model_config = ConfigDict(extra="allow")

    ts_ms: Optional[int] = None
    symbol: Optional[str] = None
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    strategy_id: Optional[str] = None
    source_path: Optional[str] = None


class DecisionHistoryView(BaseModel):
    """Persisted decision history view."""

    model_config = ConfigDict(extra="allow")

    ts_ms: Optional[int] = None
    symbol: Optional[str] = None
    decision: Optional[str] = None
    confidence: Optional[float] = None
    rationale_short: Optional[str] = None
    packet_ref: Optional[str] = None
    source_path: Optional[str] = None
    gate_trace_summary: Optional[str] = None
    raw_score: Optional[float] = None


class MarketContextPacketV1(BaseModel):
    """Canonical market-context packet for the LLM orchestration loop."""

    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    packet_kind: Literal["fast", "deep", "guardian"]
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    symbol: str = Field(min_length=2, max_length=20)
    tf_sec: int = Field(default=300, ge=1)
    snapshot: Optional[Dict[str, Any]] = None
    risk_gate: Dict[str, Any] = Field(default_factory=dict)
    active_positions: List[ActivePositionView] = Field(default_factory=list)
    recent_rejections: List[RecentRejectionView] = Field(default_factory=list)
    recent_decisions: List[DecisionHistoryView] = Field(default_factory=list)
    market_overview: Optional[Dict[str, Any]] = None
    lifecycle_id: Optional[str] = None
    provenance: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _normalize_packet_symbol(cls, v: str) -> str:
        return str(v).upper().strip()


class TradingDecisionOpenPayloadV1(BaseModel):
    """Structured open-intent decision payload."""

    model_config = ConfigDict(extra="forbid")

    side: Literal["BUY", "SELL"]
    qty: str
    limit_price: str
    tp_price: str
    sl_price: str
    time_in_force: Literal["GTC"] = "GTC"


class TradingDecisionClosePayloadV1(BaseModel):
    """Structured close-position decision payload."""

    model_config = ConfigDict(extra="forbid")

    lifecycle_id: str
    reason: str = Field(min_length=1, max_length=120)
    qty: Optional[str] = None


class TradingDecisionAmendPayloadV1(BaseModel):
    """Structured bracket-amend decision payload."""

    model_config = ConfigDict(extra="forbid")

    lifecycle_id: str
    side: Literal["BUY", "SELL"]
    tp_price: str
    sl_price: str
    entry_price: Optional[str] = None
    reason: str = Field(min_length=1, max_length=120)


class TradingDecisionV1(BaseModel):
    """Canonical typed trading decision emitted by the main model."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    action: Literal["NO_ACTION", "OPEN_INTENT", "CLOSE_POSITION", "AMEND_BRACKETS"]
    symbol: str = Field(min_length=2, max_length=20)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale_short: str = Field(min_length=1, max_length=240)
    packet_ref: str = Field(min_length=1)
    ttl_ms: int = Field(ge=1000)
    open: Optional[TradingDecisionOpenPayloadV1] = None
    close: Optional[TradingDecisionClosePayloadV1] = None
    amend: Optional[TradingDecisionAmendPayloadV1] = None
    model_meta: Optional[LLMModelMetaV1] = None

    @field_validator("symbol")
    @classmethod
    def _normalize_decision_symbol(cls, v: str) -> str:
        return str(v).upper().strip()

    @model_validator(mode="after")
    def _validate_action_payload(self) -> "TradingDecisionV1":
        if self.action == "OPEN_INTENT":
            if self.open is None:
                raise ValueError("open payload is required for OPEN_INTENT")
            if self.close is not None or self.amend is not None:
                raise ValueError("OPEN_INTENT cannot carry close/amend payloads")
        elif self.action == "CLOSE_POSITION":
            if self.close is None:
                raise ValueError("close payload is required for CLOSE_POSITION")
            if self.open is not None or self.amend is not None:
                raise ValueError("CLOSE_POSITION cannot carry open/amend payloads")
        elif self.action == "AMEND_BRACKETS":
            if self.amend is None:
                raise ValueError("amend payload is required for AMEND_BRACKETS")
            if self.open is not None or self.close is not None:
                raise ValueError("AMEND_BRACKETS cannot carry open/close payloads")
        else:
            if self.open is not None or self.close is not None or self.amend is not None:
                raise ValueError("NO_ACTION must not carry execution payloads")
        return self


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


def compute_close_idempotency_key(req: LLMCloseRequestV1) -> str:
    stable = {
        "v": "close_v1",
        "symbol": req.symbol,
        "lifecycle_id": req.lifecycle_id,
        "qty": req.qty,
        "reason": req.reason,
    }
    digest = canonical_payload_hash(stable)
    return f"llm:close:{req.symbol}:{digest}"


def compute_bracket_amend_idempotency_key(req: LLMBracketAmendRequestV1) -> str:
    stable = {
        "v": "amend_v1",
        "symbol": req.symbol,
        "lifecycle_id": req.lifecycle_id,
        "side": req.side,
        "tp_price": req.brackets.tp_price,
        "sl_price": req.brackets.sl_price,
        "entry_price": req.entry_price,
    }
    digest = canonical_payload_hash(stable)
    return f"llm:amend:{req.symbol}:{digest}"


MarketContextPacketV1.model_rebuild()
TradingDecisionV1.model_rebuild()
