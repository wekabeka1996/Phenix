"""Typed execution-side bridge for ManageFlowFSM max-hold DEC:CLOSE emission.

This module owns only the bounded autonomous close seam:
``ManageFlowFSM._check_max_hold_time() -> DEC:CLOSE``.

Scope:
- typed max-hold close intake normalization from ManageFlowFSM runtime state;
- typed DEC:CLOSE emission payload ownership for timer-originated close;
- explicit non-CMD trigger and stable idempotent-key derivation;
- additive diagnostics for seam success/reject.

Out of scope:
- explicit CMD:CLOSE producer bridge ownership (Package 6);
- close execution, reconcile, bracket teardown, or broader ManageFlowFSM flow.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field

from vfoundation.core.protocol import Message, truncate_why


MANAGE_MAX_HOLD_CLOSE_CONTRACT = "manage_max_hold_close_v1"
MANAGE_MAX_HOLD_CLOSE_PATH = "ManageFlowFSM:max_hold->DEC:CLOSE"
MANAGE_MAX_HOLD_CLOSE_TRIGGER = "FSM:MANAGE_MAX_HOLD"
_MANAGE_MAX_HOLD_CLOSE_TRACE_REF_PREFIX = (
    "obs://execution_position/manage_max_hold_close?"
)


class ManageMaxHoldCloseBridgeError(ValueError):
    """Fail-closed error for the bounded max-hold close bridge."""


def _clean_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_symbol(raw_symbol: Any) -> str:
    symbol = _clean_optional_str(raw_symbol)
    if symbol is None:
        raise ManageMaxHoldCloseBridgeError(
            "max-hold close requires non-empty symbol"
        )
    return symbol.upper()


def _normalize_side(raw_side: Any) -> Literal["BUY", "SELL"]:
    side = (_clean_optional_str(raw_side) or "").upper()
    if side not in {"BUY", "SELL"}:
        raise ManageMaxHoldCloseBridgeError(
            f"max-hold close side invalid: {raw_side!r}"
        )
    return side


def _normalize_qty(raw_qty: Any) -> str:
    try:
        qty = Decimal(str(raw_qty))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ManageMaxHoldCloseBridgeError(
            f"max-hold close qty invalid: {raw_qty!r}"
        ) from exc
    if qty <= 0:
        raise ManageMaxHoldCloseBridgeError(
            f"max-hold close qty must be positive: {raw_qty!r}"
        )
    return str(qty)


def _normalize_non_negative_float(raw_value: Any, *, field_name: str) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ManageMaxHoldCloseBridgeError(
            f"max-hold close {field_name} invalid: {raw_value!r}"
        ) from exc
    if value < 0:
        raise ManageMaxHoldCloseBridgeError(
            f"max-hold close {field_name} must be non-negative: {raw_value!r}"
        )
    return value


def _normalize_positive_float(raw_value: Any, *, field_name: str) -> float:
    value = _normalize_non_negative_float(raw_value, field_name=field_name)
    if value <= 0:
        raise ManageMaxHoldCloseBridgeError(
            f"max-hold close {field_name} must be positive: {raw_value!r}"
        )
    return value


class ManageMaxHoldCloseIntake(BaseModel):
    """Typed intake for ManageFlowFSM autonomous max-hold close state."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    side: Literal["BUY", "SELL"]
    qty: str = Field(..., pattern=r"^[0-9]+(\.[0-9]+)?$")
    elapsed_sec: float = Field(..., ge=0)
    max_hold_sec: float = Field(..., gt=0)
    position_open_ts: float = Field(..., ge=0)

    @classmethod
    def from_runtime(
        cls,
        *,
        symbol: Any,
        side: Any,
        qty: Any,
        elapsed_sec: Any,
        max_hold_sec: Any,
        position_open_ts: Any,
    ) -> "ManageMaxHoldCloseIntake":
        try:
            return cls(
                symbol=_normalize_symbol(symbol),
                side=_normalize_side(side),
                qty=_normalize_qty(qty),
                elapsed_sec=_normalize_non_negative_float(
                    elapsed_sec,
                    field_name="elapsed_sec",
                ),
                max_hold_sec=_normalize_positive_float(
                    max_hold_sec,
                    field_name="max_hold_sec",
                ),
                position_open_ts=_normalize_non_negative_float(
                    position_open_ts,
                    field_name="position_open_ts",
                ),
            )
        except Exception as exc:
            if isinstance(exc, ManageMaxHoldCloseBridgeError):
                raise
            raise ManageMaxHoldCloseBridgeError(str(exc)) from exc

    def resolved_idempotent_key(self) -> str:
        open_ts_ms = int(self.position_open_ts * 1000)
        max_hold_key = int(self.max_hold_sec)
        return (
            f"manage_max_hold:{self.symbol}:{open_ts_ms}:{self.qty}:{max_hold_key}"
        )


