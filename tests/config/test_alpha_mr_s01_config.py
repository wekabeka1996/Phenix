from __future__ import annotations

from pathlib import Path

from apps.reference.config_loader import ConfigLoader


def test_alpha_mr_s01_profile_loads_as_testnet_candidate():
    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
    assert cfg.strategies.alpha_mr_s01 is not None
    assert cfg.strategies.alpha_mr_s01.mode == "testnet_candidate"
    assert cfg.strategies.alpha_mr_s01.enabled is True
    assert cfg.strategies.alpha_mr_s01.weights.rsi == 0.55
