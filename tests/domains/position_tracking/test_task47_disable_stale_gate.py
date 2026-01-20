import asyncio
import logging

import pytest

from apps.reference.config_loader import get_config
from vfoundation.core.protocol import Message


class _DummyFsm:
    def __init__(self):
        self.emitted: list[tuple[str, dict]] = []

    def emit(self, event_name: str, payload=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}))

    def listen(self, _event_name: str, _callback) -> None:
        return


@pytest.mark.skip(reason="AuroraBridge removed from main.py - test deprecated")
@pytest.mark.asyncio
async def test_task47_portfolio_stale_gate_blocks_by_default(monkeypatch) -> None:
    import apps.reference.main as main

    fsm = _DummyFsm()
    cfg = get_config()

    bridge = main.AuroraBridge(fsm=fsm, config=cfg, logger=logging.getLogger("tests.task47.bridge"))

    # Force stale portfolio (no updates).
    bridge._last_portfolio_ts = 0

    async def _emit_compat(_fsm, msg: Message, **_k):
        _fsm.emit(f"{msg.op}:{msg.verb}", payload=msg.pld, why=msg.why)

    monkeypatch.setattr(main, "emit_compat", _emit_compat)
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: coro.close())

    dispatched = {"open": 0}
    bridge._dispatch_open = lambda _evt: dispatched.__setitem__("open", dispatched["open"] + 1)  # type: ignore[method-assign]

    evt = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="bridge",
        rid="rid-1",
        pld={"instrument": "BTCUSDT", "order": {"qty": "1", "price": "100", "reduce_only": False}},
        why="test",
    )

    await bridge.on_trade_intent_proposed(evt)

    assert dispatched["open"] == 0
    assert any(name == "EVT:INTENT_DEFERRED" and payload.get("reason") == "PORTFOLIO_STALE" for name, payload in fsm.emitted)


@pytest.mark.skip(reason="AuroraBridge removed from main.py - test deprecated")
@pytest.mark.asyncio
async def test_task47_portfolio_stale_gate_can_be_disabled_in_debug(monkeypatch) -> None:
    import apps.reference.main as main

    fsm = _DummyFsm()
    cfg = get_config()
    cfg = cfg.model_copy(
        deep=True,
        update={
            "domains": cfg.domains.model_copy(
                update={
                    "debug": cfg.domains.debug.model_copy(
                        update={"disable_positions_stale_gate": True}
                    )
                }
            )
        },
    )

    bridge = main.AuroraBridge(fsm=fsm, config=cfg, logger=logging.getLogger("tests.task47.bridge"))
    bridge._last_portfolio_ts = 0  # stale

    async def _emit_compat(_fsm, msg: Message, **_k):
        _fsm.emit(f"{msg.op}:{msg.verb}", payload=msg.pld, why=msg.why)

    monkeypatch.setattr(main, "emit_compat", _emit_compat)
    monkeypatch.setattr(main.asyncio, "create_task", lambda coro: coro.close())

    dispatched = {"open": 0}
    bridge._dispatch_open = lambda _evt: dispatched.__setitem__("open", dispatched["open"] + 1)  # type: ignore[method-assign]

    evt = Message(
        op="EVT",
        verb="TRADE_INTENT_PROPOSED",
        src="decision_making",
        dst="bridge",
        rid="rid-2",
        pld={"instrument": "BTCUSDT", "order": {"qty": "1", "price": "100", "reduce_only": False}},
        why="test",
    )

    await bridge.on_trade_intent_proposed(evt)

    assert dispatched["open"] == 1
    assert any(name == "EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE" for name, _ in fsm.emitted)
