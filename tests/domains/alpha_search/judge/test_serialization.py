"""
LLM Judge Phase 1 — Serialization & Replay Tests

Tests JSON round-trip serialization, cross-validation (Pydantic model_dump →
JSON Schema), and full chain reconstruction.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator, RefResolver

from apps.reference.domains.alpha_search.judge.contracts import (
    ChamberAggregate,
    EnvelopeProvenance,
    ExpertOutput,
    JudgeEvidenceEnvelope,
    JudgeVerdict,
    PositionContextSnapshot,
)

SCHEMAS_DIR = Path("apps/reference/domains/alpha_search/judge/schemas")


def _load_schema(name: str) -> dict:
    path = SCHEMAS_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_resolver():
    store = {}
    for schema_file in SCHEMAS_DIR.glob("*.json"):
        with open(schema_file, "r", encoding="utf-8") as f:
            schema = json.load(f)
        store[schema_file.name] = schema
    return RefResolver("file:///", {}, store=store)


def _make_entry_expert():
    return ExpertOutput(
        expert_id="ta_expert_v1",
        expert_version="1.0.0",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000000,
        entry_verdict="OPEN_LONG",
        confidence=0.85,
        signal_direction="LONG",
        reasoning=["Strong OBI", "Positive regime"],
        schema_version="1",
    )


def _make_lifecycle_expert():
    return ExpertOutput(
        expert_id="lc_expert_v1",
        expert_version="1.0.0",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000000,
        lifecycle_verdict="HOLD",
        confidence=0.75,
        signal_direction="LONG",
        reasoning=["Position healthy"],
        schema_version="1",
    )


def _make_entry_chamber(experts=None):
    if experts is None:
        experts = [_make_entry_expert()]
    return ChamberAggregate(
        chamber_id="ch-entry-001",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000100,
        verdict_scope="ENTRY",
        expert_outputs=experts,
        expert_count=3,
        responding_count=1,
        abstaining_count=2,
        consensus_direction="LONG",
        consensus_strength=0.7,
        admissibility="ADMISSIBLE",
        admissibility_reason=None,
        schema_version="1",
    )


def _make_entry_envelope(chamber=None):
    if chamber is None:
        chamber = _make_entry_chamber()
    return JudgeEvidenceEnvelope(
        envelope_id="env-entry-001",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000200,
        verdict_scope="ENTRY",
        chamber_aggregate=chamber,
        strategy_id="aurora",
        regime="TREND_UP",
        regime_confidence=0.9,
        features_ref="rid:abc123",
        freshness_deadline_ms=30000,
        provenance=EnvelopeProvenance(
            cortex_version="0.1.0",
            assembly_source="alpha_search.judge.assembler",
        ),
        schema_version="1",
    )


def _make_entry_verdict():
    return JudgeVerdict(
        verdict_id="v-entry-001",
        envelope_id="env-entry-001",
        chamber_id="ch-entry-001",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000300,
        verdict_scope="ENTRY",
        entry_verdict="OPEN_LONG",
        confidence=0.85,
        reasoning=["Strong consensus"],
        dissent_noted=False,
        authority_mode="off",
        applied=False,
        strategy_id="aurora",
        schema_version="1",
    )


# ---------------------------------------------------------------------------
# A. Pydantic → JSON → Pydantic round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_expert_output_round_trip(self):
        original = _make_entry_expert()
        serialized = original.model_dump_json()
        restored = ExpertOutput.model_validate_json(serialized)
        assert restored == original

    def test_chamber_aggregate_round_trip(self):
        original = _make_entry_chamber()
        serialized = original.model_dump_json()
        restored = ChamberAggregate.model_validate_json(serialized)
        assert restored == original

    def test_evidence_envelope_round_trip(self):
        original = _make_entry_envelope()
        serialized = original.model_dump_json()
        restored = JudgeEvidenceEnvelope.model_validate_json(serialized)
        assert restored == original

    def test_judge_verdict_round_trip(self):
        original = _make_entry_verdict()
        serialized = original.model_dump_json()
        restored = JudgeVerdict.model_validate_json(serialized)
        assert restored == original


# ---------------------------------------------------------------------------
# B. Cross-validation: Pydantic model_dump → JSON Schema validation
# ---------------------------------------------------------------------------

class TestCrossValidation:
    def test_expert_output_cross(self):
        schema = _load_schema("expert_output_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        data = _make_entry_expert().model_dump()
        validator.validate(data)

    def test_chamber_aggregate_cross(self):
        schema = _load_schema("chamber_aggregate_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        data = _make_entry_chamber().model_dump()
        validator.validate(data)

    def test_evidence_envelope_cross(self):
        schema = _load_schema("judge_evidence_envelope_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        data = _make_entry_envelope().model_dump()
        validator.validate(data)

    def test_judge_verdict_cross(self):
        schema = _load_schema("judge_verdict_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        data = _make_entry_verdict().model_dump()
        validator.validate(data)


# ---------------------------------------------------------------------------
# C. Full chain reconstruction
# ---------------------------------------------------------------------------

class TestFullChainReconstruction:
    def test_entry_chain(self):
        """Expert → Chamber → Envelope → Verdict full chain."""
        expert = _make_entry_expert()
        chamber = _make_entry_chamber([expert])
        envelope = _make_entry_envelope(chamber)
        verdict = _make_entry_verdict()

        # Verify chain links
        assert verdict.envelope_id == envelope.envelope_id
        assert verdict.chamber_id == chamber.chamber_id
        assert chamber.expert_outputs[0].expert_id == expert.expert_id

        # Verify scope consistency
        assert verdict.verdict_scope == envelope.verdict_scope == chamber.verdict_scope == "ENTRY"

        # Serialize full chain
        chain = {
            "verdict": verdict.model_dump(),
            "envelope": envelope.model_dump(),
            "chamber": chamber.model_dump(),
            "experts": [expert.model_dump()],
        }
        chain_json = json.dumps(chain)
        chain_restored = json.loads(chain_json)

        # Reconstruct
        v_restored = JudgeVerdict.model_validate(chain_restored["verdict"])
        env_restored = JudgeEvidenceEnvelope.model_validate(
            chain_restored["envelope"])
        assert v_restored.envelope_id == env_restored.envelope_id

    def test_lifecycle_chain(self):
        """Lifecycle expert → Chamber → Envelope → Verdict chain."""
        expert = _make_lifecycle_expert()
        chamber = ChamberAggregate(
            chamber_id="ch-lc-001",
            symbol="BTCUSDT",
            tf_sec=300,
            ts_ms=1712000000100,
            verdict_scope="LIFECYCLE",
            expert_outputs=[expert],
            expert_count=2,
            responding_count=1,
            abstaining_count=1,
            consensus_direction="LONG",
            consensus_strength=0.6,
            admissibility="ADMISSIBLE",
            admissibility_reason=None,
            schema_version="1",
        )
        position = PositionContextSnapshot(
            has_position=True, side="LONG",
            unrealized_pnl_pct=0.5, hold_duration_sec=300,
            bracket_state="ACTIVE",
        )
        envelope = JudgeEvidenceEnvelope(
            envelope_id="env-lc-001",
            symbol="BTCUSDT",
            tf_sec=300,
            ts_ms=1712000000200,
            verdict_scope="LIFECYCLE",
            chamber_aggregate=chamber,
            strategy_id="aurora",
            position_context=position,
            freshness_deadline_ms=30000,
            provenance=EnvelopeProvenance(
                cortex_version="0.1.0",
                assembly_source="alpha_search.judge.assembler",
            ),
            schema_version="1",
        )
        verdict = JudgeVerdict(
            verdict_id="v-lc-001",
            envelope_id="env-lc-001",
            chamber_id="ch-lc-001",
            symbol="BTCUSDT",
            tf_sec=300,
            ts_ms=1712000000300,
            verdict_scope="LIFECYCLE",
            lifecycle_verdict="HOLD",
            confidence=0.75,
            reasoning=["Position healthy"],
            dissent_noted=False,
            authority_mode="off",
            applied=False,
            strategy_id="aurora",
            schema_version="1",
        )
        assert verdict.verdict_scope == "LIFECYCLE"
        assert envelope.position_context.has_position is True
        assert verdict.lifecycle_verdict == "HOLD"

        # Cross-validate against schema
        schema = _load_schema("judge_verdict_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        validator.validate(verdict.model_dump())


# ---------------------------------------------------------------------------
# D. Provenance preservation
# ---------------------------------------------------------------------------

class TestProvenancePreservation:
    def test_provenance_survives_serialization(self):
        envelope = _make_entry_envelope()
        data = envelope.model_dump()
        restored = JudgeEvidenceEnvelope.model_validate(data)
        assert restored.provenance.cortex_version == "0.1.0"
        assert restored.provenance.assembly_source == "alpha_search.judge.assembler"
        assert restored.provenance.prompt_template_id is None

    def test_provenance_with_phase2_fields(self):
        envelope = JudgeEvidenceEnvelope(
            envelope_id="env-p2",
            symbol="ETHUSDT",
            tf_sec=60,
            ts_ms=1712000000000,
            verdict_scope="ENTRY",
            chamber_aggregate=_make_entry_chamber(),
            strategy_id="aurora",
            freshness_deadline_ms=15000,
            provenance=EnvelopeProvenance(
                cortex_version="0.2.0",
                prompt_template_id="regime_aware_v3",
                model_version="claude-sonnet-4-6",
                assembly_source="alpha_search.judge.assembler",
            ),
            schema_version="1",
        )
        data = json.loads(envelope.model_dump_json())
        assert data["provenance"]["prompt_template_id"] == "regime_aware_v3"
        assert data["provenance"]["model_version"] == "claude-sonnet-4-6"
