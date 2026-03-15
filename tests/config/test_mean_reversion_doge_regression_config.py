from __future__ import annotations

from pathlib import Path

from apps.reference.config_loader import ConfigLoader


def test_mean_reversion_doge_uses_last_known_healthy_300s_profile() -> None:
    config = ConfigLoader(Path("config/aurora")).load_config()
    doge = config.strategies.mean_reversion.assets["DOGEUSDT"].strategy

    assert config.strategies.mean_reversion.timeframe_sec == 300
    assert doge.bb_window == 20
    assert doge.bb_num_std == 2.1
    assert doge.min_bb_width == 0.005
    assert doge.entry_threshold == 0.05
    assert doge.cooldown_sec == 210
    assert doge.flat_low_short_min_bb_width is None
    assert doge.squeeze_expansion_veto is None
    assert doge.momentum_separation_veto is None
