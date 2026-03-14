"""
EP-CONTRACT-BOUNDARY-01 — execution_position contract boundary guardrails.

Enforces:
- EXPOSURE_SUMMARY_UPDATED is owned by execution_position in registry
- co_emitters annotations exist for sanctioned co-emission contracts
- NRR import uses shared/types path, not direct DM import
- No direct decision_making imports in EP production code
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EP_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "execution_position"
REGISTRY_PATH = (
    PROJECT_ROOT / "apps" / "reference" / "dictionaries" / "verb_registry_v1.yaml"
)


def _load_registry():
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return data.get("registry", data) if isinstance(data, dict) else data


def _find_entry(registry, verb: str):
    for entry in registry:
        if isinstance(entry, dict) and entry.get("verb") == verb:
            return entry
    return None


class TestExposureOwnership:
    """Guard: EXPOSURE_SUMMARY_UPDATED must be owned by execution_position."""

    def test_exposure_summary_owner_is_ep(self):
        registry = _load_registry()
        entry = _find_entry(registry, "EXPOSURE_SUMMARY_UPDATED")
        assert entry is not None, "EXPOSURE_SUMMARY_UPDATED not found in registry"
        assert entry["owner"] == "execution_position", (
            f"EXPOSURE_SUMMARY_UPDATED owner must be execution_position, "
            f"got {entry['owner']}"
        )

    def test_exposure_summary_schema_is_in_ep(self):
        registry = _load_registry()
        entry = _find_entry(registry, "EXPOSURE_SUMMARY_UPDATED")
        assert entry is not None
        schema_path = entry.get("schema", "")
        assert "execution_position" in schema_path, (
            f"EXPOSURE_SUMMARY_UPDATED schema must be in execution_position, "
            f"got {schema_path}"
        )


class TestCoEmitterAnnotations:
    """Guard: sanctioned co-emission contracts must have co_emitters in registry."""

    def test_trade_intent_rejected_has_co_emitters(self):
        registry = _load_registry()
        entry = _find_entry(registry, "TRADE_INTENT_REJECTED")
        assert entry is not None
        co = entry.get("co_emitters", [])
        assert "execution_position" in co, (
            "TRADE_INTENT_REJECTED must list execution_position as co_emitter"
        )

    def test_trade_executed_has_co_emitters(self):
        registry = _load_registry()
        entry = _find_entry(registry, "TRADE_EXECUTED")
        assert entry is not None
        co = entry.get("co_emitters", [])
        assert "execution_position" in co, (
            "TRADE_EXECUTED must list execution_position as co_emitter"
        )


class TestNRRBoundary:
    """Guard: EP must not import NRR directly from decision_making."""

    def _get_import_sources(self, filepath: Path) -> list[str]:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
        sources = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                sources.append(node.module)
        return sources

    def test_leverage_service_uses_shared_types(self):
        """leverage_service.py must import NRR via shared/types, not direct DM."""
        ls_path = EP_DIR / "leverage_service.py"
        imports = self._get_import_sources(ls_path)
        for imp in imports:
            assert "decision_making.normalized_reject_reasons" not in imp, (
                f"leverage_service.py imports NRR directly from decision_making: {imp}. "
                "Use apps.reference.shared.types instead."
            )

    def test_no_direct_dm_imports_in_ep_production(self):
        """No EP production file should import directly from decision_making."""
        violations = []
        for py_file in EP_DIR.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            for imp in self._get_import_sources(py_file):
                if "domains.decision_making" in imp:
                    violations.append(f"{py_file.name} imports {imp}")

        assert not violations, (
            f"EP production files import directly from decision_making "
            f"(use shared/types instead): {violations}"
        )


class TestDomainDictBoundaryNotes:
    """Guard: domain_dict.json must document co-emission policy."""

    def test_co_emission_policy_documented(self):
        import json
        dd = json.loads(
            (EP_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        ssot = dd.get("ssot_notes", {})
        policy = ssot.get("co_emission_policy", {})
        assert "EVT:TRADE_INTENT_REJECTED" in policy, (
            "domain_dict must document TRADE_INTENT_REJECTED co-emission"
        )
        assert "EVT:TRADE_EXECUTED" in policy, (
            "domain_dict must document TRADE_EXECUTED co-emission"
        )
        assert "EVT:EXPOSURE_SUMMARY_UPDATED" in policy, (
            "domain_dict must document EXPOSURE_SUMMARY_UPDATED ownership"
        )

    def test_nrr_dependency_documented(self):
        import json
        dd = json.loads(
            (EP_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        ssot = dd.get("ssot_notes", {})
        assert "nrr_dependency" in ssot, (
            "domain_dict must document NRR dependency path"
        )
        assert "shared" in ssot["nrr_dependency"].lower(), (
            "NRR dependency note must reference shared/types"
        )
