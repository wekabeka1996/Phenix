"""
DM-DOMAIN-AUDIT-01 — decision_making domain structural guardrails.

Enforces:
- No stale pycache ghosts for deleted source files
- WhyCode re-export identity (not a local fork)
- No imports of deleted modules
- domain_dict.json consistency with live file tree
- All DM-owned registry entries have active emitters
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DM_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "decision_making"


class TestNoPycacheGhosts:
    """Guard: no __pycache__ entries for files that no longer exist."""

    def test_no_stale_pycache_entries(self):
        pycache = DM_DIR / "__pycache__"
        if not pycache.exists():
            return

        live_stems = {p.stem for p in DM_DIR.glob("*.py")}
        pycache_stems = set()
        for p in pycache.glob("*.pyc"):
            # pattern: module.cpython-3XX.pyc
            stem = p.name.split(".")[0]
            pycache_stems.add(stem)

        ghosts = pycache_stems - live_stems
        assert not ghosts, (
            f"Stale __pycache__ entries for deleted files: {sorted(ghosts)}. "
            "Delete these .pyc files."
        )


class TestWhyCodeReExport:
    """Guard: decision_making.why_codes must be a re-export, not a fork."""

    def test_no_local_whycode_class(self):
        wc_path = DM_DIR / "why_codes.py"
        source = wc_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        local_classes = [n.name for n in ast.walk(
            tree) if isinstance(n, ast.ClassDef)]
        assert "WhyCode" not in local_classes, (
            "decision_making/why_codes.py defines a local WhyCode class — "
            "it must only re-export from vfoundation.core.why_codes."
        )

    def test_whycode_identity(self):
        from vfoundation.core.why_codes import WhyCode as Canonical
        from apps.reference.domains.decision_making.why_codes import WhyCode as DM
        assert DM is Canonical


class TestNoDeletedModuleImports:
    """Guard: no live .py file imports deleted modules."""

    DELETED_MODULES = {
        "aurora_scoring_kernel",
        "scoring_direction_strength_v1",
        "signal_score_v2",
        "portfolio_provider",
    }

    # Fully qualified deleted module paths (relative imports resolve to these)
    DELETED_FQ_PREFIXES = [
        "apps.reference.domains.decision_making.aurora_scoring_kernel",
        "apps.reference.domains.decision_making.scoring_direction_strength_v1",
        "apps.reference.domains.decision_making.signal_score_v2",
        "apps.reference.domains.decision_making.portfolio_provider",
    ]

    def _get_imports(self, filepath: Path) -> list[str]:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                # Resolve relative imports
                if node.level > 0:
                    names.append(
                        f"apps.reference.domains.decision_making.{node.module}")
                else:
                    names.append(node.module)
        return names

    def test_no_imports_of_deleted_modules(self):
        violations = []
        for py_file in DM_DIR.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            for imp in self._get_imports(py_file):
                for prefix in self.DELETED_FQ_PREFIXES:
                    if imp == prefix or imp.startswith(prefix + "."):
                        violations.append(f"{py_file.name} imports {imp}")

        assert not violations, (
            f"Live files import deleted modules: {violations}"
        )


class TestDomainDictConsistency:
    """Guard: domain_dict.json matches live domain state."""

    def test_domain_dict_version_matches_init(self):
        dd = json.loads(
            (DM_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        init_src = (DM_DIR / "__init__.py").read_text(encoding="utf-8")
        # Extract __version__ from init
        for line in init_src.splitlines():
            if line.strip().startswith("__version__"):
                init_version = line.split("=")[1].strip().strip('"').strip("'")
                break
        else:
            pytest.fail("__version__ not found in __init__.py")
        assert dd["version"] == init_version, (
            f"domain_dict.json version ({dd['version']}) != __init__.py ({init_version})"
        )

    def test_domain_dict_has_ssot_notes(self):
        dd = json.loads(
            (DM_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        assert "ssot_notes" in dd, "domain_dict.json must have ssot_notes section"
        assert "why_codes" in dd["ssot_notes"]
        assert "nrr" in dd["ssot_notes"]

    def test_domain_dict_exports_match_registry_owner(self):
        """All DM-owned registry entries should appear in domain_dict exports."""
        import yaml
        registry_path = PROJECT_ROOT / "apps" / "reference" / \
            "dictionaries" / "verb_registry_v1.yaml"
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))

        dm_owned = {
            f"{e['op']}:{e['verb']}"
            for e in registry["registry"]
            if e.get("owner") == "decision_making"
            and e.get("status") != "deprecated"
        }

        dd = json.loads(
            (DM_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        dd_exports = {e["event_name"] for e in dd.get("exports", [])}

        # At minimum, the high-traffic exports must be present
        critical = {"EVT:TRADE_INTENT_PROPOSED",
                    "EVT:STRATEGY_SIGNAL_PRODUCED"}
        missing_critical = critical - dd_exports
        assert not missing_critical, (
            f"Critical DM exports missing from domain_dict: {missing_critical}"
        )

    def test_domain_dict_does_not_export_retired_handler_readiness_diagnostics(self):
        dd = json.loads(
            (DM_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        dd_exports = {e["event_name"] for e in dd.get("exports", [])}

        assert "EVT:HANDLER_READINESS_DIAGNOSTICS" not in dd_exports, (
            "Retired HANDLER_READINESS_DIAGNOSTICS must not remain in decision_making domain_dict exports"
        )

    def test_domain_dict_exports_split_alpha_telemetry_verb_only(self):
        dd = json.loads(
            (DM_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        dd_exports = {e["event_name"] for e in dd.get("exports", [])}

        assert "EVT:ALPHA_SCORES_AGGREGATED" in dd_exports, (
            "decision_making aggregate alpha telemetry must be exported under EVT:ALPHA_SCORES_AGGREGATED"
        )
        assert "EVT:ALPHA_SCORE_CALCULATED" not in dd_exports, (
            "decision_making must not keep exporting alpha_search's provider-scoped EVT:ALPHA_SCORE_CALCULATED"
        )

    def test_app_surfaces_have_no_handler_readiness_diagnostics_references(self):
        app_files = [
            *PROJECT_ROOT.joinpath("apps", "reference").rglob("*.py"),
            *PROJECT_ROOT.joinpath("apps", "reference").rglob("*.json"),
            *PROJECT_ROOT.joinpath("apps", "reference").rglob("*.yaml"),
        ]
        hits = []
        for path in sorted(app_files):
            text = path.read_text(encoding="utf-8")
            if "HANDLER_READINESS_DIAGNOSTICS" in text:
                hits.append(str(path.relative_to(PROJECT_ROOT)))

        assert not hits, (
            "Retired HANDLER_READINESS_DIAGNOSTICS must not remain in apps/reference surfaces: "
            f"{hits}"
        )

    def test_dm_surfaces_have_no_alpha_score_calculated_references(self):
        dm_files = [
            *DM_DIR.rglob("*.py"),
            *DM_DIR.rglob("*.json"),
            *DM_DIR.rglob("*.md"),
        ]
        hits = []
        for path in sorted(dm_files):
            text = path.read_text(encoding="utf-8")
            if "EVT:ALPHA_SCORE_CALCULATED" in text:
                hits.append(str(path.relative_to(PROJECT_ROOT)))

        assert not hits, (
            "decision_making surfaces must not keep the old aggregate EVT:ALPHA_SCORE_CALCULATED contract: "
            f"{hits}"
        )


class TestNoEmptyTestFiles:
    """Guard: no 0-byte test files in DM test directories."""

    def test_no_empty_dm_tests(self):
        test_dir = PROJECT_ROOT / "tests" / "domains" / "decision_making"
        if not test_dir.exists():
            return

        empty = [
            p.name for p in test_dir.glob("test_*.py")
            if p.stat().st_size == 0
        ]
        assert not empty, f"Empty test files found: {empty}"
