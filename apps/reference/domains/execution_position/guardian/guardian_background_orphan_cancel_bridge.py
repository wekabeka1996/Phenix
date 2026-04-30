"""Typed bridge for guardian background orphan cleanup cancels.

This module owns only the bounded internal seam:
``OrderGuardian.cleanup_orphans(hard=False) -> DEC:CANCEL_ORDER``.

Scope:
- typed normalization of discovered orphan bracket records on the
  background (hard=False) polling path;
- explicit conversion into canonical ``DEC:CANCEL_ORDER`` requests;
- additive diagnostics proving traversal into the existing Package 4 seam.

Out of scope:
- Package 4 cancel intake ownership;
- downstream adapter cancel ownership;
- broader ``cleanup_orphans()`` redesign;
- Package 9 hard-reconcile path (guardian_reconcile_cancel_bridge);
- cleanup_other_brackets_for_symbol ownership (Package 10);
- cleanup_before_close ownership (Package 11);
- tidy / reconciled event ownership;
- positionAmt / position parsing;
- DEF-005 restart remediation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.domains.execution_position.cancel_bridge_utils import (
    build_trace_ref,
    clean_required_str,
)
from vfoundation.core.protocol import Message, truncate_why


GUARDIAN_BACKGROUND_ORPHAN_CANCEL_CONTRACT = "guardian_background_orphan_cancel_v1"
GUARDIAN_BACKGROUND_ORPHAN_CANCEL_PATH = (
    "OrderGuardian.cleanup_orphans(hard=False)->DEC:CANCEL_ORDER"
)
GUARDIAN_BACKGROUND_ORPHAN_CANCEL_TRIGGER = "guardian_background_orphan_cancel"
_GUARDIAN_BACKGROUND_ORPHAN_CANCEL_TRACE_REF_PREFIX = (
    "obs://execution_position/guardian_background_orphan_cancel?"
)


class GuardianBackgroundOrphanCancelBridgeError(ValueError):
    """Fail-closed error for guardian background orphan cancel normalization."""


class GuardianBackgroundOrphanCancelRequest(BaseModel):
    """Typed request for one discovered orphan bracket on the background polling path.

    This bridges ``cleanup_orphans(hard=False)`` discoveries into canonical
    ``DEC:CANCEL_ORDER`` requests.  The ``order_type`` field carries the
    discovered order type as observable context only; it is propagated in the
    ``DEC:CANCEL_ORDER`` payload so Package 4 can accept it via the bounded
    ``order_type: Optional[str]`` field on ``CancelSubmissionRawPayload``.
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    order_type: str = Field(..., min_length=1)

    @classmethod
    def from_background_orphan(
        cls,
        *,
        symbol: Any,
        order_id: Any,
        order_type: Any,
    ) -> "GuardianBackgroundOrphanCancelRequest":
        try:
            return cls(
                symbol=clean_required_str(
                    symbol,
                    field_name="symbol",
                    message_prefix="guardian background orphan cancel",
                    error_type=GuardianBackgroundOrphanCancelBridgeError,
                ).upper(),
                order_id=clean_required_str(
                    order_id,
                    field_name="order_id",
                    message_prefix="guardian background orphan cancel",
                    error_type=GuardianBackgroundOrphanCancelBridgeError,
                ),
                order_type=clean_required_str(
                    order_type,
                    field_name="order_type",
                    message_prefix="guardian background orphan cancel",
                    error_type=GuardianBackgroundOrphanCancelBridgeError,
                ).upper(),
            )
        except Exception as exc:
            if isinstance(exc, GuardianBackgroundOrphanCancelBridgeError):
                raise
            raise GuardianBackgroundOrphanCancelBridgeError(str(exc)) from exc

    def idempotent_key(self) -> str:
        return (
            f"{self.symbol}:guardian_background_orphan_cancel:"
            f"{self.order_type}:{self.order_id}"
        )

    def why(self) -> str:
        return truncate_why("guardian_background_orphan_cancel")


def build_guardian_background_orphan_cancel_trace_ref(
    *,
    status: Literal["success", "reject"],
    order_type: str,
    reason: str | None = None,
) -> str:
    params = {
        "contract": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_CONTRACT,
        "path": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_PATH,
        "status": status,
        "order_type": order_type[:40],
        "trigger": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_TRIGGER,
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return build_trace_ref(
        prefix=_GUARDIAN_BACKGROUND_ORPHAN_CANCEL_TRACE_REF_PREFIX,
        params=params,
    )


def adapt_guardian_background_orphan_to_dec_cancel(
    *,
    symbol: Any,
    order_id: Any,
    order_type: Any,
) -> tuple[GuardianBackgroundOrphanCancelRequest, Message]:
    """Build the canonical DEC:CANCEL_ORDER request for background orphan cleanup.

    The ``DEC:CANCEL_ORDER`` payload emitted here contains only the fields
    accepted by ``CancelSubmissionRawPayload``:
    - ``symbol``
    - ``order_id``
    - ``order_type``   (Optional on intake side; carried for diagnostics)
    - ``trigger``      (Optional on intake side; identifies the seam)

    ``parent_entry_id`` and other internal guardian metadata are explicitly
    excluded from the payload and remain in the request object only.
    """
    request = GuardianBackgroundOrphanCancelRequest.from_background_orphan(
        symbol=symbol,
        order_id=order_id,
        order_type=order_type,
    )
    success_ref = build_guardian_background_orphan_cancel_trace_ref(
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
            "trigger": GUARDIAN_BACKGROUND_ORPHAN_CANCEL_TRIGGER,
        },
        data_ref=[success_ref],
    )
    return request, cancel_decision
