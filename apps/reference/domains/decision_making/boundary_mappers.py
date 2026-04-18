"""Mappers from Pydantic boundary models to internal core models.

These are pure functions with no side effects. They own:
- type coercion (confidence → float, timestamps → int)
- structural normalization (warmup dict → WarmupState dataclass)
- regime label normalization (delegated to normalize_structural_regime_label)
- read-only wrapping (MappingProxyType for top-level safety)

They do NOT own:
- business policy decisions (those stay in handlers)
- validation logic (belongs in boundary models or handler gates)
- Pydantic model construction for downstream use

Residual note: features remains Mapping because deeper feature typing
is deferred to Package 2. Callers that need a mutable dict must convert
via dict(cmd.features).

Behavioral preservation notes:
- normalize_structural_regime_label maps BULL_TREND→TREND_UP,
  BEAR_TREND→TREND_DOWN, and leaves unknown labels as-is (e.g. UNCERTAIN).
  This is the same normalization the handler applied before this package.
- confidence and raw_confidence are float-resolved; None on failure.
  This matches the previous float(confidence_raw) coercion in the handler.
- regime_raw_confidence is preserved from the raw transport dict (as string)
  for state fields that historically stored the raw string value.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any

from apps.reference.contracts.runtime_regime_layers import (
    normalize_structural_regime_label,
)
from apps.reference.domains.decision_making.boundary_models import (
    ProcessStrategyBoundary,
    RegimeDetectedBoundary,
)
from apps.reference.domains.decision_making.core_models import (
    ProcessStrategyCmd,
    RegimeEvent,
    WarmupState,
)


def _map_warmup(warmup_dict: dict[str, Any] | None) -> WarmupState:
    """Convert raw warmup blob to typed WarmupState.

    Absent or None warmup_dict produces a zero/False/empty WarmupState
    rather than crashing. Handler gates own the fail-closed logic for
    warmup-related business rules.
    """
    d = warmup_dict or {}
    ready_raw = d.get("ready") or {}
    return WarmupState(
        full_ready=bool(d.get("full_ready", False)),
        ticks_seen=int(d.get("ticks_seen", 0)),
        ready=MappingProxyType(
            {k: bool(v) for k, v in ready_raw.items()}
        ),
        reasons=tuple(str(r) for r in (d.get("reasons") or [])),
    )


def _resolve_confidence(value: Any) -> float | None:
    """Resolve confidence to float, return None on failure or absence."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def map_process_strategy_boundary_to_cmd(
    boundary: ProcessStrategyBoundary,
    raw: dict[str, Any],
) -> ProcessStrategyCmd:
    """Map ProcessStrategyBoundary and original payload to ProcessStrategyCmd.

    Args:
        boundary: Pydantic-validated boundary model (control fields only).
        raw: The original transport dict, preserved as-is for pass-through
             to utilities (extract_canonical_bar_identity, gap extractors,
             etc.) that need full dict-like access and predate this model.

    Returns:
        Immutable ProcessStrategyCmd suitable for business logic consumption.

    Residual note: features is wrapped in MappingProxyType for read-only
    safety. Callers that need a mutable dict (e.g. _process_decision for
    feature enrichment) must call dict(cmd.features).
    """
    warmup = _map_warmup(boundary.warmup)
    features: dict[str, Any] = dict(boundary.features or {})
    return ProcessStrategyCmd(
        symbol=boundary.symbol,
        tf_sec=boundary.tf_sec,
        bar_close_ts=boundary.bar_close_ts,
        rid=boundary.rid,
        features=MappingProxyType(features),
        warmup=warmup,
        raw=MappingProxyType(raw),
    )


def map_regime_boundary_to_event(
    boundary: RegimeDetectedBoundary,
    raw: dict[str, Any],
) -> RegimeEvent:
    """Map RegimeDetectedBoundary and original payload to RegimeEvent.

    Regime normalization is applied here via normalize_structural_regime_label
    so that downstream logic always receives a canonical label. Unknown labels
    (those not in the canonical set) pass through unchanged — preserving the
    existing runtime behavior where the handler cached unrecognized labels.

    BEHAVIORAL PRESERVATION: The previous handler called
    normalize_structural_regime_label(event.get("regime")) inline. This mapper
    replicates that behavior exactly.

    Args:
        boundary: Pydantic-validated boundary model.
        raw: The original transport dict, preserved for provenance helpers
             (build_regime_provenance_fields) and fields not promoted to
             first-class attributes (raw_regime, bar_close_ts_ms, etc.).

    Returns:
        Immutable RegimeEvent with normalized regime label.
    """
    # Normalize regime label. Unknown labels pass through unchanged.
    regime_normalized = normalize_structural_regime_label(
        str(boundary.regime or "")
    )

    # Timestamps: prefer ts_ms (ms epoch), fall back to ts (μs → ms).
    ts_ms: int
    if boundary.ts_ms is not None:
        ts_ms = int(boundary.ts_ms)
    elif boundary.ts is not None:
        ts_ms = int(boundary.ts) // 1000
    else:
        ts_ms = 0

    return RegimeEvent(
        symbol=boundary.symbol,
        regime=regime_normalized,
        confidence=_resolve_confidence(boundary.confidence),
        ts_ms=ts_ms,
        structural_regime_ref=boundary.structural_regime_ref,
        changed=boundary.changed,
        raw_confidence=_resolve_confidence(boundary.raw_confidence),
        last_update_ts_ms=int(boundary.last_update_ts_ms or 0),
        raw=MappingProxyType(raw),
    )
