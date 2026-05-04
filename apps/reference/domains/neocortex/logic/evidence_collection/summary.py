from __future__ import annotations

import sys
from collections import Counter
from typing import Iterable

from apps.reference.domains.neocortex.logic.evidence_collection.contracts import (
    DecisionOutcomeEvidenceSummary,
    EvidenceCollectionBundle,
    EvidenceCollectionSummary,
    ObservationEvidenceSummary,
)


LEGACY_EXPERIMENTS_PREFIX = "apps.reference.domains.neocortex.experiments"


def legacy_experiments_import_state() -> tuple[bool, tuple[str, ...]]:
    modules = tuple(
        sorted(
            module_name
            for module_name in sys.modules
            if module_name == LEGACY_EXPERIMENTS_PREFIX
            or module_name.startswith(f"{LEGACY_EXPERIMENTS_PREFIX}.")
        )
    )
    return bool(modules), modules


def merge_histograms(*histograms: dict[str, int]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for histogram in histograms:
        counter.update({str(key): int(value)
                       for key, value in histogram.items() if int(value)})
    return dict(sorted(counter.items()))


def build_bundle_completeness(summary: EvidenceCollectionSummary) -> bool:
    return bool(
        summary.dataset_cutover_summary is not None
        and summary.dataset_cutover_decision is not None
        and not summary.legacy_experiments_imported
    )


def _format_count_lines(title: str, items: Iterable[tuple[str, int]]) -> list[str]:
    lines = [f"## {title}"]
    for key, value in items:
        lines.append(f"- {key}: {value}")
    return lines


def render_evidence_collection_markdown(
    bundle: EvidenceCollectionBundle,
) -> str:
    summary = bundle.summary
    lines: list[str] = [
        "# Neocortex Phase 8A.1 Evidence Collection Bundle",
        "",
        f"- bundle_version: {bundle.bundle_version}",
        f"- generated_at_ms: {bundle.generated_at_ms}",
        f"- evidence_bundle_complete: {summary.evidence_bundle_complete}",
        f"- reward_valid_requested: {summary.reward_valid_requested}",
        f"- reward_valid: {summary.reward_valid}",
        f"- reward_methodology_present: {summary.reward_methodology_present}",
        f"- legacy_experiments_imported: {summary.legacy_experiments_imported}",
        "",
    ]

    observation = summary.observation
    lines.extend(
        _format_count_lines(
            "Observation Evidence",
            (
                ("observation_envelope_count",
                 observation.observation_envelope_count),
                ("causal_valid_count", observation.causal_valid_count),
                ("trainable_count", observation.trainable_count),
                ("diagnostics_only_count", observation.diagnostics_only_count),
                ("invalid_count", observation.invalid_count),
            ),
        )
    )
    lines.append("")

    decision = summary.decision_outcome
    lines.extend(
        _format_count_lines(
            "Decision Outcome Evidence",
            (
                ("decision_row_count", decision.decision_row_count),
                ("trainable_count", decision.trainable_count),
                ("diagnostics_only_count", decision.diagnostics_only_count),
                ("invalid_count", decision.invalid_count),
                ("decision_id_join_count", decision.decision_id_join_count),
                ("rid_join_count", decision.rid_join_count),
                ("lifecycle_id_join_count", decision.lifecycle_id_join_count),
                ("trade_id_join_count", decision.trade_id_join_count),
                ("no_join_count", decision.no_join_count),
                ("terminal_joined_count", decision.terminal_joined_count),
                ("terminal_missing_count", decision.terminal_missing_count),
                ("synthetic_fallback_count", decision.synthetic_fallback_count),
                ("reward_valid_rows_count", decision.reward_valid_rows_count),
            ),
        )
    )
    lines.append("")

    lines.append("## Invalid Reason Histogram")
    if summary.invalid_reason_histogram:
        for key, value in summary.invalid_reason_histogram.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Dataset Cutover Summary")
    if summary.dataset_cutover_summary is not None:
        cutover_summary = summary.dataset_cutover_summary.model_dump(
            mode="json")
        for key in sorted(cutover_summary):
            lines.append(f"- {key}: {cutover_summary[key]}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Dataset Cutover Decision")
    if summary.dataset_cutover_decision is not None:
        cutover_decision = summary.dataset_cutover_decision.model_dump(
            mode="json")
        for key in sorted(cutover_decision):
            lines.append(f"- {key}: {cutover_decision[key]}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Legacy Runtime Import Check")
    lines.append(
        f"- modules: {', '.join(summary.legacy_experiments_modules) or 'none'}")

    return "\n".join(lines).rstrip() + "\n"
