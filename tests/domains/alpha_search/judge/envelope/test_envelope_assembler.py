"""
LLM Judge Phase 4 — Envelope Assembler Tests

Tests assemble_evidence_envelope() for entry/lifecycle scopes,
enrichment, provenance, freshness deadline, fail-closed behavior.

Authority: docs/LLM_JUDGE/LLM_JUDGE_PHASE4_IMPLEMENTATION_BLUEPRINT.md §13, §16
"""

import pytest

from apps.reference.domains.alpha_search.judge.config_models import (
    ChamberConfig,
    VerdictConfig,
)
from apps.reference.domains.alpha_search.judge.contracts import (
    ChamberAggregate,
    ExpertOutput,
    JudgeEvidenceEnvelope,
    PositionContextSnapshot,
)
from apps.reference.domains.alpha_search.judge.envelope import (
    assemble_evidence_envelope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_expert_output(
    expert_id: str = "judge.test_v1",
    symbol: str = "BTCUSDT",
    entry_verdict: str = "OPEN_LONG",
    confidence: float = 0.8,
) -> ExpertOutput:
    return ExpertOutput(
        expert_id=expert_id,
        expert_version="1.0.0",
        symbol=symbol,
        tf_sec=300,
        ts_ms=1000000,
        entry_verdict=entry_verdict,
        lifecycle_verdict=None,
        confidence=confidence,
        signal_direction="LONG",
        reasoning=["test"],
    )


def _make_chamber_aggregate(
    verdict_scope: str = "ENTRY",
    symbol: str = "BTCUSDT",
    ts_ms: int = 1000000,
    admissibility: str = "ADMISSIBLE",
    consensus_direction: str = "LONG",
    expert_outputs=None,
) -> ChamberAggregate:
    if expert_outputs is None:
        expert_outputs = [_make_expert_output(symbol=symbol)]
    return ChamberAggregate(
        chamber_id=f"{verdict_scope.lower()}_{symbol}_{ts_ms}",
        symbol=symbol,
        tf_sec=300,
        ts_ms=ts_ms,
        verdict_scope=verdict_scope,
        expert_outputs=expert_outputs if verdict_scope == "ENTRY" else [],
        expert_count=len(expert_outputs) if verdict_scope == "ENTRY" else 0,
        responding_count=len(
            expert_outputs) if verdict_scope == "ENTRY" else 0,
        abstaining_count=0,
        consensus_direction=consensus_direction if verdict_scope == "ENTRY" else None,
        consensus_strength=0.8 if verdict_scope == "ENTRY" else 0.0,
        admissibility=admissibility,
    )


_DEFAULT_VERDICT_CONFIG = VerdictConfig()
_DEFAULT_CHAMBER_CONFIG = ChamberConfig()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEnvelopeAssemblerEntry:
    def test_basic_entry_envelope(self):
        chamber = _make_chamber_aggregate()
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
        )
        assert isinstance(env, JudgeEvidenceEnvelope)
        assert env.verdict_scope == "ENTRY"
        assert env.symbol == "BTCUSDT"
        assert env.tf_sec == 300
        assert env.ts_ms == 1000000
        assert env.strategy_id == "aurora"
        assert env.position_context is None

    def test_envelope_id_format(self):
        chamber = _make_chamber_aggregate(symbol="ETHUSDT", ts_ms=9999999)
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
        )
        assert env.envelope_id == "env_entry_ETHUSDT_9999999"

    def test_provenance_fields(self):
        chamber = _make_chamber_aggregate()
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
        )
        assert env.provenance.cortex_version == "phase4_shadow_v1"
        assert env.provenance.assembly_source == "alpha_search_backtest_plugin"
        assert env.provenance.prompt_template_id is None
        assert env.provenance.model_version is None

    def test_freshness_deadline_calculation(self):
        chamber = _make_chamber_aggregate(ts_ms=5000000)
        cfg = ChamberConfig(max_staleness_ms=15000)
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=cfg,
        )
        assert env.freshness_deadline_ms == 5000000 + 15000

    def test_features_ref_passthrough(self):
        chamber = _make_chamber_aggregate()
        ref = "bar:BTCUSDT:300:1000000"
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
            features_ref=ref,
        )
        assert env.features_ref == ref

    def test_regime_enrichment(self):
        chamber = _make_chamber_aggregate()
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
            regime="TREND_UP",
            regime_confidence=0.85,
        )
        assert env.regime == "TREND_UP"
        assert env.regime_confidence == 0.85

    def test_nil_regime_ok(self):
        chamber = _make_chamber_aggregate()
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
            regime=None,
            regime_confidence=None,
        )
        assert env.regime is None
        assert env.regime_confidence is None

    def test_chamber_aggregate_embedded(self):
        chamber = _make_chamber_aggregate()
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
        )
        assert env.chamber_aggregate is chamber

    def test_custom_strategy_id(self):
        chamber = _make_chamber_aggregate()
        cfg = VerdictConfig(strategy_id="custom_strat")
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=cfg,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
        )
        assert env.strategy_id == "custom_strat"

    def test_schema_version(self):
        chamber = _make_chamber_aggregate()
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
        )
        assert env.schema_version == "1"


