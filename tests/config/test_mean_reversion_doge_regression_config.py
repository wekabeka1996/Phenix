from __future__ import annotations

from pathlib import Path

from apps.reference.config_loader import ConfigLoader


def test_mean_reversion_profile_keeps_doge_asset_after_registry_cut() -> None:
    config = ConfigLoader(Path("config/aurora")).load_config()

    if "DOGEUSDT" in config.strategies_registry.assignments:
        del config.strategies_registry.assignments["DOGEUSDT"]

    assert config.strategies.mean_reversion is not None
    assert "DOGEUSDT" not in config.strategies_registry.assignments
    assert config.strategies.mean_reversion.assets["DOGEUSDT"].enabled is True
