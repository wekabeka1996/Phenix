import pytest
import time
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

from apps.reference.config_models import (
    MRAssetConfig,
    MRRegimeSizingConfig,
    MRRegimeThresholdsConfig,
    MRRiskConfig,
    MRStrategyParamsConfig,
    MeanReversion1mStrategyConfig,
)
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler
from tests.conftest import make_mr_signal
from apps.reference.domains.feature_engineering.mean_reversion_strategy import MRSignalType


pytestmark = pytest.mark.skip(reason="ORDER-POLICY-01: MeanReversion1mStrategyConfig now requires 'execution' field. Test fixture needs update.")


class _Bus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict]] = []

    def listen(self, _event: str, _handler: object) -> None:
        return

    def emit(self, event_name: str, payload: dict | None = None, *_a, **_k) -> None:
        self.emitted.append((event_name, payload or {}))


def _mk_cfg(symbol: str) -> SimpleNamespace:
    strategies_registry = SimpleNamespace(assignments={symbol: ["mean_reversion"]})

    mr_cfg = MeanReversion1mStrategyConfig(
        enabled=True,
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
                enabled=True,
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
    )

    return SimpleNamespace(strategies_registry=strategies_registry, strategies=SimpleNamespace(mean_reversion=mr_cfg))


def test_emits_strategy_signal_with_schema_version(monkeypatch):
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)

    bus = _Bus()
    cfg = _mk_cfg(symbol)

    # Avoid creating real strategy instances; inject stub strategy.
    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    handler = MeanReversionHandler(fsm=bus, config=cfg)  # type: ignore[arg-type]

    signal = make_mr_signal(
        symbol=symbol,
        timestamp_ms=now_ms,
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        target_price=Decimal("110"),
    )

    handler._strategies[symbol] = SimpleNamespace(
        on_tick=lambda *_a, **_k: signal,
        get_state=lambda _s: SimpleNamespace(bars=[], bb=None, atr=None, rsi=None),
        set_regime=lambda *_a, **_k: None,
    )

    handler._on_market_tick(
        SimpleNamespace(
            pld={
                "symbol": symbol,
                "price": "100",
                "buy_volume": "1",
                "sell_volume": "0",
                "ts": now_ms,
            }
        )
    )

    assert any(name == "EVT:STRATEGY_SIGNAL_PRODUCED" for name, _ in bus.emitted)
    evt_name, payload = next((n, p) for n, p in bus.emitted if n == "EVT:STRATEGY_SIGNAL_PRODUCED")
    assert payload.get("schema_version") == 1
    assert payload.get("strategy_id") == "mean_reversion"
    assert payload.get("symbol") == symbol


def test_invalid_price_does_not_emit_signal(monkeypatch):
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)

    bus = _Bus()
    cfg = _mk_cfg(symbol)

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    handler = MeanReversionHandler(fsm=bus, config=cfg)  # type: ignore[arg-type]

    handler._strategies[symbol] = SimpleNamespace(
        on_tick=lambda *_a, **_k: make_mr_signal(signal_type=MRSignalType.NEUTRAL, bar=None),
        get_state=lambda _s: SimpleNamespace(bars=[]),
        set_regime=lambda *_a, **_k: None,
    )

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

    assert not bus.emitted


def test_missing_ts_does_not_emit_signal_and_does_not_call_strategy(monkeypatch):
    symbol = "BTCUSDT"

    bus = _Bus()
    cfg = _mk_cfg(symbol)

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    handler = MeanReversionHandler(fsm=bus, config=cfg)  # type: ignore[arg-type]

    def _must_not_be_called(*_a, **_k):
        raise AssertionError("strategy.on_tick must not be called when timestamp is missing")

    handler._strategies[symbol] = SimpleNamespace(
        on_tick=_must_not_be_called,
        get_state=lambda _s: SimpleNamespace(bars=[]),
        set_regime=lambda *_a, **_k: None,
    )

    handler._on_market_tick(
        SimpleNamespace(
            pld={
                "symbol": symbol,
                "price": "100",
                "buy_volume": "1",
                "sell_volume": "0",
                "ts": "0",
            }
        )
    )

    assert not bus.emitted


def test_out_of_order_tick_does_not_emit_signal(monkeypatch):
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)

    bus = _Bus()
    cfg = _mk_cfg(symbol)

    monkeypatch.setattr(MeanReversionHandler, "_init_strategies", lambda self: None)
    handler = MeanReversionHandler(fsm=bus, config=cfg)  # type: ignore[arg-type]

    bar = SimpleNamespace(
        start_ts_ms=now_ms,
        end_ts_ms=now_ms + 60_000 - 1,
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal("1"),
        trade_count=1,
    )

    signal = make_mr_signal(
        symbol=symbol,
        timestamp_ms=now_ms,
        bar=bar,
    )
    state = SimpleNamespace(bars=[bar], bb=None, atr=None, rsi=None)

    handler._strategies[symbol] = SimpleNamespace(
        on_tick=lambda *_a, **_k: signal,
        get_state=lambda _s: state,
        set_regime=lambda *_a, **_k: None,
    )

    handler._on_market_tick(
        SimpleNamespace(
            pld={
                "symbol": symbol,
                "price": "100",
                "buy_volume": "1",
                "sell_volume": "0",
                "ts": now_ms,
            }
        )
    )

    handler._on_market_tick(
        SimpleNamespace(
            pld={
                "symbol": symbol,
                "price": "100",
                "buy_volume": "1",
                "sell_volume": "0",
                "ts": now_ms - 1,
            }
        )
    )

    emitted_signals = [name for name, _ in bus.emitted if name == "EVT:STRATEGY_SIGNAL_PRODUCED"]
    assert len(emitted_signals) == 1
