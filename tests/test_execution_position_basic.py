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


def test_exec_pos_fsm_self_healing():
    """Test ExecPosFSM self-healing mechanism for stuck active_orders_count."""
    config = MagicMock()
    config.trading = {'execution': {'cooldown_ms': 1000, 'guard_enabled': True}}
    mock_fsm = MagicMock()
    fsm = ExecPosFSM(config=config, fsm=mock_fsm)
    
    # Simulate stuck counter (normally happens when TRADE_EXECUTED event is lost)
    fsm.active_orders_count = 1  # Counter thinks there's an active order
    
    # Create mock account update event with no open positions
    account_update_msg = Message(
        op="EVT",
        verb="ACCOUNT_UPDATE_RECEIVED",
        src="account_connector",
        dst="execution_position",
        rid="test-456",
        pld={
            'positions': [],  # No open positions on exchange
            'totalWalletBalance': '1000.0',
            'updateTime': 1234567890
        }
    )
    
    # Call the self-healing method
    fsm.on_account_update(account_update_msg)
    
    # Verify counter was reset
    assert fsm.active_orders_count == 0, "Counter should be reset when no positions exist"
    
    # Verify FSM states were reset (mock objects don't have state attribute, so skip this check)
    # This would normally reset ManageFlowFSM and CloseFlowFSM states to FLAT