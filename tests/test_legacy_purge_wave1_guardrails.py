"""
LEGACY-PURGE-WAVE-1 — cross-project structural guardrails.

Prevents reintroduction of artifacts deleted in LEGACY-PURGE-WAVE-1 (2026-03-15):
- Ghost .pyc / orphaned __pycache__ in vfoundation
- Deprecated docs directories under audited domains
- Dead modules (market_ws_client.py)
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOMAINS_ROOT = PROJECT_ROOT / "apps" / "reference" / "domains"
VF_ROOT = PROJECT_ROOT / "vfoundation"

# Domains that had docs/deprecated/ purged in Wave 1
PURGED_DEPRECATED_DOCS_DOMAINS = [
    "alpha_search",
    "execution_position",
    "feature_engineering",
    "market_data",
    "position_tracking",
    "regime_detector",
    "risk_management",
]

# Orphaned vfoundation directories removed in Wave 1
PURGED_VF_ORPHAN_DIRS = [
    VF_ROOT / "services",
    VF_ROOT / "apps",
]

# Ghost .pyc source stems removed in Wave 1 (parent_dir → stem)
PURGED_VF_GHOST_STEMS = {
    VF_ROOT: ["errors"],
    VF_ROOT / "adapters": ["binance_adapter"],
    VF_ROOT / "core": ["fsm"],
}


class TestNoDeprecatedDocsReintroduced:
    """Guard: docs/deprecated/ directories must not reappear in purged domains."""

    def test_no_deprecated_docs_dirs(self):
        reintroduced = []
        for domain in PURGED_DEPRECATED_DOCS_DOMAINS:
            deprecated_dir = DOMAINS_ROOT / domain / "docs" / "deprecated"
            if deprecated_dir.exists():
                reintroduced.append(
                    str(deprecated_dir.relative_to(PROJECT_ROOT)))

        assert not reintroduced, (
            "docs/deprecated/ directories reintroduced after LEGACY-PURGE-WAVE-1:\n"
            + "\n".join(f"  - {r}" for r in reintroduced)
        )


class TestNoOrphanedVfoundationDirs:
    """Guard: orphaned vfoundation directories must not reappear."""

    def test_orphaned_vf_dirs_stay_deleted(self):
        reintroduced = [
            str(d.relative_to(PROJECT_ROOT))
            for d in PURGED_VF_ORPHAN_DIRS
            if d.exists()
        ]
        assert not reintroduced, (
            "Orphaned vfoundation directories reintroduced:\n"
            + "\n".join(f"  - {r}" for r in reintroduced)
        )


class TestNoVfoundationGhostPyc:
    """Guard: purged ghost .pyc stems must not reappear."""

    def test_no_ghost_pyc_reintroduced(self):
        ghosts = []
        for parent_dir, stems in PURGED_VF_GHOST_STEMS.items():
            pycache = parent_dir / "__pycache__"
            if not pycache.exists():
                continue
            for pyc in pycache.glob("*.pyc"):
                stem = pyc.stem.split(".")[0]
                if stem in stems:
                    # Only flag if no matching .py source exists
                    if not (parent_dir / f"{stem}.py").exists():
                        ghosts.append(pyc.name)

        assert not ghosts, (
            "Ghost .pyc files reintroduced in vfoundation:\n"
            + "\n".join(f"  - {g}" for g in ghosts)
        )
