"""
LLM Judge Phase 1 — JSON Schema Validation Tests

Tests all 4 JSON schemas compile via Draft7Validator and validate
positive/negative payloads correctly.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator, RefResolver

SCHEMAS_DIR = Path("apps/reference/domains/alpha_search/judge/schemas")


def _load_schema(name: str) -> dict:
    path = SCHEMAS_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_resolver():
    """Build a resolver that can resolve $ref between schemas in the same directory."""
    store = {}
    for schema_file in SCHEMAS_DIR.glob("*.json"):
        with open(schema_file, "r", encoding="utf-8") as f:
            schema = json.load(f)
        store[schema_file.name] = schema
    base_uri = "file:///"
    return RefResolver(base_uri, {}, store=store)


def _make_valid_expert_output():
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


def _make_valid_chamber_aggregate():
    return {
        "chamber_id": "ch-001",
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "ts_ms": 1712000000100,
        "verdict_scope": "ENTRY",
        "expert_outputs": [_make_valid_expert_output()],
        "expert_count": 3,
        "responding_count": 1,
        "abstaining_count": 2,
        "consensus_direction": "LONG",
        "consensus_strength": 0.7,
        "admissibility": "ADMISSIBLE",
        "admissibility_reason": None,
        "schema_version": "1",
    }


def _make_valid_evidence_envelope():
    return {
        "envelope_id": "env-001",
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "ts_ms": 1712000000200,
        "verdict_scope": "ENTRY",
        "chamber_aggregate": _make_valid_chamber_aggregate(),
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


def _make_valid_judge_verdict():
    return {
        "verdict_id": "v-001",
        "envelope_id": "env-001",
        "chamber_id": "ch-001",
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "ts_ms": 1712000000300,
        "verdict_scope": "ENTRY",
        "entry_verdict": "OPEN_LONG",
        "lifecycle_verdict": None,
        "suppression_reason": None,
        "suppression_code": None,
        "confidence": 0.85,
        "reasoning": ["Strong consensus"],
        "dissent_noted": False,
        "authority_mode": "off",
        "applied": False,
        "strategy_id": "aurora",
        "schema_version": "1",
    }


# ---------------------------------------------------------------------------
# A. Schema compilation
# ---------------------------------------------------------------------------

class TestSchemaCompilation:
    def test_expert_output_schema_compiles(self):
        schema = _load_schema("expert_output_v1.json")
        Draft7Validator.check_schema(schema)

    def test_chamber_aggregate_schema_compiles(self):
        schema = _load_schema("chamber_aggregate_v1.json")
        Draft7Validator.check_schema(schema)

    def test_evidence_envelope_schema_compiles(self):
        schema = _load_schema("judge_evidence_envelope_v1.json")
        Draft7Validator.check_schema(schema)

    def test_judge_verdict_schema_compiles(self):
        schema = _load_schema("judge_verdict_v1.json")
        Draft7Validator.check_schema(schema)


# ---------------------------------------------------------------------------
# B. Valid payloads pass
# ---------------------------------------------------------------------------

class TestValidPayloads:
    def test_expert_output_valid(self):
        schema = _load_schema("expert_output_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        validator.validate(_make_valid_expert_output())

    def test_chamber_aggregate_valid(self):
        schema = _load_schema("chamber_aggregate_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        validator.validate(_make_valid_chamber_aggregate())

    def test_evidence_envelope_valid(self):
        schema = _load_schema("judge_evidence_envelope_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        validator.validate(_make_valid_evidence_envelope())

    def test_judge_verdict_valid(self):
        schema = _load_schema("judge_verdict_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        validator.validate(_make_valid_judge_verdict())


# ---------------------------------------------------------------------------
# C. Unknown fields rejected on strict schemas
# ---------------------------------------------------------------------------

class TestAdditionalPropertiesStrict:
    def test_expert_output_rejects_unknown(self):
        schema = _load_schema("expert_output_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_expert_output()
        payload["unknown_field"] = "bad"
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_judge_verdict_rejects_unknown(self):
        schema = _load_schema("judge_verdict_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_judge_verdict()
        payload["unknown_field"] = "bad"
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_chamber_aggregate_rejects_unknown(self):
        schema = _load_schema("chamber_aggregate_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_chamber_aggregate()
        payload["unknown_field"] = "bad"
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_evidence_envelope_allows_extra(self):
        """Evidence envelope has additionalProperties: true per blueprint."""
        schema = _load_schema("judge_evidence_envelope_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_evidence_envelope()
        payload["extra_analysis"] = {"custom": "ok"}
        validator.validate(payload)  # Should NOT raise


# ---------------------------------------------------------------------------
# D. Missing required fields rejected
# ---------------------------------------------------------------------------

class TestMissingRequired:
    def test_expert_output_missing_expert_id(self):
        schema = _load_schema("expert_output_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_expert_output()
        del payload["expert_id"]
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_judge_verdict_missing_verdict_id(self):
        schema = _load_schema("judge_verdict_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_judge_verdict()
        del payload["verdict_id"]
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_chamber_missing_chamber_id(self):
        schema = _load_schema("chamber_aggregate_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_chamber_aggregate()
        del payload["chamber_id"]
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_envelope_missing_envelope_id(self):
        schema = _load_schema("judge_evidence_envelope_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_evidence_envelope()
        del payload["envelope_id"]
        with pytest.raises(Exception):
            validator.validate(payload)


# ---------------------------------------------------------------------------
# E. Invalid enum values rejected
# ---------------------------------------------------------------------------

class TestInvalidEnumSchema:
    def test_invalid_entry_verdict(self):
        schema = _load_schema("expert_output_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_expert_output()
        payload["entry_verdict"] = "INVALID"
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_invalid_admissibility(self):
        schema = _load_schema("chamber_aggregate_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_chamber_aggregate()
        payload["admissibility"] = "INVALID"
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_invalid_authority_mode(self):
        schema = _load_schema("judge_verdict_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_judge_verdict()
        payload["authority_mode"] = "INVALID"
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_invalid_verdict_scope(self):
        schema = _load_schema("judge_verdict_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_judge_verdict()
        payload["verdict_scope"] = "INVALID"
        with pytest.raises(Exception):
            validator.validate(payload)


# ---------------------------------------------------------------------------
# F. Type validation
# ---------------------------------------------------------------------------

class TestTypeValidation:
    def test_confidence_must_be_number(self):
        schema = _load_schema("expert_output_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_expert_output()
        payload["confidence"] = "not_a_number"
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_tf_sec_must_be_integer(self):
        schema = _load_schema("expert_output_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_expert_output()
        payload["tf_sec"] = "not_an_int"
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_reasoning_must_be_array(self):
        schema = _load_schema("expert_output_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_expert_output()
        payload["reasoning"] = "not_an_array"
        with pytest.raises(Exception):
            validator.validate(payload)

    def test_empty_reasoning_rejected(self):
        schema = _load_schema("expert_output_v1.json")
        resolver = _make_resolver()
        validator = Draft7Validator(schema, resolver=resolver)
        payload = _make_valid_expert_output()
        payload["reasoning"] = []
        with pytest.raises(Exception):
            validator.validate(payload)
