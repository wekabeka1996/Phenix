"""
LLM Judge Phase 4 — Verdict Synthesizer

Stateless function that maps a JudgeEvidenceEnvelope (containing a
ChamberAggregate) to a typed JudgeVerdict using deterministic rules.

No LLM calls. No external APIs. The chamber's consensus IS the verdict
in Phase 4. Phase 5+ adds intelligence.

Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE4_IMPLEMENTATION_BLUEPRINT.md §14
"""

import logging
from typing import List, Optional

from apps.reference.domains.alpha_search.judge.config_models import VerdictConfig
from apps.reference.domains.alpha_search.judge.contracts import (
    EntryVerdict,
    JudgeEvidenceEnvelope,
    JudgeVerdict,
    LifecycleVerdict,
)

LOG = logging.getLogger(__name__)


def synthesize_verdict(
    envelope: JudgeEvidenceEnvelope,
    *,
    verdict_config: VerdictConfig,
) -> JudgeVerdict:
    """Synthesize a JudgeVerdict from an evidence envelope.

    Deterministic mapping per Phase 4 blueprint §14.1 / §14.2:
        ADMISSIBLE + LONG → OPEN_LONG
        ADMISSIBLE + SHORT → OPEN_SHORT
        ADMISSIBLE + NEUTRAL → NO_ENTRY
        ADMISSIBLE + SPLIT → NO_ENTRY (confidence discounted)
        ADMISSIBLE + None → UNKNOWN
        INADMISSIBLE → UNKNOWN
        QUORUM_INSUFFICIENT → UNKNOWN

    Args:
        envelope: The evidence envelope containing the chamber aggregate.
        verdict_config: Verdict configuration (strategy_id, discount).

    Returns:
        Typed JudgeVerdict with shadow-only posture.
    """
    chamber = envelope.chamber_aggregate
    scope = envelope.verdict_scope
    ts_ms = envelope.ts_ms
    symbol = envelope.symbol

    # Verdict ID is stage-local for backward compatibility.
    # Canonical replay/review identity lives in JudgeVerdict.cycle_key.
    verdict_id = f"vrd_{scope.lower()}_{symbol}_{ts_ms}"

    if scope == "ENTRY":
        entry_verdict, confidence, reasoning, dissent = _map_entry_verdict(
            chamber.admissibility,
            chamber.admissibility_reason,
            chamber.consensus_direction,
            chamber.consensus_strength,
            chamber.expert_outputs,
            verdict_config.split_confidence_discount,
        )
        suppression_reason = None
        suppression_code = None
        if entry_verdict == "SUPPRESS":
            suppression_reason = reasoning[0]
            suppression_code = _suppression_code_from_admissibility_reason(
                chamber.admissibility_reason
            )
        return JudgeVerdict(
            verdict_id=verdict_id,
            envelope_id=envelope.envelope_id,
            chamber_id=chamber.chamber_id,
            symbol=symbol,
            tf_sec=envelope.tf_sec,
            ts_ms=ts_ms,
            verdict_scope="ENTRY",
            entry_verdict=entry_verdict,
            lifecycle_verdict=None,
            suppression_reason=suppression_reason,
            suppression_code=suppression_code,
            confidence=confidence,
            reasoning=reasoning,
            dissent_noted=dissent,
            authority_mode="shadow",
            applied=False,
            strategy_id=verdict_config.strategy_id,
        )
    else:
        # LIFECYCLE path: always UNKNOWN in Phase 4 (no lifecycle experts)
        lifecycle_verdict, confidence, reasoning, dissent = _map_lifecycle_verdict(
            chamber.admissibility,
            chamber.consensus_direction,
            chamber.consensus_strength,
            chamber.expert_outputs,
            verdict_config.split_confidence_discount,
        )
        return JudgeVerdict(
            verdict_id=verdict_id,
            envelope_id=envelope.envelope_id,
            chamber_id=chamber.chamber_id,
            symbol=symbol,
            tf_sec=envelope.tf_sec,
            ts_ms=ts_ms,
            verdict_scope="LIFECYCLE",
            entry_verdict=None,
            lifecycle_verdict=lifecycle_verdict,
            suppression_reason=None,
            suppression_code=None,
            confidence=confidence,
            reasoning=reasoning,
            dissent_noted=dissent,
            authority_mode="shadow",
            applied=False,
            strategy_id=verdict_config.strategy_id,
        )


