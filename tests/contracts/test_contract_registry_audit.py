"""
CONTRACT-AUDIT-01 — Event/command contract registry integrity guards.

Enforces:
- All registry schema references resolve to existing files on disk
- No duplicate (op, verb) pairs in the registry
- Wildcard CMD policy remains fail-closed
- Core runtime-critical contracts are present in registry
- No dead config namespace references in schema paths
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PROJECT_ROOT / "apps" / "reference" / \
    "dictionaries" / "verb_registry_v1.yaml"


def _load_registry() -> list[dict]:
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry = data.get("registry")
    assert isinstance(
        registry, list), "verb registry: expected top-level 'registry' list"
    return registry


def _load_policies() -> dict:
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return data.get("policies", {})


class TestRegistrySchemaIntegrity:
    """All schema references in the registry must resolve to real files."""

    def test_all_schema_refs_resolve(self):
        registry = _load_registry()
        broken = []
        for entry in registry:
            schema = entry.get("schema")
            if schema:
                full = PROJECT_ROOT / schema
                if not full.exists():
                    broken.append(f"{entry['op']}:{entry['verb']} -> {schema}")
        assert not broken, f"Broken schema references:\n" + "\n".join(broken)

    def test_no_schema_paths_reference_dead_config_namespaces(self):
        registry = _load_registry()
        dead_prefixes = ("config/aurora_baseline", "config/mean_reversion")
        violations = []
        for entry in registry:
            schema = entry.get("schema") or ""
            if any(schema.startswith(p) for p in dead_prefixes):
                violations.append(f"{entry['op']}:{entry['verb']} -> {schema}")
        assert not violations, f"Schema paths reference archived config trees:\n" + \
            "\n".join(violations)


class TestRegistryNoDuplicates:
    """No duplicate (op, verb) pairs allowed."""

    def test_no_duplicate_op_verb_pairs(self):
        registry = _load_registry()
        seen: dict[tuple[str, str], int] = {}
        duplicates = []
        for entry in registry:
            key = (entry["op"], entry["verb"])
            if key in seen:
                duplicates.append(
                    f"{key[0]}:{key[1]} (first at index {seen[key]})")
            else:
                seen[key] = len(seen)
        assert not duplicates, f"Duplicate registry entries:\n" + \
            "\n".join(duplicates)


class TestFailClosedPolicies:
    """Wildcard policies must remain fail-closed for CMD/DEC/ERR."""

    def test_cmd_wildcard_fail_closed(self):
        policies = _load_policies()
        wc = policies.get("wildcard", {})
        assert wc.get(
            "CMD") is False, "CMD wildcard must be False (fail-closed)"

    def test_dec_wildcard_fail_closed(self):
        policies = _load_policies()
        wc = policies.get("wildcard", {})
        assert wc.get(
            "DEC") is False, "DEC wildcard must be False (fail-closed)"

    def test_err_wildcard_fail_closed(self):
        policies = _load_policies()
        wc = policies.get("wildcard", {})
        assert wc.get(
            "ERR") is False, "ERR wildcard must be False (fail-closed)"


# Core runtime-critical contracts that MUST be in registry for the pipeline to work
CORE_CONTRACTS = [
    ("EVT", "MARKET_TICK_RECEIVED"),
    ("EVT", "BAR_CLOSED"),
    ("EVT", "FEATURES_CALCULATED"),
    ("EVT", "REGIME_DETECTED"),
    ("EVT", "RISK_ASSESSMENT_COMPLETED"),
    ("CMD", "PROCESS_STRATEGY"),
    ("EVT", "STRATEGY_SIGNAL_PRODUCED"),
    ("EVT", "TRADE_INTENT_PROPOSED"),
    ("EVT", "TRADE_INTENT_REJECTED"),
    ("CMD", "OPEN"),
    ("CMD", "CLOSE"),
    ("EVT", "TRADE_EXECUTED"),
    ("EVT", "PORTFOLIO_STATE_UPDATED"),
    ("EVT", "EXPOSURE_SUMMARY_UPDATED"),
    ("EVT", "ORDER_PLACED"),
    ("EVT", "SYSTEM_STRESS_STATE_UPDATED"),
]


class TestCoreContractsRegistered:
    """Every runtime-critical pipeline contract must be in the verb registry."""

    @pytest.mark.parametrize("op,verb", CORE_CONTRACTS, ids=[f"{o}:{v}" for o, v in CORE_CONTRACTS])
    def test_core_contract_registered(self, op: str, verb: str):
        registry = _load_registry()
        match = [e for e in registry if e.get(
            "op") == op and e.get("verb") == verb]
        assert match, f"Core contract {op}:{verb} is missing from verb_registry_v1.yaml"


# Contracts that have schemas and are most critical should also have correct schema files
SCHEMA_REQUIRED_CONTRACTS = [
    ("EVT", "FEATURES_CALCULATED"),
    ("EVT", "REGIME_DETECTED"),
    ("EVT", "TRADE_INTENT_PROPOSED"),
    ("EVT", "TRADE_INTENT_REJECTED"),
    ("CMD", "OPEN"),
    ("CMD", "PROCESS_STRATEGY"),
    ("EVT", "TRADE_EXECUTED"),
]


class TestSchemaRequiredContracts:
    """Critical contracts must have non-null schema references that exist on disk."""

    @pytest.mark.parametrize("op,verb", SCHEMA_REQUIRED_CONTRACTS, ids=[f"{o}:{v}" for o, v in SCHEMA_REQUIRED_CONTRACTS])
    def test_has_schema(self, op: str, verb: str):
        registry = _load_registry()
        entry = next((e for e in registry if e.get("op") ==
                     op and e.get("verb") == verb), None)
        assert entry, f"{op}:{verb} not in registry"
        schema = entry.get("schema")
        assert schema, f"{op}:{verb} has no schema reference"
        assert (PROJECT_ROOT /
                schema).exists(), f"{op}:{verb} schema file missing: {schema}"