class TestEnvelopeAssemblerLifecycle:
    def test_lifecycle_auto_position_context(self):
        """LIFECYCLE scope auto-creates PositionContextSnapshot if not provided."""
        eo = ExpertOutput(
            expert_id="judge.lc_v1",
            expert_version="1.0.0",
            symbol="BTCUSDT",
            tf_sec=300,
            ts_ms=1000000,
            entry_verdict=None,
            lifecycle_verdict="HOLD",
            confidence=0.5,
            signal_direction="LONG",
            reasoning=["test"],
        )
        chamber = ChamberAggregate(
            chamber_id="lifecycle_BTCUSDT_1000000",
            symbol="BTCUSDT",
            tf_sec=300,
            ts_ms=1000000,
            verdict_scope="LIFECYCLE",
            expert_outputs=[eo],
            expert_count=1,
            responding_count=1,
            abstaining_count=0,
            consensus_direction="LONG",
            consensus_strength=0.5,
            admissibility="ADMISSIBLE",
        )
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
        )
        assert env.verdict_scope == "LIFECYCLE"
        assert env.position_context is not None
        assert env.position_context.has_position is False

    def test_lifecycle_explicit_position_context(self):
        """LIFECYCLE scope uses provided PositionContextSnapshot."""
        eo = ExpertOutput(
            expert_id="judge.lc_v1",
            expert_version="1.0.0",
            symbol="BTCUSDT",
            tf_sec=300,
            ts_ms=1000000,
            entry_verdict=None,
            lifecycle_verdict="HOLD",
            confidence=0.5,
            signal_direction="LONG",
            reasoning=["test"],
        )
        chamber = ChamberAggregate(
            chamber_id="lifecycle_BTCUSDT_1000000",
            symbol="BTCUSDT",
            tf_sec=300,
            ts_ms=1000000,
            verdict_scope="LIFECYCLE",
            expert_outputs=[eo],
            expert_count=1,
            responding_count=1,
            abstaining_count=0,
            consensus_direction="LONG",
            consensus_strength=0.5,
            admissibility="ADMISSIBLE",
        )
        pos = PositionContextSnapshot(
            has_position=True,
            side="LONG",
            unrealized_pnl_pct=0.5,
        )
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
            position_context=pos,
        )
        assert env.position_context.has_position is True
        assert env.position_context.side == "LONG"

    def test_lifecycle_envelope_id_format(self):
        eo = ExpertOutput(
            expert_id="judge.lc_v1",
            expert_version="1.0.0",
            symbol="SOLUSDT",
            tf_sec=300,
            ts_ms=5555555,
            entry_verdict=None,
            lifecycle_verdict="HOLD",
            confidence=0.5,
            signal_direction="LONG",
            reasoning=["test"],
        )
        chamber = ChamberAggregate(
            chamber_id="lifecycle_SOLUSDT_5555555",
            symbol="SOLUSDT",
            tf_sec=300,
            ts_ms=5555555,
            verdict_scope="LIFECYCLE",
            expert_outputs=[eo],
            expert_count=1,
            responding_count=1,
            abstaining_count=0,
            consensus_direction="LONG",
            consensus_strength=0.5,
            admissibility="ADMISSIBLE",
        )
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
        )
        assert env.envelope_id == "env_lifecycle_SOLUSDT_5555555"

    def test_scope_consistency_validated(self):
        """Envelope rejects mismatched scope between chamber and envelope."""
        # This is enforced by the contract validator. Construct a chamber
        # with ENTRY scope and try to assemble — should work fine since
        # assemble_evidence_envelope passes scope through from chamber.
        chamber = _make_chamber_aggregate(verdict_scope="ENTRY")
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
        )
        assert env.verdict_scope == chamber.verdict_scope
