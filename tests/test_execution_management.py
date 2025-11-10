import logging
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.execution_management.execution_management import (
    ExecutionManagement,
)
from vfoundation.core.protocol import Message


class TestExecutionManagement:
    """Test suite for ExecutionManagement component."""

    @pytest.fixture
    def mock_fsm(self):
        """Mock FSM instance."""
        fsm = MagicMock()
        fsm.listen = MagicMock()
        return fsm

    @pytest.fixture
    def config(self):
        """Test configuration."""
        return {
            "execution": {
                "management": {
                    "enabled": True,
                    "forward_to_execution_position": True,
                }
            }
        }

    @pytest.fixture
    def execution_management(self, mock_fsm, config):
        """ExecutionManagement instance with mocked dependencies."""
        return ExecutionManagement(mock_fsm, config)

    def test_initialization(self, mock_fsm, config):
        """Test ExecutionManagement initialization."""
        em = ExecutionManagement(mock_fsm, config)

        assert em.fsm == mock_fsm
        assert em.config == config
        assert hasattr(em, "logger")

        # Verify event subscription
        mock_fsm.listen.assert_called_once_with(
            "EVT:TRADE_INTENT_PROPOSED", em.on_trade_intent
        )

    def test_start_method(self, execution_management, caplog):
        """Test component start method."""
        with caplog.at_level(logging.INFO):
            execution_management.start()

        assert "ExecutionManagement started" in caplog.text

    @patch("apps.reference.domains.execution_management.execution_management.chain_logger")
    def test_on_trade_intent_basic_handling(self, mock_chain_logger, execution_management):
        """Test basic trade intent event handling."""
        trade_intent = {
            "instrument": "BTCUSDT",
            "side": "buy",
            "order": {"qty": "0.001", "price": "50000.0"},
        }
        event = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="execution_management",
            pld=trade_intent
        )

        execution_management.on_trade_intent(event)

        assert mock_chain_logger.info.call_count == 3

        receipt_call = mock_chain_logger.info.call_args_list[0]
        assert receipt_call[1]["extra"]["event_type"] == "EVT:TRADE_INTENT_PROPOSED"
        assert receipt_call[1]["extra"]["domain"] == "execution_management"
        assert receipt_call[1]["extra"]["symbol"] == "BTCUSDT"
        assert receipt_call[1]["extra"]["stage"] == "event_receipt"

        processing_call = mock_chain_logger.info.call_args_list[1]
        assert processing_call[1]["extra"]["stage"] == "event_processing"
        assert processing_call[1]["extra"]["action"] == "trade_intent_received"
        assert processing_call[1]["extra"]["side"] == "buy"
        assert processing_call[1]["extra"]["quantity"] == "0.001"
        assert processing_call[1]["extra"]["price"] == "50000.0"

        forward_call = mock_chain_logger.info.call_args_list[2]
        assert forward_call[1]["extra"]["stage"] == "event_forwarded"
        assert (
            forward_call[1]["extra"]["action"] == "forwarded_to_execution_position"
        )

    @patch("apps.reference.domains.execution_management.execution_management.chain_logger")
    def test_on_trade_intent_missing_fields(self, mock_chain_logger, execution_management):
        """Test trade intent handling with missing fields."""
        trade_intent = {"instrument": "ETHUSDT"}  # missing side and order
        event = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="execution_management",
            pld=trade_intent
        )

        execution_management.on_trade_intent(event)

        processing_call = mock_chain_logger.info.call_args_list[1]
        assert processing_call[1]["extra"]["symbol"] == "ETHUSDT"
        assert processing_call[1]["extra"]["side"] is None
        assert processing_call[1]["extra"]["quantity"] is None
        assert processing_call[1]["extra"]["price"] is None

    @patch("apps.reference.domains.execution_management.execution_management.chain_logger")
    def test_on_trade_intent_unknown_symbol(self, mock_chain_logger, execution_management):
        """Test trade intent handling with unknown/missing symbol."""
        trade_intent = {"side": "sell", "order": {
            "qty": "0.002", "price": "30000.0"}}
        event = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="execution_management",
            pld=trade_intent
        )

        execution_management.on_trade_intent(event)

        receipt_call = mock_chain_logger.info.call_args_list[0]
        assert receipt_call[1]["extra"]["symbol"] == "unknown"

    def test_on_trade_intent_application_logging(self, execution_management, caplog):
        """Test application-level logging during event handling."""
        trade_intent = {
            "instrument": "ADAUSDT",
            "side": "buy",
            "order": {"qty": "100.0", "price": "0.5"},
        }
        event = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="execution_management",
            pld=trade_intent
        )

        with caplog.at_level(logging.INFO):
            execution_management.on_trade_intent(event)

        log_messages = [record.message for record in caplog.records]
        assert "Handling EVT:TRADE_INTENT_PROPOSED..." in log_messages
        assert (
            "Forwarding trade intent for ADAUSDT to execution_position FSM"
            in log_messages
        )
        assert "Trade intent processed: buy 100.0 ADAUSDT" in log_messages

    @patch("apps.reference.domains.execution_management.execution_management.chain_logger")
    def test_on_trade_intent_rid_generation(self, mock_chain_logger, execution_management):
        """Test that unique RIDs are generated for each event."""
        trade_intent = {"instrument": "DOTUSDT", "side": "buy"}

        event1 = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="execution_management",
            pld=trade_intent
        )
        event2 = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="execution_management",
            pld=trade_intent
        )

        execution_management.on_trade_intent(event1)
        execution_management.on_trade_intent(event2)

        rid1 = mock_chain_logger.info.call_args_list[0][1]["extra"]["rid"]
        # next event's first call occurs at index 3 if each event produces 3 calls
        rid2 = mock_chain_logger.info.call_args_list[3][1]["extra"]["rid"]

        assert rid1 != rid2
        assert len(rid1) == 36
        assert len(rid2) == 36

    def test_component_lifecycle(self, execution_management, caplog):
        """Test component start/stop lifecycle."""
        with caplog.at_level(logging.INFO):
            execution_management.start()

        assert "ExecutionManagement started" in caplog.text

    def test_event_subscription_setup(self, mock_fsm, config):
        """Test that event subscriptions are properly configured."""
        em = ExecutionManagement(mock_fsm, config)

        mock_fsm.listen.assert_called_once()
        call_args = mock_fsm.listen.call_args
        assert call_args[0][0] == "EVT:TRADE_INTENT_PROPOSED"
        assert callable(call_args[0][1])

    @patch("apps.reference.domains.execution_management.execution_management.chain_logger")
    def test_chain_logging_structure(self, mock_chain_logger, execution_management):
        """Test that chain logging includes all required fields."""
        trade_intent = {
            "instrument": "LINKUSDT",
            "side": "sell",
            "order": {"qty": "5.0", "price": "15.0"},
        }
        event = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="execution_management",
            pld=trade_intent
        )
        execution_management.on_trade_intent(event)

        required_fields = [
            "rid",
            "event_type",
            "domain",
            "symbol",
            "stage",
            "handler",
        ]
        for call in mock_chain_logger.info.call_args_list:
            extra = call[1]["extra"]
            for field in required_fields:
                assert field in extra, f"Missing required field: {field}"

    def test_config_preservation(self, execution_management, config):
        """Test that configuration is properly stored and accessible."""
        assert execution_management.config == config
        assert execution_management.config["execution"]["management"]["enabled"] is True

    def test_logger_initialization(self, execution_management):
        """Test that logger is properly initialized."""
        expected_name = (
            "apps.reference.domains.execution_management.execution_management."
            "ExecutionManagement"
        )
        assert execution_management.logger.name == expected_name

    @patch("apps.reference.domains.execution_management.execution_management.chain_logger")
    def test_event_processing_order(self, mock_chain_logger, execution_management):
        """Test that events are processed in the correct order."""
        trade_intent = {"instrument": "SOLUSDT", "side": "buy"}
        event = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="execution_management",
            pld=trade_intent
        )

        execution_management.on_trade_intent(event)

        stages = [call[1]["extra"]["stage"]
                  for call in mock_chain_logger.info.call_args_list]
        expected_stages = ["event_receipt",
                           "event_processing", "event_forwarded"]
        assert stages == expected_stages
