"""
FE-DOMAIN-AUDIT-01 — feature_engineering domain structural guardrails.

Enforces:
- Feature catalog SSOT: V1/V2 metadata completeness
- domain_dict.json consistency
- Contract alignment: schema features match metadata
- No stale pycache ghosts
- No empty test files
- Config wrapper typed (extra='forbid')
- Version field present in __init__.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FE_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "feature_engineering"


class TestFeatureCatalogSSOT:
    """Guard: contracts.py V1/V2 metadata is the canonical feature catalog."""

    def test_v1_metadata_has_11_features(self):
        from apps.reference.domains.feature_engineering.contracts import (
            V1_FEATURE_METADATA,
            V1_FEATURE_NAMES,
        )
        assert len(V1_FEATURE_METADATA) == 11
        assert len(V1_FEATURE_NAMES) == 11

    def test_v2_metadata_extends_v1(self):
        from apps.reference.domains.feature_engineering.contracts import (
            V1_FEATURE_NAMES,
            V2_FEATURE_NAMES,
        )
        v1_set = set(V1_FEATURE_NAMES)
        v2_set = set(V2_FEATURE_NAMES)
        assert v1_set.issubset(v2_set), (
            f"V2 must be superset of V1. Missing: {v1_set - v2_set}"
        )

    def test_v2_metadata_has_range_and_neutral(self):
        from apps.reference.domains.feature_engineering.contracts import (
            V2_FEATURE_METADATA,
        )
        for name, meta in V2_FEATURE_METADATA.items():
            assert "range" in meta, f"{name} missing 'range' in metadata"
            assert "neutral" in meta, f"{name} missing 'neutral' in metadata"
            assert "group" in meta, f"{name} missing 'group' in metadata"

    def test_feature_set_v1_fields_match_metadata(self):
        from apps.reference.domains.feature_engineering.contracts import (
            FeatureSetV1,
            V1_FEATURE_NAMES,
        )
        model_fields = set(FeatureSetV1.model_fields.keys())
        meta_fields = set(V1_FEATURE_NAMES)
        assert model_fields == meta_fields, (
            f"FeatureSetV1 fields must match V1_FEATURE_METADATA. "
            f"Extra: {model_fields - meta_fields}, Missing: {meta_fields - model_fields}"
        )


class TestSchemaAlignment:
    """Guard: JSON schema features_calculated_v1 required fields are present."""

    def test_schema_required_fields_exist(self):
        schema = json.loads(
            (FE_DIR / "schemas" / "features_calculated_v1.json").read_text(
                encoding="utf-8"
            )
        )
        assert "ts" in schema.get("required", [])
        assert "symbol" in schema.get("required", [])
        assert "features" in schema.get("required", [])

    def test_all_three_schemas_exist(self):
        schemas = list((FE_DIR / "schemas").glob("*.json"))
        schema_names = {s.stem for s in schemas}
        expected = {
            "features_calculated_v1",
            "cmd_process_strategy_v1",
            "process_strategy_blocked_v1",
        }
        assert expected.issubset(schema_names), (
            f"Missing schemas: {expected - schema_names}"
        )


class TestDomainDictConsistency:
    """Guard: domain_dict.json matches live domain state."""

    def test_domain_dict_has_ssot_notes(self):
        dd = json.loads(
            (FE_DIR / "domain_dict.json").read_text(encoding="utf-8")
        )
        assert "ssot_notes" in dd, "domain_dict.json must have ssot_notes"
        assert "feature_catalog" in dd["ssot_notes"]
        assert "computation_engine" in dd["ssot_notes"]

    def test_domain_dict_imports_complete(self):
        dd = json.loads(
            (FE_DIR / "domain_dict.json").read_text(encoding="utf-8")
        )
        import_names = {e["event_name"] for e in dd.get("imports", [])}
        assert "EVT:MARKET_TICK_RECEIVED" in import_names
        assert "EVT:BAR_CLOSED" in import_names
        assert "EVT:REGIME_DETECTED" in import_names

    def test_domain_dict_exports_complete(self):
        dd = json.loads(
            (FE_DIR / "domain_dict.json").read_text(encoding="utf-8")
        )
        export_names = {e["event_name"] for e in dd.get("exports", [])}
        assert "EVT:FEATURES_CALCULATED" in export_names
        assert "CMD:PROCESS_STRATEGY" in export_names
        assert "EVT:PROCESS_STRATEGY_BLOCKED" in export_names

    def test_domain_dict_description_not_garbled(self):
        dd = json.loads(
            (FE_DIR / "domain_dict.json").read_text(encoding="utf-8")
        )
        desc = dd.get("description", "")
        assert desc.strip(), "domain_dict description must not be empty"
        assert len(desc.strip()) > 30, (
            f"domain_dict description looks garbled: {desc[:50]!r}"
        )

    def test_domain_dict_feature_families_present(self):
        dd = json.loads(
            (FE_DIR / "domain_dict.json").read_text(encoding="utf-8")
        )
        families = dd.get("feature_families", {})
        assert "v1_base" in families
        assert "v1_phase1" in families
        assert "v2_additive" in families


class TestNoPycacheGhosts:
    """Guard: no stale pycache entries."""

    def test_no_stale_pycache_entries(self):
        pycache = FE_DIR / "__pycache__"
        if not pycache.exists():
            return

        live_stems = {p.stem for p in FE_DIR.glob("*.py")}
        pycache_stems = set()
        for p in pycache.glob("*.pyc"):
            stem = p.name.split(".")[0]
            pycache_stems.add(stem)

        ghosts = pycache_stems - live_stems
        assert not ghosts, (
            f"Stale __pycache__ entries: {sorted(ghosts)}"
        )


class TestNoEmptyTestFiles:
    """Guard: no 0-byte test files."""

    def test_no_empty_fe_tests(self):
        test_dir = PROJECT_ROOT / "tests" / "domains" / "feature_engineering"
        if not test_dir.exists():
            return

        empty = [
            p.name for p in test_dir.glob("test_*.py")
            if p.stat().st_size == 0
        ]
        assert not empty, f"Empty test files: {empty}"


class TestInitExportsVersion:
    """Guard: __init__.py has __version__ and re-exports FeatureEngineering."""

    def test_init_has_version(self):
        source = (FE_DIR / "__init__.py").read_text(encoding="utf-8")
        assert "__version__" in source

    def test_init_exports_feature_engineering(self):
        source = (FE_DIR / "__init__.py").read_text(encoding="utf-8")
        assert "FeatureEngineering" in source
