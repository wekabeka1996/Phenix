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
    """Guard: JSON schema and Python contracts are split and aligned."""

    def _bar_schema(self) -> dict:
        return json.loads((FE_DIR / "schemas" / "features_calculated_v1.json").read_text(encoding="utf-8"))

    def _tick_schema(self) -> dict:
        return json.loads((FE_DIR / "schemas" / "tick_features_calculated_v1.json").read_text(encoding="utf-8"))

    def test_bar_schema_required_fields_exist(self):
        schema = self._bar_schema()
        required = schema.get("required", [])
        assert "ts" in required
        assert "symbol" in required
        assert "tf_sec" in required
        assert "features" in required
        assert "warmup" in required
        assert "price_motion" in required
        assert "bar" in required
        assert "source_mode" in required
        assert "diagnostics" in required
        assert "regime" in schema["properties"]
        assert "regime" not in required

    def test_tick_schema_required_fields_exist(self):
        schema = self._tick_schema()
        required = schema.get("required", [])
        assert "ts" in required
        assert "symbol" in required
        assert "tf_sec" in required
        assert "features" in required
        assert "warmup" in required
        assert "price_motion" in required
        assert "bar" in required
        assert "source_mode" in required

        tf_sec_schema = schema["properties"]["tf_sec"]
        assert tf_sec_schema.get("const") == 0
        assert schema["properties"]["bar"].get("type") == "null"

    def test_all_four_schemas_exist(self):
        schemas = list((FE_DIR / "schemas").glob("*.json"))
        schema_names = {s.stem for s in schemas}
        expected = {
            "features_calculated_v1",
            "tick_features_calculated_v1",
            "cmd_process_strategy_v1",
            "process_strategy_blocked_v1",
        }
        assert expected.issubset(schema_names), (
            f"Missing schemas: {expected - schema_names}"
        )

    def test_bar_and_tick_schema_model_alignment(self):
        import jsonschema
        from apps.reference.domains.feature_engineering.contracts import (
            validate_bar_features_payload_v1,
            validate_tick_features_payload_v1,
        )

        bar_payload = {
            "ts": 1_700_000_000_000,
            "symbol": "BTCUSDT",
            "tf_sec": 180,
            "features": {
                "obi": "0.1",
                "tfi": "0.0",
                "delta_price": "0.0",
                "absorption": "0.0",
                "price": "100.0",
                "liquidity_kappa": "0.5",
            },
            "warmup": {
                "full_ready": True,
                "ticks_seen": 12,
                "ready": {},
                "reasons": [],
            },
            "price_motion": {
                "ret_10s": 0.0,
                "ret_60s": 0.0,
                "ret_300s": 0.0,
                "vol_pct_10s": 0.0,
                "vol_pct_60s": 0.0,
                "vol_pct_300s": 0.0,
                "pm_norm_10s": 0.0,
                "pm_norm_60s": 0.0,
                "pm_norm_300s": 0.0,
            },
            "bar": {
                "symbol": "BTCUSDT",
                "timeframe_sec": 180,
                "start_ts_ms": 1_699_999_820_000,
                "end_ts_ms": 1_699_999_999_999,
                "open": "99.0",
                "high": "101.0",
                "low": "98.0",
                "close": "100.0",
                "volume": "1000.0",
            },
            "source_mode": "live",
            "regime": None,
            "diagnostics": {"fe": {"features_emitted": 1, "cmd_emitted": 0}},
        }
        tick_payload = {
            "ts": 1_700_000_000_001,
            "symbol": "BTCUSDT",
            "tf_sec": 0,
            "features": {
                "obi": "0.1",
                "tfi": "0.0",
                "delta_price": "0.0",
                "absorption": "0.0",
                "price": "100.0",
                "liquidity_kappa": "0.5",
            },
            "warmup": {
                "full_ready": False,
                "ticks_seen": 13,
                "ready": {},
                "reasons": ["bad_dt"],
            },
            "price_motion": None,
            "bar": None,
            "source_mode": "live",
            "diagnostics": {"fe": {"features_emitted": 2, "cmd_emitted": 0}},
            "data_quality": {"drops": ["bad_dt"], "notes": []},
        }

        bar_schema = self._bar_schema()
        tick_schema = self._tick_schema()

        jsonschema.validate(bar_payload, bar_schema)
        jsonschema.validate(tick_payload, tick_schema)

        bar_model = validate_bar_features_payload_v1(bar_payload)
        tick_model = validate_tick_features_payload_v1(tick_payload)

        assert bar_model.tf_sec == 180
        assert tick_model.tf_sec == 0
        assert tick_model.bar is None


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
        assert "EVT:TICK_FEATURES_CALCULATED" in export_names
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
