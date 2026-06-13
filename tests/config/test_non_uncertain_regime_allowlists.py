from pathlib import Path

from apps.reference.config_loader import ConfigLoader


def test_active_assigned_symbols_match_live_non_uncertain_allowlists() -> None:
    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()
    # Phase 10.1: Only 6 canonical RegimeLabel values emitted by detector.
    # FLAT_LOW/FLAT_NORMAL/FLAT_HIGH are internal to mean_reversion strategy
    # and never emitted by RegimeDetector — they were phantom entries.
    all_regimes = {
        "TREND_UP", "TREND_DOWN", "LOW_VOLATILITY", "HIGH_VOLATILITY",
        "MEAN_REVERSION", "UNCERTAIN"
    }
    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "BNBUSDT", "1000PEPEUSDT"]:
        actual = set(
            cfg.strategies.aurora.assets[symbol].allowed_regimes or [])
        assert actual == all_regimes

    if cfg.strategies.md_amr is not None:
        md_amr_expected = {
            "XRPUSDT": {"MEAN_REVERSION", "TREND_DOWN"},
        }
        for symbol, expected in md_amr_expected.items():
            actual = set(
                cfg.strategies.md_amr.assets[symbol].allowed_regimes or [])
            assert actual == expected
            assert "UNCERTAIN" not in actual
