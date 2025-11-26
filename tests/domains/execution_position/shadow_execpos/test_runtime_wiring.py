"""
Tests for runtime factory and event adapter.
"""
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from apps.reference.domains.execution_position.runtime_factory import build_execution_runtime, V2RuntimeFacade
from apps.reference.domains.execution_position.shadow_execpos.event_adapter import MessageToRuntimeEventAdapter

@dataclass
class MockMessage:
    op: str
    verb: str
    pld: dict
    ts: float = 1234567890.0

class MockConfig:
    def __init__(self, data):
        self.data = data
    def to_dict(self):
        return self.data

@pytest.fixture
def mock_fsm():
    return MagicMock()

@pytest.fixture
def mock_adapter():
    return MagicMock()

def test_factory_legacy_mode_raises_error(mock_fsm, mock_adapter):
    """Ensure legacy mode raises ValueError."""
    config = MockConfig({"execution_position": {"runtime_mode": "legacy"}})
    
    with pytest.raises(ValueError, match="ExecPosFSM \(legacy mode\) has been removed"):
        build_execution_runtime(config, mock_fsm, mock_adapter)

def test_factory_default_mode_is_v2(mock_fsm, mock_adapter):
    """Ensure default mode builds V2."""
    config = MockConfig({}) # No runtime_mode
    
    # We need to mock ExecPosRuntimeV2 to avoid full instantiation
    with patch("apps.reference.domains.execution_position.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_instance = MagicMock()
        MockV2.return_value = mock_instance
        
        runtime = build_execution_runtime(config, mock_fsm, mock_adapter)
        
        assert isinstance(runtime, V2RuntimeFacade)
        MockV2.assert_called_once()
        assert runtime.runtime == mock_instance

def test_factory_v2_mode(mock_fsm, mock_adapter):
    """Ensure explicit v2 mode builds V2."""
    config = MockConfig({"execution_position": {"runtime_mode": "v2"}})
    
    with patch("apps.reference.domains.execution_position.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_instance = MagicMock()
        MockV2.return_value = mock_instance
        
        runtime = build_execution_runtime(config, mock_fsm, mock_adapter)
        
        assert isinstance(runtime, V2RuntimeFacade)
        MockV2.assert_called_once()
        assert runtime.runtime == mock_instance

def test_factory_invalid_mode_defaults_to_v2(mock_fsm, mock_adapter):
    """Ensure invalid mode defaults to V2."""
    config = MockConfig({"execution_position": {"runtime_mode": "invalid_mode"}})
    
    with patch("apps.reference.domains.execution_position.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_instance = MagicMock()
        MockV2.return_value = mock_instance
        
        runtime = build_execution_runtime(config, mock_fsm, mock_adapter)
        
        assert isinstance(runtime, V2RuntimeFacade)
        MockV2.assert_called_once()

def test_adapter_entry_intent():
    adapter = MessageToRuntimeEventAdapter()
    msg = MockMessage(
        op="CMD", 
        verb="OPEN", 
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0", "price": "50000"}
    )
    event = adapter.from_legacy_message(msg)
    assert event is not None
    assert event.kind == "ENTRY_INTENT"
    assert event.symbol == "BTCUSDT"
    assert event.payload["side"] == "BUY"
    assert str(event.payload["quantity"]) == "1.0"

def test_adapter_cancel_intent():
    adapter = MessageToRuntimeEventAdapter()
    msg = MockMessage(
        op="CMD", 
        verb="CANCEL", 
        pld={"symbol": "BTCUSDT", "order_id": "123"}
    )
    event = adapter.from_legacy_message(msg)
    assert event is not None
    assert event.kind == "CANCEL_INTENT"
    assert event.payload["order_id"] == "123"

def test_adapter_trade_executed():
    adapter = MessageToRuntimeEventAdapter()
    msg = MockMessage(
        op="EVT", 
        verb="TRADE_EXECUTED", 
        pld={"symbol": "BTCUSDT", "order_id": "123", "last_qty": "0.5", "last_price": "50100"}
    )
    event = adapter.from_legacy_message(msg)
    assert event is not None
    assert event.kind == "TRADE_EXECUTED"
    assert event.payload["quantity"] == "0.5"
    assert event.payload["price"] == "50100"

def test_adapter_ignored_message():
    adapter = MessageToRuntimeEventAdapter()
    msg = MockMessage(op="INFO", verb="HEARTBEAT", pld={})
    event = adapter.from_legacy_message(msg)
    assert event is None
