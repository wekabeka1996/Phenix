from __future__ import annotations

import json
from pathlib import Path

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _registry_path() -> Path:
    return _repo_root() / "apps" / "reference" / "dictionaries" / "verb_registry_v1.yaml"


def _load_registry() -> dict:
    path = _registry_path()
    if not path.exists():
        raise AssertionError(f"Missing registry file: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_cmd_process_strategy_registered() -> None:
    data = _load_registry()
    registry = data.get("registry")
    if not isinstance(registry, list):
        raise AssertionError("verb registry: expected top-level 'registry' list")

    entry = next(
        (
            e
            for e in registry
            if isinstance(e, dict) and e.get("op") == "CMD" and e.get("verb") == "PROCESS_STRATEGY"
        ),
        None,
    )
    assert entry is not None, "Expected CMD:PROCESS_STRATEGY to be registered"

    schema = entry.get("schema")
    assert schema == "apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json"
    assert (_repo_root() / schema).exists(), f"Missing schema file referenced by registry: {schema}"


def test_unknown_cmd_is_rejected() -> None:
    data = _load_registry()
    policies = data.get("policies")
    assert isinstance(policies, dict)
    wildcard = policies.get("wildcard")
    assert isinstance(wildcard, dict)
    assert wildcard.get("CMD") is False, "Fail-closed policy regression: wildcard CMD must remain false"


def test_cmd_process_strategy_schema_has_minimal_contract() -> None:
    schema_path = (
        _repo_root()
        / "apps"
        / "reference"
        / "domains"
        / "feature_engineering"
        / "schemas"
        / "cmd_process_strategy_v1.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    required = schema.get("required")
    assert isinstance(required, list)
    for key in ("symbol", "tf_sec", "bar_close_ts", "bar", "features", "warmup", "regime"):
        assert key in required
