import pytest
from types import SimpleNamespace
from vfoundation.core.fsm_emit_compat import Message, emit_compat


class CaptureFSM:
    def __init__(self):
        self.emitted = []

    async def emit(self, op, payload, why):  # емулируем 3-арг сигнатуру
        self.emitted.append((op, payload, why))


@pytest.mark.asyncio
async def test_execpos_emit_error_compat():
    """Test that emit_compat works with different FSM signatures."""
    fsm = CaptureFSM()
    logger = SimpleNamespace(exception=lambda *a, **k: None)

    err = Message(
        op="ERR",
        verb="OPEN",
        intent="REJECTION",
        src="execution_position",
        dst="x",
        rid="r1",
        pld={"reason": "TEST_ERR"},
        why="unit",
    )

    # Test emit_compat directly
    await emit_compat(fsm, err, logger=logger)

    assert fsm.emitted and fsm.emitted[0][0] == "ERR"
    assert fsm.emitted[0][1]["reason"] == "TEST_ERR"
    # і meta додано
    assert fsm.emitted[0][1]["verb"] == "OPEN"
