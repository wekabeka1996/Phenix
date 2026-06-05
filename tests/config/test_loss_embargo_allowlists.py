from pathlib import Path

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.regime_allowlist.contract import RegimeAllowlistContract


def test_forensic_loss_embargo_allowlists_from_ssot() -> None:
    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()

    assert cfg.strategies.aurora is not None

    btc = cfg.strategies.aurora.assets["BTCUSDT"]
    eth = cfg.strategies.aurora.assets["ETHUSDT"]

    assert set(btc.allowed_regimes or []) == {"HIGH_VOLATILITY"}
    assert set(eth.allowed_regimes or []) == {
        "TREND_UP",
        "TREND_DOWN",
        "HIGH_VOLATILITY",
    }
    assert "MEAN_REVERSION" not in (eth.allowed_regimes or [])

    assert RegimeAllowlistContract.is_regime_allowed(
        current_regime="HIGH_VOLATILITY",
        allowed_regimes=btc.allowed_regimes,
    )
    assert not RegimeAllowlistContract.is_regime_allowed(
        current_regime="TREND_UP",
        allowed_regimes=btc.allowed_regimes,
    )
    assert not RegimeAllowlistContract.is_regime_allowed(
        current_regime="TREND_DOWN",
        allowed_regimes=btc.allowed_regimes,
    )
    assert not RegimeAllowlistContract.is_regime_allowed(
        current_regime="MEAN_REVERSION",
        allowed_regimes=btc.allowed_regimes,
    )
    assert not RegimeAllowlistContract.is_regime_allowed(
        current_regime="MEAN_REVERSION",
        allowed_regimes=eth.allowed_regimes,
    )