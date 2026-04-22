"""Typed bridge for guardian old-bracket cleanup cancels.

This module owns only the bounded internal seam:
``OrderGuardian.cleanup_other_brackets_for_symbol -> DEC:CANCEL_ORDER``.

Scope:
- typed normalization of outdated bracket discoveries tied to a previous entry;
- explicit conversion into canonical ``DEC:CANCEL_ORDER`` requests;
- additive diagnostics proving traversal into the existing Package 4 seam.

Out of scope:
- Package 4 cancel intake ownership;
- downstream adapter cancel ownership;
- broader guardian cleanup redesign;
- cleanup_before_close ownership;
- background cleanup_orphans ownership.
"""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field

from vfoundation.core.protocol import Message, truncate_why


GUARDIAN_OLD_BRACKET_CLEANUP_CONTRACT = "guardian_old_bracket_cleanup_v1"
GUARDIAN_OLD_BRACKET_CLEANUP_PATH = (
    "OrderGuardian.cleanup_other_brackets_for_symbol->DEC:CANCEL_ORDER"
)
GUARDIAN_OLD_BRACKET_CLEANUP_TRIGGER = "guardian_old_bracket_cleanup"
_GUARDIAN_OLD_BRACKET_CLEANUP_TRACE_REF_PREFIX = (
    "obs://execution_position/guardian_old_bracket_cleanup?"
)


class GuardianOldBracketCleanupBridgeError(ValueError):
    """Fail-closed error for guardian old-bracket cleanup normalization."""


def _clean_required_str(value: Any, *, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise GuardianOldBracketCleanupBridgeError(
            f"guardian old bracket cleanup missing required field: {field_name}"
        )
    return cleaned


class GuardianOldBracketCleanupRequest(BaseModel):
    """Typed request for one outdated bracket cleanup cancel."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    order_type: str = Field(..., min_length=1)
    keep_parent_order_id: str = Field(..., min_length=1)

    @classmethod
    def from_outdated_bracket(
        cls,
        *,
        symbol: Any,
        order_id: Any,
        order_type: Any,
        keep_parent_order_id: Any,
    ) -> "GuardianOldBracketCleanupRequest":
        try:
            return cls(
                symbol=_clean_required_str(symbol, field_name="symbol").upper(),
                order_id=_clean_required_str(order_id, field_name="order_id"),
                order_type=_clean_required_str(
                    order_type,
                    field_name="order_type",
                ).upper(),
                keep_parent_order_id=_clean_required_str(
                    keep_parent_order_id,
                    field_name="keep_parent_order_id",
                ),
            )
        except Exception as exc:
            if isinstance(exc, GuardianOldBracketCleanupBridgeError):
                raise
            raise GuardianOldBracketCleanupBridgeError(str(exc)) from exc

    def idempotent_key(self) -> str:
        return (
            f"{self.symbol}:guardian_old_bracket_cleanup:"
            f"{self.keep_parent_order_id}:{self.order_type}:{self.order_id}"
        )

    def why(self) -> str:
        return truncate_why("guardian_old_bracket_cleanup")


def build_guardian_old_bracket_cleanup_trace_ref(
    *,
    status: Literal["success", "reject"],
    order_type: str,
    reason: str | None = None,
) -> str:
    params = {
        "contract": GUARDIAN_OLD_BRACKET_CLEANUP_CONTRACT,
        "path": GUARDIAN_OLD_BRACKET_CLEANUP_PATH,
        "status": status,
        "order_type": order_type[:40],
        "trigger": GUARDIAN_OLD_BRACKET_CLEANUP_TRIGGER,
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return (
        f"{_GUARDIAN_OLD_BRACKET_CLEANUP_TRACE_REF_PREFIX}{urlencode(params)}"
    )


def adapt_guardian_old_bracket_cleanup_to_dec_cancel(
    *,
    symbol: Any,
    order_id: Any,
    order_type: Any,
    keep_parent_order_id: Any,
) -> tuple[GuardianOldBracketCleanupRequest, Message]:
    """Build the canonical DEC:CANCEL_ORDER request for old-bracket cleanup."""
    request = GuardianOldBracketCleanupRequest.from_outdated_bracket(
        symbol=symbol,
        order_id=order_id,
        order_type=order_type,
        keep_parent_order_id=keep_parent_order_id,
    )
    success_ref = build_guardian_old_bracket_cleanup_trace_ref(
        status="success",
        order_type=request.order_type,
    )
    cancel_decision = Message(
        op="DEC",
        verb="CANCEL_ORDER",
        src="execution_position.order_guardian",
        dst="execution_position",
        why=request.why(),
        idempotent_key=request.idempotent_key(),
        pld={
            "symbol": request.symbol,
            "order_id": request.order_id,
            "order_type": request.order_type,
            "trigger": GUARDIAN_OLD_BRACKET_CLEANUP_TRIGGER,
            "keep_parent_order_id": request.keep_parent_order_id,
        },
        data_ref=[success_ref],
    )
    return request, cancel_decision
