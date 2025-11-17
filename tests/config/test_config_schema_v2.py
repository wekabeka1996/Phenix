from apps.reference.config_models import AuroraConfig, ConfigV2


def test_pydantic_config_models_match_v2_structure():
    """Verify AuroraConfig can encode a minimal config v2 payload."""
    required_domains = [
        "execution",
        "risk",
        "decision",
        "sizing",
        "features",
        "regimes",
    ]
    sample_domains = {name: {"note": "dummy"} for name in required_domains}
    config_v2 = ConfigV2(
        core={"logging": {"level": "DEBUG"}},
        symbols={"BTCUSDT": {"source": "test"}},
        instruments={"BTCUSDT": {"min_qty": 0.001}},
        overrides={"symbols": {"BTCUSDT": {"limits": {"max_leverage": 10}}}},
        modes={"profiles": {"test_profile": {"trading_mode": "testnet", "domains": {}}}},
        domains=sample_domains,
    )

    validated = AuroraConfig(config_v2=config_v2)

    assert validated.config_v2 is not None
    assert set(validated.config_v2.domains.keys()) == set(sample_domains.keys())
