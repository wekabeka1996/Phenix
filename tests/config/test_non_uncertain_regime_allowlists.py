from pathlib import Path

from apps.reference.config_loader import ConfigLoader


def test_active_assigned_symbols_allow_all_non_uncertain_structural_regimes() -> None:
    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
    # P1.5 experiment: LOW_VOLATILITY intentionally removed from Aurora symbols (BTC/ETH/SOL)
    aurora_expected = {
        "TREND_UP",
        "TREND_DOWN",
        "MEAN_REVERSION",
        "HIGH_VOLATILITY",
    }
    md_amr_expected = {
        "TREND_UP",
        "TREND_DOWN",
        "MEAN_REVERSION",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
    }

    for symbol in ("ETHUSDT", "SOLUSDT", "BTCUSDT"):
        actual = set(
            cfg.strategies.aurora.assets[symbol].allowed_regimes or [])
        assert actual == aurora_expected
        assert "UNCERTAIN" not in actual
        assert "LOW_VOLATILITY" not in actual  # P1.5: explicitly blocked

    if cfg.strategies.md_amr is not None:
        for symbol in ("XRPUSDT", "BNBUSDT"):
            actual = set(
                cfg.strategies.md_amr.assets[symbol].allowed_regimes or [])
            assert actual == md_amr_expected
            assert "UNCERTAIN" not in actual
