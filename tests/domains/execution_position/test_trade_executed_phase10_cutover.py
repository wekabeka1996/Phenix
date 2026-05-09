import pytest
from unittest.mock import MagicMock
from vfoundation.core.fsm_emit_compat import Message
from apps.reference.domains.execution_position.orchestration.fill_ingress_coordinator import FillIngressCoordinator
from apps.reference.domains.execution_position.orchestration.event_handlers import EPEventHandlers


@pytest.fixture
def mock_fsm():
    fsm = MagicMock()
    fsm.config.domains.execution_position.trade_executed_cutover_active = False
    fsm._evt_handlers = MagicMock(spec=EPEventHandlers)
    fsm.manage_flows = {}

    manage_flow_mock = MagicMock()
    manage_flow_mock.handle.return_value = None
    fsm._get_or_create_flows.return_value = (None, manage_flow_mock, None)
    return fsm


@pytest.fixture
def coordinator(mock_fsm):
    return FillIngressCoordinator(mock_fsm)


def test_trade_executed_cutover_false_routes_to_legacy(coordinator, mock_fsm):
    # Arrange
    mock_fsm.config.domains.execution_position.trade_executed_cutover_active = False
    msg = Message(op="EVT", verb="TRADE_EXECUTED", src="test", dst="execution_position", pld={
                  "symbol": "BTCUSDT", "qty": "1.0", "price": "50000", "side": "BUY", "orderId": "123"})

    # Act
    coordinator.handle_canonical_fill_ingress(
        msg, fill_source="trade_executed", process_result=False)

    # Assert
    # shadow mode formal path
    mock_fsm._evt_handlers.on_trade_executed.assert_called_once()
    assert mock_fsm._evt_handlers.on_trade_executed.call_args[1].get(
        'authoritative') is False

    # legacy mutation path
    mock_fsm._evt_handlers.on_order_fill.assert_called_once()
    bookkeeping_msg = mock_fsm._evt_handlers.on_order_fill.call_args[0][0]
    assert bookkeeping_msg.pld["_skip_trade_lifecycle_on_fill"] is True


def test_trade_executed_cutover_true_routes_to_formal(coordinator, mock_fsm):
    # Arrange
    mock_fsm.config.domains.execution_position.trade_executed_cutover_active = True
    msg = Message(op="EVT", verb="TRADE_EXECUTED", src="test", dst="execution_position", pld={
                  "symbol": "BTCUSDT", "qty": "1.0", "price": "50000", "side": "BUY", "orderId": "123"})

    # Act
    coordinator.handle_canonical_fill_ingress(
        msg, fill_source="trade_executed", process_result=False)

    # Assert
    # authoritative formal path
    mock_fsm._evt_handlers.on_trade_executed.assert_called_once()
    assert mock_fsm._evt_handlers.on_trade_executed.call_args[1].get(
        'authoritative') is True

    # legacy mutation path is skipped completely for this event
    mock_fsm._evt_handlers.on_order_fill.assert_not_called()


def test_legacy_fill_source_routes_to_legacy_regardless_of_flag(coordinator, mock_fsm):
    # Arrange
    mock_fsm.config.domains.execution_position.trade_executed_cutover_active = True
    msg = Message(op="EVT", verb="ORDER_FILL", src="test", dst="execution_position", pld={
                  "symbol": "BTCUSDT", "qty": "1.0", "price": "50000", "side": "BUY", "orderId": "123"})

    # Act
    coordinator.handle_canonical_fill_ingress(
        msg, fill_source="order_fill", process_result=False)

    # Assert
    # formal path is not called for legacy fill sources
    mock_fsm._evt_handlers.on_trade_executed.assert_not_called()

    # legacy mutation path is called
    mock_fsm._evt_handlers.on_order_fill.assert_called_once()
