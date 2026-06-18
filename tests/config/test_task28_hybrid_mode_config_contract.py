import shutil
from pathlib import Path

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader


def test_hybrid_mode_config_contract_mapping_and_credentials_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)

    # Force HYBRID mode for this contract test without depending on repo-default mode.
    system_path = cfg_dir / "system.yaml"
    system = yaml.safe_load(system_path.read_text(encoding="utf-8"))
    system["trading_mode"] = "hybrid_live_data_testnet_exec"
    system_path.write_text(yaml.safe_dump(
        system, sort_keys=False), encoding="utf-8")

    # T-TMODE-SSOT-2026-05-09: trading.mode must NOT be set in trading.yaml.
    # system.yaml:trading_mode is the canonical source; loader injects trading.mode.

    # Ensure env placeholders resolve (tests must not rely on the user's environment).
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "testnet_key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "testnet_secret")
    monkeypatch.setenv("BINANCE_FUTURES_API_KEY_LIVE", "live_key")
    monkeypatch.setenv("BINANCE_FUTURES_API_SECRET_LIVE", "live_secret")
    monkeypatch.setenv("BINANCE_FUTURES_BASE_URL_LIVE",
                       "https://fapi.binance.com")

    cfg = ConfigLoader(config_dir=cfg_dir).load_config()

    assert cfg.trading_mode == "hybrid_live_data_testnet_exec"

    dc = cfg.trading.domain_configuration
    assert dc.market_data.trading_mode == "live"
    assert dc.feature_engineering.trading_mode == "live"
    assert dc.decision_making.trading_mode == "live"
    # PURGE-DIRTY-DOZEN: risk_management, execution_position trading_modes are now Optional (deprecated)
    # Global trading_mode is SSOT for these domains

    assert cfg.domains.decision_making.arming.require_regime_warmup is True

    # Hybrid execution requires testnet API creds to be present and resolved (no ${VAR} placeholders).
    testnet = cfg.binance_api.testnet
    assert testnet.api_key and "${" not in testnet.api_key
    assert testnet.api_secret and "${" not in testnet.api_secret
    assert testnet.rest_url and "${" not in testnet.rest_url


def test_hybrid_live_market_data_has_absolute_rest_url_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BINANCE_FUTURES_BASE_URL_LIVE", raising=False)

    cfg = ConfigLoader(config_dir=Path("config/aurora")).load_config()

    assert cfg.binance_api.live.rest_url == "https://fapi.binance.com"
