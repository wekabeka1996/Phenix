"""
LLM Judge Phase 3 — Chamber Aggregator

Stateless aggregator that collects ExpertOutput records for a given
evaluation cycle and produces a ChamberAggregate.

Instantiated with verdict_scope and config. Called once per decision
cycle with a list of ExpertOutput records AND the solicited expert
roster.

Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE3_IMPLEMENTATION_BLUEPRINT.md §11.1
"""

import logging
from typing import List, Literal, Optional

from apps.reference.domains.alpha_search.judge.config_models import ChamberConfig
from apps.reference.domains.alpha_search.judge.contracts import (
    ChamberAggregate,
    ExpertOutput,
)
from .admissibility import evaluate_admissibility

LOG = logging.getLogger(__name__)
_ABSTAINING_VERDICTS = {"UNKNOWN", "SUPPRESS"}


class ChamberAggregator:
    """Aggregates ExpertOutput records into a ChamberAggregate.

    Stateless. Instantiated with verdict_scope and config.
    Called once per evaluation cycle with a list of ExpertOutput records
    AND the roster of solicited expert IDs for that cycle.
    """

    def __init__(
        self,
        verdict_scope: Literal["ENTRY", "LIFECYCLE"],
        config: ChamberConfig,
    ) -> None:
        self.verdict_scope = verdict_scope
        self.config = config

    def aggregate(
        self,
        expert_outputs: List[ExpertOutput],
        *,
        expected_expert_ids: List[str],
        symbol: str,
        tf_sec: int,
        ts_ms: int,
    ) -> ChamberAggregate:
        """Aggregate expert outputs into a ChamberAggregate.

        Args:
            expert_outputs: ExpertOutput records collected from the
                provider loop. May be fewer than expected if experts
                crashed or were fail-closed suppressed.
            expected_expert_ids: The roster of expert IDs that were
                solicited in this cycle. This is the ground truth for
                expert_count — invariant regardless of how many actually
                returned.
            symbol: Trading pair symbol.
            tf_sec: Timeframe in seconds.
            ts_ms: Cycle timestamp in milliseconds.
        """
        # Step 1: expert_count from solicited roster
        expert_count = len(expected_expert_ids)

        # Step 2: Filter by scope
        scope_filtered = self._filter_by_scope(expert_outputs)

        # Step 3: Classify responding vs abstaining
        responding = [
            eo
            for eo in scope_filtered
            if eo.confidence > 0.0
            and self._get_verdict(eo) not in _ABSTAINING_VERDICTS
        ]
        responding_count = len(responding)

        # Step 4: Fail-closed accounting
        abstaining_count = expert_count - responding_count

        # Step 5: Admissibility
        admissibility, admissibility_reason = evaluate_admissibility(
            expert_outputs=scope_filtered,
            responding_count=responding_count,
            expected_expert_count=expert_count,
            min_quorum=self.config.min_quorum,
            max_staleness_ms=self.config.max_staleness_ms,
            cycle_ts_ms=ts_ms,
            verdict_scope=self.verdict_scope,
        )

        # Step 6: Consensus
        consensus_direction = self._compute_consensus_direction(responding)
        consensus_strength = self._compute_consensus_strength(responding)

        # Step 7: stage-local compatibility id.
        # Canonical replay/review identity lives in ChamberAggregate.cycle_key.
        chamber_id = f"{self.verdict_scope.lower()}_{symbol}_{ts_ms}"

        return ChamberAggregate(
            chamber_id=chamber_id,
            symbol=symbol,
            tf_sec=tf_sec,
            ts_ms=ts_ms,
            verdict_scope=self.verdict_scope,
            expert_outputs=scope_filtered,
            expert_count=expert_count,
            responding_count=responding_count,
            abstaining_count=abstaining_count,
            consensus_direction=consensus_direction,
            consensus_strength=consensus_strength,
            admissibility=admissibility,
            admissibility_reason=admissibility_reason,
            schema_version="1",
        )

    def _filter_by_scope(
        self, expert_outputs: List[ExpertOutput]
    ) -> List[ExpertOutput]:
        """Keep only ExpertOutputs matching this chamber's verdict_scope."""
        if self.verdict_scope == "ENTRY":
            return [eo for eo in expert_outputs if eo.entry_verdict is not None]
        else:
            return [
                eo for eo in expert_outputs if eo.lifecycle_verdict is not None
            ]

    def _get_verdict(self, eo: ExpertOutput) -> Optional[str]:
        """Get the relevant verdict for the current scope."""
        if self.verdict_scope == "ENTRY":
            return eo.entry_verdict
        return eo.lifecycle_verdict

    def _compute_consensus_direction(
        self, responding: List[ExpertOutput]
    ) -> Optional[Literal["LONG", "SHORT", "NEUTRAL", "SPLIT"]]:
        """Compute consensus direction from responding experts via majority vote."""
        if not responding:
            return None

        long_count = 0
        short_count = 0
        for eo in responding:
            if eo.signal_direction == "LONG":
                long_count += 1
            elif eo.signal_direction == "SHORT":
                short_count += 1

        if long_count > short_count:
            return "LONG"
        if short_count > long_count:
            return "SHORT"
        if long_count > 0 and long_count == short_count:
            return "SPLIT"
        # long_count == 0 and short_count == 0
        return "NEUTRAL"

    def _compute_consensus_strength(
        self, responding: List[ExpertOutput]
    ) -> float:
        """Mean confidence of responding experts."""
        if not responding:
            return 0.0
        return sum(eo.confidence for eo in responding) / len(responding)
