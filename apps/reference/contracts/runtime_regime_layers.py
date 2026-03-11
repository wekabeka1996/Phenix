from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


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


def regime_layer_of(
    payload: Mapping[str, Any] | None,
    *,
    default: RuntimeRegimeLayer = RuntimeRegimeLayer.STRUCTURAL,
) -> RuntimeRegimeLayer:
    raw = str((payload or {}).get("regime_layer") or default.value).strip().lower()
    for candidate in RuntimeRegimeLayer:
        if raw == candidate.value:
            return candidate
    return default


def regime_scope_of(
    payload: Mapping[str, Any] | None,
    *,
    default: RuntimeRegimeScope = RuntimeRegimeScope.PER_SYMBOL,
) -> RuntimeRegimeScope:
    raw = str((payload or {}).get("regime_scope") or default.value).strip().lower()
    for candidate in RuntimeRegimeScope:
        if raw == candidate.value:
            return candidate
    return default


def regime_clock_of(
    payload: Mapping[str, Any] | None,
    *,
    default: RuntimeRegimeClock = RuntimeRegimeClock.BAR,
) -> RuntimeRegimeClock:
    raw = str((payload or {}).get("regime_clock") or default.value).strip().lower()
    for candidate in RuntimeRegimeClock:
        if raw == candidate.value:
            return candidate
    return default


def structural_regime_ref(symbol: str, ts_ms: int | None) -> str:
    return f"structural:{str(symbol).upper()}:{int(ts_ms or 0)}"


def is_structural_regime_payload(payload: Mapping[str, Any] | None) -> bool:
    return regime_layer_of(payload) == RuntimeRegimeLayer.STRUCTURAL


def should_apply_global_execution_regime(payload: Mapping[str, Any] | None) -> bool:
    layer = regime_layer_of(payload)
    scope = regime_scope_of(payload)
    return scope == RuntimeRegimeScope.GLOBAL and layer in (
        RuntimeRegimeLayer.EXECUTION_MICRO,
        RuntimeRegimeLayer.GLOBAL_BACKDROP,
    )
