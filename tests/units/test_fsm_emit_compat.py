import pytest
from types import SimpleNamespace
from vfoundation.core.fsm_emit_compat import emit_compat, Message


class DummyMsgFSM:
    def __init__(self):
        self.captured = []

    async def emit(self, m: Message):
        self.captured.append(("msg", m))


class Dummy3FSM:
    def __init__(self):
        self.captured = []

    async def emit(self, op, payload, why):
        self.captured.append(("3args", op, payload, why))


class Dummy4FSM:
    def __init__(self):
        self.captured = []

    async def emit(self, op, verb, payload, why):
        self.captured.append(("4args", op, verb, payload, why))


@pytest.mark.asyncio
async def test_emit_compat_prefers_message_api():
    f = DummyMsgFSM()
    m = Message(op="EVT", verb="X", src="test", dst="any", pld={"k": "v"}, why="w")
    await emit_compat(f, m)
    kind, captured = f.captured[0][0], f.captured[0][1]
    assert kind == "msg"
    assert captured.op == "EVT" and captured.verb == "X"


@pytest.mark.asyncio
async def test_emit_compat_supports_4args():
    f = Dummy4FSM()
    m = Message(op="EVT", verb="V", src="test", dst="any", pld={"a": 1}, why="w")
    await emit_compat(f, m)
    rec = f.captured[0]
    assert rec[0] == "4args" and rec[1] == "EVT" and rec[2] == "V"
    assert rec[3]["a"] == 1 and rec[4] == "w"


@pytest.mark.asyncio
async def test_emit_compat_supports_3args_and_injects_meta():
    f = Dummy3FSM()
    m = Message(
        op="EVT",
        verb="VERB",
        src="test_src",
        dst="test_dst",
        rid="test_rid",
        pld={"x": 1},
        why="why",
    )
    await emit_compat(f, m)
    rec = f.captured[0]
    assert rec[0] == "3args" and rec[1] == "EVT" and rec[3] == "why"
    assert (
        rec[2]["x"] == 1
        and rec[2]["verb"] == "VERB"
        and rec[2]["src"] == "test_src"
        and rec[2]["dst"] == "test_dst"
        and rec[2]["rid"] == "test_rid"
    )
