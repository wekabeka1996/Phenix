from __future__ import annotations

from enum import Enum
from typing import Any


class CausalTimeProvenance(str, Enum):
    EXCHANGE_EVENT = "exchange_event"
    AURORA_EVENT = "aurora_event"
    BAR_END = "bar_end"
    CAPTURED_WALLCLOCK = "captured_wallclock"
    FILE_OFFSET_LEGACY = "file_offset_legacy"
    UNKNOWN = "unknown"


PRODUCTION_CAUSAL_TIME_PROVENANCE = frozenset(
    {
        CausalTimeProvenance.EXCHANGE_EVENT,
        CausalTimeProvenance.AURORA_EVENT,
        CausalTimeProvenance.BAR_END,
    }
)


_ALIASES = {
    "exchange_event": CausalTimeProvenance.EXCHANGE_EVENT,
    "exchange_ts_ms": CausalTimeProvenance.EXCHANGE_EVENT,
    "aurora_event": CausalTimeProvenance.AURORA_EVENT,
    "event_ts_ms": CausalTimeProvenance.AURORA_EVENT,
    "timestamp_ms": CausalTimeProvenance.AURORA_EVENT,
    "timestamp": CausalTimeProvenance.AURORA_EVENT,
    "ts": CausalTimeProvenance.AURORA_EVENT,
    "close_ts_ms": CausalTimeProvenance.AURORA_EVENT,
    "bar_end": CausalTimeProvenance.BAR_END,
    "bar_end_ts_ms": CausalTimeProvenance.BAR_END,
    "captured_wallclock": CausalTimeProvenance.CAPTURED_WALLCLOCK,
    "captured_ts_ms": CausalTimeProvenance.CAPTURED_WALLCLOCK,
    "log_timestamp": CausalTimeProvenance.CAPTURED_WALLCLOCK,
    "file_offset_legacy": CausalTimeProvenance.FILE_OFFSET_LEGACY,
    "legacy_non_causal_file_offset": CausalTimeProvenance.FILE_OFFSET_LEGACY,
    "unknown": CausalTimeProvenance.UNKNOWN,
}


def coerce_causal_time_provenance(value: Any) -> CausalTimeProvenance:
    if isinstance(value, CausalTimeProvenance):
        return value
    if value is None:
        return CausalTimeProvenance.UNKNOWN
    text = str(value).strip().lower()
    if not text:
        return CausalTimeProvenance.UNKNOWN
    return _ALIASES.get(text, CausalTimeProvenance.UNKNOWN)


def is_causal_time_provenance(provenance: CausalTimeProvenance) -> bool:
    return provenance in PRODUCTION_CAUSAL_TIME_PROVENANCE
