from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema.validators import Draft7Validator

from vfoundation.core.schema_registry import init_global_registry


REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "apps" / "reference" / \
    "dictionaries" / "verb_registry_v1.yaml"
SCHEMA_PATH = REPO_ROOT / "apps" / "reference" / "domains" / \
    "neocortex" / "schemas" / "neocortex_decision_logged_v1.json"


def _load_registry() -> list[dict[str, object]]:
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry = data.get("registry")
    assert isinstance(registry, list)
    return registry


def _load_schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_neocortex_decision_logged_registry_entry_loads_validator() -> None:
    registry = _load_registry()
    entry = next(
        (
            item
            for item in registry
            if isinstance(item, dict)
            and item.get("op") == "EVT"
            and item.get("verb") == "NEOCORTEX_DECISION_LOGGED"
        ),
        None,
    )
    assert entry is not None, "Expected EVT:NEOCORTEX_DECISION_LOGGED to be registered"
    assert entry.get("owner") == "neocortex"
    assert entry.get("status") == "experimental"
    assert entry.get(
        "schema") == "apps/reference/domains/neocortex/schemas/neocortex_decision_logged_v1.json"
    assert (REPO_ROOT / str(entry.get("schema"))).exists()

    loaded = init_global_registry(project_root=".")
    assert loaded.get_validator("EVT", "NEOCORTEX_DECISION_LOGGED") is not None


def test_neocortex_decision_logged_schema_accepts_current_embedded_and_standalone_payloads() -> None:
    schema = _load_schema()
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)

    embedded_payload = {
        "decision_id": "decision-1",
        "rid": "rid-1",
        "symbol": "BTCUSDT",
        "decision_ts_ms": 1_700_000_000_100,
        "request_ts_ms": 1_700_000_000_000,
        "response_ts_ms": 1_700_000_000_100,
        "decision_basis_ts": 1_700_000_000_000,
        "authority_mode": "shadow",
        "apply_result": "SHADOW_RECORDED",
        "action": "ALLOW",
        "capture_mode": "journal_only",
        "authority_applied": False,
        "no_effect": True,
        "shadow_logged": True,
        "fallback_reason": None,
        "causal_state_snapshot": {
            "observation_id": "obs-1",
            "dataset_visibility": "diagnostics_only",
        },
        "data_quality_flags": {
            "authority_mode": "shadow",
            "capture_mode": "journal_only",
            "authority_applied": False,
            "no_effect": True,
            "supports_counterfactual_join": True,
            "snapshot_provider_configured": True,
        },
    }
    validator.validate(embedded_payload)

    shadow_counterfactual_payload = {
        "decision_id": "decision-1b",
        "rid": "rid-1b",
        "symbol": "BTCUSDT",
        "decision_ts_ms": 1_700_000_000_120,
        "request_ts_ms": 1_700_000_000_000,
        "response_ts_ms": 1_700_000_000_120,
        "decision_basis_ts": 1_700_000_000_000,
        "authority_mode": "shadow",
        "apply_result": "SHADOW_RECORDED",
        "action": "DENY",
        "capture_mode": "shadow_counterfactual",
        "authority_applied": False,
        "no_effect": True,
        "shadow_logged": True,
        "fallback_reason": None,
        "causal_state_snapshot": {
            "observation_id": "obs-1b",
            "dataset_visibility": "trainable",
        },
        "data_quality_flags": {
            "authority_mode": "shadow",
            "capture_mode": "shadow_counterfactual",
            "authority_applied": False,
            "no_effect": True,
            "model_action": "DENY",
            "returned_action": "ALLOW",
            "counterfactual_evaluation": True,
            "supports_counterfactual_join": True,
            "shadow_mode_forced_allow": True,
        },
    }
    validator.validate(shadow_counterfactual_payload)

    standalone_payload = {
        "event_name": "SHADOW:NEOCORTEX_DECISION_LOGGED",
        "decision_id": "decision-2",
        "rid": "rid-2",
        "symbol": "ETHUSDT",
        "decision_ts_ms": 1_700_000_001_000,
        "response_ts_ms": 1_700_000_001_000,
        "decision_basis_ts": 1_700_000_000_900,
        "authority_mode": "shadow",
        "apply_result": "SHADOW_MODEL_BLOCK",
        "action": "BLOCK",
        "fallback_reason": None,
        "causal_state_snapshot": {
            "symbol": "ETHUSDT",
            "dataset_visibility": "diagnostics_only",
        },
        "data_quality_flags": {
            "authority_mode": "shadow",
            "neocortex_enforcement_mode": "shadow",
            "model_action": "BLOCK",
            "returned_action": "ALLOW",
            "shadow_mode_forced_allow": True,
        },
    }
    validator.validate(standalone_payload)
