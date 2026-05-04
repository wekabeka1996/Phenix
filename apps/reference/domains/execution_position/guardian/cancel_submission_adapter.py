"""Typed execution-side bridge for DEC:CANCEL_ORDER -> adapter cancellation.

Phase 6 Package 4 seam-local closure of the cancel-submission intake.

Ownership boundary (bounded, do not widen):
- upstream producers (`fsm_manage._emit_cancel_order`, entry_manager, limit
  order monitor, Package 7/8/9/10 internal bridges, etc.) remain unchanged;
- `CancelSubmissionRawPayload` owns bounded raw DEC:CANCEL_ORDER intake;
- `CancelSubmissionPayload` owns the canonical downstream adapter request;
- `ExecPosFSM._cancel_order` remains the downstream bridge owner;
- `IdempotentCancelHelper` remains the -2011/-2013 absorption owner;
- adapter `cancel_order` call semantics remain downstream ownership.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, model_validator


CANCEL_SUBMISSION_CONTRACT = "cancel_submission_v1"
CANCEL_SUBMISSION_PATH = "DEC:CANCEL_ORDER->adapter"
_CANCEL_SUBMISSION_TRACE_REF_PREFIX = "obs://execution_position/cancel_submission?"


class CancelSubmissionAdapterError(ValueError):
    """Fail-closed error for bounded cancel submission normalization."""


class CancelSubmissionRawPayload(BaseModel):
    """Bounded raw DEC:CANCEL_ORDER intake.

    This model accepts the live raw cancel fields currently used by the seam:
    - required identity: `symbol`, `order_id` / `orderId`
    - bounded context: `trigger`, `order_type`, `bracket_type`,
      `keep_parent_order_id`

    Unknown raw extras reject here so payload drift is no longer silently
    ignored before canonical adapter submission.
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    trigger: Optional[str] = None
    order_type: Optional[str] = None
    bracket_type: Optional[str] = None
    keep_parent_order_id: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _canonicalize_order_id_alias(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        alias_order_id = data.pop("orderId", None)
        if data.get("order_id") in (None, "") and alias_order_id not in (None, ""):
            data["order_id"] = alias_order_id
        return data


class CancelSubmissionPayload(BaseModel):
    """Canonical adapter-bound cancel request.

    This model validates the derived downstream adapter contract only:
    `symbol` and `order_id`. Raw DEC:CANCEL_ORDER intake ownership lives in
    `CancelSubmissionRawPayload`.
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
        """Construct the canonical adapter request from raw DEC:CANCEL_ORDER.

        The raw-intake model accepts only the currently live bounded context
        fields plus `symbol` and `order_id`/`orderId`. Unknown raw extras reject
        at intake. The returned typed payload remains the minimal two-field
        canonical adapter request.
        """
        if not isinstance(payload, Mapping):
            raise CancelSubmissionAdapterError(
                "DEC:CANCEL_ORDER payload must be a mapping"
            )

        try:
            raw_payload = CancelSubmissionRawPayload.model_validate(payload)
        except Exception as exc:
            raise CancelSubmissionAdapterError(str(exc)) from exc

        symbol = str(raw_payload.symbol).strip()
        order_id = str(raw_payload.order_id).strip()

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
    """Construct the stable cancel-submission seam trace reference."""
    params = {
        "contract": CANCEL_SUBMISSION_CONTRACT,
        "path": CANCEL_SUBMISSION_PATH,
        "status": status,
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return f"{_CANCEL_SUBMISSION_TRACE_REF_PREFIX}{urlencode(params)}"
