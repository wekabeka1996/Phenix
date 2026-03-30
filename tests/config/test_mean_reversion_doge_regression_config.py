from __future__ import annotations

from pathlib import Path

from apps.reference.config_loader import ConfigLoader


def test_mean_reversion_not_live_loaded_when_unassigned() -> None:
    config = ConfigLoader(Path("config/aurora")).load_config()

    assert "DOGEUSDT" not in config.strategies_registry.assignments
    assert getattr(config.strategies, "mean_reversion", None) is None
