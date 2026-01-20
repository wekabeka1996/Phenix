from __future__ import annotations

import pytest
from types import SimpleNamespace

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
        self.features_calls: list[object] = []
        self.regime_calls: list[object] = []

    def on_features_calculated(self, pld: object) -> None:
        self.features_calls.append(pld)

    def on_features_data_only(self, pld: object) -> None:
        self.features_calls.append(pld)

    def on_process_strategy(self, pld: object) -> None:
        self.features_calls.append(pld)

    def on_regime_detected(self, pld: object) -> None:
        self.regime_calls.append(pld)


@pytest.mark.skip(reason="T2B-03: on_features_data_only is data-only (no filtering); filtering in on_process_strategy")
def test_strat_assign_enforce_aurora_filters_unassigned_symbols(monkeypatch) -> None:
    # Patch the real AuroraHandler with a lightweight dummy.
    import apps.reference.domains.strategies.plugins.aurora_builtin as aurora_builtin

    monkeypatch.setattr(aurora_builtin, "AuroraHandler", _DummyAuroraHandler)

    fsm = _FSM()
    cfg = SimpleNamespace(
        strategies=SimpleNamespace(aurora=SimpleNamespace(legacy_tick_path_enabled=False)),
        strategies_registry=SimpleNamespace(assignments={"DOGEUSDT": ["mean_reversion"], "BTCUSDT": ["aurora"]}),
    )

    plugin = AuroraBuiltinPlugin()
    wrapper = plugin.create_handler(fsm=fsm, config=cfg)  # type: ignore[arg-type]
    wrapper.register()

    # Simulate incoming features events.
    features_cb = fsm.listeners["EVT:FEATURES_CALCULATED"][0]

    # DOGEUSDT is NOT assigned to aurora -> handler must not be called.
    features_cb(SimpleNamespace(pld={"symbol": "DOGEUSDT", "features": {"x": 1}}))

    # BTCUSDT IS assigned to aurora -> handler must be called.
    features_cb(SimpleNamespace(pld={"symbol": "BTCUSDT", "features": {"x": 1}}))

    assert isinstance(wrapper.handler, _DummyAuroraHandler)
    assert len(wrapper.handler.features_calls) == 1
    assert wrapper.handler.features_calls[0]["symbol"] == "BTCUSDT"
