"""
FE-DM-BOUNDARY-STABILIZATION — guardrail tests.

Enforces:
- DM production code does NOT import FE strategy files directly
- strategy_bridge.py facade provides all strategy symbols
- No new strategy-domain .py files added under FE without exemption
- Bar imports in DM use shared/types.py
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FE_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "feature_engineering"
DM_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "decision_making"

# Exempted FE .py files that contain strategy logic (known boundary leak).
# If a new strategy-domain file is added to FE, this test will fail until
# the exemption is explicitly expanded — forcing a conscious decision.
FE_STRATEGY_FILES_EXEMPTION = {
    "mean_reversion_strategy.py",
    "md_amr_strategy.py",
    "regime_mapping.py",
}

# DM production files (not tests) that must NOT contain direct FE strategy imports.
DM_PRODUCTION_FILES = [
    p for p in DM_DIR.glob("*.py")
    if not p.name.startswith("test_")
    and p.name != "strategy_bridge.py"  # bridge is the sanctioned facade
    and p.name != "__pycache__"
]

# Forbidden direct FE strategy import prefixes
FORBIDDEN_FE_STRATEGY_PREFIXES = (
    "apps.reference.domains.feature_engineering.mean_reversion_strategy",
    "apps.reference.domains.feature_engineering.md_amr_strategy",
    "apps.reference.domains.feature_engineering.regime_mapping",
)


def _extract_imports(filepath: Path) -> list[str]:
    """Extract all import source strings from a Python file AST."""
    try:
        tree = ast.parse(filepath.read_text(
            encoding="utf-8"), filename=str(filepath))
    except SyntaxError:
        return []

    sources = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            sources.append(node.module)
    return sources


class TestDMProductionNoDirectFEStrategyImports:
    """Guard: DM production code must not import FE strategy files directly."""

    def test_no_direct_fe_strategy_imports_in_dm_production(self):
        violations = []
        for filepath in DM_PRODUCTION_FILES:
            imports = _extract_imports(filepath)
            for imp in imports:
                if imp.startswith(FORBIDDEN_FE_STRATEGY_PREFIXES):
                    violations.append(f"{filepath.name}: {imp}")

        assert not violations, (
            f"DM production code imports FE strategy files directly. "
            f"Use decision_making/strategy_bridge.py instead.\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestDMBarImportsUseSharedTypes:
    """Guard: DM production Bar imports use shared/types.py, not FE direct."""

    def test_no_direct_fe_bar_imports_in_dm_production(self):
        violations = []
        for filepath in DM_PRODUCTION_FILES:
            imports = _extract_imports(filepath)
            for imp in imports:
                if imp == "apps.reference.domains.feature_engineering.bar_resampler":
                    violations.append(f"{filepath.name}: {imp}")

        assert not violations, (
            f"DM production code imports Bar directly from FE. "
            f"Use apps.reference.shared.types.Bar instead.\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestStrategyBridgeCompleteness:
    """Guard: strategy_bridge.py provides all required strategy symbols."""

    def test_bridge_exports_mr_strategy(self):
        from apps.reference.domains.decision_making.strategy_bridge import (
            MeanReversion1mStrategy,
            MRSignal,
            MRSignalType,
            MRStrategyConfig,
            MRSymbolState,
        )
        assert MeanReversion1mStrategy is not None
        assert MRSignal is not None
        assert MRSignalType is not None

    def test_bridge_exports_mdamr_strategy(self):
        from apps.reference.domains.decision_making.strategy_bridge import (
            MDAMRStrategyV11,
            MDAMRSignal,
        )
        assert MDAMRStrategyV11 is not None
        assert MDAMRSignal is not None

    def test_bridge_exports_regime_mapping(self):
        from apps.reference.domains.decision_making.strategy_bridge import (
            FlatRegime,
            FlatRegimeThresholds,
            map_to_flat_regime,
            is_flat_regime,
            get_mr_parameters,
            MRParameters,
        )
        assert FlatRegime is not None
        assert MRParameters is not None


class TestNoNewStrategyFilesInFE:
    """Guard: no new strategy-domain files added to FE without explicit exemption."""

    def test_no_new_strategy_files_in_fe(self):
        """
        Checks that no new *_strategy.py or regime_* files appear in FE
        beyond the known exempted set. Forces conscious boundary decisions.
        """
        strategy_like = set()
        for p in FE_DIR.glob("*.py"):
            if "strategy" in p.name or (
                p.name.startswith("regime_") and p.name != "regime_mapping.py"
            ):
                strategy_like.add(p.name)

        # regime_mapping.py doesn't match *strategy* but is in exemption
        for p in FE_DIR.glob("regime_*.py"):
            strategy_like.add(p.name)

        unexpected = strategy_like - FE_STRATEGY_FILES_EXEMPTION
        assert not unexpected, (
            f"New strategy-domain files found in feature_engineering/ "
            f"without exemption: {sorted(unexpected)}. "
            f"Either move to decision_making or add to FE_STRATEGY_FILES_EXEMPTION."
        )
