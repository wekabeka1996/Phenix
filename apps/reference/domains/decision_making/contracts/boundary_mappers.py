"""Mappers from Pydantic boundary models to internal core models.

These are pure functions with no side effects. They own:
- type coercion (confidence → float, timestamps → int)
- structural normalization (warmup dict → WarmupState dataclass)
- regime label normalization (delegated to canonical_structural_regime_label)
- read-only wrapping (MappingProxyType for top-level safety)

They do NOT own:
- business policy decisions (those stay in handlers)
- validation logic (belongs in boundary models or handler gates)
- Pydantic model construction for downstream use

Residual note: features remains Mapping because deeper feature typing
is deferred to Package 2. Callers that need a mutable dict must convert
via dict(cmd.features).

Behavioral preservation notes:
- canonical_structural_regime_label maps BULL_TREND→TREND_UP,
  BEAR_TREND→TREND_DOWN, and fails unknown labels closed to UNCERTAIN.
- confidence and raw_confidence are float-resolved; None on failure.
  This matches the previous float(confidence_raw) coercion in the handler.
- regime_raw_confidence is preserved from the raw transport dict (as string)
  for state fields that historically stored the raw string value.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any

from apps.reference.contracts.runtime_regime_layers import (
    canonical_structural_regime_label,
)
from apps.reference.domains.decision_making.contracts.boundary_models import (
    ProcessStrategyBoundary,
    RegimeDetectedBoundary,
)
from apps.reference.domains.decision_making.contracts.core_models import (
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


def _canonical_process_strategy_regime(
    boundary: ProcessStrategyBoundary,
) -> tuple[str, MappingProxyType[str, Any] | None]:
    """Resolve the canonical structural regime without stringifying mappings."""
    snapshot: dict[str, Any] | None = None
    if isinstance(boundary.regime, dict):
        snapshot = dict(boundary.regime)

    candidates: list[Any] = [boundary.structural_regime]
    if snapshot is not None:
        candidates.extend([snapshot.get("regime"), snapshot.get("overall_regime")])
    elif isinstance(boundary.regime, str):
        # Backward compatibility for older producers that sent a plain label.
        candidates.append(boundary.regime)

    if isinstance(boundary.regime_ctx, dict):
        candidates.append(boundary.regime_ctx.get("regime"))

    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        normalized = canonical_structural_regime_label(candidate)
        if normalized != "UNCERTAIN" or candidate.strip().upper() == "UNCERTAIN":
            return normalized, (
                MappingProxyType(snapshot) if snapshot is not None else None
            )

    return "UNCERTAIN", (
        MappingProxyType(snapshot) if snapshot is not None else None
    )
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
    price_motion = (
        MappingProxyType(dict(boundary.price_motion))
        if boundary.price_motion is not None
        else None
    )
    structural_regime, regime_snapshot = _canonical_process_strategy_regime(
        boundary
    )
    return ProcessStrategyCmd(
        symbol=boundary.symbol,
        tf_sec=boundary.tf_sec,
        bar_close_ts=boundary.bar_close_ts,
        rid=boundary.rid,
        features=MappingProxyType(features),
        warmup=warmup,
        raw=MappingProxyType(raw),
        price_motion=price_motion,
        structural_regime=structural_regime,
        regime_snapshot=regime_snapshot,
    )


def map_regime_boundary_to_event(
    boundary: RegimeDetectedBoundary,
    raw: dict[str, Any],
) -> RegimeEvent:
    """Map RegimeDetectedBoundary and original payload to RegimeEvent.

    Regime normalization is applied here via canonical_structural_regime_label
    so downstream logic always receives a known label. Unknown labels fail
    closed to UNCERTAIN.

    Args:
        boundary: Pydantic-validated boundary model.
        raw: The original transport dict, preserved for provenance helpers
             (build_regime_provenance_fields) and fields not promoted to
             first-class attributes (raw_regime, bar_close_ts_ms, etc.).

    Returns:
        Immutable RegimeEvent with normalized regime label.
    """
    regime_normalized = canonical_structural_regime_label(
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
