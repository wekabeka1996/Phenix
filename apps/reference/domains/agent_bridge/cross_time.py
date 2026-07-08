"""Deterministic cross-time session classification for P15 evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TemporalClass = Literal[
    "same_runtime_close_gap",
    "same_day_different_hour",
    "different_day",
    "operator_interrupted",
    "archived_prior_window",
]


class TimeWindowEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    window_id: str = Field(pattern=r"^[a-z0-9_]+$")
    first_ts_ms: int = Field(ge=0)
    last_ts_ms: int = Field(ge=0)
    packet_count: int = Field(ge=1)
    archived: bool = False
    operator_interrupted: bool = False


class ClassifiedTimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    window_id: str
    temporal_class: TemporalClass
    first_ts_ms: int
    last_ts_ms: int
    packet_count: int
    gap_from_previous_ms: int | None = None
    utc_date: str


def classify_time_windows(windows: list[TimeWindowEvidence]) -> list[ClassifiedTimeWindow]:
    if not windows:
        raise ValueError("at least one time window is required")
    ordered = sorted(windows, key=lambda item: item.first_ts_ms)
    result: list[ClassifiedTimeWindow] = []
    previous: TimeWindowEvidence | None = None
    for window in ordered:
        if window.last_ts_ms < window.first_ts_ms:
            raise ValueError(f"window ends before it starts: {window.window_id}")
        if previous and window.first_ts_ms <= previous.last_ts_ms:
            raise ValueError(f"time windows overlap: {previous.window_id} and {window.window_id}")
        current_date = datetime.fromtimestamp(window.first_ts_ms / 1000, tz=timezone.utc).date().isoformat()
        gap = None if previous is None else window.first_ts_ms - previous.last_ts_ms
        if previous is None:
            temporal_class: TemporalClass = "archived_prior_window" if window.archived else "same_runtime_close_gap"
        elif window.operator_interrupted:
            temporal_class = "operator_interrupted"
        else:
            previous_date = datetime.fromtimestamp(previous.first_ts_ms / 1000, tz=timezone.utc).date().isoformat()
            if current_date != previous_date:
                temporal_class = "different_day"
            elif gap is not None and gap >= 4 * 60 * 60 * 1000:
                temporal_class = "same_day_different_hour"
            elif window.archived:
                temporal_class = "archived_prior_window"
            else:
                temporal_class = "same_runtime_close_gap"
        result.append(ClassifiedTimeWindow(
            window_id=window.window_id,
            temporal_class=temporal_class,
            first_ts_ms=window.first_ts_ms,
            last_ts_ms=window.last_ts_ms,
            packet_count=window.packet_count,
            gap_from_previous_ms=gap,
            utc_date=current_date,
        ))
        previous = window
    return result


def cross_time_proof_established(windows: list[ClassifiedTimeWindow]) -> bool:
    return any(item.temporal_class in {"same_day_different_hour", "different_day"} for item in windows)


__all__ = [
    "ClassifiedTimeWindow", "TemporalClass", "TimeWindowEvidence",
    "classify_time_windows", "cross_time_proof_established",
]
