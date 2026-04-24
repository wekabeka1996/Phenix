from __future__ import annotations

import pytest
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


class _Msg:
    def __init__(self, pld: dict):
        self.pld = pld


class _Bus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[_Msg], None]]] = {}
        self.emitted: list[tuple[str, dict]] = []

    def listen(self, event_name: str, handler: Callable[[_Msg], None]) -> None:
        self._listeners.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, payload: dict | None = None, **_: Any) -> None:
        pld = payload or {}
        self.emitted.append((event_name, pld))
        for handler in list(self._listeners.get(event_name, [])):
            handler(_Msg(pld))


@pytest.mark.xfail(reason="LEGACY: FE no longer emits EVT:FEATURES_CALCULATED on every tick after TF-BAR-SSOT refactor")
def test_depth_imbalance_tick_path_reaches_decision_making_smoke() -> None:
    """Smoke/wiring: tick -> FeatureEngineering -> AuroraHandler decision surface.

    Contract:
    - We don't require BUY/SELL.
    - We only prove EVT:MARKET_TICK_RECEIVED is *consumed* and produces an observable downstream event
      (FEATURES_CALCULATED, STRATEGY_SIGNAL_PRODUCED, or STRATEGY_DECISION_BLOCKED).
    """

    from apps.reference.config_loader import ConfigLoader
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
    from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler

    cfg = ConfigLoader().load_config()

    # Ensure symbol is enabled for AuroraHandler.
    symbol = "ETHUSDT"
    cfg.strategies.aurora.assets = {symbol: SimpleNamespace(enabled=True)}

    bus = _Bus()
    _ = FeatureEngineering(fsm=bus, config=cfg)

    aurora = AuroraHandler(config=cfg, emit_fn=bus.emit, strategy_id="aurora")
    bus.listen("EVT:REGIME_DETECTED", lambda msg: aurora.on_regime_detected(msg.pld))
    bus.listen("EVT:FEATURES_CALCULATED", lambda msg: aurora.on_features_calculated(msg.pld))

    now_ms = int(time.time() * 1000)
    # Seed regime (not strictly required for smoke)
    bus.emit(
        "EVT:REGIME_DETECTED",
        {
            "symbol": symbol,
            "regime": "TREND_UP",
            "confidence": 1.0,
            "ts_ms": now_ms,
            "warmup": {"full_ready": True, "ticks_seen": 10},
        },
    )

    # FeatureEngineering requires 2 ticks (it skips first tick because it needs prev tick for dt).
    tick1 = {
        "ts": now_ms - 1000,
        "symbol": symbol,
        "bid": 100.0,
        "ask": 101.0,
        "bid_size": 10.0,
        "ask_size": 9.0,
        "buy_volume": 5.0,
        "sell_volume": 4.0,
        "price": 100.5,
    }
    tick2 = {
        "ts": now_ms,
        "symbol": symbol,
        "bid": 100.0,
        "ask": 101.0,
        "bid_size": 12.0,
        "ask_size": 8.0,
        "buy_volume": 6.0,
        "sell_volume": 3.0,
        "price": 100.6,
    }

    bus.emit("EVT:MARKET_TICK_RECEIVED", tick1)
    bus.emit("EVT:MARKET_TICK_RECEIVED", tick2)

    emitted_names = [n for (n, _) in bus.emitted]
    assert "EVT:FEATURES_CALCULATED" in emitted_names, "Expected tick -> FEATURES_CALCULATED reachability"

    # DecisionMaking surface: either Aurora produces a signal, or it explicitly emits a block reason.
    assert (
        "EVT:STRATEGY_SIGNAL_PRODUCED" in emitted_names
        or "EVT:STRATEGY_DECISION_BLOCKED" in emitted_names
    ), "Expected Aurora decision surface to be observable (signal or explicit block)"
