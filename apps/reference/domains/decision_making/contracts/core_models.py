"""Lightweight immutable internal core models for the decision-making domain.

These are the internal representation consumed by business logic AFTER
boundary parsing. They carry no Pydantic dependency and are safe to pass
into hot-path decision logic.

Design rules applied:
- @dataclass(frozen=True, slots=True) for immutability and memory efficiency.
- Mapping[str, Any] for pass-through maps (not recursively frozen in Package 1).
- ``raw: Mapping[str, Any]`` fields carry the original transport payload for
  utilities that predate the typed model and expect dict-like access:
    - extract_canonical_bar_identity
    - extract_canonical_replay_identity
    - extract_gap_status
    - build_regime_provenance_fields
  These are explicitly labeled as raw/provenance data, not part of the typed
  contract. They are wrapped in MappingProxyType in the mapper for
  read-only safety at the top level.

Residual partial typing (intentional for Package 1):
- ProcessStrategyCmd.features remains Mapping[str, Any]. Deeper feature
  typing (pillar_sum, atr, obi, etc.) is deferred to Package 2.
- ProcessStrategyCmd.raw and RegimeEvent.raw carry the full transport
  payload for backward-compatible utility integration.
- WarmupState.ready is Mapping[str, bool] (not recursively frozen).
  Nested structure is not deeply frozen in this package.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType  # noqa: F401 — re-exported for mappers
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class WarmupState:
    """Typed warmup readiness extracted from CMD:PROCESS_STRATEGY.

    Sourced from the ``warmup`` blob in the command payload. Fields are
    business-ready and no longer require .get() access in consuming logic.

    Note: ready is Mapping[str, bool] rather than a deeply typed dataclass.
    Recursive feature-flag typing is deferred to Package 2.
    """

    full_ready: bool
    ticks_seen: int
    # Feature readiness flags, e.g. {"atr_ready": True, "obi_ready": False}.
    # Mapping (not dict) to signal read-only intent at this level.
    ready: Mapping[str, bool]
    # Diagnostic reasons for warmup incompleteness.
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProcessStrategyCmd:
    """Internal typed command for CMD:PROCESS_STRATEGY.

    Represents the business-ready state after boundary parsing and mapping.
    Core business logic consumes this model rather than raw dicts.

    Fail-closed semantics:
    - tf_sec=None triggers Gate 1 in the handler (missing timeframe reject).
    - bar_close_ts=None triggers Gate 4 in the handler (missing timestamp
      reject). Both gates write structured WAL records.

    Residual note: features remains Mapping because deeper feature typing is
    deferred to Package 2. raw carries the full transport payload for
    downstream utilities (bar identity extraction, gap detection, etc.)
    that expect dict-like access and predate this typed model.
    """

    symbol: str
    tf_sec: int | None          # None → Gate 1 reject in handler
    bar_close_ts: int | None    # None → Gate 4 reject in handler
    rid: str | None

    # Deferred deeper typing (Package 2). Currently still a Mapping.
    features: Mapping[str, Any]

    warmup: WarmupState

    # Full original transport payload.
    # Used by utilities (extract_canonical_bar_identity, gap extractors, etc.)
    # that need full dict-like access and were not updated in Package 1.
    # This is NOT part of the typed contract — treat as opaque provenance.
    raw: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class RegimeEvent:
    """Internal typed event for EVT:REGIME_DETECTED.

    Regime label is normalized via normalize_structural_regime_label in
    the mapper. Business logic receives canonical labels (TREND_UP, etc.)
    or UNCERTAIN for unrecognized inputs — preserving existing behavior.

    Confidence is float-resolved (or None) in the mapper. Timestamps are
    in milliseconds.

    raw carries the full transport payload for regime provenance helpers
    (build_regime_provenance_fields) that expect dict-like access and for
    fields not promoted to first-class attributes (raw_regime, bar_close_ts_ms,
    regime_layer, etc.).
    """

    symbol: str
    # normalized label (e.g. TREND_UP, UNCERTAIN)
    regime: str
    confidence: float | None         # float-resolved, or None if absent/invalid
    ts_ms: int                       # millisecond timestamp
    structural_regime_ref: str | None
    changed: bool | None             # True if regime changed, False if heartbeat
    # raw pre-smoothed confidence (float-resolved)
    raw_confidence: float | None
    last_update_ts_ms: int           # heartbeat/liveness timestamp

    # Full original transport payload.
    # Required by build_regime_provenance_fields and other helpers that
    # need access to fields not promoted to first-class (raw_regime,
    # bar_close_ts_ms, regime_layer, regime_scope, etc.).
    raw: Mapping[str, Any]
