"""
LLM Judge Phase 3 — Admissibility Filter

Evaluates whether a chamber aggregation cycle meets the requirements
for an admissible verdict. Rules are evaluated in priority order;
first match wins.

Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE3_IMPLEMENTATION_BLUEPRINT.md §11.5
"""

from typing import List, Literal, Optional, Tuple

from apps.reference.domains.alpha_search.judge.contracts import ExpertOutput

Admissibility = Literal["ADMISSIBLE", "INADMISSIBLE", "QUORUM_INSUFFICIENT"]


def evaluate_admissibility(
    expert_outputs: List[ExpertOutput],
    responding_count: int,
    expected_expert_count: int,
    *,
    min_quorum: int,
    max_staleness_ms: int,
    cycle_ts_ms: int,
    verdict_scope: Literal["ENTRY", "LIFECYCLE"],
) -> Tuple[Admissibility, Optional[str]]:
    """Evaluate admissibility of a chamber aggregation cycle.

    Rules (evaluated in order, first match wins):
        R1: Quorum insufficient if responding_count < min_quorum
        R2: Silent failure if len(expert_outputs) < expected_expert_count
        R2.5: Duplicate expert_id detected
        R3: Freshness violation if any output is stale
        R4: Scope mismatch (defense-in-depth)
        R5: Default → ADMISSIBLE
    """
    # R1: Quorum
    if responding_count < min_quorum:
        return "QUORUM_INSUFFICIENT", "responding_below_min_quorum"

    # R2: Silent failure — solicited expert produced no output
    if len(expert_outputs) < expected_expert_count:
        return "INADMISSIBLE", "solicited_expert_missing_output"

    # R2.5: Duplicate expert_id
    expert_ids = [eo.expert_id for eo in expert_outputs]
    if len(set(expert_ids)) < len(expert_ids):
        return "INADMISSIBLE", "duplicate_expert_id"

    # R3: Freshness
    staleness_threshold = cycle_ts_ms - max_staleness_ms
    for eo in expert_outputs:
        if eo.ts_ms < staleness_threshold:
            return "INADMISSIBLE", "stale_expert_output"

    # R4: Scope mismatch (defense-in-depth)
    for eo in expert_outputs:
        if verdict_scope == "ENTRY" and eo.entry_verdict is None:
            return "INADMISSIBLE", "scope_mismatch"
        if verdict_scope == "LIFECYCLE" and eo.lifecycle_verdict is None:
            return "INADMISSIBLE", "scope_mismatch"

    # R5: Default
    return "ADMISSIBLE", None