def _map_entry_verdict(
    admissibility: str,
    admissibility_reason: Optional[str],
    consensus_direction: Optional[str],
    consensus_strength: float,
    expert_outputs: list,
    split_discount: float,
) -> tuple:
    """Map chamber state to entry verdict fields.

    Returns (entry_verdict, confidence, reasoning, dissent_noted).
    """
    if admissibility == "QUORUM_INSUFFICIENT":
        reasoning = ["quorum_insufficient"]
        if admissibility_reason:
            reasoning.append(f"admissibility_reason:{admissibility_reason}")
        return "UNKNOWN", 0.0, reasoning, False

    if admissibility == "INADMISSIBLE":
        suppression_reason = _suppression_reason_from_admissibility_reason(
            admissibility_reason
        )
        reasoning = [suppression_reason]
        if admissibility_reason:
            reasoning.append(f"admissibility_reason:{admissibility_reason}")
        return "SUPPRESS", 0.0, reasoning, False

    # ADMISSIBLE
    if consensus_direction is None:
        return "UNKNOWN", 0.0, ["no_consensus_direction"], False

    verdict_map = {
        "LONG": "OPEN_LONG",
        "SHORT": "OPEN_SHORT",
        "NEUTRAL": "NO_ENTRY",
    }

    if consensus_direction == "SPLIT":
        confidence = consensus_strength * split_discount
        reasoning = ["chamber_consensus:SPLIT", "dissent_downweight"]
        dissent = True
        return "NO_ENTRY", confidence, reasoning, dissent

    entry_verdict: EntryVerdict = verdict_map.get(
        consensus_direction, "UNKNOWN")
    reasoning_str = f"chamber_consensus:{consensus_direction}"

    # Detect dissent: any expert entry_verdict differs from mapped verdict
    dissent = _detect_entry_dissent(entry_verdict, expert_outputs)

    return entry_verdict, consensus_strength, [reasoning_str], dissent


def _suppression_reason_from_admissibility_reason(
    admissibility_reason: Optional[str],
) -> str:
    reason_map = {
        "solicited_expert_missing_output": (
            "entry_chamber_inadmissible:solicited_expert_missing_output"
        ),
        "duplicate_expert_id": "entry_chamber_inadmissible:duplicate_expert_id",
        "stale_expert_output": "entry_chamber_inadmissible:stale_expert_output",
        "scope_mismatch": "entry_chamber_inadmissible:scope_mismatch",
    }
    return reason_map.get(admissibility_reason, "entry_chamber_inadmissible")


def _suppression_code_from_admissibility_reason(
    admissibility_reason: Optional[str],
) -> str:
    code_map = {
        "solicited_expert_missing_output": "ENTRY_CHAMBER_MISSING_OUTPUT",
        "duplicate_expert_id": "ENTRY_CHAMBER_DUPLICATE_EXPERT_ID",
        "stale_expert_output": "ENTRY_CHAMBER_STALE_OUTPUT",
        "scope_mismatch": "ENTRY_CHAMBER_SCOPE_MISMATCH",
    }
    return code_map.get(admissibility_reason, "ENTRY_CHAMBER_INADMISSIBLE")


def _map_lifecycle_verdict(
    admissibility: str,
    consensus_direction: Optional[str],
    consensus_strength: float,
    expert_outputs: list,
    split_discount: float,
) -> tuple:
    """Map chamber state to lifecycle verdict fields.

    In Phase 4, this always produces UNKNOWN because no lifecycle experts
    exist. The mapping logic mirrors entry for structural completeness.

    Returns (lifecycle_verdict, confidence, reasoning, dissent_noted).
    """
    if admissibility == "QUORUM_INSUFFICIENT":
        return "UNKNOWN", 0.0, ["quorum_insufficient"], False

    if admissibility == "INADMISSIBLE":
        return "UNKNOWN", 0.0, ["inadmissible"], False

    # ADMISSIBLE — map to lifecycle verdicts
    if consensus_direction is None:
        return "UNKNOWN", 0.0, ["no_consensus_direction"], False

    # Lifecycle verdict mapping (placeholder for future phases)
    # In Phase 4 with zero lifecycle experts, chamber will always be
    # QUORUM_INSUFFICIENT, so this code path is unreachable in practice
    # but is included for structural completeness.
    lifecycle_map = {
        "LONG": "HOLD",
        "SHORT": "EXIT",
        "NEUTRAL": "HOLD",
    }

    if consensus_direction == "SPLIT":
        confidence = consensus_strength * split_discount
        return "HOLD", confidence, ["chamber_consensus:SPLIT", "dissent_downweight"], True

    lifecycle_verdict: LifecycleVerdict = lifecycle_map.get(
        consensus_direction, "UNKNOWN")
    reasoning_str = f"chamber_consensus:{consensus_direction}"
    dissent = _detect_lifecycle_dissent(lifecycle_verdict, expert_outputs)

    return lifecycle_verdict, consensus_strength, [reasoning_str], dissent


def _detect_entry_dissent(
    mapped_verdict: EntryVerdict,
    expert_outputs: list,
) -> bool:
    """Check if any expert's entry_verdict disagrees with the mapped verdict."""
    # Map from expert signal_direction to expected entry verdict
    direction_to_verdict = {
        "LONG": "OPEN_LONG",
        "SHORT": "OPEN_SHORT",
        "NEUTRAL": "NO_ENTRY",
    }
    for eo in expert_outputs:
        if eo.entry_verdict is not None:
            expected = direction_to_verdict.get(eo.signal_direction)
            if expected is not None and expected != mapped_verdict:
                return True
    return False


def _detect_lifecycle_dissent(
    mapped_verdict: LifecycleVerdict,
    expert_outputs: list,
) -> bool:
    """Check if any expert's lifecycle_verdict disagrees with the mapped verdict."""
    for eo in expert_outputs:
        if eo.lifecycle_verdict is not None and eo.lifecycle_verdict != mapped_verdict:
            return True
    return False
