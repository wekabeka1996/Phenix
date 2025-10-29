"""Basic tests for execution_position FSM to improve coverage."""
from unittest.mock import MagicMock
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.execution_position.fsm_open import OpenFlowFSM, OpenState


def test_exec_pos_fsm_basic():
    """Basic test for ExecPosFSM."""
    config = MagicMock()
    config.trading = {'execution': {'cooldown_ms': 1000, 'guard_enabled': True}}
    fsm = ExecPosFSM(config=config, fsm=MagicMock())
    assert fsm.open_flow is not None
    assert fsm.manage_flow is not None
    assert fsm.close_flow is not None


def test_open_flow_fsm_basic():
    """Basic test for OpenFlowFSM."""
    fsm = OpenFlowFSM()
    assert fsm.state == OpenState.IDLE
    assert fsm.cooldown_sec == 1.0


def test_open_flow_handle_valid():
    """Test OpenFlowFSM handles valid CMD:OPEN."""
    fsm = OpenFlowFSM()
    msg = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="execution_position",
        rid="test-123",
        pld={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.001",
            "price": "50000.00",
            "order_type": "LIMIT"
        }
    )

    result = fsm.handle(msg)
    assert result is not None
    assert result.op == "DEC"
    assert result.verb == "OPEN"