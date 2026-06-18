from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


REGIME_SOURCE_SAME_BAR_DETECTOR = "same_bar_detector"
REGIME_SOURCE_CACHED_PREVIOUS_BAR = "cached_previous_bar"
REGIME_SOURCE_MISSING_DETECTOR_HEARTBEAT = "missing_detector_heartbeat"

CANONICAL_STRUCTURAL_REGIMES = frozenset(
    {
        "TREND_UP",
        "TREND_DOWN",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "MEAN_REVERSION",
        "UNCERTAIN",
        "FLAT_LOW",
        "FLAT_NORMAL",
        "FLAT_HIGH",
    }
)


def _coerce_positive_int(value: Any) -> int | None:
    if value in (None, "", "None"):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


class RuntimeRegimeLayer(str, Enum):
    STRUCTURAL = "structural"
    EXECUTION_MICRO = "execution_micro"
    GLOBAL_BACKDROP = "global_backdrop"


class RuntimeRegimeScope(str, Enum):
    PER_SYMBOL = "per_symbol"
    GLOBAL = "global"


class RuntimeRegimeClock(str, Enum):
    BAR = "bar"
    EVENT_DRIVEN = "event_driven"


def normalize_structural_regime_label(label: Any) -> str:
    normalized = str(label or "").strip().upper()
    if normalized == "BULL_TREND":
        return "TREND_UP"
    if normalized == "BEAR_TREND":
        return "TREND_DOWN"
    return normalized


def canonical_structural_regime_label(label: Any) -> str:
    """Return a known structural label, failing closed to ``UNCERTAIN``."""
    normalized = normalize_structural_regime_label(label)
    return normalized if normalized in CANONICAL_STRUCTURAL_REGIMES else "UNCERTAIN"


def regime_layer_of(
    payload: Mapping[str, Any] | None,
    *,
    default: RuntimeRegimeLayer = RuntimeRegimeLayer.STRUCTURAL,
) -> RuntimeRegimeLayer:
    raw = str((payload or {}).get("regime_layer")
              or default.value).strip().lower()
    for candidate in RuntimeRegimeLayer:
        if raw == candidate.value:
            return candidate
    return default


def regime_scope_of(
    payload: Mapping[str, Any] | None,
    *,
    default: RuntimeRegimeScope = RuntimeRegimeScope.PER_SYMBOL,
) -> RuntimeRegimeScope:
    raw = str((payload or {}).get("regime_scope")
              or default.value).strip().lower()
    for candidate in RuntimeRegimeScope:
        if raw == candidate.value:
            return candidate
    return default


def regime_clock_of(
    payload: Mapping[str, Any] | None,
    *,
    default: RuntimeRegimeClock = RuntimeRegimeClock.BAR,
) -> RuntimeRegimeClock:
    raw = str((payload or {}).get("regime_clock")
              or default.value).strip().lower()
    for candidate in RuntimeRegimeClock:
        if raw == candidate.value:
            return candidate
    return default


def structural_regime_ref(symbol: str, ts_ms: int | None) -> str:
    return f"structural:{str(symbol).upper()}:{int(ts_ms or 0)}"


def regime_event_ts_ms_of(payload: Mapping[str, Any] | None) -> int | None:
    event = payload or {}
    for key in ("regime_event_ts_ms", "ts_ms", "ts", "bar_close_ts_ms"):
        candidate = _coerce_positive_int(event.get(key))
        if candidate is not None:
            return candidate
    return None


def build_regime_provenance_fields(
    payload: Mapping[str, Any] | None,
    *,
    bar_close_ts_ms: int | None = None,
    missing_heartbeat: bool = False,
) -> dict[str, Any]:
    if missing_heartbeat:
        return {
            "regime_source": REGIME_SOURCE_MISSING_DETECTOR_HEARTBEAT,
            "regime_event_ts_ms": None,
            "regime_same_bar": None,
            "regime_provenance_reason": "missing_detector_heartbeat_fail_closed",
        }

    event_ts_ms = regime_event_ts_ms_of(payload)
    current_bar_ts_ms = _coerce_positive_int(bar_close_ts_ms)
    if current_bar_ts_ms is None:
        current_bar_ts_ms = _coerce_positive_int(
            (payload or {}).get("bar_close_ts_ms"))

    regime = normalize_structural_regime_label(
        (payload or {}).get("regime") or (payload or {}).get("overall_regime")
    )
    explicit_uncertain = regime == "UNCERTAIN"

    regime_same_bar: bool | None = None
    if event_ts_ms is not None and current_bar_ts_ms is not None:
        regime_same_bar = event_ts_ms == current_bar_ts_ms

    if regime_same_bar is False:
        regime_source = REGIME_SOURCE_CACHED_PREVIOUS_BAR
        regime_reason = (
            "explicit_uncertain_cached_regime"
            if explicit_uncertain
            else "cached_previous_bar_regime"
        )
    elif regime_same_bar is True:
        regime_source = REGIME_SOURCE_SAME_BAR_DETECTOR
        regime_reason = (
            "explicit_uncertain_same_bar"
            if explicit_uncertain
            else "same_bar_detector_truth"
        )
    else:
        regime_source = REGIME_SOURCE_SAME_BAR_DETECTOR
        regime_reason = (
            "explicit_uncertain_without_bar_context"
            if explicit_uncertain
            else "detector_state_without_bar_context"
        )

    return {
        "regime_source": regime_source,
        "regime_event_ts_ms": event_ts_ms,
        "regime_same_bar": regime_same_bar,
        "regime_provenance_reason": regime_reason,
    }


def attach_regime_provenance(
    payload: Mapping[str, Any] | None,
    *,
    bar_close_ts_ms: int | None = None,
    missing_heartbeat: bool = False,
) -> dict[str, Any]:
    snapshot = dict(payload) if isinstance(payload, Mapping) else {}
    snapshot.update(
        build_regime_provenance_fields(
            payload,
            bar_close_ts_ms=bar_close_ts_ms,
            missing_heartbeat=missing_heartbeat,
        )
    )
    return snapshot


def is_structural_regime_payload(payload: Mapping[str, Any] | None) -> bool:
    return regime_layer_of(payload) == RuntimeRegimeLayer.STRUCTURAL


def should_apply_global_execution_regime(payload: Mapping[str, Any] | None) -> bool:
    layer = regime_layer_of(payload)
    scope = regime_scope_of(payload)
    return scope == RuntimeRegimeScope.GLOBAL and layer in (
        RuntimeRegimeLayer.EXECUTION_MICRO,
        RuntimeRegimeLayer.GLOBAL_BACKDROP,
    )