class ManageMaxHoldDecClosePayload(BaseModel):
    """Typed DEC:CLOSE emission payload for autonomous max-hold close."""

    model_config = ConfigDict(extra="forbid")

    reduce_only: bool = True
    symbol: str = Field(..., min_length=1)
    side: Literal["BUY", "SELL"]
    qty: str = Field(..., pattern=r"^[0-9]+(\.[0-9]+)?$")
    reason: Literal["MAX_HOLD_TIME_EXCEEDED"] = "MAX_HOLD_TIME_EXCEEDED"
    elapsed_sec: float = Field(..., ge=0)
    max_hold_sec: float = Field(..., gt=0)
    trigger: Literal["FSM:MANAGE_MAX_HOLD"] = MANAGE_MAX_HOLD_CLOSE_TRIGGER
    idempotent_key: str = Field(..., min_length=1)

    @classmethod
    def from_intake(
        cls,
        *,
        intake: ManageMaxHoldCloseIntake,
    ) -> "ManageMaxHoldDecClosePayload":
        try:
            return cls(
                reduce_only=True,
                symbol=intake.symbol,
                side=intake.side,
                qty=intake.qty,
                elapsed_sec=intake.elapsed_sec,
                max_hold_sec=intake.max_hold_sec,
                trigger=MANAGE_MAX_HOLD_CLOSE_TRIGGER,
                idempotent_key=intake.resolved_idempotent_key(),
            )
        except Exception as exc:
            raise ManageMaxHoldCloseBridgeError(str(exc)) from exc

    def to_dec_close_payload(self) -> Dict[str, Any]:
        return {
            "reduce_only": True,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "reason": self.reason,
            "elapsed_sec": self.elapsed_sec,
            "max_hold_sec": self.max_hold_sec,
            "trigger": self.trigger,
            "idempotent_key": self.idempotent_key,
        }


def build_manage_max_hold_close_trace_ref(
    *,
    status: Literal["success", "reject"],
    reason: str | None = None,
) -> str:
    params = {
        "contract": MANAGE_MAX_HOLD_CLOSE_CONTRACT,
        "path": MANAGE_MAX_HOLD_CLOSE_PATH,
        "status": status,
        "trigger": MANAGE_MAX_HOLD_CLOSE_TRIGGER,
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return f"{_MANAGE_MAX_HOLD_CLOSE_TRACE_REF_PREFIX}{urlencode(params)}"


def adapt_manage_max_hold_to_dec_close(
    msg: Message,
    *,
    symbol: Any,
    side: Any,
    qty: Any,
    elapsed_sec: Any,
    max_hold_sec: Any,
    position_open_ts: Any,
) -> tuple[ManageMaxHoldCloseIntake, ManageMaxHoldDecClosePayload, Message]:
    """Typed bridge adapter for the bounded autonomous max-hold close seam."""
    intake = ManageMaxHoldCloseIntake.from_runtime(
        symbol=symbol,
        side=side,
        qty=qty,
        elapsed_sec=elapsed_sec,
        max_hold_sec=max_hold_sec,
        position_open_ts=position_open_ts,
    )
    emission = ManageMaxHoldDecClosePayload.from_intake(intake=intake)
    success_ref = build_manage_max_hold_close_trace_ref(status="success")
    data_ref = list(getattr(msg, "data_ref", None) or [])
    if success_ref not in data_ref:
        data_ref.append(success_ref)
    why = truncate_why(f"max_hold_timeout_{int(intake.elapsed_sec)}s_reduce_only")
    decision = Message(
        op="DEC",
        verb="CLOSE",
        src="execution_position",
        dst="execution_position",
        rid=msg.rid,
        why=why,
        idempotent_key=emission.idempotent_key,
        pld=emission.to_dec_close_payload(),
        data_ref=data_ref,
    )
    return intake, emission, decision
