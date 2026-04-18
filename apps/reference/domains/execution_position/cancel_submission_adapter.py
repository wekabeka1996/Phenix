"""Typed execution-side bridge for DEC:CANCEL_ORDER -> adapter cancellation.

Phase 6 Package 4 seam-local closure of the cancel-submission intake. This
module is the *single* runtime normalization owner for
`DEC:CANCEL_ORDER -> adapter cancellation`. Upstream producers remain free to
emit the legacy untyped dual-key payload (`order_id` / `orderId`); this bridge
canonicalizes them at the executor intake and fails closed on drift.

Ownership boundary (bounded, do not widen):
- upstream producers (`fsm_manage._emit_cancel_order`, entry_manager, limit
  order monitor, etc.) remain unchanged;
- this typed payload owns executor-intake normalization;
- `ExecPosFSM._cancel_order` remains the downstream bridge owner;
- `IdempotentCancelHelper` remains the -2011/-2013 absorption owner;
- adapter `cancel_order` call semantics remain downstream ownership.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field


CANCEL_SUBMISSION_CONTRACT = "cancel_submission_v1"
CANCEL_SUBMISSION_PATH = "DEC:CANCEL_ORDER->adapter"
_CANCEL_SUBMISSION_TRACE_REF_PREFIX = "obs://execution_position/cancel_submission?"


class CancelSubmissionAdapterError(ValueError):
    """Fail-closed error for bounded cancel submission normalization."""


class CancelSubmissionPayload(BaseModel):
    """Typed bridge payload for adapter-bound cancel submission.

    Contract:
    - ``symbol`` and ``order_id`` are required and non-empty.
    - Extra keys are rejected (``extra=forbid``) — prevents silent payload
      drift at the seam.
    - The ``orderId`` alias is canonicalized to ``order_id`` at
      construction; the typed instance exposes only one canonical field.
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)

    @classmethod
    def from_dec_cancel(
        cls,
        *,
        payload: Mapping[str, Any],
    ) -> "CancelSubmissionPayload":
        """Seam-local construction from the legacy ``DEC:CANCEL_ORDER`` payload.

        Accepts the current live payload shape emitted by
        ``fsm_manage._emit_cancel_order`` and equivalent producers, including
        the historical ``orderId`` / ``order_id`` dual key. Canonicalizes to
        ``order_id`` and validates non-empty ``symbol`` / ``order_id``.

        Unknown keys are *not* silently accepted — they are allowed on the
        input mapping (since legacy producers may carry context fields like
        ``trigger`` or ``reason_code`` in the future), but the typed model
        itself is ``extra=forbid`` and the constructor only forwards the
        canonical two fields. Any value mismatch or missing required field
        raises :class:`CancelSubmissionAdapterError`.
        """
        if not isinstance(payload, Mapping):
            raise CancelSubmissionAdapterError(
                "DEC:CANCEL_ORDER payload must be a mapping"
            )

        symbol_raw = payload.get("symbol")
        order_id_raw = payload.get("order_id")
        if order_id_raw in (None, ""):
            order_id_raw = payload.get("orderId")

        symbol = str(symbol_raw).strip() if symbol_raw is not None else ""
        order_id = str(order_id_raw).strip(
        ) if order_id_raw is not None else ""

        if not symbol:
            raise CancelSubmissionAdapterError(
                "DEC:CANCEL_ORDER payload missing required field: symbol"
            )
        if not order_id:
            raise CancelSubmissionAdapterError(
                "DEC:CANCEL_ORDER payload missing required field: order_id"
            )

        try:
            return cls(symbol=symbol, order_id=order_id)
        except Exception as exc:
            raise CancelSubmissionAdapterError(str(exc)) from exc


def build_cancel_submission_trace_ref(
    *,
    status: Literal["success", "reject"],
    reason: Optional[str] = None,
) -> str:
    """Construct the stable cancel-submission seam trace reference.

    Format mirrors the open-submission seam trace ref:
    ``obs://execution_position/cancel_submission?contract=cancel_submission_v1
    &path=DEC:CANCEL_ORDER->adapter&status={success|reject}[&reason=...]``
    """
    params = {
        "contract": CANCEL_SUBMISSION_CONTRACT,
        "path": CANCEL_SUBMISSION_PATH,
        "status": status,
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return f"{_CANCEL_SUBMISSION_TRACE_REF_PREFIX}{urlencode(params)}"
