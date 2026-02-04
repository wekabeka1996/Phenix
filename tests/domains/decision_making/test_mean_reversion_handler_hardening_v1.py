import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.reference.config_models import (
    MRAssetConfig,
    MRRegimeSizingConfig,
    MRRegimeThresholdsConfig,
    MRStrategyParamsConfig,
    MeanReversion1mStrategyConfig,
    StrategyExecutionConfig,
)
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler, normalize_ts_ms


class _DummyFsm:
    def __init__(self):
        self.emitted: list[tuple[str, dict]] = []

    def emit(self, event_name: str, payload=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}))

    def listen(self, _event_name: str, _callback) -> None:
        return


def _mk_mr_cfg(*, symbol: str, enabled: bool, asset_enabled: bool = True) -> MeanReversion1mStrategyConfig:
    return MeanReversion1mStrategyConfig(
        enabled=enabled,
        timeframe_sec=60,
        strategy=MRStrategyParamsConfig(
            bb_window=3,
            bb_num_std=2.0,
            atr_window=14,
            rsi_window=14,
            entry_threshold=0.2,
            rsi_oversold=30.0,
            rsi_overbought=70.0,
            min_bars=3,
            min_bb_width=0.0001,
            max_bb_width=10.0,
            sl_atr_mult=1.5,
            tp_to_mid=True,
            cooldown_sec=0,
        ),
        regime_thresholds=MRRegimeThresholdsConfig(high_vol_pct=0.003, low_vol_pct=0.001),
        assets={
            symbol: MRAssetConfig(
                enabled=asset_enabled,
                strategy=None,
                
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
                position_mode="STRICT",
            )
        },
        regime_sizing={"FLAT_NORMAL": MRRegimeSizingConfig(sizing_mult=1.0, stop_mult=1.0, target_mult=1.0)},
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        execution=StrategyExecutionConfig(
            entry_order_type="MARKET",
            entry_tif=None,
        ),
        safety_gates={"enabled": False},  # Fixture fix: disable safety gates
    )


def test_mr_activation_assigned_enabled_true_ok(monkeypatch):
    symbol = "BTCUSDT"
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, enabled=True, asset_enabled=True)),
    )

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    handler = MeanReversionHandler(fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]

    assert handler.enabled is True
    assert handler.is_symbol_enabled(symbol) is True


def test_mr_activation_assigned_enabled_false_raises():
    symbol = "BTCUSDT"
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, enabled=False, asset_enabled=True)),
    )

    with pytest.raises(ValueError):
        MeanReversionHandler(fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]


def test_mr_no_assignments_enabled_true_stays_disabled(monkeypatch):
    symbol = "BTCUSDT"
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, enabled=True, asset_enabled=True)),
    )

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    handler = MeanReversionHandler(fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]

    assert handler.enabled is False
    assert handler.is_symbol_enabled(symbol) is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 0),
        ("", 0),
        ("0", 0),
        (0, 0),
        (-1, 0),
        ("1700000000", 1_700_000_000_000),
        (1_700_000_000, 1_700_000_000_000),
        (1_700_000_000_000, 1_700_000_000_000),
    ],
)
def test_normalize_ts_ms_best_effort(raw, expected):
    assert normalize_ts_ms(raw) == expected
