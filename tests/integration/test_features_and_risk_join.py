import pytest
import asyncio
from types import SimpleNamespace
from vfoundation.core.protocol import Message


class CaptureBus:
    def __init__(self):
        self.emitted = []

    async def emit(self, m):
        self.emitted.append(m)


@pytest.mark.asyncio
async def test_features_ready_but_risk_blocks():
    bus = CaptureBus()
    log = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)
    from apps.reference.domains.feature_engineering import feature_engineering
    from apps.reference.domains.decision_making import decision_making

    cfg = {
        "risk": {"max_allowed": 0.0},  # заведомо блокируем риск
        "decision": {
            "position_sizing": {"min_position_size_usd": 10, "liquidity_based_cap_usd": 10000},
            "qos": {"exposure_block_cooldown_sec": 10, "symbol_cooldown_sec": 3, "max_intents_per_minute_per_symbol": 6},
            "signal_weights": {"obi": 0.5, "tfi": 0.5},
            "signal_threshold": 0.2
        },
        "tca_prefs": {"max_slippage_bps": 10},
        "risk_budgets": {"trade_cvar95_max_bps": 100},
        "instruments": {"BTCUSDT": {"step_size": "0.001"}}
    }

    # Mock FSM for testing
    class MockFSM:
        def __init__(self, bus):
            self.bus = bus
            self.listeners = {}

        def listen(self, event, handler):
            if event not in self.listeners:
                self.listeners[event] = []
            self.listeners[event].append(handler)

        async def emit(self, event_name, payload=None, why=None):
            msg = Message(op="EVT", verb=event_name.split(":")[1], payload=payload, why=why)
            await self.bus.emit(msg)

    fsm = MockFSM(bus)

    fe = feature_engineering.FeatureEngineering(fsm, cfg)
    dm = decision_making.DecisionMaking(fsm, cfg)

    symbol = "BTCUSDT"
    feats = {"symbol": symbol, "obi": 0.3, "tfi": 0.3, "delta_price": 0.0, "ts": 1761771234567}
    msg = Message(op="EVT", verb="FEATURES_CALCULATED", intent="OBSERVATION",
                  src="test", dst="any", rid="r3", pld=feats, why="test_feats_only")

    # Manually trigger the event handlers
    dm.on_features(msg)
    await asyncio.sleep(0.005)

    intents = [m for m in bus.emitted if m.verb == "TRADE_INTENT_PROPOSED"]
    assert not intents
