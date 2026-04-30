"""Causal Time Contract — Phase 1 invariant I3.

This module is the canonical home for causal time provenance types.

CausalTimeProvenance is imported from the hot-path canonical source
(logic.datasets.time_provenance) to avoid duplicate enum definitions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

# Re-export from canonical hot-path source. Do NOT duplicate the enum.
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (  # noqa: F401
    CausalTimeProvenance,
    PRODUCTION_CAUSAL_TIME_PROVENANCE,
    coerce_causal_time_provenance,
    is_causal_time_provenance,
)
from apps.reference.telemetry.metrics import inc_neocortex_dataset_invalid

# ---------------------------------------------------------------------------
# Dataset visibility literals
# ---------------------------------------------------------------------------
DatasetVisibility = Literal["trainable", "diagnostics_only"]

NON_CAUSAL_REASON_CODE = "NON_CAUSAL_TIME"

# ---------------------------------------------------------------------------
# In-process metric counter — no external metrics subsystem required.
# The counter is module-level so any import of this module shares the state.
# Production code calls increment_non_causal_counter(); tests read it directly.
# ---------------------------------------------------------------------------
_non_causal_time_counter: int = 0


def increment_non_causal_counter() -> None:
    """Increment the dataset.invalid_total{reason_code=NON_CAUSAL_TIME} counter."""
    global _non_causal_time_counter
    _non_causal_time_counter += 1
    inc_neocortex_dataset_invalid(NON_CAUSAL_REASON_CODE)


def get_non_causal_counter() -> int:
    """Return the current value of dataset.invalid_total{reason_code=NON_CAUSAL_TIME}."""
    return _non_causal_time_counter


def reset_non_causal_counter() -> None:
    """Reset the counter to 0. For testing only — never call in production."""
    global _non_causal_time_counter
    _non_causal_time_counter = 0


# ---------------------------------------------------------------------------
# CausalTimeDecision — typed record of the gate outcome for a single row.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CausalTimeDecision:
    """Complete causal time gate decision for a single parser row.

    Contract:
    - If event_time_is_causal=True: trainable=True, dataset_visibility="trainable".
    - If event_time_is_causal=False: trainable=False,
      dataset_visibility="diagnostics_only", reason_code=NON_CAUSAL_TIME.
    - No exceptions. No silent fallbacks.
    """

    event_ts_ms: Optional[int]
    event_time_source: CausalTimeProvenance
    event_time_is_causal: bool
    trainable: bool
    dataset_visibility: DatasetVisibility
    reason_code: Optional[str]

    def __post_init__(self) -> None:
        # Hard invariant: if causal, must be trainable and visible.
        if self.event_time_is_causal:
            if not self.trainable:
                raise ValueError(
                    "CausalTimeDecision: causal time must have trainable=True"
                )
            if self.dataset_visibility != "trainable":
                raise ValueError(
                    "CausalTimeDecision: causal time must have dataset_visibility='trainable'"
                )
        else:
            if self.trainable:
                raise ValueError(
                    "CausalTimeDecision: non-causal time must have trainable=False"
                )
            if self.dataset_visibility != "diagnostics_only":
                raise ValueError(
                    "CausalTimeDecision: non-causal time must have dataset_visibility='diagnostics_only'"
                )


def make_causal_decision(
    event_ts_ms: Optional[int],
    provenance: CausalTimeProvenance,
) -> CausalTimeDecision:
    """Build a CausalTimeDecision from event_ts_ms and provenance.

    If provenance is not in PRODUCTION_CAUSAL_TIME_PROVENANCE, the row is
    non-causal, non-trainable, and reason_code=NON_CAUSAL_TIME is set.
    The in-process counter is incremented for non-causal rows.
    """
    causal = is_causal_time_provenance(provenance)
    if causal:
        return CausalTimeDecision(
            event_ts_ms=event_ts_ms,
            event_time_source=provenance,
            event_time_is_causal=True,
            trainable=True,
            dataset_visibility="trainable",
            reason_code=None,
        )
    else:
        increment_non_causal_counter()
        return CausalTimeDecision(
            event_ts_ms=event_ts_ms,
            event_time_source=provenance,
            event_time_is_causal=False,
            trainable=False,
            dataset_visibility="diagnostics_only",
            reason_code=NON_CAUSAL_REASON_CODE,
        )
