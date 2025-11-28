"""
Tests for runtime factory and V2RuntimeFacade mapping logic.
"""
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from apps.reference.domains.execution_position.infra.runtime_factory import build_execution_runtime, V2RuntimeFacade

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
    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_instance = MagicMock()
        MockV2.return_value = mock_instance

        runtime = build_execution_runtime(config, mock_fsm, mock_adapter)

        assert isinstance(runtime, V2RuntimeFacade)
        MockV2.assert_called_once()
        assert runtime.runtime == mock_instance

def test_factory_v2_mode(mock_fsm, mock_adapter):
    """Ensure explicit v2 mode builds V2."""
    config = MockConfig({"execution_position": {"runtime_mode": "v2"}})

    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_instance = MagicMock()
        MockV2.return_value = mock_instance

        runtime = build_execution_runtime(config, mock_fsm, mock_adapter)

        assert isinstance(runtime, V2RuntimeFacade)
        MockV2.assert_called_once()
        assert runtime.runtime == mock_instance

def test_factory_invalid_mode_defaults_to_v2(mock_fsm, mock_adapter):
    """Ensure invalid mode defaults to V2."""
    config = MockConfig({"execution_position": {"runtime_mode": "invalid_mode"}})

    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_instance = MagicMock()
        MockV2.return_value = mock_instance

        runtime = build_execution_runtime(config, mock_fsm, mock_adapter)

        assert isinstance(runtime, V2RuntimeFacade)
        MockV2.assert_called_once()

def test_facade_entry_intent_mapping():
    """Test mapping of CMD:OPEN to ENTRY_INTENT."""
    facade = V2RuntimeFacade(config={}, adapter=MagicMock())
    facade.runtime = MagicMock()
    facade._submit_to_loop = MagicMock()

    msg = MockMessage(
        op="CMD",
        verb="OPEN",
        pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "1.0", "price": "50000"}
    )

    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]
    assert event.kind == "ENTRY_INTENT"
    assert event.symbol == "BTCUSDT"
    assert event.payload["side"] == "BUY"
    assert str(event.payload["quantity"]) == "1.0"

def test_facade_cancel_intent_mapping():
    """Test mapping of CMD:CANCEL to CANCEL_INTENT."""
    facade = V2RuntimeFacade(config={}, adapter=MagicMock())
    facade.runtime = MagicMock()
    facade._submit_to_loop = MagicMock()

    msg = MockMessage(
        op="CMD",
        verb="CANCEL",
        pld={"symbol": "BTCUSDT", "order_id": "123"}
    )

    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]
    assert event.kind == "CANCEL_INTENT"
    assert event.payload["order_id"] == "123"

def test_facade_trade_executed_mapping():
    """Test mapping of EVT:TRADE_EXECUTED to TRADE_EXECUTED."""
    facade = V2RuntimeFacade(config={}, adapter=MagicMock())
    facade.runtime = MagicMock()
    facade._submit_to_loop = MagicMock()

    msg = MockMessage(
        op="EVT",
        verb="TRADE_EXECUTED",
        pld={"symbol": "BTCUSDT", "order_id": "123", "last_qty": "0.5", "last_price": "50100"}
    )

    facade.handle(msg)

    assert facade.runtime.handle.called
    event = facade.runtime.handle.call_args[0][0]
    assert event.kind == "TRADE_EXECUTED"
    assert event.payload["quantity"] == "0.5"
    assert event.payload["price"] == "50100"

def test_facade_ignored_message():
    """Test that irrelevant messages are ignored."""
    facade = V2RuntimeFacade(config={}, adapter=MagicMock())
    facade.runtime = MagicMock()
    facade._submit_to_loop = MagicMock()

    msg = MockMessage(op="INFO", verb="HEARTBEAT", pld={})

    facade.handle(msg)

    assert not facade.runtime.handle.called


# ============================================================================
# New tests for runtime_factory fixes (CLEANUP-S1)
# ============================================================================

def test_facade_snapshot_interval_uses_runtime_constant():
    """Ensure facade uses constant from ExecPosRuntimeV2, not hardcoded value."""
    from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2

    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_runtime = MagicMock()
        mock_runtime.set_snapshot_refresh_hook = MagicMock()
        MockV2.return_value = mock_runtime
        MockV2.SNAPSHOT_REQUEST_INTERVAL_SEC = 5.0

        facade = V2RuntimeFacade(config={}, adapter=MagicMock())

        # Verify it uses the constant, not a hardcoded value
        assert facade._snapshot_request_interval_sec == ExecPosRuntimeV2.SNAPSHOT_REQUEST_INTERVAL_SEC


def test_facade_get_agg_oco_state_snapshot_delegates_to_runtime():
    """Ensure get_agg_oco_state_snapshot delegates to runtime."""
    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_runtime = MagicMock()
        mock_runtime.set_snapshot_refresh_hook = MagicMock()
        mock_runtime.get_positions_snapshot = MagicMock(return_value=[
            {"symbol": "BTCUSDT", "qty": 1.0, "side": "LONG"}
        ])
        MockV2.return_value = mock_runtime
        MockV2.SNAPSHOT_REQUEST_INTERVAL_SEC = 5.0

        facade = V2RuntimeFacade(config={}, adapter=MagicMock())

        result = facade.get_agg_oco_state_snapshot(symbol="BTCUSDT", side="LONG")

        mock_runtime.get_positions_snapshot.assert_called_once_with(
            symbol="BTCUSDT", side="LONG"
        )
        assert len(result) == 1
        assert result[0]["symbol"] == "BTCUSDT"


def test_facade_get_agg_oco_state_snapshot_no_filters():
    """Ensure get_agg_oco_state_snapshot works with no filters."""
    with patch("apps.reference.domains.execution_position.infra.runtime_factory.ExecPosRuntimeV2") as MockV2:
        mock_runtime = MagicMock()
        mock_runtime.set_snapshot_refresh_hook = MagicMock()
        mock_runtime.get_positions_snapshot = MagicMock(return_value=[])
        MockV2.return_value = mock_runtime
        MockV2.SNAPSHOT_REQUEST_INTERVAL_SEC = 5.0

        facade = V2RuntimeFacade(config={}, adapter=MagicMock())

        result = facade.get_agg_oco_state_snapshot()

        mock_runtime.get_positions_snapshot.assert_called_once_with(
            symbol=None, side=None
        )
        assert result == []
