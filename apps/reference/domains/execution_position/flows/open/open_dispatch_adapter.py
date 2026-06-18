"""Typed execution-side bridge for CMD:OPEN -> DEC:OPEN.

This module owns only the bounded normalization seam between an already
validated CMD:OPEN and the downstream DEC:OPEN dispatch payload.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Literal, Optional
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, model_validator


OPEN_DISPATCH_CONTRACT = "open_dispatch_v1"
OPEN_DISPATCH_PATH = "CMD:OPEN->DEC:OPEN"
_OPEN_DISPATCH_TRACE_REF_PREFIX = "obs://execution_position/open_dispatch?"


class OpenDispatchAdapterError(ValueError):
    """Fail-closed error for bounded open dispatch normalization."""


class OpenDispatchPayload(BaseModel):
    """Typed bridge payload for the bounded open dispatch seam."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1)
    side: Literal["BUY", "SELL"]
    qty: str = Field(..., pattern=r"^[0-9]+(\.[0-9]+)?$")
    order_type: Literal["MARKET", "LIMIT"]
    price: Optional[str] = Field(default=None, pattern=r"^[0-9]+(\.[0-9]+)?$")
    tif: Optional[Literal["GTC", "GTX", "IOC", "FOK"]] = Field(default=None)
    valid_for_ms: Optional[int] = Field(default=None, ge=1000)
    stop_price: Optional[str] = Field(
        default=None, pattern=r"^[0-9]+(\.[0-9]+)?$")
    target_price: Optional[str] = Field(
        default=None, pattern=r"^[0-9]+(\.[0-9]+)?$")
    sl_pct: Optional[str] = Field(default=None, pattern=r"^[0-9]+(\.[0-9]+)?$")
    idempotent_key: Optional[str] = Field(default=None)
    strategy_id: Optional[str] = Field(default=None)
    decision_id: Optional[str] = Field(default=None)
    intent_id: Optional[str] = Field(default=None)
    regime_epoch_ref: Optional[str] = Field(default=None)
    regime: Optional[str] = Field(default=None)
    regime_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    resolved_min_regime_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    threshold_applied: Optional[bool] = Field(default=None)
    threshold_verdict: Optional[str] = Field(default=None)
    threshold_reason: Optional[str] = Field(default=None)
    regime_confidence_gate_verdict: Optional[str] = Field(default=None)
    regime_provenance: Optional[Dict[str, Any]] = Field(default=None)

    @model_validator(mode="after")
    def _cross_field_contract(self) -> "OpenDispatchPayload":
        if self.order_type == "LIMIT":
            if self.price is None:
                raise ValueError("LIMIT dispatch requires price")
            if self.tif is None:
                raise ValueError("LIMIT dispatch requires tif")
            if self.valid_for_ms is None:
                raise ValueError("LIMIT dispatch requires valid_for_ms")
        elif self.order_type == "MARKET":
            if self.tif is not None:
                raise ValueError("MARKET dispatch must have tif=null")
        return self

    @classmethod
    def from_cmd_open(
        cls,
        *,
        symbol: str,
        side: Literal["BUY", "SELL"],
        normalized_qty: Decimal,
        order_type: Literal["MARKET", "LIMIT"],
        normalized_price: Optional[Decimal],
        tif: Optional[Literal["GTC", "GTX", "IOC", "FOK"]],
        valid_for_ms: Optional[int],
        stop_price: Optional[str],
        target_price: Optional[str],
        sl_pct: Optional[str],
        idempotent_key: Optional[str],
        regime_epoch_ref: Optional[str],
        regime: Optional[str],
        regime_confidence: Optional[float],
        resolved_min_regime_confidence: Optional[float],
        threshold_applied: Optional[bool],
        threshold_verdict: Optional[str],
        threshold_reason: Optional[str],
        regime_confidence_gate_verdict: Optional[str],
        regime_provenance: Optional[Dict[str, Any]],
        strategy_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        intent_id: Optional[str] = None,
    ) -> "OpenDispatchPayload":
        try:
            return cls(
                symbol=symbol,
                side=side,
                qty=str(normalized_qty),
                order_type=order_type,
                price=str(
                    normalized_price) if normalized_price is not None else None,
                tif=tif,
                valid_for_ms=valid_for_ms,
                stop_price=stop_price,
                target_price=target_price,
                sl_pct=sl_pct,
                idempotent_key=idempotent_key,
                strategy_id=strategy_id,
                decision_id=decision_id,
                intent_id=intent_id or idempotent_key,
                regime_epoch_ref=regime_epoch_ref,
                regime=regime,
                regime_confidence=regime_confidence,
                resolved_min_regime_confidence=resolved_min_regime_confidence,
                threshold_applied=threshold_applied,
                threshold_verdict=threshold_verdict,
                threshold_reason=threshold_reason,
                regime_confidence_gate_verdict=regime_confidence_gate_verdict,
                regime_provenance=regime_provenance,
            )
        except Exception as exc:
            raise OpenDispatchAdapterError(str(exc)) from exc

    def to_dec_open_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "order_type": self.order_type,
            "regime_epoch_ref": self.regime_epoch_ref,
            "regime": self.regime,
            "regime_confidence": self.regime_confidence,
            "resolved_min_regime_confidence": self.resolved_min_regime_confidence,
            "threshold_applied": self.threshold_applied,
            "threshold_verdict": self.threshold_verdict,
            "threshold_reason": self.threshold_reason,
            "regime_confidence_gate_verdict": self.regime_confidence_gate_verdict,
            "regime_provenance": self.regime_provenance,
        }
        if self.strategy_id is not None:
            payload["strategy"] = self.strategy_id
        if self.decision_id is not None:
            payload["decision_id"] = self.decision_id
        if self.intent_id is not None:
            payload["intent_id"] = self.intent_id
        if self.tif is not None:
            payload["tif"] = self.tif
        if self.price is not None:
            payload["price"] = self.price
        if self.valid_for_ms is not None:
            payload["valid_for_ms"] = self.valid_for_ms
        if self.stop_price is not None:
            payload["stop_price"] = self.stop_price
        if self.target_price is not None:
            payload["target_price"] = self.target_price
        if self.sl_pct is not None:
            payload["sl_pct"] = self.sl_pct
        if self.idempotent_key is not None:
            payload["idempotent_key"] = self.idempotent_key
        return payload


def build_open_dispatch_trace_ref(
    *,
    status: Literal["success", "reject"],
    qty_normalized: bool,
    price_normalized: bool,
    reason: Optional[str] = None,
) -> str:
    params = {
        "contract": OPEN_DISPATCH_CONTRACT,
        "path": OPEN_DISPATCH_PATH,
        "status": status,
        "qty_normalized": "true" if qty_normalized else "false",
        "price_normalized": "true" if price_normalized else "false",
    }
    if reason is not None:
        params["reason"] = reason[:80]
    return f"{_OPEN_DISPATCH_TRACE_REF_PREFIX}{urlencode(params)}"
