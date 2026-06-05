"""Typed bridge for guardian pre-close cleanup cancels.

This module owns only the bounded internal seam:
``OrderGuardian.cleanup_before_close -> DEC:CANCEL_ORDER``.

Scope:
- typed normalization of bracket cancels tied to a selected entry before close;
- explicit conversion into canonical ``DEC:CANCEL_ORDER`` requests;
- additive diagnostics proving traversal into the existing Package 4 seam.

Out of scope:
- Package 4 cancel intake ownership;
- downstream adapter cancel ownership;
- broader guardian cleanup redesign;
- cleanup_other_brackets_for_symbol ownership;
- background cleanup_orphans ownership.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .cancel_bridge_utils import (
    build_trace_ref,
    clean_required_str,
)
from vfoundation.core.protocol import Message, truncate_why


GUARDIAN_PRE_CLOSE_CLEANUP_CONTRACT = "guardian_pre_close_cleanup_v1"
GUARDIAN_PRE_CLOSE_CLEANUP_PATH = (
    "OrderGuardian.cleanup_before_close->DEC:CANCEL_ORDER"
)
GUARDIAN_PRE_CLOSE_CLEANUP_TRIGGER = "guardian_pre_close_cleanup"
_GUARDIAN_PRE_CLOSE_CLEANUP_TRACE_REF_PREFIX = (
    "obs://execution_position/guardian_pre_close_cleanup?"
)


class GuardianPreCloseCleanupBridgeError(ValueError):
    """Fail-closed error for guardian pre-close cleanup normalization."""


class GuardianPreCloseCleanupRequest(BaseModel):
    """Typed request for one bracket cancel on the pre-close path."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    bracket_type: str = Field(..., min_length=1)
    parent_order_id: str = Field(..., min_length=1)

    @classmethod
    def from_pre_close_bracket(
        cls,
        *,
        symbol: Any,
        order_id: Any,
        bracket_type: Any,
        parent_order_id: Any,
    ) -> "GuardianPreCloseCleanupRequest":
        try:
            return cls(
                symbol=clean_required_str(
                    symbol,
                    field_name="symbol",
                    message_prefix="guardian pre-close cleanup",
                    error_type=GuardianPreCloseCleanupBridgeError,
                ).upper(),
                order_id=clean_required_str(
                    order_id,
                    field_name="order_id",
                    message_prefix="guardian pre-close cleanup",
                    error_type=GuardianPreCloseCleanupBridgeError,
                ),
                bracket_type=clean_required_str(
                    bracket_type,
                    field_name="bracket_type",
                    message_prefix="guardian pre-close cleanup",
                    error_type=GuardianPreCloseCleanupBridgeError,
                ).upper(),
                parent_order_id=clean_required_str(
                    parent_order_id,
                    field_name="parent_order_id",
                    message_prefix="guardian pre-close cleanup",
                    error_type=GuardianPreCloseCleanupBridgeError,
                ),
            )
        except Exception as exc:
            if isinstance(exc, GuardianPreCloseCleanupBridgeError):
                raise
            raise GuardianPreCloseCleanupBridgeError(str(exc)) from exc

    def idempotent_key(self) -> str:
        return (
            f"{self.symbol}:guardian_pre_close_cleanup:"
            f"{self.parent_order_id}:{self.bracket_type}:{self.order_id}"
        )

    def why(self) -> str:
        return truncate_why("guardian_pre_close_cleanup")


def build_guardian_pre_close_cleanup_trace_ref(
    *,
    status: Literal["success", "reject"],
    bracket_type: str,
    reason: str | None = None,
) -> str:
    params = {
        "contract": GUARDIAN_PRE_CLOSE_CLEANUP_CONTRACT,
        "path": GUARDIAN_PRE_CLOSE_CLEANUP_PATH,
        "status": status,
        "bracket_type": bracket_type[:40],
        "trigger": GUARDIAN_PRE_CLOSE_CLEANUP_TRIGGER,
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return build_trace_ref(
        prefix=_GUARDIAN_PRE_CLOSE_CLEANUP_TRACE_REF_PREFIX,
        params=params,
    )


def adapt_guardian_pre_close_cleanup_to_dec_cancel(
    *,
    symbol: Any,
    order_id: Any,
    bracket_type: Any,
    parent_order_id: Any,
) -> tuple[GuardianPreCloseCleanupRequest, Message]:
    """Build the canonical DEC:CANCEL_ORDER request for pre-close cleanup."""
    request = GuardianPreCloseCleanupRequest.from_pre_close_bracket(
        symbol=symbol,
        order_id=order_id,
        bracket_type=bracket_type,
        parent_order_id=parent_order_id,
    )
    success_ref = build_guardian_pre_close_cleanup_trace_ref(
        status="success",
        bracket_type=request.bracket_type,
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
            "bracket_type": request.bracket_type,
            "trigger": GUARDIAN_PRE_CLOSE_CLEANUP_TRIGGER,
        },
        data_ref=[success_ref],
    )
    return request, cancel_decision
