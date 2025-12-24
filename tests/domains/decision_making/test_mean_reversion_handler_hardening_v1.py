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
    MRRiskConfig,
    MRStrategyParamsConfig,
    MeanReversion1mStrategyConfig,
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
                risk=None,
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
                position_mode="STRICT",
            )
        },
        regime_sizing={"FLAT_NORMAL": MRRegimeSizingConfig(sizing_mult=1.0, stop_mult=1.0, target_mult=1.0)},
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
        risk=MRRiskConfig(
            position_size_usd=100.0,
            max_concurrent_positions=1,
            daily_loss_limit_usd=10_000.0,
            expected_pnl_multiplier=1.0,
            fees_pct=0.0,
            slippage_pct=0.0,
        ),
        emit_trade_intent_directly=False,
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


def test_tick_drops_invalid_price_and_does_not_call_on_tick(monkeypatch):
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, enabled=True, asset_enabled=True)),
    )

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    handler = MeanReversionHandler(fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]
    handler._strategies[symbol] = SimpleNamespace(get_state=lambda _s: None)

    on_tick = SimpleNamespace(calls=0)

    def _spy_on_tick(*_a, **_k):
        on_tick.calls += 1
        return None

    handler.on_tick = _spy_on_tick  # type: ignore[assignment]

    handler._on_market_tick(
        SimpleNamespace(
            pld={
                "symbol": symbol,
                "price": "0",
                "buy_volume": "1",
                "sell_volume": "0",
                "ts": now_ms,
            }
        )
    )

    assert handler._stats["ticks_dropped_invalid_price"] == 1
    assert on_tick.calls == 0


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


def test_tick_drops_missing_ts_and_does_not_call_on_tick(monkeypatch):
    symbol = "BTCUSDT"
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, enabled=True, asset_enabled=True)),
    )

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    handler = MeanReversionHandler(fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]
    handler._strategies[symbol] = SimpleNamespace(get_state=lambda _s: None)

    on_tick = SimpleNamespace(calls=0)

    def _spy_on_tick(*_a, **_k):
        on_tick.calls += 1
        return None

    handler.on_tick = _spy_on_tick  # type: ignore[assignment]

    handler._on_market_tick(
        SimpleNamespace(
            pld={
                "symbol": symbol,
                "price": "100",
                "volume": "1",
                "ts": "0",
            }
        )
    )

    assert handler._stats["ticks_dropped_missing_ts"] == 1
    assert on_tick.calls == 0


def test_out_of_order_tick_dropped_and_counter_incremented(monkeypatch):
    symbol = "BTCUSDT"
    base_ms = int(time.time() * 1000)
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, enabled=True, asset_enabled=True)),
    )

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    handler = MeanReversionHandler(fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]
    handler._strategies[symbol] = SimpleNamespace(get_state=lambda _s: None)
    handler.on_tick = lambda *_a, **_k: None  # type: ignore[assignment]

    handler._on_market_tick(SimpleNamespace(pld={"symbol": symbol, "price": "100", "volume": "1", "ts": base_ms}))
    handler._on_market_tick(SimpleNamespace(pld={"symbol": symbol, "price": "100", "volume": "1", "ts": base_ms - 1}))

    assert handler._stats["ticks_dropped_out_of_order"] == 1


@dataclass
class _Bar:
    start_ts_ms: int
    end_ts_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    trade_count: int


@dataclass
class _State:
    bars: list[_Bar]
    bb: object | None = None
    atr: object | None = None
    rsi: object | None = None


@dataclass
class _SignalType:
    name: str


@dataclass
class _Signal:
    is_signal: bool
    signal_type: _SignalType
    why: str


def test_bars_completed_counts_once_per_bar_end_ts(monkeypatch):
    symbol = "BTCUSDT"
    base_ms = int(time.time() * 1000)
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, enabled=True, asset_enabled=True)),
    )

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    handler = MeanReversionHandler(fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]

    st1 = _State(
        bars=[
            _Bar(
                start_ts_ms=base_ms,
                end_ts_ms=base_ms + 59_999,
                open=Decimal("1"),
                high=Decimal("1"),
                low=Decimal("1"),
                close=Decimal("1"),
                volume=Decimal("1"),
                trade_count=1,
            )
        ]
    )
    st2 = st1
    st3 = _State(
        bars=[
            _Bar(
                start_ts_ms=base_ms + 60_000,
                end_ts_ms=base_ms + 120_000 - 1,
                open=Decimal("1"),
                high=Decimal("1"),
                low=Decimal("1"),
                close=Decimal("1"),
                volume=Decimal("1"),
                trade_count=1,
            )
        ]
    )

    states = [st1, st2, st3]

    def _get_state(_symbol: str):
        return states.pop(0)

    handler._strategies[symbol] = SimpleNamespace(get_state=_get_state)
    handler.on_tick = lambda *_a, **_k: _Signal(is_signal=False, signal_type=_SignalType(name="NONE"), why="no")  # type: ignore[assignment]

    handler._on_market_tick(SimpleNamespace(pld={"symbol": symbol, "price": "100", "volume": "1", "ts": base_ms}))
    handler._on_market_tick(SimpleNamespace(pld={"symbol": symbol, "price": "100", "volume": "1", "ts": base_ms + 1}))
    handler._on_market_tick(SimpleNamespace(pld={"symbol": symbol, "price": "100", "volume": "1", "ts": base_ms + 60_000}))

    assert handler._stats["bars_completed"] == 2
    assert handler._stats["neutral_bars"] == 2


def test_bar_logging_exception_increments_counter_and_logs_warning(monkeypatch, caplog):
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)
    cfg = SimpleNamespace(
        strategies_registry=SimpleNamespace(assignments={symbol: ["mean_reversion"]}),
        strategies=SimpleNamespace(mean_reversion=_mk_mr_cfg(symbol=symbol, enabled=True, asset_enabled=True)),
    )

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    handler = MeanReversionHandler(fsm=_DummyFsm(), config=cfg)  # type: ignore[arg-type]

    def _boom(_symbol: str):
        raise RuntimeError("boom")

    handler._strategies[symbol] = SimpleNamespace(get_state=_boom)
    handler.on_tick = lambda *_a, **_k: _Signal(is_signal=False, signal_type=_SignalType(name="NONE"), why="no")  # type: ignore[assignment]

    with caplog.at_level(logging.WARNING):
        handler._on_market_tick(SimpleNamespace(pld={"symbol": symbol, "price": "100", "volume": "1", "ts": now_ms}))

    assert handler._stats["bar_logging_errors"] == 1
    assert any("failed to log bar state" in rec.message for rec in caplog.records)
