"""
LLM Judge Phase 4 — Evidence Envelope Assembler

Stateless function that assembles a JudgeEvidenceEnvelope from a
ChamberAggregate and contextual metadata. Pure data packaging — no
decision logic.

Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE4_IMPLEMENTATION_BLUEPRINT.md §13
"""

import logging
from typing import Optional

from apps.reference.domains.alpha_search.judge.config_models import (
    ChamberConfig,
    VerdictConfig,
)
from apps.reference.domains.alpha_search.judge.contracts import (
    ChamberAggregate,
    EnvelopeProvenance,
    JudgeEvidenceEnvelope,
    PositionContextSnapshot,
)

LOG = logging.getLogger(__name__)


def assemble_evidence_envelope(
    chamber_aggregate: ChamberAggregate,
    *,
    verdict_config: VerdictConfig,
    chamber_config: ChamberConfig,
    features_ref: Optional[str] = None,
    regime: Optional[str] = None,
    regime_confidence: Optional[float] = None,
    position_context: Optional[PositionContextSnapshot] = None,
) -> JudgeEvidenceEnvelope:
    """Assemble a JudgeEvidenceEnvelope from a ChamberAggregate.

    Args:
        chamber_aggregate: The chamber aggregation result.
        verdict_config: Verdict configuration (strategy_id, cortex_version).
        chamber_config: Chamber configuration (max_staleness_ms for deadline).
        features_ref: Logical reference to the feature bar, e.g.
            ``"bar:{symbol}:{tf_sec}:{bar_close_ts}"``. Optional.
        regime: Regime label from feature cache, if available.
        regime_confidence: Regime confidence from feature cache, if available.
        position_context: Position snapshot for LIFECYCLE scope. Required
            for LIFECYCLE, None for ENTRY.

    Returns:
        Assembled JudgeEvidenceEnvelope.
    """
    scope = chamber_aggregate.verdict_scope
    symbol = chamber_aggregate.symbol
    ts_ms = chamber_aggregate.ts_ms

    # Envelope ID is a stage-local compatibility id.
    # Canonical replay/review identity lives in JudgeEvidenceEnvelope.cycle_key.
    envelope_id = f"env_{scope.lower()}_{symbol}_{ts_ms}"

    # For LIFECYCLE scope, provide a synthetic no-position stub if
    # position_context was not explicitly supplied
    if scope == "LIFECYCLE" and position_context is None:
        position_context = PositionContextSnapshot(has_position=False)

    # Freshness deadline: forward-looking from chamber staleness window
    freshness_deadline_ms = ts_ms + chamber_config.max_staleness_ms

    # Provenance: static Phase 4 metadata
    provenance = EnvelopeProvenance(
        cortex_version=verdict_config.cortex_version,
        assembly_source="alpha_search_backtest_plugin",
    )

    return JudgeEvidenceEnvelope(
        envelope_id=envelope_id,
        symbol=symbol,
        tf_sec=chamber_aggregate.tf_sec,
        ts_ms=ts_ms,
        verdict_scope=scope,
        chamber_aggregate=chamber_aggregate,
        strategy_id=verdict_config.strategy_id,
        regime=regime,
        regime_confidence=regime_confidence,
        features_ref=features_ref,
        position_context=position_context,
        freshness_deadline_ms=freshness_deadline_ms,
        provenance=provenance,
    )
