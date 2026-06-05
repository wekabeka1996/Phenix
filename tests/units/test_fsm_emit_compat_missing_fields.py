import pytest
from types import SimpleNamespace
from vfoundation.core.fsm_emit_compat import emit_compat, Message


class ThreeArgsFSM:
    def __init__(self):
        self.captured = []

    async def emit(self, op, payload, why):
        self.captured.append((op, payload, why))


@pytest.mark.asyncio
async def test_emit_compat_handles_missing_intent():
    fsm = ThreeArgsFSM()
    # Message без 'intent'
    m = Message(
        op="ERR",
        verb="OPEN",
        src="exec",
        dst="dm",
        rid="r1",
        pld={"reason": "TEST"},
        why="unit",
    )
    await emit_compat(fsm, m)
    assert fsm.captured
    op, payload, why = fsm.captured[0]
    assert op == "ERR" and why == "unit"
    # Інжектимось лише в payload, без intent
    assert payload["verb"] == "OPEN"
    assert payload["reason"] == "TEST"
    assert (
        payload["src"] == "exec" and payload["dst"] == "dm" and payload["rid"] == "r1"
    )
