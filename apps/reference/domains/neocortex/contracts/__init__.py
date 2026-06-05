"""Neocortex contracts package.

Keep package imports light so submodule imports like contracts.causal_time do
not eagerly pull the control-decision stack and its numpy dependency.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .causal_time import (
        CausalTimeDecision,
        CausalTimeProvenance,
        DatasetVisibility,
        PRODUCTION_CAUSAL_TIME_PROVENANCE,
        coerce_causal_time_provenance,
        get_non_causal_counter,
        increment_non_causal_counter,
        is_causal_time_provenance,
        make_causal_decision,
        reset_non_causal_counter,
    )
    from .control_decision import (
        AuthorityMode,
        ControlDecisionAction,
        ControlDecisionApplyResult,
        ControlDecisionRequest,
        ControlDecisionRequestKind,
        ControlDecisionResponse,
    )
    from .failure_taxonomy import (
        FailureOutcome,
        FailureOutcomeTaxonomy,
        FailureReasonCode,
        get_failure_outcome_counts,
        get_failure_outcome_total,
        record_failure_outcome,
        reset_failure_outcomes,
    )


_EXPORT_MAP = {
    "CausalTimeDecision": (".causal_time", "CausalTimeDecision"),
    "CausalTimeProvenance": (".causal_time", "CausalTimeProvenance"),
    "DatasetVisibility": (".causal_time", "DatasetVisibility"),
    "PRODUCTION_CAUSAL_TIME_PROVENANCE": (
        ".causal_time",
        "PRODUCTION_CAUSAL_TIME_PROVENANCE",
    ),
    "coerce_causal_time_provenance": (".causal_time", "coerce_causal_time_provenance"),
    "get_non_causal_counter": (".causal_time", "get_non_causal_counter"),
    "increment_non_causal_counter": (".causal_time", "increment_non_causal_counter"),
    "is_causal_time_provenance": (".causal_time", "is_causal_time_provenance"),
    "make_causal_decision": (".causal_time", "make_causal_decision"),
    "reset_non_causal_counter": (".causal_time", "reset_non_causal_counter"),
    "FailureOutcome": (".failure_taxonomy", "FailureOutcome"),
    "FailureOutcomeTaxonomy": (".failure_taxonomy", "FailureOutcomeTaxonomy"),
    "FailureReasonCode": (".failure_taxonomy", "FailureReasonCode"),
    "get_failure_outcome_counts": (".failure_taxonomy", "get_failure_outcome_counts"),
    "get_failure_outcome_total": (".failure_taxonomy", "get_failure_outcome_total"),
    "record_failure_outcome": (".failure_taxonomy", "record_failure_outcome"),
    "reset_failure_outcomes": (".failure_taxonomy", "reset_failure_outcomes"),
    "AuthorityMode": (".control_decision", "AuthorityMode"),
    "ControlDecisionAction": (".control_decision", "ControlDecisionAction"),
    "ControlDecisionApplyResult": (".control_decision", "ControlDecisionApplyResult"),
    "ControlDecisionRequest": (".control_decision", "ControlDecisionRequest"),
    "ControlDecisionRequestKind": (".control_decision", "ControlDecisionRequestKind"),
    "ControlDecisionResponse": (".control_decision", "ControlDecisionResponse"),
}

__all__ = sorted(_EXPORT_MAP)


def __getattr__(name: str) -> object:
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, export_name = _EXPORT_MAP[name]
    value = getattr(import_module(module_name, __name__), export_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
