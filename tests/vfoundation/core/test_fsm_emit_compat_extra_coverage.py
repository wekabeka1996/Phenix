from __future__ import annotations

import importlib
import sys

import pytest
from unittest.mock import MagicMock


def test_message_class_fallback(monkeypatch):
    import vfoundation.core.fsm_emit_compat as compat_mod

    monkeypatch.setitem(sys.modules, "vfoundation.core.protocol", None)
    importlib.reload(compat_mod)

    msg = compat_mod.Message(
        op="EVT",
        verb="OPEN",
        src="A",
        dst="B",
        rid="r",
        pld={"x": 1},
        why="t",
        data_ref=["obs://x"],
    )
    assert msg.op == "EVT"
    assert msg.verb == "OPEN"
    assert msg.src == "A"
    assert msg.dst == "B"
    assert msg.rid == "r"
    assert msg.pld == {"x": 1}
    assert msg.why == "t"
    assert msg.data_ref == ["obs://x"]

    monkeypatch.delitem(sys.modules, "vfoundation.core.protocol")
    importlib.reload(compat_mod)


def test_get_exceptions():
    from vfoundation.core.fsm_emit_compat import _get

    class PydV1Fail:
        def dict(self):
            raise RuntimeError("dict fail")

    class PydV2Fail:
        def model_dump(self):
            raise ValueError("dump fail")

    assert _get(PydV1Fail(), "k", "fb") == "fb"
    assert _get(PydV2Fail(), "k", "fb") == "fb"


@pytest.mark.asyncio
async def test_emit_compat_async_override_to_4arg():
    from vfoundation.core.fsm_emit_compat import Message, emit_compat

    calls: list[tuple] = []

    class FakeFsm:
        _emit_compat_mode = "op_verb_payload_why"

        async def emit(self, *args):
            calls.append(args)
            return "ok"

    msg = Message(op="EVT", verb="V", src="S", dst="D", rid="R")
    await emit_compat(FakeFsm(), msg)

    assert calls == [("EVT", "V", {"verb": "V", "rid": "R", "src": "S", "dst": "D"}, None)]


@pytest.mark.asyncio
async def test_emit_compat_async_override_to_3arg():
    from vfoundation.core.fsm_emit_compat import Message, emit_compat

    calls: list[tuple] = []

    class FakeFsm:
        _emit_compat_mode = "op_payload_why"

        async def emit(self, *args):
            calls.append(args)
            return "ok"

    msg = Message(op="EVT", verb="V", src="S", dst="D", rid="R", why="w")
    await emit_compat(FakeFsm(), msg)

    assert calls == [("EVT", {"verb": "V", "rid": "R", "src": "S", "dst": "D"}, "w")]


@pytest.mark.asyncio
async def test_unresolved_emit_contract_logs_once():
    from vfoundation.core.fsm_emit_compat import Message, emit_compat

    class FakeFsm:
        def emit(self, *args):
            raise AssertionError("should not be called")

    logger = MagicMock()
    await emit_compat(FakeFsm(), Message(op="EVT", verb="V", src="S", dst="D"), logger=logger)
    logger.error.assert_called_once()
