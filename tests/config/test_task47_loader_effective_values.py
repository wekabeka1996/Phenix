from pathlib import Path

from apps.reference.config_loader import ConfigLoader


def test_task47_loader_effective_values_from_ssot() -> None:
    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()

    # SSOT: position_tracking.positions_stale_ttl_sec must come from domains.yaml only.
    assert cfg.domains.position_tracking.positions_stale_ttl_sec == 15

    # SSOT: trading.market_data.websocket_streams must come from trading.yaml only.
    assert cfg.trading.market_data is not None
    assert cfg.trading.market_data.websocket_streams == ["bookTicker", "trade"]

    # MR threshold tuning (Aurora mean-reversion regime threshold lowered for BTC).
    assert cfg.strategies.aurora is not None
    btc = cfg.strategies.aurora.assets["BTCUSDT"]
    assert btc.regime_thresholds is not None
    assert btc.regime_thresholds["MEAN_REVERSION"] == 0.5
    assert "MEAN_REVERSION" in (btc.allowed_regimes or [])

    # BTC must have 2 strategies assigned (aurora + mean_reversion).
    assert cfg.strategies_registry is not None
    assert set(cfg.strategies_registry.assignments["BTCUSDT"]) == {"aurora", "mean_reversion"}
