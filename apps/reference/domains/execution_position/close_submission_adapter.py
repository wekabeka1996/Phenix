"""Typed execution-side bridge for DEC:CLOSE -> adapter close submission.

Phase 6 Package 5 seam-local closure of the close-submission boundary.
This module is the *single* runtime normalization owner for
``DEC:CLOSE -> adapter.place_market_reduce_only``.

Ownership boundary (bounded, do not widen):
- upstream ``DEC:CLOSE`` producers remain unchanged;
- bracket teardown, reconcile plane, sidecar signaling, exchange-position
  re-read, and restore-artifact persistence all remain unchanged;
- this typed payload owns close-submission derivation:
  * ``side`` from ``position_amt`` sign,
  * ``quantity`` from partial-vs-full logic,
  * ``client_order_id`` via ``generate_client_order_id("CLOSE", ...)``;
- ``adapter.place_market_reduce_only`` call semantics remain downstream
  ownership.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal, Optional
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field


CLOSE_SUBMISSION_CONTRACT = "close_submission_v1"
CLOSE_SUBMISSION_PATH = "DEC:CLOSE->adapter"
_CLOSE_SUBMISSION_TRACE_REF_PREFIX = "obs://execution_position/close_submission?"


class CloseSubmissionAdapterError(ValueError):
    """Fail-closed error for bounded close submission normalization."""


class CloseSubmissionPayload(BaseModel):
    """Typed bridge payload for adapter-bound close submission.

    Contract:
    - ``symbol``, ``side``, ``quantity`` and ``client_order_id`` are required;
    - ``side`` is ``BUY`` or ``SELL`` only;
    - ``quantity`` is a positive-decimal string;
    - ``partial_close`` distinguishes the partial-close branch from the
      full-close branch;
    - extras are rejected (``extra=forbid``) — prevents silent payload drift
      at the seam.
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    side: Literal["BUY", "SELL"]
    quantity: str = Field(..., pattern=r"^[0-9]+(\.[0-9]+)?$")
    client_order_id: str = Field(..., min_length=1)
    partial_close: bool

    @classmethod
    def from_dec_close(
        cls,
        *,
        symbol: str,
        position_amt: Decimal,
        requested_qty: Optional[Decimal],
        idempotent_key: Optional[str],
    ) -> "CloseSubmissionPayload":
        """Seam-local construction for the close-submission boundary.

        Owns the three derivations that were previously inlined in the
        executor glue:
        - ``side`` from the sign of ``position_amt`` (positive → ``SELL``,
          negative → ``BUY``);
        - ``quantity`` as ``requested_qty`` when a strictly-smaller partial
          close is requested (``0 < requested_qty < |position_amt|``), else
          ``|position_amt|`` for a full close;
        - ``client_order_id`` via
          ``generate_client_order_id("CLOSE", symbol, idempotent_key=...)``.

        Fails closed on any inconsistency (empty symbol, zero position,
        non-positive requested_qty, empty idempotent_key).
        """
        # Local import to avoid import cycles with the execution_position
        # package's utils module at import time (Package 3 precedent).
        from apps.reference.domains.execution_position.utils import (
            generate_client_order_id,
        )

        if not isinstance(symbol, str) or not symbol.strip():
            raise CloseSubmissionAdapterError(
                "close submission requires non-empty symbol"
            )
        symbol_clean = symbol.strip()

        try:
            amt = Decimal(str(position_amt))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise CloseSubmissionAdapterError(
                f"close submission position_amt invalid: {position_amt!r}"
            ) from exc
        if amt == 0:
            raise CloseSubmissionAdapterError(
                "close submission requires non-zero position_amt"
            )

        position_qty = abs(amt)
        side: Literal["BUY", "SELL"] = "SELL" if amt > 0 else "BUY"

        partial_close = False
        if requested_qty is not None:
            try:
                req = abs(Decimal(str(requested_qty)))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise CloseSubmissionAdapterError(
                    f"close submission requested_qty invalid: {requested_qty!r}"
                ) from exc
            if req <= 0:
                raise CloseSubmissionAdapterError(
                    "close submission requested_qty must be positive"
                )
            if req < position_qty:
                qty_dec = req
                partial_close = True
            else:
                qty_dec = position_qty
        else:
            qty_dec = position_qty

        key = str(idempotent_key).strip() if idempotent_key else ""
        if not key:
            raise CloseSubmissionAdapterError(
                "close submission requires non-empty idempotent_key"
            )

        client_order_id = generate_client_order_id(
            "CLOSE", symbol_clean, idempotent_key=key
        )

        try:
            return cls(
                symbol=symbol_clean,
                side=side,
                quantity=str(qty_dec),
                client_order_id=str(client_order_id),
                partial_close=partial_close,
            )
        except Exception as exc:
            raise CloseSubmissionAdapterError(str(exc)) from exc


def build_close_submission_trace_ref(
    *,
    status: Literal["success", "reject"],
    partial_close: bool,
    reason: Optional[str] = None,
) -> str:
    """Construct the stable close-submission seam trace reference.

    Format mirrors the open/cancel submission trace refs:
    ``obs://execution_position/close_submission?contract=close_submission_v1
    &path=DEC:CLOSE->adapter&status={success|reject}&partial={true|false}
    [&reason=...]``.
    """
    params = {
        "contract": CLOSE_SUBMISSION_CONTRACT,
        "path": CLOSE_SUBMISSION_PATH,
        "status": status,
        "partial": "true" if partial_close else "false",
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return f"{_CLOSE_SUBMISSION_TRACE_REF_PREFIX}{urlencode(params)}"
