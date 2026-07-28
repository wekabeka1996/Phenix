from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.reference.config.testnet_proof import (
    P46TestnetProofConfig,
    load_p46_testnet_proof_config,
)
from scripts.p46_1g_testnet_preflight import run_read_only_preflight


CONFIG = Path("config/aurora/p46_1g_testnet_proof.yaml")


def test_real_proof_config_is_strict_and_bounded() -> None:
    config = load_p46_testnet_proof_config(CONFIG)
    assert str(config.exposure.target_notional_quote) == "10.0"
    assert str(config.exposure.operator_max_notional_quote) == "20.0"
    assert config.endpoint == "https://testnet.binancefuture.com"
    assert len(config.symbol_selection.allowed_symbols) == 6


def test_mainnet_endpoint_and_unknown_fields_fail() -> None:
    raw = load_p46_testnet_proof_config(CONFIG).model_dump(mode="python")
    raw["endpoint"] = "https://fapi.binance.com"
    with pytest.raises(ValidationError):
        P46TestnetProofConfig.model_validate(raw)

    raw = load_p46_testnet_proof_config(CONFIG).model_dump(mode="python")
    raw["hidden_default"] = True
    with pytest.raises(ValidationError):
        P46TestnetProofConfig.model_validate(raw)


def test_exposure_and_cleanup_fail_closed() -> None:
    raw = load_p46_testnet_proof_config(CONFIG).model_dump(mode="python")
    raw["exposure"]["target_notional_quote"] = "21"
    with pytest.raises(ValidationError):
        P46TestnetProofConfig.model_validate(raw)

    raw = load_p46_testnet_proof_config(CONFIG).model_dump(mode="python")
    raw["cleanup"]["require_final_flat"] = False
    with pytest.raises(ValidationError):
        P46TestnetProofConfig.model_validate(raw)


def test_missing_credentials_blocks_before_adapter_or_network() -> None:
    config = load_p46_testnet_proof_config(CONFIG)
    result = run_read_only_preflight(config, {})
    assert result.allowed is False
    assert result.verdict == "CREDENTIALS_UNAVAILABLE"
    assert result.reason_code == "CREDENTIALS_MISSING"
    assert result.adapter_created is False
    assert result.network_calls == 0
    assert result.key_fingerprint is None


def test_live_credentials_in_proof_environment_block() -> None:
    config = load_p46_testnet_proof_config(CONFIG)
    result = run_read_only_preflight(
        config,
        {
            "BINANCE_TESTNET_API_KEY": "test-key",
            "BINANCE_TESTNET_API_SECRET": "test-secret",
            "BINANCE_FUTURES_API_KEY_LIVE": "live-key",
        },
    )
    assert result.allowed is False
    assert result.verdict == "FAIL"
    assert result.reason_code == "LIVE_CREDENTIALS_PRESENT_IN_PROOF_ENV"
    assert result.adapter_created is False
    assert result.network_calls == 0


def test_runtime_not_ready_fails_closed() -> None:
    config = load_p46_testnet_proof_config(CONFIG)
    result = run_read_only_preflight(
        config,
        {
            "BINANCE_TESTNET_API_KEY": "test-key",
            "BINANCE_TESTNET_API_SECRET": "test-secret",
        },
        async_loop_ready=False,
    )
    assert result.allowed is False
    assert result.verdict == "FAIL"
    assert result.reason_code == "TESTNET_PREFLIGHT_RUNTIME_NOT_READY"


def test_unexpectedly_armed_fails_closed() -> None:
    config = load_p46_testnet_proof_config(CONFIG)
    result = run_read_only_preflight(
        config,
        {
            "BINANCE_TESTNET_API_KEY": "test-key",
            "BINANCE_TESTNET_API_SECRET": "test-secret",
        },
        armed=True,
    )
    assert result.allowed is False
    assert result.verdict == "FAIL"
    assert result.reason_code == "UNEXPECTEDLY_ARMED"


def test_no_write_proof_zero_writes_zero_orders() -> None:
    config = load_p46_testnet_proof_config(CONFIG)
    result = run_read_only_preflight(
        config,
        {
            "BINANCE_TESTNET_API_KEY": "test-key",
            "BINANCE_TESTNET_API_SECRET": "test-secret",
        },
    )
    assert result.writes_performed == 0
    assert result.orders_created == 0
    assert result.armed is False
