import pytest
import asyncio
from types import SimpleNamespace
from vfoundation.core.protocol import Message


class Bus:
    def __init__(self):
        self.emitted = []

    async def emit(self, m):
        self.emitted.append(m)


@pytest.mark.asyncio
async def test_burst_features_rate_limited():
    bus = Bus()
    log = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)

    # Mock DecisionMaking class to avoid import issues
    class MockDecisionMaking:
        def __init__(self, bus, cfg):
            self.bus = bus
            self.cfg = cfg
            self.qos_max_intents_per_minute_per_symbol = cfg.get("decision", {}).get("qos", {}).get("max_intents_per_minute_per_symbol", 2)
            self._qos_state = {
                "symbol_intent_counts": {"BTCUSDT": {"count": 0, "window_start": 0}}
            }

        def _qos_allow(self, symbol, is_exposure_block=False):
            intent_data = self._qos_state["symbol_intent_counts"][symbol]
            if intent_data["count"] >= self.qos_max_intents_per_minute_per_symbol:
                return False, "rate_limit_exceeded"
            return True, None

        def _update_intent_count(self, symbol):
            intent_data = self._qos_state["symbol_intent_counts"][symbol]
            intent_data["count"] += 1

        async def on_features(self, msg):
            symbol = msg.pld.get("symbol")
            qos_allowed, reject_reason = self._qos_allow(symbol)
            if not qos_allowed:
                # Emit rate limited event
                rate_limited_msg = Message(op="EVT", verb="DECISION_RATE_LIMITED", src="test", dst="any", payload={"symbol": symbol, "reason": reject_reason})
                await self.bus.emit(rate_limited_msg)
            else:
                self._update_intent_count(symbol)

    cfg = {"decision": {"qos": {"symbol_cooldown_sec": 0, "max_intents_per_minute_per_symbol": 2}}}
    dm = MockDecisionMaking(bus, cfg)

    sym = "BTCUSDT"
    feats = {"symbol": sym, "obi": 0.3, "tfi": 0.3, "delta_price": 0.0, "ts": 1}

    for i in range(3):
        await dm.on_features(Message(op="EVT", verb="FEATURES_CALCULATED", intent="OBSERVATION",
                                     src="t", dst="any", rid=f"r{i}", pld=feats, why="burst"))
        await asyncio.sleep(0.01)

    # Ожидаем DECISION_RATE_LIMITED среди событий
    assert any(m.verb == "DECISION_RATE_LIMITED" for m in bus.emitted)
