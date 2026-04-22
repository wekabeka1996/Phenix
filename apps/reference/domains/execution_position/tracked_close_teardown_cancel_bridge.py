"""Typed bridge for tracked local bracket teardown inside full-close execution.

This module owns only the bounded internal seam:
``DEC:CLOSE tracked local bracket teardown -> DEC:CANCEL_ORDER``.

Scope:
- typed normalization of locally tracked ``sl_order_id`` / ``tp_order_id``;
- explicit conversion into canonical ``DEC:CANCEL_ORDER`` requests;
- additive seam diagnostics proving traversal into the existing Package 4 seam.

Out of scope:
- Package 4 cancel intake ownership;
- downstream ``ExecPosFSM._cancel_order`` / adapter cancel ownership;
- executor second-pass reconcile scan;
- guardian cleanup / reconcile ownership.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field

from vfoundation.core.protocol import Message, truncate_why


TRACKED_CLOSE_TEARDOWN_CANCEL_CONTRACT = "tracked_close_teardown_cancel_v1"
TRACKED_CLOSE_TEARDOWN_CANCEL_PATH = "DEC:CLOSE:tracked_brackets->DEC:CANCEL_ORDER"
TRACKED_CLOSE_TEARDOWN_CANCEL_TRIGGER = "DEC:CLOSE:tracked_bracket_teardown"
_TRACKED_CLOSE_TEARDOWN_CANCEL_TRACE_REF_PREFIX = (
    "obs://execution_position/tracked_close_teardown_cancel?"
)


class TrackedCloseTeardownCancelBridgeError(ValueError):
    """Fail-closed error for tracked local bracket teardown normalization."""


def _clean_required_str(value: Any, *, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise TrackedCloseTeardownCancelBridgeError(
            f"tracked close teardown missing required field: {field_name}"
        )
    return cleaned


class TrackedCloseTeardownCancelRequest(BaseModel):
    """Typed request for a tracked local bracket teardown cancel."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    bracket_type: Literal["SL", "TP"]
    close_rid: str | None = None

    @classmethod
    def from_runtime(
        cls,
        *,
        symbol: Any,
        order_id: Any,
        bracket_type: Any,
        close_rid: Any,
    ) -> "TrackedCloseTeardownCancelRequest":
        try:
            normalized_symbol = _clean_required_str(symbol, field_name="symbol").upper()
            normalized_order_id = _clean_required_str(order_id, field_name="order_id")
            normalized_bracket_type = _clean_required_str(
                bracket_type,
                field_name="bracket_type",
            ).upper()
            close_rid_clean = str(close_rid).strip() if close_rid is not None else None
            if close_rid_clean == "":
                close_rid_clean = None
            return cls(
                symbol=normalized_symbol,
                order_id=normalized_order_id,
                bracket_type=normalized_bracket_type,
                close_rid=close_rid_clean,
            )
        except Exception as exc:
            if isinstance(exc, TrackedCloseTeardownCancelBridgeError):
                raise
            raise TrackedCloseTeardownCancelBridgeError(str(exc)) from exc

    def idempotent_key(self) -> str:
        anchor = self.close_rid or "manual-close"
        return (
            f"{anchor}:tracked_close_teardown:{self.bracket_type}:{self.order_id}"
        )

    def why(self) -> str:
        return truncate_why(
            f"tracked_close_teardown_{self.bracket_type.lower()}"
        )


def build_tracked_close_teardown_cancel_trace_ref(
    *,
    status: Literal["success", "reject"],
    bracket_type: Literal["SL", "TP"],
    reason: str | None = None,
) -> str:
    params = {
        "contract": TRACKED_CLOSE_TEARDOWN_CANCEL_CONTRACT,
        "path": TRACKED_CLOSE_TEARDOWN_CANCEL_PATH,
        "status": status,
        "bracket_type": bracket_type,
        "trigger": TRACKED_CLOSE_TEARDOWN_CANCEL_TRIGGER,
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return f"{_TRACKED_CLOSE_TEARDOWN_CANCEL_TRACE_REF_PREFIX}{urlencode(params)}"


def adapt_tracked_close_teardown_to_dec_cancel(
    close_decision: Message,
    *,
    symbol: Any,
    order_id: Any,
    bracket_type: Literal["SL", "TP"],
) -> tuple[TrackedCloseTeardownCancelRequest, Message]:
    """Build the canonical DEC:CANCEL_ORDER request for tracked teardown."""
    request = TrackedCloseTeardownCancelRequest.from_runtime(
        symbol=symbol,
        order_id=order_id,
        bracket_type=bracket_type,
        close_rid=getattr(close_decision, "rid", None),
    )
    success_ref = build_tracked_close_teardown_cancel_trace_ref(
        status="success",
        bracket_type=request.bracket_type,
    )
    data_ref = list(getattr(close_decision, "data_ref", None) or [])
    if success_ref not in data_ref:
        data_ref.append(success_ref)
    cancel_decision = Message(
        op="DEC",
        verb="CANCEL_ORDER",
        src="execution_position.close_executor",
        dst="execution_position",
        rid=getattr(close_decision, "rid", None),
        why=request.why(),
        idempotent_key=request.idempotent_key(),
        pld={
            "symbol": request.symbol,
            "order_id": request.order_id,
            "bracket_type": request.bracket_type,
            "trigger": TRACKED_CLOSE_TEARDOWN_CANCEL_TRIGGER,
        },
        data_ref=data_ref,
    )
    return request, cancel_decision
