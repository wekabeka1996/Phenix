"""Typed execution-side bridge for DEC:OPEN -> adapter submission."""

from __future__ import annotations

from typing import Any, Mapping, Literal, Optional
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, model_validator


OPEN_SUBMISSION_CONTRACT = "open_submission_v1"
OPEN_SUBMISSION_PATH = "DEC:OPEN->adapter"
_OPEN_SUBMISSION_TRACE_REF_PREFIX = "obs://execution_position/open_submission?"


class OpenSubmissionAdapterError(ValueError):
    """Fail-closed error for bounded open submission normalization."""


class OpenSubmissionPayload(BaseModel):
    """Typed bridge payload for adapter-bound open submission."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    side: Literal["BUY", "SELL"]
    quantity: str = Field(..., pattern=r"^[0-9]+(\.[0-9]+)?$")
    order_type: Literal["MARKET", "LIMIT"]
    client_order_id: str = Field(..., min_length=1)
    price: Optional[str] = Field(default=None, pattern=r"^[0-9]+(\.[0-9]+)?$")
    time_in_force: Optional[Literal["GTC", "GTX", "IOC", "FOK"]] = Field(
        default=None,
    )

    @model_validator(mode="after")
    def _cross_field_contract(self) -> "OpenSubmissionPayload":
        if self.order_type == "LIMIT":
            if self.price is None:
                raise ValueError("LIMIT submission requires price")
            if self.time_in_force is None:
                raise ValueError("LIMIT submission requires time_in_force")
        elif self.order_type == "MARKET":
            if self.price is not None:
                raise ValueError("MARKET submission must have price=null")
            if self.time_in_force is not None:
                raise ValueError("MARKET submission must have time_in_force=null")
        return self

    @classmethod
    def from_dec_open(
        cls,
        *,
        payload: Mapping[str, Any],
        normalized_qty: str,
        client_order_id: str,
    ) -> "OpenSubmissionPayload":
        try:
            return cls(
                symbol=str(payload["symbol"]),
                side=str(payload["side"]).upper(),
                quantity=str(normalized_qty),
                order_type=str(payload["order_type"]).upper(),
                client_order_id=str(client_order_id),
                price=str(payload["price"]) if payload.get("price") is not None else None,
                time_in_force=(
                    str(payload["tif"]).upper()
                    if payload.get("tif") is not None
                    else None
                ),
            )
        except Exception as exc:
            raise OpenSubmissionAdapterError(str(exc)) from exc

    def with_limit_price(self, price: str) -> "OpenSubmissionPayload":
        try:
            return self.model_copy(update={"price": str(price)})
        except Exception as exc:
            raise OpenSubmissionAdapterError(str(exc)) from exc

    @property
    def submit_kind(self) -> Literal["market", "limit"]:
        return "limit" if self.order_type == "LIMIT" else "market"


def build_open_submission_trace_ref(
    *,
    status: Literal["success", "reject"],
    submit_kind: Literal["market", "limit"],
    price_adjusted: bool,
    reason: Optional[str] = None,
) -> str:
    params = {
        "contract": OPEN_SUBMISSION_CONTRACT,
        "path": OPEN_SUBMISSION_PATH,
        "status": status,
        "submit_kind": submit_kind,
        "price_adjusted": "true" if price_adjusted else "false",
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return f"{_OPEN_SUBMISSION_TRACE_REF_PREFIX}{urlencode(params)}"
