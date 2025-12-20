from apps.reference.config_loader import ConfigLoader


def test_hybrid_mode_config_contract_mapping_and_credentials_present() -> None:
    cfg = ConfigLoader().load_config()

    assert cfg.trading_mode == "hybrid_live_data_testnet_exec"

    dc = cfg.trading.domain_configuration
    assert dc.market_data.trading_mode == "live"
    assert dc.feature_engineering.trading_mode == "live"
    assert dc.decision_making.trading_mode == "live"
    assert dc.risk_management.trading_mode == "testnet"
    assert dc.execution_position.trading_mode == "testnet"

    assert cfg.domains.decision_making.arming.require_regime_warmup is True

    # Hybrid execution requires testnet API creds to be present and resolved (no ${VAR} placeholders).
    testnet = cfg.binance_api.testnet
    assert testnet.api_key and "${" not in testnet.api_key
    assert testnet.api_secret and "${" not in testnet.api_secret
    assert testnet.rest_url and "${" not in testnet.rest_url
