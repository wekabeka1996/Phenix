import os
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader


def _write_yaml(path: Path, obj) -> None:  # type: ignore[no-untyped-def]
    path.write_text(yaml.safe_dump(obj, sort_keys=False), encoding="utf-8")


def test_trading_config_typos_fail_validation(tmp_path: Path) -> None:
    config_dir = tmp_path / "config" / "aurora"
    config_dir.mkdir(parents=True)

    _write_yaml(
        config_dir / "system.yaml",
        {
            "trading_mode": "testnet",
            "bridge": {"retry_scheduler": {"max_attempts": 5, "min_retry_delay_ms": 500}},
        },
    )
    _write_yaml(
        config_dir / "domains.yaml",
        {"decision_making": {"position_sizing": {"min_position_size_usd": 10}}},
    )
    _write_yaml(
        config_dir / "instruments.yaml",
        {"instruments": {"BTCUSDT": {"tick_size": "0.01", "step_size": "0.00001"}}},
    )
    _write_yaml(config_dir / "aurora_instruments.yaml", {"aurora_instruments": {"BTCUSDT": {}}})
    _write_yaml(
        config_dir / "strategies.yaml",
        {"assignments": {}, "arbitration": {"mode": "priority", "priority": {}}},
    )
    _write_yaml(
        config_dir / "regime.yaml",
        {"models": {"sma_trend": {}, "volatility": {}, "mean_reversion": {}}, "hmm": {"enabled": False}},
    )

    # trading.yaml with a typo at trading-level key: "levrage" (should be rejected by extra='forbid')
    _write_yaml(
        config_dir / "trading.yaml",
        {
            "binance_api": {
                "testnet": {"api_key": "x", "api_secret": "y", "rest_url": "https://test"},
                "live": {"api_key": "x", "api_secret": "y", "rest_url": "https://live"},
            },
            "trading": {
                "mode": "testnet",
                "decision": {"signal_threshold": 0.1, "symbols_to_track": ["BTCUSDT"]},
                "risk_management": {"data_sources": {"portfolio_state": "testnet", "market_data": "live"}},
                "levrage": 10,
            },
        },
    )

    os.environ.pop("STRICT_CONFIG_CONFLICTS", None)
    loader = ConfigLoader(config_dir=config_dir)
    with pytest.raises(ValidationError):
        loader.load_config()

