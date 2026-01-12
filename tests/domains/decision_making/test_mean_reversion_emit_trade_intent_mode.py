from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.reference.config_models import (
    MRAssetConfig,
    MRAssetRiskConfig,
    MRRegimeSizingConfig,
    MRRegimeThresholdsConfig,
    MRRiskConfig,
    MRStrategyParamsConfig,
    MeanReversion1mStrategyConfig,
    StrategyExecutionConfig,
)
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
from apps.reference.domains.feature_engineering.mean_reversion_strategy import MRSignal, MRSignalType


class _DummyFsm:
    def __init__(self):
        self.emitted: list[tuple[str, dict]] = []

    def emit(self, event_name: str, payload=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}))

    def listen(self, _event_name: str, _callback) -> None:
        return


def _mk_mr_cfg(
    *,
    symbol: str,
    emit_direct: bool,
    asset_risk_usd: float | None = None,
    global_risk_usd: float = 100.0,
) -> MeanReversion1mStrategyConfig:
    return MeanReversion1mStrategyConfig(
        enabled=True,
        timeframe_sec=180,
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
                enabled=True,
                strategy=None,
                risk=(MRAssetRiskConfig(position_size_usd=asset_risk_usd, max_risk_score=0.9) if asset_risk_usd is not None else None),
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
                position_mode="STRICT",
            )
        },
        regime_sizing={"FLAT_NORMAL": MRRegimeSizingConfig(sizing_mult=1.0, stop_mult=1.0, target_mult=1.0)},
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        risk=MRRiskConfig(
            position_size_usd=global_risk_usd,
            max_concurrent_positions=1,
            daily_loss_limit_usd=10_000.0,
            expected_pnl_multiplier=1.0,
            fees_pct=0.0,
            slippage_pct=0.0,
        ),
        execution=StrategyExecutionConfig(
            entry_order_type="MARKET",
            entry_tif=None,
        ),
        emit_trade_intent_directly=emit_direct,
    )


def test_mr_emit_direct_trade_intent_uses_asset_risk_position_size_usd(monkeypatch) -> None:
    symbol = "BTCUSDT"
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, emit_direct=True, asset_risk_usd=150.0, global_risk_usd=100.0)),
    )

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    fsm = _DummyFsm()
    handler = MeanReversionHandler(fsm=fsm, config=cfg)  # type: ignore[arg-type]

    signal = MRSignal(
        signal_type=MRSignalType.LONG,
        symbol=symbol,
        price=Decimal("100"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        target_price=Decimal("110"),
        confidence=Decimal("0.66"),
        timestamp_ms=1,
        why="test",
    )

    handler._emit_signal(signal)

    assert fsm.emitted, "expected an emitted event"
    evt, pld = fsm.emitted[-1]
    assert evt == "EVT:TRADE_INTENT_PROPOSED"
    assert pld["instrument"] == symbol
    assert pld["side"] == "buy"

    # qty = 150 / 100 = 1.5
    assert pld["order"]["qty"] == "1.5"
    assert pld["order"]["price"] == "100"


def test_mr_emit_direct_trade_intent_falls_back_to_global_risk_position_size_usd(monkeypatch) -> None:
    symbol = "BTCUSDT"
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, emit_direct=True, asset_risk_usd=None, global_risk_usd=200.0)),
    )

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    fsm = _DummyFsm()
    handler = MeanReversionHandler(fsm=fsm, config=cfg)  # type: ignore[arg-type]

    signal = MRSignal(
        signal_type=MRSignalType.SHORT,
        symbol=symbol,
        price=Decimal("50"),
        entry_price=Decimal("50"),
        stop_price=Decimal("55"),
        target_price=Decimal("45"),
        confidence=Decimal("0.5"),
        timestamp_ms=1,
        why="test",
    )

    handler._emit_signal(signal)

    evt, pld = fsm.emitted[-1]
    assert evt == "EVT:TRADE_INTENT_PROPOSED"
    assert pld["side"] == "sell"
    # qty = 200 / 50 = 4
    assert Decimal(pld["order"]["qty"]) == Decimal("4")


def test_mr_emit_direct_forbidden_for_hybrid_assignments(monkeypatch) -> None:
    symbol = "BTCUSDT"
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["aurora", "mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, emit_direct=True)),
    )

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)

    with pytest.raises(ValueError) as exc:
        MeanReversionHandler(fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]

    assert "hybrid" in str(exc.value).lower() or "forbidden" in str(exc.value).lower()


def test_mr_emit_signal_gateway_when_direct_disabled(monkeypatch) -> None:
    symbol = "BTCUSDT"
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, emit_direct=False)),
    )

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    fsm = _DummyFsm()
    handler = MeanReversionHandler(fsm=fsm, config=cfg)  # type: ignore[arg-type]

    signal = MRSignal(
        signal_type=MRSignalType.LONG,
        symbol=symbol,
        price=Decimal("100"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        target_price=Decimal("110"),
        confidence=Decimal("0.66"),
        timestamp_ms=1,
        why="test",
    )

    handler._emit_signal(signal)

    evt, _pld = fsm.emitted[-1]
    assert evt == "EVT:STRATEGY_SIGNAL_PRODUCED"
