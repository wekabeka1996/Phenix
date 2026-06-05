"""Summary report building and JSON writing for Phase 5 Package 5E.

This module consumes existing simulator outputs from Packages 5A-5D and
produces a single deterministic summary report object.  It is offline-only
and does not mutate runtime config, emit events, or set policy thresholds.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from jsonschema import Draft7Validator

if TYPE_CHECKING:
    from .simulator_engine import SimulationResult

_SCHEMA_PATH = Path(__file__).resolve().parent / \
    "schemas" / "summary_report_v1.json"

_ACTIONABLE_VERDICTS = {"OPEN_LONG", "OPEN_SHORT"}
_COHORT_LABELS = (
    "CORRECT_ENTRY",
    "INCORRECT_ENTRY",
    "CORRECT_ABSTAIN",
    "MISSED_OPPORTUNITY",
    "INCONCLUSIVE",
)


@lru_cache(maxsize=1)
def _load_summary_schema() -> dict[str, Any]:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft7Validator.check_schema(schema)
    return schema


def _format_jsonschema_error(error: Any) -> str:
    if error.path:
        segments = []
        for segment in error.path:
            if isinstance(segment, int):
                segments.append(f"[{segment}]")
            else:
                segments.append(f".{segment}")
        location = "$" + "".join(segments)
    else:
        location = "$"
    return f"{location}: {error.message}"


def _compute_input_counts(result: SimulationResult) -> dict[str, int]:
    return {
        "verdict_count": result.total_verdict_records_loaded,
        "outcome_count": result.total_outcome_records_loaded,
        "matched_count": result.matched_count,
        "unmatched_count": result.unmatched_count,
    }


def _compute_match_stats(result: SimulationResult) -> dict[str, object]:
    total = result.total_verdict_records_loaded
    match_rate: float | None = None
    if total > 0:
        match_rate = result.matched_count / total

    actionable = 0
    non_actionable = 0
    for c in result.correlations:
        if c.outcome is None:
            continue
        if c.verdict.entry_verdict in _ACTIONABLE_VERDICTS:
            actionable += 1
        else:
            non_actionable += 1

    return {
        "match_rate": match_rate,
        "actionable_matched_count": actionable,
        "non_actionable_matched_count": non_actionable,
    }


def _compute_economics(result: SimulationResult) -> dict[str, object]:
    raw_returns: list[float] = []
    net_returns: list[float] = []
    positive_net = 0
    negative_net = 0

    for c in result.correlations:
        if c.raw_return is not None:
            raw_returns.append(c.raw_return)
        if c.net_return is not None:
            net_returns.append(c.net_return)
            if c.net_return > 0:
                positive_net += 1
            elif c.net_return < 0:
                negative_net += 1

    return {
        "avg_raw_return": sum(raw_returns) / len(raw_returns) if raw_returns else None,
        "avg_net_return": sum(net_returns) / len(net_returns) if net_returns else None,
        "positive_net_count": positive_net,
        "negative_net_count": negative_net,
    }


def _compute_disagreement_stats(result: SimulationResult) -> dict[str, object]:
    count = len(result.disagreements)
    total_cost = sum(
        float(d.get("cost_of_disagreement", 0.0))
        for d in result.disagreements
    )
    matched = result.matched_count
    rate: float | None = None
    if matched > 0:
        rate = count / matched

    return {
        "disagreement_count": count,
        "disagreement_rate": rate,
        "total_cost_of_disagreement": total_cost,
    }


def _compute_cohort_stats(
    calibration_records: Sequence[Mapping[str, object]],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in calibration_records:
        cohort = record.get("cohort")
        if isinstance(cohort, str) and cohort in _COHORT_LABELS:
            counts[cohort] += 1

    return {label: counts.get(label, 0) for label in _COHORT_LABELS}


def _build_policy_readiness_notes(
    input_counts: dict[str, int],
    economics: dict[str, object],
    disagreement_stats: dict[str, object],
    cohort_stats: dict[str, int],
) -> list[str]:
    notes: list[str] = []

    verdict_count = input_counts["verdict_count"]
    matched_count = input_counts["matched_count"]

    if verdict_count == 0:
        notes.append("No verdict records loaded; summary is vacuous.")
        return notes

    if matched_count == 0:
        notes.append(
            "No matched correlations; economics and disagreement stats are empty."
        )
        return notes

    match_rate = matched_count / verdict_count if verdict_count > 0 else 0
    if match_rate < 0.5:
        notes.append(
            f"Low match rate ({match_rate:.2%}); "
            "outcome data may be incomplete."
        )

    disagreement_rate = disagreement_stats.get("disagreement_rate")
    if isinstance(disagreement_rate, (int, float)) and disagreement_rate > 0.3:
        notes.append(
            f"High disagreement rate ({disagreement_rate:.2%}); "
            "review optimal-action calibration."
        )

    incorrect = cohort_stats.get("INCORRECT_ENTRY", 0)
    correct = cohort_stats.get("CORRECT_ENTRY", 0)
    total_entries = incorrect + correct
    if total_entries > 0 and incorrect / total_entries > 0.5:
        notes.append(
            f"Majority of entries are incorrect ({incorrect}/{total_entries}); "
            "entry quality may need attention."
        )

    if not notes:
        notes.append("No anomalies detected in summary statistics.")

    return notes


def build_summary_report(
    result: SimulationResult,
    *,
    generated_at_ms: int | None = None,
) -> dict[str, object]:
    """Build a deterministic summary report dict from a SimulationResult.

    Parameters
    ----------
    result:
        Complete simulation result from ``run_simulation()``.
    generated_at_ms:
        Explicit writer-time timestamp.  When ``None`` the current wall
        clock is used.  Callers that need deterministic output for tests
        should pass a fixed value.

    Returns
    -------
    dict
        Summary report conforming to ``summary_report_v1.json`` schema.
    """

    if generated_at_ms is None:
        generated_at_ms = int(time.time() * 1000)

    input_counts = _compute_input_counts(result)
    match_stats = _compute_match_stats(result)
    economics = _compute_economics(result)
    disagreement_stats = _compute_disagreement_stats(result)
    cohort_stats = _compute_cohort_stats(result.calibration_records)

    expert_summary: dict[str, object] = {}
    if result.expert_accuracy_summary:
        expert_summary = {
            "total_count": result.expert_accuracy_summary.get("total_count", 0),
            "correct_count": result.expert_accuracy_summary.get("correct_count", 0),
            "accuracy_rate": result.expert_accuracy_summary.get("accuracy_rate"),
        }
    else:
        expert_summary = {
            "total_count": 0,
            "correct_count": 0,
            "accuracy_rate": None,
        }

    policy_readiness_notes = _build_policy_readiness_notes(
        input_counts, economics, disagreement_stats, cohort_stats,
    )

    report: dict[str, object] = {
        "schema_version": "1",
        "generated_at_ms": generated_at_ms,
        "input_counts": input_counts,
        "match_stats": match_stats,
        "economics": economics,
        "disagreement_stats": disagreement_stats,
        "expert_accuracy_summary": expert_summary,
        "cohort_stats": cohort_stats,
        "policy_readiness_notes": policy_readiness_notes,
    }

    validator = Draft7Validator(_load_summary_schema())
    errors = sorted(
        validator.iter_errors(report),
        key=lambda error: list(error.path),
    )
    if errors:
        formatted = "; ".join(
            _format_jsonschema_error(e) for e in errors[:5]
        )
        raise ValueError(
            f"Built summary report failed schema validation: {formatted}"
        )

    return report


def write_summary_report(
    *,
    report: Mapping[str, object],
    output_path: str | Path,
) -> Path:
    """Write a validated summary report to deterministic JSON.

    Policy: creates missing parent directories, sorts keys
    deterministically, and **overwrites** the target file if it already
    exists.  This explicit-overwrite policy is chosen because summary
    reports are regenerated on each simulation run; a create-only policy
    would force callers to manage cleanup.

    Raises
    ------
    TypeError
        If *report* is not a mapping.
    IsADirectoryError
        If *output_path* is an existing directory.
    ValueError
        If *report* fails schema validation or if *output_path* does not
        use a ``.json`` extension.
    """

    if isinstance(report, (str, bytes)):
        raise TypeError(
            "report must be a mapping, not a string-like value"
        )

    path = Path(output_path)
    if path.is_dir():
        raise IsADirectoryError(
            f"summary report path is a directory: {path}"
        )
    if path.suffix.lower() != ".json":
        raise ValueError(
            "summary report path must use a .json extension"
        )

    validator = Draft7Validator(_load_summary_schema())
    errors = sorted(
        validator.iter_errors(dict(report)),
        key=lambda error: list(error.path),
    )
    if errors:
        formatted = "; ".join(
            _format_jsonschema_error(e) for e in errors[:5]
        )
        raise ValueError(
            f"Summary report failed schema validation: {formatted}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(dict(report), handle, sort_keys=True, indent=2)
        handle.write("\n")

    return path
