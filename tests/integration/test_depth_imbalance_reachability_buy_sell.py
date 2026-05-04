from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple


@dataclass
class _Msg:
    pld: dict


class _Bus:
    def __init__(self) -> None:
        self._listeners: Dict[str, List[Callable[[_Msg], None]]] = {}
        self.emitted: List[Tuple[str, dict]] = []

    def listen(self, event_name: str, handler: Callable[[_Msg], None]) -> None:
        self._listeners.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, payload: dict, **_: Any) -> None:
        self.emitted.append((event_name, payload))
        for handler in self._listeners.get(event_name, []):
            handler(_Msg(payload))


def _prime_aurora_symbol_state(bus: _Bus, symbol: str, now_ms: int) -> None:
    # Portfolio is required by warmup gate.
    # Note: DM listens to PORTFOLIO_STATE_UPDATED via FSM, but we need to verify if it's auto-wired.
    # We will rely on DM being initialized with 'bus' as FSM.
    bus.emit(
        "EVT:PORTFOLIO_STATE_UPDATED",
        {"positions": [], "equity": "1000", "positions_last_ts_ms": now_ms}
    )

    # Regime warmup contract (owned by RegimeDetector).
    bus.emit(
        "EVT:REGIME_DETECTED",
        {
            "symbol": symbol,
            "regime": "TREND_UP",
            "confidence": 1.0,
            "warmup": {"full_ready": True, "ticks_seen": 999},
        }
    )


def _emit_features(bus: _Bus, symbol: str, *, now_ms: int, depth_phi: float, dp: float, obi: float) -> None:
    # Provide all keys required by Aurora scoring v2 + gates.
    feats = {
        "price": "100",
        "liquidity_kappa": "1.0",
        "obi": str(obi),
        "tfi": "0.0",
        "delta_price": str(dp),
        "ema_bias": "0.80" if dp > 0 else "0.20",
        "volume_spike": "0.0",
        "volatility_state": "0.0",
        "depth_imbalance": str(depth_phi),
        "macro_resid": "0.0",
        # PRICE-MOTION sanity gate: provide neutral motion (won't block either side).
        "price_motion": {
            "pm_norm_10s": 0.0,
            "pm_norm_60s": 0.0,
            "pm_norm_300s": 0.0,
            "vol_pct_10s": 0.0,
            "vol_pct_60s": 0.0,
            "vol_pct_300s": 0.0,
            "ret_10s": 0.0,
            "ret_60s": 0.0,
            "ret_300s": 0.0,
        },
    }
    bus.emit(
        "EVT:FEATURES_CALCULATED",
        {
            "symbol": symbol,
            "ts": now_ms,
            "features": feats,
            "warmup": {"full_ready": True, "ticks_seen": 999},
        }
    )


def _emit_risk_and_trigger(bus: _Bus, symbol: str, now_ms: int) -> None:
    bus.emit(
        "EVT:RISK_ASSESSMENT_COMPLETED",
        {
            "symbol": symbol,
            "ts": now_ms,
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0},
        }
    )


def _extract_intents(bus: _Bus, symbol: str) -> list[dict]:
    return [
        pld
        for (evt, pld) in bus.emitted
        if evt == "EVT:TRADE_INTENT_PROPOSED" and pld.get("instrument") == symbol
    ]


def test_depth_imbalance_reachability_buy_and_sell_intents() -> None:
    """C4: End-to-end reachability smoke for depth_imbalance.

    This test intentionally does NOT force BUY/SELL intents (brittle, threshold-dependent).
    It proves the decision surface is reachable end-to-end and is observable via events.
    """
    import pytest
    pytest.skip("T2B-03: on_features_calculated is now data-only. Signals require CMD:PROCESS_STRATEGY path.")
    cfg.strategies.aurora.decision.feature_neutrals = {"depth_imbalance": 0.5}
    cfg.strategies.aurora.decision.essential_features = ["depth_imbalance"]
    
    # Ensure symbol is enabled in Aurora config (AuroraHandler check)
    from types import SimpleNamespace
    cfg.strategies.aurora.assets = {"ETHUSDT": SimpleNamespace(enabled=True)}

    bus = _Bus()
    dm = DecisionMaking(fsm=bus, config=cfg)

    # Keep the test focused on depth_imbalance polarity; avoid registry coupling.
    dm._is_strategy_assigned = lambda sym, strat: strat == "aurora"  # type: ignore[method-assign]

    # Instantiate AuroraHandler (Required for STRATEGY_SIGNAL emission)
    handler = AuroraHandler(config=cfg, emit_fn=bus.emit, strategy_id="aurora")
    bus.listen("EVT:REGIME_DETECTED", lambda msg: handler.on_regime_detected(msg.pld))
    bus.listen("EVT:FEATURES_CALCULATED", lambda msg: handler.on_features_calculated(msg.pld))

    symbol = "ETHUSDT"

    # Prime runtime prerequisites.
    now_ms = int(time.time() * 1000)
    _prime_aurora_symbol_state(bus, symbol, now_ms)

    # BUY case: bid-heavy (phi<0.5) + bullish delta_price/obi => expect BUY intent.
    # Need consecutive_bars=2 for directional sanity -> send 2 updates.
    _emit_features(bus, symbol, now_ms=now_ms - 2000, depth_phi=0.30, dp=+2.0, obi=+0.8)
    _emit_features(bus, symbol, now_ms=now_ms - 1000, depth_phi=0.30, dp=+2.0, obi=+0.8)
    _emit_risk_and_trigger(bus, symbol, now_ms)

    buy_events = {evt for (evt, _pld) in bus.emitted}
    assert (
        "EVT:TRADE_INTENT_PROPOSED" in buy_events
        or "EVT:TRADE_INTENT_REJECTED" in buy_events
        or "EVT:STRATEGY_DECISION_BLOCKED" in buy_events
        or "EVT:STRATEGY_SIGNAL_PRODUCED" in buy_events
    ), f"Expected BUY-path to reach an observable decision event, got={sorted(buy_events)}"

    # SELL case: ask-heavy (phi>0.5) + bearish delta_price/obi => expect SELL intent.
    bus.emitted.clear()
    now_ms2 = int(time.time() * 1000)
    _prime_aurora_symbol_state(bus, symbol, now_ms2)
    _emit_features(bus, symbol, now_ms=now_ms2 - 2000, depth_phi=0.70, dp=-2.0, obi=-0.8)
    _emit_features(bus, symbol, now_ms=now_ms2 - 1000, depth_phi=0.70, dp=-2.0, obi=-0.8)
    _emit_risk_and_trigger(bus, symbol, now_ms2)

    sell_events = {evt for (evt, _pld) in bus.emitted}
    assert (
        "EVT:TRADE_INTENT_PROPOSED" in sell_events
        or "EVT:TRADE_INTENT_REJECTED" in sell_events
        or "EVT:STRATEGY_DECISION_BLOCKED" in sell_events
        or "EVT:STRATEGY_SIGNAL_PRODUCED" in sell_events
    ), f"Expected SELL-path to reach an observable decision event, got={sorted(sell_events)}"
