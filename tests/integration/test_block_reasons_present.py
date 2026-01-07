from __future__ import annotations

import time
from decimal import Decimal
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


def test_block_reason_readiness_present() -> None:
    """readiness=false => reason contains READINESS."""

    from apps.reference.config_loader import ConfigLoader
    from apps.reference.domains.decision_making.aurora_handler import AuroraHandler

    cfg = ConfigLoader().load_config()

    symbol = "ETHUSDT"
    cfg.strategies.aurora.assets = {symbol: SimpleNamespace(enabled=True)}

    bus = _Bus()
    handler = AuroraHandler(config=cfg, emit_fn=bus.emit, strategy_id="aurora")

    # Warmup not ready (fail-closed) => must emit explicit block reason.
    handler.on_features_calculated(
        {
            "symbol": symbol,
            "ts": int(time.time() * 1000),
            "features": {"price": "100", "delta_price": "0"},
            "warmup": {"full_ready": False, "ready": {}},
        }
    )

    blocked = [pld for (evt, pld) in bus.emitted if evt == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert blocked, "Expected explicit STRATEGY_DECISION_BLOCKED event"
    assert "READINESS" in str(blocked[-1].get("reason", ""))


def test_block_reason_regime_mapping_none_present() -> None:
    """regime_mapping None => reason contains REGIME_MAPPING_NONE."""

    from apps.reference.config_loader import ConfigLoader
    from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler

    cfg = ConfigLoader().load_config()

    symbol = "BTCUSDT"
    # Ensure MR is assigned for this symbol (activation SSOT).
    try:
        assignments = dict(getattr(cfg.strategies_registry, "assignments", {}) or {})
    except Exception:
        assignments = {}
    assignments[symbol] = ["mean_reversion"]
    cfg.strategies_registry.assignments = assignments

    bus = _Bus()
    handler = MeanReversionHandler(fsm=bus, config=cfg)  # type: ignore[arg-type]
    assert handler.enabled is True
    assert symbol in getattr(handler, "_strategies", {})

    now_ms = int(time.time() * 1000)
    tf_ms = int(getattr(cfg.strategies.mean_reversion, "timeframe_sec", 180)) * 1000
    base = (now_ms // tf_ms) * tf_ms

    # TREND_UP maps to None in map_to_flat_regime => must surface REGIME_MAPPING_NONE.
    handler.on_regime(symbol, "TREND_UP")

    # Need enough completed bars to pass config min_bars (default 25 in production config).
    min_bars = int(getattr(cfg.strategies.mean_reversion.strategy, "min_bars", 25))
    # Completed bar count increments when a tick arrives at/after bar_end.
    # With N ticks spaced by tf_ms, completed bars ~= N-1.
    tick_count = max(min_bars + 1, 3)
    ticks = [(base + i * tf_ms, Decimal("100")) for i in range(tick_count)]
    last_signal = None
    for ts_ms, price in ticks:
        last_signal = handler.on_tick(symbol, price, Decimal("1"), ts_ms)

    assert last_signal is not None, "Expected MR strategy to produce a (neutral) signal after bars complete"
    why = str(getattr(last_signal, "why", "") or "")
    assert "regime_not_flat:" in why, f"Expected regime_not_flat why, got={why!r}"

    blocked = [pld for (evt, pld) in bus.emitted if evt == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert blocked, "Expected explicit STRATEGY_DECISION_BLOCKED for regime mapping"
    assert "REGIME_MAPPING_NONE" in str(blocked[-1].get("reason_code", "")) or "REGIME_MAPPING_NONE" in str(
        blocked[-1].get("reason", "")
    )


def test_block_reason_spread_present() -> None:
    """spread gate => reason contains SPREAD."""

    from apps.reference.config_loader import ConfigLoader
    from apps.reference.domains.decision_making.aurora_handler import AuroraHandler

    cfg = ConfigLoader().load_config()

    symbol = "ETHUSDT"
    cfg.strategies.aurora.assets = {symbol: SimpleNamespace(enabled=True)}

    # Minimal scoring: require spread_bps and mark it not ready.
    cfg.strategies.aurora.decision.signal_weights = {"spread_bps": 1.0}
    cfg.strategies.aurora.decision.feature_neutrals = {"spread_bps": 0.0}
    cfg.strategies.aurora.decision.essential_features = ["spread_bps"]

    ds_cfg = cfg.strategies.aurora.decision.direction_strength_scoring
    ds_cfg.directional_features = ["spread_bps"]
    ds_cfg.strength_features = []
    ds_cfg.strength_alpha = 0.0
    ds_cfg.strength_cap = 1.0

    bus = _Bus()
    handler = AuroraHandler(config=cfg, emit_fn=bus.emit, strategy_id="aurora")

    handler.on_features_calculated(
        {
            "symbol": symbol,
            "ts": int(time.time() * 1000),
            "features": {"price": "100", "delta_price": "0", "spread_bps": "100"},
            "warmup": {
                "full_ready": True,
                "ready": {"spread_bps": False},
            },
        }
    )

    blocked = [pld for (evt, pld) in bus.emitted if evt == "EVT:STRATEGY_DECISION_BLOCKED"]
    assert blocked, "Expected explicit STRATEGY_DECISION_BLOCKED for spread"
    assert "SPREAD" in str(blocked[-1].get("reason", ""))
