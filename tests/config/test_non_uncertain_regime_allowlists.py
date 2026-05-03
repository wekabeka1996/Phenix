from pathlib import Path

from apps.reference.config_loader import ConfigLoader


def test_active_assigned_symbols_match_live_non_uncertain_allowlists() -> None:
    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
    aurora_expected = {
        "ETHUSDT": {"TREND_UP", "TREND_DOWN", "LOW_VOLATILITY"},
        "SOLUSDT": {"TREND_UP", "TREND_DOWN", "LOW_VOLATILITY", "MEAN_REVERSION", "HIGH_VOLATILITY"},
        "BTCUSDT": {"TREND_UP", "TREND_DOWN", "LOW_VOLATILITY", "MEAN_REVERSION", "HIGH_VOLATILITY"},
        "BNBUSDT": {"TREND_UP", "TREND_DOWN", "MEAN_REVERSION", "HIGH_VOLATILITY"},
        "XRPUSDT": {"TREND_UP", "TREND_DOWN", "MEAN_REVERSION", "HIGH_VOLATILITY", "LOW_VOLATILITY"},
    }
    low_vol_expected = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}
    for symbol, expected in aurora_expected.items():
        actual = set(
            cfg.strategies.aurora.assets[symbol].allowed_regimes or [])
        assert actual == expected
        assert "UNCERTAIN" not in actual
        if symbol in low_vol_expected:
            assert "LOW_VOLATILITY" in actual
        else:
            assert "LOW_VOLATILITY" not in actual

    if cfg.strategies.md_amr is not None:
        md_amr_expected = {
            "XRPUSDT": {"MEAN_REVERSION", "TREND_DOWN"},
        }
        for symbol, expected in md_amr_expected.items():
            actual = set(
                cfg.strategies.md_amr.assets[symbol].allowed_regimes or [])
            assert actual == expected
            assert "UNCERTAIN" not in actual
