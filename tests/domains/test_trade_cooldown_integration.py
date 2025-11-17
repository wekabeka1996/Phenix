"""Tests for trade cooldown resolution in execution_position domain."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.reference.config_loader import AuroraConfig
from apps.reference.domains.execution_position import fsm as exec_fsm_module
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.utils.trade_cooldowns import get_trade_cooldown_sec_for_symbol


@pytest.fixture(autouse=True)
def disable_cleanup_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable async cleanup scheduling to avoid un-awaited coroutine warnings."""

    monkeypatch.setattr(
        exec_fsm_module.ExecPosFSM,
        "_schedule_fsm_cleanup_loop",
        lambda self: None,
    )


def _make_config(symbol: str, instrument_overrides: dict, execution_overrides: dict | None = None) -> AuroraConfig:
    execution_cfg = {
        "cooldown_ms": 1000,
        "guard_enabled": True,
        "exposure": {
            "max_portfolio_fraction": "0.20",
        },
    }
    if execution_overrides:
        execution_cfg.update(execution_overrides)

    instrument_cfg = {
        symbol: {
            "symbol": symbol,
            **instrument_overrides,
        }
    }

    config_dict = {
        "trading_mode": "testnet",
        "trading": {
            "mode": "testnet",
            "execution": execution_cfg,
            "instruments": instrument_cfg,
        },
    }
    return AuroraConfig.model_validate(config_dict)


@pytest.mark.parametrize(
    "symbol,instrument_overrides,expected",
    [
        ("BTCUSDT", {"trade_cooldown_sec": 7.5}, 7.5),
        ("ETHUSDT", {"cooldown_sec": 4}, 4.0),
        ("SOLUSDT", {"trade_cooldown_sec": 9, "cooldown_sec": 1}, 9.0),
    ],
)
def test_exec_pos_fsm_uses_trade_cooldown(symbol: str, instrument_overrides: dict, expected: float) -> None:
    config = _make_config(symbol, instrument_overrides)
    fsm = ExecPosFSM(config=config, fsm=MagicMock())

    open_flow, _, _ = fsm._get_or_create_flows(symbol)

    assert open_flow.cooldown_sec == pytest.approx(expected)


def test_exec_pos_fsm_falls_back_to_execution_cooldown_ms() -> None:
    symbol = "XRPUSDT"
    config = _make_config(symbol, {}, execution_overrides={
                          "cooldown_ms": 2500})
    fsm = ExecPosFSM(config=config, fsm=MagicMock())

    open_flow, _, _ = fsm._get_or_create_flows(symbol)

    assert open_flow.cooldown_sec == pytest.approx(2.5)


def test_exec_pos_fsm_handles_zero_cooldown_when_not_configured() -> None:
    symbol = "ADAUSDT"
    config = _make_config(symbol, {}, execution_overrides={"cooldown_ms": 0})
    fsm = ExecPosFSM(config=config, fsm=MagicMock())

    open_flow, _, _ = fsm._get_or_create_flows(symbol)

    assert open_flow.cooldown_sec == pytest.approx(0.0)


def test_get_trade_cooldown_uses_default_entry() -> None:
    config_dict = {
        "trading": {
            "instruments": {
                "__default__": {
                    "symbol": "__DEFAULT__",
                    "trade_cooldown_sec": 11,
                }
            }
        }
    }

    assert get_trade_cooldown_sec_for_symbol(
        config_dict, "DOTUSDT") == pytest.approx(11.0)


def test_get_trade_cooldown_returns_zero_when_unset() -> None:
    config_dict = {
        "trading": {
            "instruments": {
                "LTCUSDT": {
                    "symbol": "LTCUSDT",
                }
            }
        }
    }

    assert get_trade_cooldown_sec_for_symbol(config_dict, "LTCUSDT") == 0.0
