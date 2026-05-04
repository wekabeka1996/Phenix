"""
RD-DOMAIN-AUDIT-01 — regime_detector domain structural guardrails.

Enforces:
- Fail-closed: RegimeDetector rejects dict config
- Fail-closed: Missing models raises ConfigContractError
- domain_dict.json consistency
- Schema enum matches code regime labels
- No stale pycache ghosts
- No empty test files
- __init__.py version present
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RD_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "regime_detector"


class TestFailClosed:
    """Guard: regime_detector must be fail-closed under invalid/missing inputs."""

    def test_rejects_dict_config(self):
        from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
        from unittest.mock import MagicMock
        with pytest.raises(TypeError, match="dict"):
            RegimeDetector(config={"bad": "config"}, fsm=MagicMock())

    def test_missing_models_raises_config_contract_error(self):
        from apps.reference.config_contract import ConfigContractError
        from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
        from unittest.mock import MagicMock

        class FakeConfig:
            basis_tf_sec = 300
            uncertain_cutoff = 0.55
            models = None
            system = None
        with pytest.raises(ConfigContractError):
            RegimeDetector(config=FakeConfig(), fsm=MagicMock())


class TestDomainDictConsistency:
    """Guard: domain_dict.json matches live domain state."""

    def test_domain_dict_has_ssot_notes(self):
        dd = json.loads(
            (RD_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        assert "ssot_notes" in dd, "domain_dict.json must have ssot_notes"
        assert "regime_labels" in dd["ssot_notes"]
        assert "detection_cascade" in dd["ssot_notes"]
        assert "hysteresis" in dd["ssot_notes"]

    def test_domain_dict_imports_complete(self):
        dd = json.loads(
            (RD_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        import_names = {e["event_name"] for e in dd.get("imports", [])}
        assert "EVT:FEATURES_CALCULATED" in import_names

    def test_domain_dict_exports_complete(self):
        dd = json.loads(
            (RD_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        export_names = {e["event_name"] for e in dd.get("exports", [])}
        assert "EVT:REGIME_DETECTED" in export_names

    def test_domain_dict_description_not_garbled(self):
        dd = json.loads(
            (RD_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        desc = dd.get("description", "")
        assert desc.strip(), "domain_dict description must not be empty"
        assert len(desc.strip()) > 20, (
            f"domain_dict description looks garbled: {desc[:50]!r}"
        )


class TestSchemaEnumMatchesCode:
    """Guard: regime labels in schema match the strings used in detector code."""

    def test_schema_regime_enum_covers_code_labels(self):
        schema = json.loads(
            (RD_DIR / "schemas" / "regime_detected_v1.json").read_text(encoding="utf-8"))
        schema_regimes = set(schema["properties"]["regime"]["enum"])
        # These are the labels emitted by regime_detector.py
        code_labels = {
            "TREND_UP", "TREND_DOWN", "MEAN_REVERSION",
            "HIGH_VOLATILITY", "LOW_VOLATILITY", "UNCERTAIN",
        }
        assert code_labels == schema_regimes, (
            f"Schema/code regime label mismatch: "
            f"schema_only={schema_regimes - code_labels}, "
            f"code_only={code_labels - schema_regimes}"
        )


class TestNoPycacheGhosts:
    """Guard: no stale pycache entries."""

    def test_no_stale_pycache_entries(self):
        pycache = RD_DIR / "__pycache__"
        if not pycache.exists():
            return

        live_stems = {p.stem for p in RD_DIR.glob("*.py")}
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

    def test_no_empty_rd_tests(self):
        test_dir = PROJECT_ROOT / "tests" / "domains" / "regime_detector"
        if not test_dir.exists():
            return

        empty = [
            p.name for p in test_dir.glob("test_*.py")
            if p.stat().st_size == 0
        ]
        assert not empty, f"Empty test files: {empty}"


class TestInitExportsVersion:
    """Guard: __init__.py has __version__."""

    def test_init_has_version(self):
        source = (RD_DIR / "__init__.py").read_text(encoding="utf-8")
        assert "__version__" in source, (
            "regime_detector __init__.py must define __version__"
        )
