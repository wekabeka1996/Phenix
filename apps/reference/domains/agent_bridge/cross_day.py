"""Typed P16 UTC-date boundary evidence and deterministic classification."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CrossDayClass = Literal[
    "different_utc_date",
    "same_utc_date_different_hour",
    "same_runtime_close_gap",
    "operator_interrupted",
    "blocked_no_later_date",
]


class CrossDayEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: CrossDayClass
    current_utc_date: str
    prior_utc_dates: list[str]
    current_first_ts_ms: int = Field(ge=0)
    current_last_ts_ms: int = Field(ge=0)
    prior_last_ts_ms: int | None = Field(default=None, ge=0)
    gap_from_prior_ms: int | None = None
    cross_day_proof_established: bool


def classify_cross_day_session(
    *,
    current_first_ts_ms: int,
    current_last_ts_ms: int,
    prior_utc_dates: list[str],
    prior_last_ts_ms: int | None,
    operator_interrupted: bool = False,
) -> CrossDayEvidence:
    if current_last_ts_ms < current_first_ts_ms:
        raise ValueError("current window ends before it starts")
    current_date = datetime.fromtimestamp(current_first_ts_ms / 1000, tz=timezone.utc).date().isoformat()
    normalized_prior = sorted(set(prior_utc_dates))
    gap = None if prior_last_ts_ms is None else current_first_ts_ms - prior_last_ts_ms
    if gap is not None and gap <= 0:
        raise ValueError("current window overlaps prior evidence")
    if operator_interrupted:
        classification: CrossDayClass = "operator_interrupted"
    elif normalized_prior and current_date not in normalized_prior:
        classification = "different_utc_date"
    elif not normalized_prior:
        classification = "blocked_no_later_date"
    elif gap is not None and gap >= 4 * 60 * 60 * 1000:
        classification = "same_utc_date_different_hour"
    else:
        classification = "same_runtime_close_gap"
    return CrossDayEvidence(
        classification=classification,
        current_utc_date=current_date,
        prior_utc_dates=normalized_prior,
        current_first_ts_ms=current_first_ts_ms,
        current_last_ts_ms=current_last_ts_ms,
        prior_last_ts_ms=prior_last_ts_ms,
        gap_from_prior_ms=gap,
        cross_day_proof_established=classification == "different_utc_date",
    )


__all__ = ["CrossDayClass", "CrossDayEvidence", "classify_cross_day_session"]
