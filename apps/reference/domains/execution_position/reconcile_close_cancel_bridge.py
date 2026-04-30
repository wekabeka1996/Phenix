"""Typed bridge for executor second-pass close reconcile cancel requests.

This module owns only the bounded internal seam:
``DEC:CLOSE second-pass reconcile scan -> DEC:CANCEL_ORDER``.

Scope:
- typed normalization of cancelable open-order discoveries from the executor's
  second-pass reconcile scan;
- explicit conversion into canonical ``DEC:CANCEL_ORDER`` requests;
- additive diagnostics proving traversal into the existing Package 4 seam.

Out of scope:
- Package 7 tracked teardown ownership;
- Package 4 cancel intake ownership;
- downstream ``ExecPosFSM._cancel_order`` / adapter cancel ownership;
- ``OrderGuardian`` cleanup / reconcile ownership.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.reference.domains.execution_position.cancel_bridge_utils import (
    build_trace_ref,
    clean_required_str,
    clean_optional_str,
)
from vfoundation.core.protocol import Message, truncate_why


RECONCILE_CLOSE_CANCEL_CONTRACT = "reconcile_close_cancel_v1"
RECONCILE_CLOSE_CANCEL_PATH = "DEC:CLOSE:reconcile_scan->DEC:CANCEL_ORDER"
RECONCILE_CLOSE_CANCEL_TRIGGER = "DEC:CLOSE:reconcile_scan_cancel"
_RECONCILE_CLOSE_CANCEL_TRACE_REF_PREFIX = (
    "obs://execution_position/reconcile_close_cancel?"
)


class ReconcileCloseCancelBridgeError(ValueError):
    """Fail-closed error for second-pass reconcile cancel normalization."""


class ReconcileCloseCancelRequest(BaseModel):
    """Typed request for one cancelable open-order discovery."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    order_type: str = Field(..., min_length=1)
    close_rid: str | None = None

    @classmethod
    def from_open_order(
        cls,
        *,
        symbol: Any,
        order_id: Any,
        order_type: Any,
        close_rid: Any,
    ) -> "ReconcileCloseCancelRequest":
        try:
            symbol_clean = clean_required_str(
                symbol,
                field_name="symbol",
                message_prefix="reconcile close cancel",
                error_type=ReconcileCloseCancelBridgeError,
            ).upper()
            order_id_clean = clean_required_str(
                order_id,
                field_name="order_id",
                message_prefix="reconcile close cancel",
                error_type=ReconcileCloseCancelBridgeError,
            )
            order_type_clean = clean_required_str(
                order_type,
                field_name="order_type",
                message_prefix="reconcile close cancel",
                error_type=ReconcileCloseCancelBridgeError,
            ).upper()
            close_rid_clean = clean_optional_str(
                close_rid,
                field_name="close_rid",
                message_prefix="reconcile close cancel",
                error_type=ReconcileCloseCancelBridgeError,
            )
            return cls(
                symbol=symbol_clean,
                order_id=order_id_clean,
                order_type=order_type_clean,
                close_rid=close_rid_clean,
            )
        except Exception as exc:
            if isinstance(exc, ReconcileCloseCancelBridgeError):
                raise
            raise ReconcileCloseCancelBridgeError(str(exc)) from exc

    def idempotent_key(self) -> str:
        anchor = self.close_rid or "manual-close"
        return f"{anchor}:reconcile_close_cancel:{self.order_type}:{self.order_id}"

    def why(self) -> str:
        return truncate_why(
            f"reconcile_close_cancel_{self.order_type.lower()}"
        )


def build_reconcile_close_cancel_trace_ref(
    *,
    status: Literal["success", "reject"],
    order_type: str,
    reason: str | None = None,
) -> str:
    params = {
        "contract": RECONCILE_CLOSE_CANCEL_CONTRACT,
        "path": RECONCILE_CLOSE_CANCEL_PATH,
        "status": status,
        "order_type": order_type[:40],
        "trigger": RECONCILE_CLOSE_CANCEL_TRIGGER,
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return build_trace_ref(
        prefix=_RECONCILE_CLOSE_CANCEL_TRACE_REF_PREFIX,
        params=params,
    )


def adapt_reconcile_close_to_dec_cancel(
    close_decision: Message,
    *,
    symbol: Any,
    order_id: Any,
    order_type: Any,
) -> tuple[ReconcileCloseCancelRequest, Message]:
    """Build the canonical DEC:CANCEL_ORDER request for reconcile-scan cancels."""
    request = ReconcileCloseCancelRequest.from_open_order(
        symbol=symbol,
        order_id=order_id,
        order_type=order_type,
        close_rid=getattr(close_decision, "rid", None),
    )
    success_ref = build_reconcile_close_cancel_trace_ref(
        status="success",
        order_type=request.order_type,
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
            "order_type": request.order_type,
            "trigger": RECONCILE_CLOSE_CANCEL_TRIGGER,
        },
        data_ref=data_ref,
    )
    return request, cancel_decision
