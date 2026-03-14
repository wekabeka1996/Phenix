"""
CFG-NAMESPACE-SSOT-01 — Config namespace SSOT regression guard.

Enforces:
- Default ConfigLoader resolves to config/aurora (the canonical SSOT directory)
- Dead config trees (aurora_baseline, mean_reversion) do not exist under config/
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


class TestConfigNamespaceSSOT:
    """Guard: config/ contains only active runtime config, no dead trees."""

    def test_default_config_dir_is_aurora(self):
        """ConfigLoader default must resolve to config/aurora."""
        from apps.reference.config_loader import ConfigLoader

        loader = ConfigLoader()
        resolved = Path(loader.config_dir).resolve()
        assert resolved.name == "aurora", (
            f"Default config dir resolved to '{resolved.name}', expected 'aurora'"
        )

    def test_no_dead_config_trees_under_config(self):
        """Archived config trees must not exist under config/."""
        dead_trees = ["aurora_baseline", "mean_reversion"]
        for name in dead_trees:
            dead_path = CONFIG_DIR / name
            assert not dead_path.exists(), (
                f"Dead config tree '{name}' still exists under config/. "
                f"It should be in archive/config_snapshots/."
            )

    def test_active_aurora_dir_exists(self):
        """The canonical SSOT directory must exist."""
        assert (CONFIG_DIR / "aurora").is_dir(), (
            "config/aurora/ does not exist — SSOT directory is missing"
        )
