"""Typed execution-side bridge for DEC:OPEN -> adapter submission."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Literal, Optional, Tuple
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
                raise ValueError(
                    "MARKET submission must have time_in_force=null")
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
                price=str(payload["price"]) if payload.get(
                    "price") is not None else None,
                time_in_force=(
                    str(payload["tif"]).upper()
                    if payload.get("tif") is not None
                    else None
                ),
            )
        except Exception as exc:
            raise OpenSubmissionAdapterError(str(exc)) from exc

    @classmethod
    def from_dec_open_with_key(
        cls,
        *,
        payload: Mapping[str, Any],
        normalized_qty: str,
        idempotent_key: Optional[str],
    ) -> "OpenSubmissionPayload":
        """Seam-owned construction: derive client_order_id from idempotent_key.

        This closes the previous ownership split where the executor synthesised
        the client_order_id before invoking ``from_dec_open``. The mapping
        ``idempotent_key -> client_order_id`` is now a submit-boundary rule
        owned by the typed bridge.
        """
        # Import locally to avoid an import cycle with utils at module load.
        from apps.reference.domains.execution_position.utils import (
            generate_client_order_id,
        )

        try:
            symbol = str(payload["symbol"])
        except Exception as exc:
            raise OpenSubmissionAdapterError(str(exc)) from exc

        key = str(idempotent_key) if idempotent_key else None
        client_order_id = generate_client_order_id(
            "ENTRY",
            symbol,
            idempotent_key=key,
        )
        return cls.from_dec_open(
            payload=payload,
            normalized_qty=normalized_qty,
            client_order_id=client_order_id,
        )

    def with_limit_price(self, price: str) -> "OpenSubmissionPayload":
        try:
            return self.model_copy(update={"price": str(price)})
        except Exception as exc:
            raise OpenSubmissionAdapterError(str(exc)) from exc

    def apply_gtx_passive_guard(
        self,
        *,
        best_bid: Decimal,
        best_ask: Decimal,
    ) -> Tuple["OpenSubmissionPayload", bool, Optional[str]]:
        """Seam-owned GTX passive-side price adjustment.

        Returns ``(maybe_new_payload, price_adjusted, original_price)``.

        - No adjustment is applied for non-LIMIT/non-GTX orders, a missing
          price, or a crossed/zero-spread book. In those cases the original
          submission is returned unchanged and ``price_adjusted`` is False.
        - BUY crossing the ask is pinned to ``best_bid``;
          SELL crossing the bid is pinned to ``best_ask``.
        - The executor retains ownership of the runtime book-ticker lookup
          and of observability side-effects (``LIMIT_PRICE_ADJUSTED`` log,
          crossed-book warnings). Only the normalization rule lives here.
        """
        if self.order_type != "LIMIT" or self.time_in_force != "GTX":
            return self, False, None
        if self.price is None:
            return self, False, None
        if best_bid is None or best_ask is None:
            return self, False, None
        if best_bid >= best_ask:
            # Crossed / zero-spread: seam leaves the price untouched; the
            # executor owns the observability warning.
            return self, False, None
        try:
            submit_price = Decimal(self.price)
        except (InvalidOperation, ValueError, TypeError):
            return self, False, None
        original = self.price
        if self.side == "BUY" and submit_price >= best_ask:
            return self.with_limit_price(str(best_bid)), True, original
        if self.side == "SELL" and submit_price <= best_bid:
            return self.with_limit_price(str(best_ask)), True, original
        return self, False, None

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
