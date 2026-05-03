"""Typed execution-side bridge for CMD:CLOSE -> DEC:CLOSE.

This module owns only the bounded producer-side close seam between the
incoming explicit close command and the emitted execution decision payload.

Scope:
- typed CMD:CLOSE intake normalization;
- typed DEC:CLOSE emission payload ownership;
- explicit preservation / normalization of close bridge fields;
- stable idempotent-key propagation without ad hoc time-based regeneration.

Out of scope:
- close execution, bracket teardown, exchange-position reads, reconcile,
  and any Package 5 downstream submission ownership.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Literal, Optional
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field

from vfoundation.core.protocol import Message, truncate_why


CLOSE_PRODUCER_BRIDGE_CONTRACT = "close_producer_bridge_v1"
CLOSE_PRODUCER_BRIDGE_PATH = "CMD:CLOSE->DEC:CLOSE"
_CLOSE_PRODUCER_BRIDGE_TRACE_REF_PREFIX = (
    "obs://execution_position/close_producer_bridge?"
)


class CloseProducerBridgeError(ValueError):
    """Fail-closed error for the bounded close producer bridge."""


def _clean_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_close_qty(raw_qty: Any) -> Optional[str]:
    if raw_qty in (None, "", "0", 0, "0.0", "0.00"):
        return None
    try:
        qty = Decimal(str(raw_qty))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CloseProducerBridgeError(
            f"CMD:CLOSE qty invalid: {raw_qty!r}"
        ) from exc
    if qty <= 0:
        raise CloseProducerBridgeError(
            f"CMD:CLOSE qty must be positive when present: {raw_qty!r}"
        )
    return str(qty)


def _normalize_trace(raw_trace: Any) -> Optional[Any]:
    if raw_trace is None:
        return None
    if isinstance(raw_trace, (str, dict)):
        return raw_trace
    raise CloseProducerBridgeError(
        f"CMD:CLOSE trace must be str or dict, got {type(raw_trace).__name__}"
    )


def _normalize_policy_context(raw_context: Any) -> Optional[Dict[str, Any]]:
    if raw_context is None:
        return None
    if isinstance(raw_context, dict):
        return dict(raw_context)
    raise CloseProducerBridgeError(
        "CMD:CLOSE policy_context must be a mapping when present"
    )


def _coerce_bool(raw_value: Any, *, field_name: str) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value in (None, "", 0, "0", "false", "False", "FALSE"):
        return False
    if raw_value in (1, "1", "true", "True", "TRUE"):
        return True
    raise CloseProducerBridgeError(
        f"CMD:CLOSE {field_name} invalid bool value: {raw_value!r}"
    )


class CloseCommandIntake(BaseModel):
    """Typed intake for live CMD:CLOSE producer payloads."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    qty: Optional[str] = Field(default=None, pattern=r"^[0-9]+(\.[0-9]+)?$")
    trace: Optional[Any] = None
    policy_context: Optional[Dict[str, Any]] = None
    idempotent_key: Optional[str] = None
    retry_key: Optional[str] = None
    trigger: str = Field(..., min_length=1)
    close_guard_prevalidated: bool = False
    command_rid: Optional[str] = None

    @classmethod
    def from_cmd_close_message(cls, msg: Message) -> "CloseCommandIntake":
        if getattr(msg, "op", None) != "CMD" or getattr(msg, "verb", None) != "CLOSE":
            raise CloseProducerBridgeError("close producer bridge requires CMD:CLOSE")
        payload = msg.pld or {}
        if not isinstance(payload, dict):
            raise CloseProducerBridgeError("CMD:CLOSE payload must be a mapping")

        symbol = _clean_optional_str(payload.get("symbol"))
        if symbol is None:
            raise CloseProducerBridgeError("CMD:CLOSE payload missing required field: symbol")

        reason = _clean_optional_str(payload.get("reason"))
        if reason is None:
            reason = truncate_why(_clean_optional_str(getattr(msg, "why", None)) or "MANUAL_CLOSE")
        if reason is None:
            raise CloseProducerBridgeError("CMD:CLOSE reason normalization failed")

        return cls(
            symbol=symbol.upper(),
            reason=reason,
            qty=_normalize_close_qty(payload.get("qty")),
            trace=_normalize_trace(payload.get("trace")),
            policy_context=_normalize_policy_context(payload.get("policy_context")),
            idempotent_key=(
                _clean_optional_str(payload.get("idempotent_key"))
                or _clean_optional_str(getattr(msg, "idempotent_key", None))
            ),
            retry_key=_clean_optional_str(payload.get("retry_key")),
            trigger=_clean_optional_str(payload.get("trigger")) or "CMD:CLOSE",
            close_guard_prevalidated=_coerce_bool(
                payload.get("close_guard_prevalidated", False),
                field_name="close_guard_prevalidated",
            ),
            command_rid=_clean_optional_str(payload.get("rid")),
        )

    def resolved_idempotent_key(self, *, message_rid: str) -> str:
        resolved = self.idempotent_key or self.command_rid or _clean_optional_str(message_rid)
        if resolved is None:
            raise CloseProducerBridgeError("CMD:CLOSE requires rid or idempotent_key")
        return resolved


