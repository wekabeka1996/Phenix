import pytest
from types import SimpleNamespace
from vfoundation.core.protocol import Message


class StubFSM:
    def __init__(self):
        self.captured = []

    async def emit(self, m: Message):
        # очікуємо саме Message
        assert isinstance(m, Message)
        self.captured.append(m)


@pytest.mark.asyncio
async def test_error_emit_uses_message_object(monkeypatch):
    from apps.reference.domains.execution_position import fsm as exec_fsm

    stub = StubFSM()
    logger = SimpleNamespace(exception=lambda *a, **k: None)
    f = exec_fsm.ExecPosFSM(config={}, fsm=stub)

    err = Message(
        op="ERR",
        verb="OPEN",
        intent="REJECTION",
        src="execution_position",
        dst="x",
        rid="r1",
        pld={"reason": "TEST"},
        why="unit",
    )
    # викликаємо приватний метод напряму
    await f._emit_error_async(err)
    assert stub.captured and stub.captured[0].op == "ERR"
