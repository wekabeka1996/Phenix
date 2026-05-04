from __future__ import annotations

import yaml

from apps.reference.config_loader import get_config


def test_execution_cooldown_after_close_is_loaded_from_trading_yaml() -> None:
    with open("config/aurora/trading.yaml", "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    expected = raw["trading"]["execution"]["cooldown_after_close_ms"]
    cfg = get_config()

    assert cfg.trading.execution is not None
    assert cfg.trading.execution.cooldown_after_close_ms == expected