class DecCloseBridgePayload(BaseModel):
    """Typed DEC:CLOSE emission payload for the bounded close bridge."""

    model_config = ConfigDict(extra="forbid")

    reduce_only: bool = True
    symbol: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    qty: Optional[str] = Field(default=None, pattern=r"^[0-9]+(\.[0-9]+)?$")
    trace: Optional[Any] = None
    policy_context: Optional[Dict[str, Any]] = None
    idempotent_key: str = Field(..., min_length=1)
    retry_key: Optional[str] = None
    trigger: str = Field(..., min_length=1)
    close_guard_prevalidated: bool = False
    command_trigger: Optional[str] = None

    @classmethod
    def from_cmd_close(
        cls,
        *,
        intake: CloseCommandIntake,
        message_rid: str,
    ) -> "DecCloseBridgePayload":
        command_trigger = intake.trigger if intake.trigger != "CMD:CLOSE" else None
        try:
            return cls(
                reduce_only=True,
                symbol=intake.symbol,
                reason=intake.reason,
                qty=intake.qty,
                trace=intake.trace,
                policy_context=intake.policy_context,
                idempotent_key=intake.resolved_idempotent_key(message_rid=message_rid),
                retry_key=intake.retry_key,
                trigger="CMD:CLOSE",
                close_guard_prevalidated=intake.close_guard_prevalidated,
                command_trigger=command_trigger,
            )
        except Exception as exc:
            raise CloseProducerBridgeError(str(exc)) from exc

    def to_dec_close_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "reduce_only": True,
            "symbol": self.symbol,
            "reason": self.reason,
            "idempotent_key": self.idempotent_key,
            "trigger": self.trigger,
            "close_guard_prevalidated": self.close_guard_prevalidated,
        }
        if self.qty is not None:
            payload["qty"] = self.qty
        if self.trace is not None:
            payload["trace"] = self.trace
        if self.policy_context is not None:
            payload["policy_context"] = self.policy_context
        if self.retry_key is not None:
            payload["retry_key"] = self.retry_key
        if self.command_trigger is not None:
            payload["command_trigger"] = self.command_trigger
        return payload


def build_close_producer_bridge_trace_ref(
    *,
    status: Literal["success", "reject"],
    qty_present: bool,
    preserved_idempotent_key: bool,
    preserved_command_trigger: bool,
    reason: Optional[str] = None,
) -> str:
    params = {
        "contract": CLOSE_PRODUCER_BRIDGE_CONTRACT,
        "path": CLOSE_PRODUCER_BRIDGE_PATH,
        "status": status,
        "qty": "true" if qty_present else "false",
        "idem": "true" if preserved_idempotent_key else "false",
        "command_trigger": "true" if preserved_command_trigger else "false",
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return f"{_CLOSE_PRODUCER_BRIDGE_TRACE_REF_PREFIX}{urlencode(params)}"


def adapt_cmd_close_to_dec_close(msg: Message) -> tuple[CloseCommandIntake, DecCloseBridgePayload, Message]:
    """Typed bridge adapter for the bounded CMD:CLOSE -> DEC:CLOSE seam."""
    intake = CloseCommandIntake.from_cmd_close_message(msg)
    emission = DecCloseBridgePayload.from_cmd_close(
        intake=intake,
        message_rid=str(getattr(msg, "rid", "") or ""),
    )
    success_ref = build_close_producer_bridge_trace_ref(
        status="success",
        qty_present=emission.qty is not None,
        preserved_idempotent_key=bool(intake.idempotent_key),
        preserved_command_trigger=bool(emission.command_trigger),
    )
    data_ref = list(getattr(msg, "data_ref", None) or [])
    if success_ref not in data_ref:
        data_ref.append(success_ref)
    decision = Message(
        op="DEC",
        verb="CLOSE",
        src=msg.dst,
        dst="execution_position",
        rid=msg.rid,
        why=truncate_why(emission.reason),
        idempotent_key=emission.idempotent_key,
        pld=emission.to_dec_close_payload(),
        data_ref=data_ref,
    )
    return intake, emission, decision
