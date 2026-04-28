from __future__ import annotations

import pytest
from jsonschema.exceptions import ValidationError

from vfoundation.core.schema_registry import VerbSchemaRegistry


REGISTRY_PATH = "apps/reference/dictionaries/verb_registry_v1.yaml"


def _load_registry() -> VerbSchemaRegistry:
    registry = VerbSchemaRegistry(project_root=".")
    registry.load_registry(REGISTRY_PATH)
    return registry


def _valid_expert_output() -> dict:
    return {
        "expert_id": "ta_expert_v1",
        "expert_version": "1.0.0",
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "ts_ms": 1712000000000,
        "entry_verdict": "OPEN_LONG",
        "lifecycle_verdict": None,
        "confidence": 0.85,
        "signal_direction": "LONG",
        "reasoning": ["Strong signal"],
        "schema_version": "1",
    }


def _valid_chamber_aggregate() -> dict:
    return {
        "chamber_id": "ch-001",
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "ts_ms": 1712000000100,
        "verdict_scope": "ENTRY",
        "expert_outputs": [_valid_expert_output()],
        "expert_count": 3,
        "responding_count": 1,
        "abstaining_count": 2,
        "consensus_direction": "LONG",
        "consensus_strength": 0.7,
        "admissibility": "ADMISSIBLE",
        "admissibility_reason": None,
        "schema_version": "1",
    }


def _valid_evidence_envelope() -> dict:
    return {
        "envelope_id": "env-001",
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "ts_ms": 1712000000200,
        "verdict_scope": "ENTRY",
        "chamber_aggregate": _valid_chamber_aggregate(),
        "strategy_id": "aurora",
        "regime": "TREND_UP",
        "regime_confidence": 0.9,
        "features_ref": "rid:abc123",
        "position_context": None,
        "freshness_deadline_ms": 30000,
        "provenance": {
            "cortex_version": "0.1.0",
            "prompt_template_id": None,
            "model_version": None,
            "assembly_source": "alpha_search.judge.assembler",
        },
        "schema_version": "1",
    }


@pytest.fixture(scope="module")
def registry() -> VerbSchemaRegistry:
    loaded = _load_registry()
    assert loaded.get_validator("EVT", "JUDGE_CHAMBER_AGGREGATED_V1") is not None
    assert loaded.get_validator("EVT", "JUDGE_EVIDENCE_ASSEMBLED_V1") is not None
    return loaded


def test_judge_chamber_aggregate_validator_resolves_local_ref(registry: VerbSchemaRegistry) -> None:
    validator = registry.get_validator("EVT", "JUDGE_CHAMBER_AGGREGATED_V1")
    assert validator is not None
    validator.validate(_valid_chamber_aggregate())


def test_judge_chamber_aggregate_rejects_missing_required_field_in_ref_subschema(
    registry: VerbSchemaRegistry,
) -> None:
    validator = registry.get_validator("EVT", "JUDGE_CHAMBER_AGGREGATED_V1")
    assert validator is not None
    payload = _valid_chamber_aggregate()
    del payload["expert_outputs"][0]["expert_id"]

    with pytest.raises(ValidationError, match="expert_id"):
        validator.validate(payload)


def test_judge_evidence_envelope_validator_resolves_nested_local_refs(
    registry: VerbSchemaRegistry,
) -> None:
    validator = registry.get_validator("EVT", "JUDGE_EVIDENCE_ASSEMBLED_V1")
    assert validator is not None
    validator.validate(_valid_evidence_envelope())


def test_judge_evidence_envelope_rejects_missing_required_field_in_nested_ref_subschema(
    registry: VerbSchemaRegistry,
) -> None:
    validator = registry.get_validator("EVT", "JUDGE_EVIDENCE_ASSEMBLED_V1")
    assert validator is not None
    payload = _valid_evidence_envelope()
    del payload["chamber_aggregate"]["expert_outputs"][0]["expert_version"]

    with pytest.raises(ValidationError, match="expert_version"):
        validator.validate(payload)
