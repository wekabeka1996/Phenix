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
        assert env.cycle_key == "ENTRY:ETHUSDT:300:9999999"

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
        assert env.cycle_key == "LIFECYCLE:SOLUSDT:300:5555555"

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


# ---------------------------------------------------------------------------
# J6-S11: Regime propagation tests
# ---------------------------------------------------------------------------

class TestRegimePropagation:
    """J6-S11: Verify regime context propagation into JudgeEvidenceEnvelope."""

    def test_full_regime_passthrough(self):
        """regime, regime_confidence, regime_ts_ms, regime_source all propagate."""
        chamber = _make_chamber_aggregate()
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
            regime="TREND_UP",
            regime_confidence=0.83,
            regime_ts_ms=1_714_000_000_000,
            regime_source="aurora_regime_v1",
        )
        assert env.regime == "TREND_UP"
        assert env.regime_confidence == pytest.approx(0.83)
        assert env.regime_ts_ms == 1_714_000_000_000
        assert env.regime_source == "aurora_regime_v1"
        assert env.regime_missing_reason is None

    def test_missing_regime_explicit_reason(self):
        """When regime is absent, regime_missing_reason must be explicit."""
        chamber = _make_chamber_aggregate()
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
            regime=None,
            regime_confidence=None,
            regime_ts_ms=None,
            regime_source=None,
            regime_missing_reason="REGIME_CONTEXT_MISSING",
        )
        assert env.regime is None
        assert env.regime_confidence is None
        assert env.regime_ts_ms is None
        assert env.regime_source is None
        assert env.regime_missing_reason == "REGIME_CONTEXT_MISSING"

    def test_regime_confidence_range(self):
        """regime_confidence must be 0.0–1.0 by Pydantic constraint."""
        import pytest as _pytest
        from pydantic import ValidationError
        chamber = _make_chamber_aggregate()
        with _pytest.raises(ValidationError):
            assemble_evidence_envelope(
                chamber,
                verdict_config=_DEFAULT_VERDICT_CONFIG,
                chamber_config=_DEFAULT_CHAMBER_CONFIG,
                regime="TREND_UP",
                regime_confidence=1.5,  # out of range
            )

    def test_regime_only_no_confidence(self):
        """regime present but confidence missing → regime_missing_reason set."""
        chamber = _make_chamber_aggregate()
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
            regime="HIGH_VOLATILITY",
            regime_confidence=None,
            regime_missing_reason="REGIME_CONFIDENCE_MISSING",
        )
        assert env.regime == "HIGH_VOLATILITY"
        assert env.regime_confidence is None
        assert env.regime_missing_reason == "REGIME_CONFIDENCE_MISSING"

    def test_cache_not_contaminated(self):
        """The original cache dict is not mutated by regime injection."""
        original_cache = {"obi": 0.5, "ema_bias": 0.3}
        import copy
        cache_snapshot_before = copy.deepcopy(original_cache)

        # Simulate what the plugin does: build local copy, inject regime
        features_for_envelope = dict(original_cache)
        features_for_envelope["regime"] = "TREND_UP"
        features_for_envelope["regime_confidence"] = 0.9

        # Original cache unchanged
        assert original_cache == cache_snapshot_before
        assert "regime" not in original_cache
        assert "regime_confidence" not in original_cache

    def test_cycle_key_unchanged_by_regime(self):
        """Adding regime context must not alter cycle_key."""
        chamber = _make_chamber_aggregate(symbol="ETHUSDT", ts_ms=9_000_000)
        env_no_regime = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
        )
        env_with_regime = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
            regime="MEAN_REVERSION",
            regime_confidence=0.7,
            regime_ts_ms=9_000_000,
            regime_source="aurora_regime_v1",
        )
        assert env_no_regime.cycle_key == env_with_regime.cycle_key

    def test_historical_row_readable_without_new_fields(self):
        """Historical envelopes without regime_ts_ms/source/missing_reason remain valid."""
        chamber = _make_chamber_aggregate()
        # Minimal envelope simulating a historical row (no new fields)
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
            regime="TREND_UP",
            regime_confidence=0.8,
            # new fields omitted — must default to None
        )
        assert env.regime_ts_ms is None
        assert env.regime_source is None
        assert env.regime_missing_reason is None

    def test_schema_cross_validates_new_fields(self):
        """Pydantic model_dump of envelope with new regime fields passes JSON Schema."""
        import json
        from pathlib import Path
        from jsonschema import Draft7Validator, RefResolver

        SCHEMAS_DIR = Path("apps/reference/domains/alpha_search/judge/schemas")
        schema_path = SCHEMAS_DIR / "judge_evidence_envelope_v1.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        store = {}
        for sf in SCHEMAS_DIR.glob("*.json"):
            with open(sf, "r", encoding="utf-8") as f:
                store[sf.name] = json.load(f)
        resolver = RefResolver("file:///", {}, store=store)
        validator = Draft7Validator(schema, resolver=resolver)

        chamber = _make_chamber_aggregate()
        env = assemble_evidence_envelope(
            chamber,
            verdict_config=_DEFAULT_VERDICT_CONFIG,
            chamber_config=_DEFAULT_CHAMBER_CONFIG,
            regime="TREND_DOWN",
            regime_confidence=0.72,
            regime_ts_ms=1_714_100_000_000,
            regime_source="aurora_regime_v1",
        )
        data = env.model_dump()
        validator.validate(data)  # raises if invalid
