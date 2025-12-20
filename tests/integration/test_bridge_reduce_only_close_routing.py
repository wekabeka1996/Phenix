import logging
from unittest.mock import MagicMock

from vfoundation.core.protocol import Message


def test_bridge_routes_reduce_only_trade_intent_to_cmd_close(monkeypatch):
    from apps.reference.main import AuroraBridge
    import apps.reference.main as mainmod

    fsm = MagicMock()
    fsm.listen = MagicMock()
    fsm.emit = MagicMock()

    # Avoid depending on full config loading here: we only need to verify routing logic.
    bridge = AuroraBridge.__new__(AuroraBridge)
    bridge.fsm = fsm
    bridge.config = MagicMock()
    bridge.logger = logging.getLogger("test.bridge")
    bridge._last_portfolio = {}
    bridge._last_portfolio_ts = 0
    bridge._deferred = {}
    bridge._deferred_tries = {}
    bridge._qos_next_allowed_ts_per_symbol = {}
    bridge._ttl_sec = 5
    bridge._max_retries = 1
    bridge._retry_delay_sec = 0.01
    bridge._retry_scheduler = MagicMock()

    received: list[Message] = []

    class _StubExecPos:
        def handle(self, msg: Message):
            received.append(msg)
            return None

    monkeypatch.setattr(mainmod, "execution_position", _StubExecPos())

    evt = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="any",
        rid="rid-test",
        pld={
            "instrument": "BTCUSDT",
            "side": "SELL",
            "order": {"qty": "1", "price": "0", "reduce_only": True},
        },
        why="test",
    )

    # This must bypass QoS/portfolio gates and must NOT become CMD:OPEN.
    bridge.on_trade_intent_proposed_sync(evt)

    assert received, "expected bridge to dispatch to execution_position"
    assert received[0].op == "CMD"
    assert received[0].verb == "CLOSE"
    assert received[0].pld.get("symbol") == "BTCUSDT"
