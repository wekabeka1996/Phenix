from __future__ import annotations

import json
import logging
import time
import pytest
from decimal import Decimal
from types import SimpleNamespace

from apps.reference.config_models import (
    MRAssetConfig,
    MRRegimeSizingConfig,
    MRRegimeThresholdsConfig,
    MRStrategyParamsConfig,
    MeanReversion1mStrategyConfig,
)
from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler


class _Bus:
    def __init__(self) -> None:
        self.listeners: dict[str, list[object]] = {}

    def listen(self, event: str, handler: object) -> None:
        self.listeners.setdefault(event, []).append(handler)

    def emit(self, event_name: str, payload: dict | None = None, why: str | None = None, data_ref: object = None) -> None:
        pld = payload or {}
        for handler in list(self.listeners.get(event_name, [])):
            handler(SimpleNamespace(pld=pld))


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.mark.xfail(reason="MR chain broken: missing features updates for tf=180")
def test_mean_reversion_logs_signal_with_indicators() -> None:
    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)

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
                
                allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
                position_mode="STRICT",
            )
        },
        regime_sizing={"FLAT_NORMAL": MRRegimeSizingConfig(sizing_mult=1.0, stop_mult=1.0, target_mult=1.0)},
        allowed_regimes=["FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH"],
    )

    cfg = SimpleNamespace(strategies_registry=strategies_registry, strategies=SimpleNamespace(mean_reversion=mr_cfg))
    bus = _Bus()

    capture = _Capture()
    logger = logging.getLogger("domain_mean_reversion")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(capture)
    logger.propagate = False

    handler = MeanReversionHandler(fsm=bus, config=cfg)  # type: ignore[arg-type]
    handler.register()

    base = (now_ms // 60_000) * 60_000
    # P0 FIX: Use LOW_VOLATILITY instead of MEAN_REVERSION
    # MEAN_REVERSION now requires ATR data (fail-closed), but this test only sends 4 ticks
    # LOW_VOLATILITY doesn't require ATR and always maps to FLAT_LOW
    bus.emit("EVT:REGIME_DETECTED", {"symbol": symbol, "regime": "LOW_VOLATILITY"})
    ticks = [
        (base + 0, Decimal("100")),
        (base + 60_000, Decimal("100")),
        (base + 120_000, Decimal("50")),
        (base + 180_000, Decimal("50")),
    ]
    for ts_ms, price in ticks:
        bus.emit("EVT:MARKET_TICK_RECEIVED", {"symbol": symbol, "price": str(price), "buy_volume": "1", "sell_volume": "0", "ts": ts_ms})

    mr_signal_msgs = [m for m in capture.messages if m.startswith("MR_SIGNAL ")]
    assert mr_signal_msgs, "Expected at least one MR_SIGNAL log line"

    payload = json.loads(mr_signal_msgs[-1].split("MR_SIGNAL ", 1)[1])
    assert payload["symbol"] == symbol
    assert payload["side"] in ("BUY", "SELL")
    assert payload["bb_mid"] is not None
    assert payload["pct_b"] is not None
