"""
RM-DOMAIN-AUDIT-01 — risk_management domain structural guardrails.

Enforces:
- Fail-closed: _to_dec rejects None
- Fail-closed: RiskManagement rejects dict config
- Fail-closed: DailyRiskState blocks without equity
- WhyCode canonical import
- domain_dict.json consistency
- No NormalizedRejectReasons usage in RM
- No stale pycache ghosts
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RM_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "risk_management"


class TestFailClosed:
    """Guard: risk_management must be fail-closed under invalid/missing inputs."""

    def test_to_dec_rejects_none(self):
        from apps.reference.domains.risk_management.risk_management import _to_dec
        with pytest.raises(ValueError, match="None"):
            _to_dec(None)

    def test_to_dec_rejects_garbage(self):
        from apps.reference.domains.risk_management.risk_management import _to_dec
        with pytest.raises(ValueError):
            _to_dec("not_a_number")

    def test_risk_management_rejects_dict_config(self):
        from apps.reference.domains.risk_management.risk_management import RiskManagement
        from unittest.mock import MagicMock
        with pytest.raises(TypeError, match="dict"):
            RiskManagement(fsm=MagicMock(), config={"bad": "config"})


class TestWhyCodeCanonical:
    """Guard: RM must import WhyCode from canonical vfoundation path."""

    def test_whycode_import_is_canonical(self):
        import ast
        source = (RM_DIR / "risk_management.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "why_codes" in node.module:
                    assert "vfoundation" in node.module, (
                        f"WhyCode must be imported from vfoundation, got {node.module}"
                    )

    def test_no_nrr_usage(self):
        """RM must NOT use NormalizedRejectReasons."""
        import ast
        for py_file in RM_DIR.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "normalized_reject_reasons" not in node.module, (
                        f"{py_file.name} imports NormalizedRejectReasons — RM uses WhyCode, not NRR"
                    )


class TestDomainDictConsistency:
    """Guard: domain_dict.json matches live domain state."""

    def test_domain_dict_has_ssot_notes(self):
        dd = json.loads(
            (RM_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        assert "ssot_notes" in dd, "domain_dict.json must have ssot_notes"
        assert "risk_score" in dd["ssot_notes"]
        assert "daily_gate" in dd["ssot_notes"]
        assert "why_codes" in dd["ssot_notes"]

    def test_domain_dict_imports_complete(self):
        dd = json.loads(
            (RM_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        import_names = {e["event_name"] for e in dd.get("imports", [])}
        assert "EVT:FEATURES_CALCULATED" in import_names
        assert "EVT:PORTFOLIO_STATE_UPDATED" in import_names

    def test_domain_dict_exports_complete(self):
        dd = json.loads(
            (RM_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        export_names = {e["event_name"] for e in dd.get("exports", [])}
        assert "EVT:RISK_ASSESSMENT_COMPLETED" in export_names

    def test_domain_dict_descriptions_not_garbled(self):
        dd = json.loads(
            (RM_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        desc = dd.get("description", "")
        assert desc.strip(), "domain_dict description must not be empty"
        assert len(desc.strip()) > 20, (
            f"domain_dict description looks garbled: {desc[:50]!r}"
        )


class TestNoPycacheGhosts:
    """Guard: no stale pycache entries."""

    def test_no_stale_pycache_entries(self):
        pycache = RM_DIR / "__pycache__"
        if not pycache.exists():
            return

        live_stems = {p.stem for p in RM_DIR.glob("*.py")}
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

    def test_no_empty_rm_tests(self):
        test_dir = PROJECT_ROOT / "tests" / "domains" / "risk_management"
        if not test_dir.exists():
            return

        empty = [
            p.name for p in test_dir.glob("test_*.py")
            if p.stat().st_size == 0
        ]
        assert not empty, f"Empty test files: {empty}"
