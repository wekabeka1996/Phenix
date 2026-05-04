from unittest.mock import patch

import pytest

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.objective_engine.runtime import ObjectiveEngineRuntime


class _FSMStub:
    def __init__(self) -> None:
        self.listeners = {}
        self.emitted = []

    def listen(self, event_name, handler):
        self.listeners[event_name] = handler

    def emit(self, event_name, payload=None, why=None):
        self.emitted.append((event_name, payload, why))


class _Event:
    def __init__(self, payload):
        self.pld = payload


def _objective_trace(trace_id: str) -> dict:
    return {
        "trace_id": trace_id,
        "multiplier": 0.9,
        "objective_score": 0.45,
        "components": {"cost": -0.1, "edge": 0.3},
        "raw_metrics": {"spread_bps": 1.2},
    }


@pytest.mark.parametrize("strategy_id", ["aurora", "md_amr", "mean_reversion"])
def test_runtime_emits_realized_objective_event_for_supported_strategy(strategy_id: str) -> None:
    fsm = _FSMStub()
    cfg = ConfigLoader().load_config()
    runtime = ObjectiveEngineRuntime(fsm=fsm, config=cfg)

    assert "EVT:TRADE_INTENT_PROPOSED" in fsm.listeners
    assert "EVT:TRADE_EXECUTED" in fsm.listeners

    runtime._on_trade_intent_proposed(
        _Event(
            {
                "strategy": strategy_id,
                "instrument": "BTCUSDT",
                "side": "BUY",
                "rid": f"{strategy_id}-entry-rid",
                "decision_ts_ms": 1_700_000_000_000,
                "order": {"price_ref": "100.0"},
                "stop_price": "95.0",
                "target_price": "110.0",
                "regime": "TREND_UP",
                "trace": {
                    "objective": _objective_trace(f"obj-{strategy_id}"),
                    "alpha_search": {"signal_id": f"sig-{strategy_id}"},
                },
            }
        )
    )
    runtime._on_regime_detected(_Event({"symbol": "BTCUSDT", "regime": "TREND_UP"}))
    runtime._on_market_tick(_Event({"symbol": "BTCUSDT", "price": "102.0"}))
    runtime._on_trade_executed(
        _Event(
            {
                "symbol": "BTCUSDT",
                "side": "buy",
                "quantity": "1.0",
                "price": "100.0",
                "fees": "0.25",
                "ts_ms": 1_700_000_000_500,
            }
        )
    )
    runtime._on_market_tick(_Event({"symbol": "BTCUSDT", "price": "108.0"}))
    runtime._on_regime_detected(_Event({"symbol": "BTCUSDT", "regime": "MEAN_REVERSION"}))

    with patch("apps.reference.domains.objective_engine.runtime.wal.append") as wal_append:
        runtime._on_trade_executed(
            _Event(
                {
                    "symbol": "BTCUSDT",
                    "side": "sell",
                    "quantity": "1.0",
                    "price": "107.0",
                    "fees": "0.20",
                    "ts_ms": 1_700_000_600_000,
                    "rid": f"{strategy_id}-close-rid",
                }
            )
        )

    wal_append.assert_called_once()
    assert fsm.emitted[-1][0] == "EVT:OBJECTIVE_REALIZED_V1"
    realized_payload = fsm.emitted[-1][1]
    assert realized_payload["strategy_id"] == strategy_id
    assert realized_payload["pretrade_objective_trace"]["trace_id"] == f"obj-{strategy_id}"
    assert realized_payload["signal_id"] == f"sig-{strategy_id}"
