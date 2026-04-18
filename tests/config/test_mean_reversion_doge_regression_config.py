from __future__ import annotations

from pathlib import Path

from apps.reference.config_loader import ConfigLoader


def test_mean_reversion_live_loaded_when_assigned() -> None:
    config = ConfigLoader(Path("config/aurora")).load_config()

    assert config.strategies.mean_reversion is not None
    assert config.strategies_registry.assignments["DOGEUSDT"] == [
        "aurora",
        "mean_reversion",
    ]
    assert config.strategies.mean_reversion.assets["DOGEUSDT"].enabled is True
