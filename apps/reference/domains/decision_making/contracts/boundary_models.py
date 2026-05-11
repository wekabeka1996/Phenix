"""Strict Pydantic v2 boundary models for selected active event seams.

These models are the ONLY place Pydantic validation runs for the covered
seams. They MUST NOT be passed into core business logic — use core_models
instead.

Covered seams (Package 1):
- CMD:PROCESS_STRATEGY      → ProcessStrategyBoundary
- EVT:REGIME_DETECTED       → RegimeDetectedBoundary
- EVT:TRADE_INTENT_PROPOSED → TradeIntentRoutingEnvelope (routing fields only)

Design rules applied:
- frozen=True: models are immutable after construction.
- extra="ignore" for seams where schema is additive (CMD:PROCESS_STRATEGY,
  EVT:TRADE_INTENT_PROPOSED routing). Extra fields flow through the
  ProcessStrategyCmd.raw pass-through mapping.
- extra="allow" for EVT:REGIME_DETECTED: the regime_detected_v1.json schema
  explicitly allows additional properties and producers add diagnostic
  fields over time (vol_ratio, vol_ratio_slope, etc.).
- Critical fields (symbol, regime) are required at the boundary level.
  Business-validation fields (tf_sec, bar_close_ts) are Optional so handler
  gates continue to own that logic and emit appropriate WAL records.

Rule 7 note: features and warmup are Optional at the boundary.
Defaulting them to {} would mask absence from upstream. Handler business
logic owns the fail-closed behavior for missing required blobs.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

# Re-exported from contracts so EP domain can import without violating the
# EP→DM import guardrail (test_ep_contract_boundary_guardrails).
from apps.reference.contracts.trade_intent_envelope import TradeIntentRoutingEnvelope

__all__ = [
    "ProcessStrategyBoundary",
    "RegimeDetectedBoundary",
    "TradeIntentRoutingEnvelope",
]


class ProcessStrategyBoundary(BaseModel):
    """Boundary model for CMD:PROCESS_STRATEGY transport payload.

    Only the control-envelope fields needed for routing and core processing
    are declared. All remaining fields (bar, bar_identity, gap_state,
  diagnostics, regime snapshot, etc.) flow through the
    ``ProcessStrategyCmd.raw`` pass-through mapping.

    ``extra="ignore"`` is intentional: the schema is additive (was extended
    in FE_SCHEMA_SILENCE) and new fields must not cause boundary failures.

    Runtime: produced by FeatureEngineering, consumed by AuroraBuiltinPlugin.
    Schema reference: feature_engineering/schemas/cmd_process_strategy_v1.json
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    # Required: cannot route without a symbol.
    symbol: str

    # Optional at boundary: handler Gates 1/2/4 own missing-value logic
    # and emit structured WAL records for each case. Defaulting these here
    # would suppress those gates.
    tf_sec: int | None = None
    bar_close_ts: int | None = None
    rid: str | None = None

    # Feature / warmup blobs: None signals upstream did not send them.
    # Rule 7: do NOT default to {} — handler decides whether to fail-closed.
    features: dict[str, Any] | None = None
    warmup: dict[str, Any] | None = None
    price_motion: dict[str, Any] | None = None


class RegimeDetectedBoundary(BaseModel):
    """Boundary model for EVT:REGIME_DETECTED transport payload.

    ``extra="allow"`` is intentional: regime_detected_v1.json schema allows
    additional properties (additionalProperties not set to false), and the
    regime domain adds diagnostic fields over time.

    Regime normalization is NOT performed here. The mapper owns that step so
    the boundary model reflects transport reality, not business rules.

    Confidence is typed broadly (str | float | int | None) to match actual
    runtime inbound surface: producers may send Decimal-string, float, or
    integer representations of the 0.0–1.0 value.

    Runtime: produced by regime_detector, consumed by AuroraBuiltinPlugin.
    Schema reference: regime_detector/schemas/regime_detected_v1.json
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    # Required by schema
    symbol: str
    regime: str

    # Optional but present in most payloads
    confidence: str | float | int | None = None
    source_model: str | None = None

    # Timing — ts is microseconds (schema), ts_ms is additive ms alias
    ts: int | None = None
    ts_ms: int | None = None

    # Heartbeat / change tracking (DM-CRITICAL-PATCHES-02)
    changed: bool | None = None
    last_update_ts_ms: int | None = None

    # Provenance / diagnostic fields
    structural_regime_ref: str | None = None
    raw_regime: str | None = None
    raw_confidence: str | float | int | None = None
    stable_confidence: str | float | int | None = None
    storm_rejected: bool | None = None
