"""Typed execution-side intake for EVT:TRADE_INTENT_PROPOSED -> CMD:OPEN.

This module is intentionally narrow. It does not replace:
- upstream EVT:TRADE_INTENT_PROPOSED JSON Schema validation
- downstream CMD:OPEN schema validation
- downstream CmdOpenPayload validation inside OpenFlowFSM

It only owns execution-side normalization of the open-intake seam.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


INTENT_OPEN_INTAKE_CONTRACT = "trade_intent_open_intake_v1"


class TradeIntentOpenIntakeError(ValueError):
    """Raised when execution cannot truthfully normalize an open intent."""

    def __init__(self, reason_code: str, why: str) -> None:
        super().__init__(why)
        self.reason_code = str(reason_code)
        self.why = str(why)


def _stringify_optional(value: Any) -> Optional[str]:
    if value in (None, "", "None", "null"):
        return None
    return str(value)


def _resolve_optional_price(payload: Mapping[str, Any], key: str) -> Optional[str]:
    root_value = _stringify_optional(payload.get(key))
    if root_value is not None:
        return root_value

    price_ctx = payload.get("price_ctx")
    if isinstance(price_ctx, Mapping):
        ctx_value = _stringify_optional(price_ctx.get(key))
        if ctx_value is not None:
            return ctx_value

    order_block = payload.get("order")
    if isinstance(order_block, Mapping):
        order_value = _stringify_optional(order_block.get(key))
        if order_value is not None:
            return order_value

    return None


class TradeIntentOpenOrder(BaseModel):
    """Subset of TRADE_INTENT_PROPOSED.order used by execution open intake."""

    model_config = ConfigDict(extra="ignore")

    qty: str = Field(..., pattern=r"^[0-9]+(\.[0-9]+)?$")
    reduce_only: bool = False
    order_type: str
    price: Optional[str] = Field(default=None, pattern=r"^[0-9]+(\.[0-9]+)?$")
    tif: Optional[str] = None
    price_ref: Optional[str] = Field(
        default=None, pattern=r"^[0-9]+(\.[0-9]+)?$")

    @field_validator("order_type", mode="before")
    @classmethod
    def _normalize_order_type(cls, value: Any) -> Any:
        if value is None:
            return value
        return str(value).strip().upper()

    @field_validator("tif", mode="before")
    @classmethod
    def _normalize_tif(cls, value: Any) -> Any:
        if value is None:
            return None
        return str(value).strip().upper()


class TradeIntentOpenIntake(BaseModel):
    """Execution-side typed bridge for normal open-intent intake."""

    model_config = ConfigDict(extra="ignore")

    rid: Optional[str] = None
    symbol: str = Field(..., min_length=1)
    side: str
    strategy_id: Optional[str] = None
    order: TradeIntentOpenOrder
    valid_for_ms: Optional[int] = Field(default=None, ge=1000)
    idempotent_key: Optional[str] = None
    stop_price: Optional[str] = Field(
        default=None, pattern=r"^[0-9]+(\.[0-9]+)?$")
    target_price: Optional[str] = Field(
        default=None, pattern=r"^[0-9]+(\.[0-9]+)?$")
    regime: Optional[str] = None
    regime_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    regime_provenance: Optional[Dict[str, Any]] = None
    tca_budget: Optional[Dict[str, Any]] = None
    risk_context: Optional[Dict[str, Any]] = None
    trace: Optional[Dict[str, Any]] = None

    @field_validator("symbol", mode="before")
    @classmethod
    def _normalize_symbol(cls, value: Any) -> Any:
        if value is None:
            return value
        return str(value).strip().upper()

    @field_validator("side", mode="before")
    @classmethod
    def _normalize_side(cls, value: Any) -> Any:
        if value is None:
            return value
        return str(value).strip().upper()

    def to_cmd_open_payload(self) -> Dict[str, Any]:
        """Build the bounded CMD:OPEN payload owned by this seam."""
        payload: Dict[str, Any] = {
            "rid": self.rid,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.order.qty,
            "order_type": self.order.order_type,
            "price": self.order.price,
            "tif": self.order.tif,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "valid_for_ms": self.valid_for_ms,
            "idempotent_key": self.idempotent_key,
            "price_ref": self.order.price_ref,
            "strategy": self.strategy_id,
            "regime": self.regime,
            "regime_confidence": self.regime_confidence,
            "regime_provenance": dict(self.regime_provenance) if isinstance(self.regime_provenance, dict) else None,
        }

        metadata: Dict[str, Any] = {
            "execution_intake_contract": INTENT_OPEN_INTAKE_CONTRACT,
            "execution_intake_path": "EVT:TRADE_INTENT_PROPOSED->CMD:OPEN",
        }
        if self.strategy_id:
            metadata["strategy_id"] = self.strategy_id
        if isinstance(self.tca_budget, dict) and self.tca_budget:
            metadata["tca_budget"] = dict(self.tca_budget)
        if isinstance(self.risk_context, dict) and self.risk_context:
            metadata["risk_context"] = dict(self.risk_context)
        if metadata:
            payload["metadata"] = metadata

        return payload


def parse_trade_intent_open_intake(
    payload: Mapping[str, Any],
    *,
    fallback_rid: Optional[str] = None,
) -> TradeIntentOpenIntake:
    """Validate and normalize one execution-side open intent."""
    raw = dict(payload or {})
    symbol = _stringify_optional(
        raw.get("instrument")) or _stringify_optional(raw.get("symbol"))
    if symbol is None:
        keys = sorted(str(key) for key in raw.keys())
        raise TradeIntentOpenIntakeError(
            "NRR-INTENT-MISSING-SYMBOL",
            f"NRR-INTENT-MISSING-SYMBOL: TRADE_INTENT_PROPOSED missing symbol/instrument: keys={keys}",
        )

    strategy_id = _stringify_optional(
        raw.get("strategy")) or _stringify_optional(raw.get("strategy_id"))
    order_block = raw.get("order")
    if not isinstance(order_block, Mapping):
        raise TradeIntentOpenIntakeError(
            "NRR-INTENT-MISSING-ORDER",
            "NRR-INTENT-MISSING-ORDER: TRADE_INTENT_PROPOSED requires order block",
        )
    raw_order_type = _stringify_optional(order_block.get("order_type"))
    if raw_order_type is None:
        raise TradeIntentOpenIntakeError(
            "NRR-INTENT-MISSING-ORDER_TYPE",
            "NRR-INTENT-MISSING-ORDER_TYPE: Strategy must provide explicit order_type (LIMIT/MARKET)",
        )
    raw_order_type = raw_order_type.upper()
    if raw_order_type == "LIMIT" and _stringify_optional(order_block.get("price")) is None:
        raise TradeIntentOpenIntakeError(
            "NRR-INTENT-MISSING-PRICE",
            "NRR-INTENT-MISSING-PRICE: LIMIT order requires price",
        )
    raw_tif = _stringify_optional(order_block.get("tif"))
    if raw_order_type == "LIMIT" and raw_tif is None:
        raise TradeIntentOpenIntakeError(
            "NRR-INTENT-MISSING-TIF",
            "NRR-INTENT-MISSING-TIF: LIMIT order requires tif (GTC/GTX/IOC/FOK)",
        )
    if raw_order_type == "MARKET" and raw_tif is not None:
        raise TradeIntentOpenIntakeError(
            "NRR-INTENT-INVALID-TIF",
            f"NRR-INTENT-INVALID-TIF: MARKET order must not have tif (got {raw_tif})",
        )

    try:
        intake = TradeIntentOpenIntake.model_validate(
            {
                "rid": _stringify_optional(raw.get("rid")) or _stringify_optional(fallback_rid),
                "symbol": symbol,
                "side": raw.get("side"),
                "strategy_id": strategy_id,
                "order": dict(order_block),
                "valid_for_ms": raw.get("valid_for_ms"),
                "idempotent_key": _stringify_optional(raw.get("idempotent_key")),
                "stop_price": _resolve_optional_price(raw, "stop_price"),
                "target_price": _resolve_optional_price(raw, "target_price"),
                "regime": raw.get("regime"),
                "regime_confidence": raw.get("regime_confidence"),
                "regime_provenance": raw.get("regime_provenance"),
                "tca_budget": raw.get("tca_budget"),
                "risk_context": raw.get("risk_context"),
                "trace": raw.get("trace"),
            }
        )
    except ValidationError as exc:
        raise TradeIntentOpenIntakeError(
            "NRR-INTENT-OPEN-INTAKE-INVALID",
            f"NRR-INTENT-OPEN-INTAKE-INVALID: {exc.errors()[0]['msg']}",
        ) from exc

    if intake.side not in {"BUY", "SELL"}:
        raise TradeIntentOpenIntakeError(
            "NRR-INTENT-INVALID-SIDE",
            f"NRR-INTENT-INVALID-SIDE: unsupported side={intake.side!r}",
        )
    if intake.order.reduce_only:
        raise TradeIntentOpenIntakeError(
            "NRR-INTENT-REDUCE-ONLY-OPEN-BYPASS",
            "NRR-INTENT-REDUCE-ONLY-OPEN-BYPASS: reduce_only intent must not enter typed open intake",
        )
    if intake.order.order_type not in {"LIMIT", "MARKET"}:
        raise TradeIntentOpenIntakeError(
            "NRR-INTENT-MISSING-ORDER_TYPE",
            "NRR-INTENT-MISSING-ORDER_TYPE: Strategy must provide explicit order_type (LIMIT/MARKET)",
        )
    if intake.order.order_type == "LIMIT":
        if intake.order.price is None:
            raise TradeIntentOpenIntakeError(
                "NRR-INTENT-MISSING-PRICE",
                "NRR-INTENT-MISSING-PRICE: LIMIT order requires price",
            )
        if intake.order.tif is None:
            raise TradeIntentOpenIntakeError(
                "NRR-INTENT-MISSING-TIF",
                "NRR-INTENT-MISSING-TIF: LIMIT order requires tif (GTC/GTX/IOC/FOK)",
            )
        if intake.order.tif not in {"GTC", "GTX", "IOC", "FOK"}:
            raise TradeIntentOpenIntakeError(
                "NRR-INTENT-MISSING-TIF",
                f"NRR-INTENT-MISSING-TIF: LIMIT order requires tif (got {intake.order.tif})",
            )
        if intake.valid_for_ms is None:
            raise TradeIntentOpenIntakeError(
                "NRR-INTENT-MISSING-VALID-FOR-MS",
                "NRR-INTENT-MISSING-VALID-FOR-MS: LIMIT order requires valid_for_ms",
            )
    elif intake.order.tif is not None:
        raise TradeIntentOpenIntakeError(
            "NRR-INTENT-INVALID-TIF",
            f"NRR-INTENT-INVALID-TIF: MARKET order must not have tif (got {intake.order.tif})",
        )

    return intake


__all__ = [
    "INTENT_OPEN_INTAKE_CONTRACT",
    "TradeIntentOpenIntake",
    "TradeIntentOpenIntakeError",
    "parse_trade_intent_open_intake",
]
