"""
LLM Judge Phase 1 — Verb Registry Integration Tests

Tests that all 4 Phase 1 verbs are present in the verb registry, with
correct schema paths and metadata.
"""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft7Validator

REGISTRY_PATH = Path("apps/reference/dictionaries/verb_registry_v1.yaml")
SCHEMAS_DIR = Path("apps/reference/domains/alpha_search/judge/schemas")

PHASE1_VERBS = [
    "JUDGE_ENTRY_VERDICT_V1",
    "JUDGE_LIFECYCLE_VERDICT_V1",
    "JUDGE_EVIDENCE_ASSEMBLED_V1",
    "JUDGE_CHAMBER_AGGREGATED_V1",
]

PHASE2_VERBS = [
    "JUDGE_EXPERT_PRODUCED_V1",
]


def _load_registry():
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["registry"]


def _find_verb(registry, verb_name):
    for entry in registry:
        if entry["verb"] == verb_name:
            return entry
    return None


# ---------------------------------------------------------------------------
# A. All 4 verbs exist
# ---------------------------------------------------------------------------

class TestVerbsExist:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.registry = _load_registry()

    @pytest.mark.parametrize("verb", PHASE1_VERBS)
    def test_verb_present(self, verb):
        entry = _find_verb(self.registry, verb)
        assert entry is not None, f"Verb {verb} not found in registry"

    @pytest.mark.parametrize("verb", PHASE1_VERBS)
    def test_verb_owner_is_alpha_search(self, verb):
        entry = _find_verb(self.registry, verb)
        assert entry["owner"] == "alpha_search"

    @pytest.mark.parametrize("verb", PHASE1_VERBS)
    def test_verb_status_experimental(self, verb):
        entry = _find_verb(self.registry, verb)
        assert entry["status"] == "experimental"

    @pytest.mark.parametrize("verb", PHASE1_VERBS)
    def test_verb_op_is_evt(self, verb):
        entry = _find_verb(self.registry, verb)
        assert entry["op"] == "EVT"


# ---------------------------------------------------------------------------
# B. Schema paths resolve and compile
# ---------------------------------------------------------------------------

class TestSchemaPathsResolve:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.registry = _load_registry()

    @pytest.mark.parametrize("verb", PHASE1_VERBS)
    def test_schema_path_exists(self, verb):
        entry = _find_verb(self.registry, verb)
        schema_path = Path(entry["schema"])
        assert schema_path.exists(), f"Schema file not found: {schema_path}"

    @pytest.mark.parametrize("verb", PHASE1_VERBS)
    def test_schema_compiles(self, verb):
        entry = _find_verb(self.registry, verb)
        schema_path = Path(entry["schema"])
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        Draft7Validator.check_schema(schema)


# ---------------------------------------------------------------------------
# C. Phase 2 verbs exist
# ---------------------------------------------------------------------------

class TestPhase2VerbsExist:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.registry = _load_registry()

    @pytest.mark.parametrize("verb", PHASE2_VERBS)
    def test_verb_present(self, verb):
        entry = _find_verb(self.registry, verb)
        assert entry is not None, f"Phase 2 verb {verb} not found"

    @pytest.mark.parametrize("verb", PHASE2_VERBS)
    def test_verb_owner_is_alpha_search(self, verb):
        entry = _find_verb(self.registry, verb)
        assert entry["owner"] == "alpha_search"

    @pytest.mark.parametrize("verb", PHASE2_VERBS)
    def test_verb_schema_exists(self, verb):
        entry = _find_verb(self.registry, verb)
        schema_path = Path(entry["schema"])
        assert schema_path.exists(), f"Schema file not found: {schema_path}"


# ---------------------------------------------------------------------------
# D. Deferred verbs still absent
# ---------------------------------------------------------------------------

class TestDeferredVerbsAbsent:
    @pytest.fixture(autouse=True)
    def _load(self):
        self.registry = _load_registry()

    def test_verdict_applied_not_in_phase2(self):
        entry = _find_verb(self.registry, "JUDGE_VERDICT_APPLIED")
        assert entry is None, "JUDGE_VERDICT_APPLIED should not be in Phase 2"

    def test_mode_active_not_in_phase2(self):
        entry = _find_verb(self.registry, "JUDGE_MODE_ACTIVE")
        assert entry is None, "JUDGE_MODE_ACTIVE should not be in Phase 2"
