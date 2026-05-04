"""Typed bridge for guardian symbol-scoped reconcile orphan cancels.

This module owns only the bounded internal seam:
``OrderGuardian.reconcile_symbol -> cleanup_orphans(symbol, hard=True)
-> DEC:CANCEL_ORDER``.

Scope:
- typed normalization of discovered orphan bracket records on the
  authoritative symbol-scoped hard-reconcile path;
- explicit conversion into canonical ``DEC:CANCEL_ORDER`` requests;
- additive diagnostics proving traversal into the existing Package 4 seam.

Out of scope:
- Package 4 cancel intake ownership;
- downstream adapter cancel ownership;
- broader ``cleanup_orphans()`` redesign;
- other guardian cancel paths;
- tidy / reconciled event ownership.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .cancel_bridge_utils import (
    build_trace_ref,
    clean_required_str,
    clean_optional_str,
)
from vfoundation.core.protocol import Message, truncate_why


GUARDIAN_RECONCILE_CANCEL_CONTRACT = "guardian_reconcile_cancel_v1"
GUARDIAN_RECONCILE_CANCEL_PATH = (
    "OrderGuardian.reconcile_symbol->cleanup_orphans->DEC:CANCEL_ORDER"
)
GUARDIAN_RECONCILE_CANCEL_TRIGGER = "guardian_reconcile_orphan_cancel"
_GUARDIAN_RECONCILE_CANCEL_TRACE_REF_PREFIX = (
    "obs://execution_position/guardian_reconcile_cancel?"
)


class GuardianReconcileCancelBridgeError(ValueError):
    """Fail-closed error for guardian reconcile orphan normalization."""


class GuardianReconcileCancelRequest(BaseModel):
    """Typed request for one orphan order on the selected guardian path."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    order_type: str = Field(..., min_length=1)
    rid: str | None = None

    @classmethod
    def from_orphan_record(
        cls,
        *,
        symbol: Any,
        order_id: Any,
        order_type: Any,
        rid: Any,
    ) -> "GuardianReconcileCancelRequest":
        try:
            symbol_clean = clean_required_str(
                symbol,
                field_name="symbol",
                message_prefix="guardian reconcile cancel",
                error_type=GuardianReconcileCancelBridgeError,
            ).upper()
            order_id_clean = clean_required_str(
                order_id,
                field_name="order_id",
                message_prefix="guardian reconcile cancel",
                error_type=GuardianReconcileCancelBridgeError,
            )
            order_type_clean = clean_required_str(
                order_type,
                field_name="order_type",
                message_prefix="guardian reconcile cancel",
                error_type=GuardianReconcileCancelBridgeError,
            ).upper()
            rid_clean = clean_optional_str(
                rid,
                field_name="rid",
                message_prefix="guardian reconcile cancel",
                error_type=GuardianReconcileCancelBridgeError,
            )
            return cls(
                symbol=symbol_clean,
                order_id=order_id_clean,
                order_type=order_type_clean,
                rid=rid_clean,
            )
        except Exception as exc:
            if isinstance(exc, GuardianReconcileCancelBridgeError):
                raise
            raise GuardianReconcileCancelBridgeError(str(exc)) from exc

    def idempotent_key(self) -> str:
        anchor = self.rid or f"guardian-reconcile:{self.symbol}"
        return f"{anchor}:guardian_reconcile_cancel:{self.order_type}:{self.order_id}"

    def why(self) -> str:
        return truncate_why("guardian_reconcile_orphan_cancel")


def build_guardian_reconcile_cancel_trace_ref(
    *,
    status: Literal["success", "reject"],
    order_type: str,
    reason: str | None = None,
) -> str:
    params = {
        "contract": GUARDIAN_RECONCILE_CANCEL_CONTRACT,
        "path": GUARDIAN_RECONCILE_CANCEL_PATH,
        "status": status,
        "order_type": order_type[:40],
        "trigger": GUARDIAN_RECONCILE_CANCEL_TRIGGER,
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return build_trace_ref(
        prefix=_GUARDIAN_RECONCILE_CANCEL_TRACE_REF_PREFIX,
        params=params,
    )


def adapt_guardian_reconcile_to_dec_cancel(
    *,
    symbol: Any,
    order_id: Any,
    order_type: Any,
    rid: Any,
) -> tuple[GuardianReconcileCancelRequest, Message]:
    """Build the canonical DEC:CANCEL_ORDER request for guardian reconcile."""
    request = GuardianReconcileCancelRequest.from_orphan_record(
        symbol=symbol,
        order_id=order_id,
        order_type=order_type,
        rid=rid,
    )
    success_ref = build_guardian_reconcile_cancel_trace_ref(
        status="success",
        order_type=request.order_type,
    )
    message_kwargs = {
        "op": "DEC",
        "verb": "CANCEL_ORDER",
        "src": "execution_position.order_guardian",
        "dst": "execution_position",
        "why": request.why(),
        "idempotent_key": request.idempotent_key(),
        "pld": {
            "symbol": request.symbol,
            "order_id": request.order_id,
            "order_type": request.order_type,
            "trigger": GUARDIAN_RECONCILE_CANCEL_TRIGGER,
        },
        "data_ref": [success_ref],
    }
    if request.rid is not None:
        message_kwargs["rid"] = request.rid
    cancel_decision = Message(
        **message_kwargs,
    )
    return request, cancel_decision
