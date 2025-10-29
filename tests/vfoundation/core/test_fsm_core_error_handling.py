import logging
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message


def test_fsm_core_logs_exceptions(caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    fsm = FSMCore()

    # register a listener that raises
    def raising_listener(msg: Message):
        raise ValueError("listener failure")

    fsm.listen("EVT:TEST", raising_listener)

    # Act
    with caplog.at_level(logging.ERROR):
        fsm.emit("EVT:TEST", {"key": "value"}, "test reason")

    # Assert: there is an ERROR or CRITICAL log with our message
    logged = "\n".join([r.getMessage() for r in caplog.records])
    assert "CRITICAL: Unhandled exception in listener for event 'EVT:TEST'" in logged or "CRITICAL: Unhandled exception in listener for event 'TEST'" in logged
    # Also ensure stacktrace present in logs (ValueError text should be visible)
    assert "listener failure" in logged
