from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from apps.reference.domains.strategies.registry import StrategyPluginRegistry, StrategyRuntime
from apps.reference.domains.strategies.plugins.aurora_builtin import AuroraBuiltinPlugin


class _FSM:
    def __init__(self) -> None:
        self.listeners: dict[str, list[object]] = {}
        self.emitted: list[tuple[str, dict]] = []

    def listen(self, event: str, handler: object) -> None:
        self.listeners.setdefault(event, []).append(handler)

    def emit(self, event: str, payload=None, *_args, **_kwargs) -> None:
        self.emitted.append((event, payload or {}))


class _DummyAuroraHandler:
    def __init__(self, *, config: object, emit_fn, strategy_id: str) -> None:
        self.config = config
        self.emit_fn = emit_fn
        self.strategy_id = strategy_id

    def on_features_calculated(self, pld: Any) -> None:
        symbol = pld.get("symbol") if isinstance(pld, dict) else getattr(pld, "symbol", None)
        self.emit_fn(
            "EVT:STRATEGY_SIGNAL_PRODUCED",
            {
                "schema_version": 1,
                "strategy_id": "aurora",
                "symbol": str(symbol or ""),
                "side": "BUY",
                "score": 1.0,
                "rid": "rid-test",
                "why": "test",
                "why_chain": ["test"],
                "readiness": {"warmup_ok": True},
                "ts_ms": 1,
            },
        )

    def on_regime_detected(self, _pld: Any) -> None:
        return


@dataclass(frozen=True)
class _NoopHandler:
    def register(self) -> None:
        return


@dataclass(frozen=True)
class _NoopPlugin:
    strategy_id: str

    def create_handler(self, *, fsm: _FSM, config: object) -> _NoopHandler:
        return _NoopHandler()


def test_assignments_block_aurora_signals_for_mr_only_symbols(monkeypatch) -> None:
    # Patch AuroraHandler to avoid pulling in full Aurora stack and to force a deterministic emission.
    import apps.reference.domains.strategies.plugins.aurora_builtin as aurora_builtin

    monkeypatch.setattr(aurora_builtin, "AuroraHandler", _DummyAuroraHandler)

    fsm = _FSM()
    registry = StrategyPluginRegistry()

    # Register both strategy ids to match real runtime shape.
    registry.register(AuroraBuiltinPlugin())
    registry.register(_NoopPlugin(strategy_id="mean_reversion"))

    cfg = SimpleNamespace(
        strategies=SimpleNamespace(aurora=SimpleNamespace(legacy_tick_path_enabled=False)),
        strategies_registry=SimpleNamespace(assignments={"DOGEUSDT": ["mean_reversion"], "BTCUSDT": ["aurora"]}),
    )

    StrategyRuntime(fsm=fsm, config=cfg, registry=registry).start()  # type: ignore[arg-type]

    # Fire synthetic FEATURES_CALCULATED events (Aurora listens to this).
    callbacks = list(fsm.listeners.get("EVT:FEATURES_CALCULATED", []))
    assert callbacks, "Aurora handler should register FEATURES_CALCULATED listener"

    evt_doge = SimpleNamespace(pld={"symbol": "DOGEUSDT", "features": {"x": 1}})
    evt_btc = SimpleNamespace(pld={"symbol": "BTCUSDT", "features": {"x": 1}})

    for cb in callbacks:
        cb(evt_doge)
        cb(evt_btc)

    aurora_signals = [
        pld
        for (name, pld) in fsm.emitted
        if name == "EVT:STRATEGY_SIGNAL_PRODUCED" and isinstance(pld, dict) and pld.get("strategy_id") == "aurora"
    ]

    # Negative assertion: aurora must not emit for MR-only symbols.
    assert not any(pld.get("symbol") == "DOGEUSDT" for pld in aurora_signals)

    # Positive control: aurora is allowed for BTCUSDT.
    assert any(pld.get("symbol") == "BTCUSDT" for pld in aurora_signals)
