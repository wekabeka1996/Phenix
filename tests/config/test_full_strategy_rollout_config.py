from pathlib import Path

from apps.reference.config_loader import ConfigLoader


def test_full_strategy_rollout_config_loads() -> None:
    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()

    expected_symbols = [
        "1000PEPEUSDT",
        "BNBUSDT",
        "BTCUSDT",
        "DOGEUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "XRPUSDT",
    ]
    expected_strategies = {
        "aurora",
        "mean_reversion",
        "md_amr",
        "llm_microstructure",
    }
    full_regimes = {
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "TREND_UP",
        "TREND_DOWN",
        "MEAN_REVERSION",
        "UNCERTAIN",
        "FLAT_LOW",
        "FLAT_NORMAL",
        "FLAT_HIGH",
    }
    mr_regimes = {
        "FLAT_LOW",
        "FLAT_NORMAL",
        "FLAT_HIGH",
        "MEAN_REVERSION",
    }

    assert sorted(cfg.strategies_registry.assignments.keys()) == expected_symbols
    assert cfg.trading.symbols_to_track == expected_symbols

    for symbol in expected_symbols:
        assert set(cfg.strategies_registry.assignments[symbol]) == expected_strategies

        aurora_asset = cfg.strategies.aurora.assets[symbol]
        assert aurora_asset.enabled is True
        assert aurora_asset.position_mode == "DYNAMIC"
        assert set(aurora_asset.allowed_regimes or []) == full_regimes

        mr_asset = cfg.strategies.mean_reversion.assets[symbol]
        assert mr_asset.enabled is True
        assert mr_asset.position_mode == "DYNAMIC"
        assert set(mr_asset.allowed_regimes) == mr_regimes

        md_asset = cfg.strategies.md_amr.assets[symbol]
        assert md_asset.enabled is True
        assert md_asset.position_mode == "DYNAMIC"
        assert set(md_asset.allowed_regimes or []) == full_regimes

    assert cfg.domains.decision_making.directional_sanity.enabled is False
    assert cfg.domains.decision_making.directional_sanity.min_regime_confidence == 0.0
    assert cfg.domains.decision_making.price_motion_sanity.enabled is False
    assert set(cfg.trading.llm_orchestration.symbols_llm) == set(expected_symbols)
    assert set(cfg.trading.llm_orchestration.allowlist_symbols) == set(expected_symbols)