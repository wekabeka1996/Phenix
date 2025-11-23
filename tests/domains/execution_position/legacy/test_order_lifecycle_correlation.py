#!/usr/bin/env python3
"""
Integration tests for order lifecycle correlation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from vfoundation.core.protocol import Message
from vfoundation.obs.correlation import CorrelationStore
# ExecPosFSM is legacy monolithic FSM - not used in V2
# from apps.reference.domains.execution_position.legacy.fsm import ExecPosFSM
from apps.reference.domains.execution_position.legacy.fsm_open import OpenFlowFSM
from apps.reference.domains.account_observer.account_observer import AccountObserver

pytestmark = pytest.mark.execpos_legacy


@pytest.mark.skip(reason="Legacy ExecPosFSM removed - needs V2 migration")
class TestOrderLifecycleCorrelation:
    """Test end-to-end correlation through order lifecycle."""

    def test_correlation_through_open_flow(self):
        """Test that corr_id and oco_group_id are generated in DEC:OPEN."""
        config = {"trading": {"execution": {
            "cooldown_ms": 1000, "guard_enabled": False}}}
        open_fsm = OpenFlowFSM(config=config)

        msg = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",
            dst="execution_position",
            rid="test-rid-123",
            pld={
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price": "50000",
                "order_type": "LIMIT"
            }
        )

        result = open_fsm.handle(msg)

        assert result is not None
        assert result.op == "DEC"
        assert result.verb == "OPEN"
        assert result.corr_id is not None
        assert result.oco_group_id is not None
        assert result.rid == "test-rid-123"

    def test_correlation_store_integration(self):
        """Test correlation store put/get operations."""
        store = CorrelationStore()

        # Simulate entry order ACK
        entry_order_id = "12345"
        entry_data = {
            'corr_id': 'corr-uuid-1',
            'oco_group_id': 'oco-uuid-1',
            'rid': 'rid-123',
            'parent_client_order_id': None
        }
        store.put_entry_ack(entry_order_id, entry_data)

        # Simulate SL order ACK
        sl_order_id = "67890"
        store.put_sl_tp_ack(sl_order_id, "entry-client-123",
                            'corr-uuid-1', 'oco-uuid-1', 'rid-123')

        # Verify retrieval
        entry_corr = store.get_by_order_id(entry_order_id)
        sl_corr = store.get_by_order_id(sl_order_id)

        assert entry_corr['corr_id'] == 'corr-uuid-1'
        assert sl_corr['parent_client_order_id'] == "entry-client-123"
        assert sl_corr['corr_id'] == 'corr-uuid-1'

    def test_account_observer_fill_correlation(self):
        """Test that AccountObserver emits correlated EVT:TRADE_EXECUTED payloads."""
        # Mock FSM
        mock_fsm = MagicMock()
        mock_fsm.emit = MagicMock()

        # Setup config
        config = {
            "binance_api": {"testnet": {"api_key": "test", "api_secret": "test"}},
            "account_observer": {}
        }

        # Mock Binance client
        mock_client = MagicMock()
        mock_client.get_my_trades.return_value = [{
            "id": 12345,
            "orderId": "12345",
            "symbol": "BTCUSDT",
            "price": "50000",
            "qty": "0.001",
            "quoteQty": "50.0",
            "commission": "0.0001",
            "commissionAsset": "BTC",
            "time": 1640995200000,
            "isBuyer": True,
            "isMaker": False,
            "isBestMatch": True
        }]

        observer = AccountObserver(mock_fsm, config)
        observer.client = mock_client
        observer.correlation_store = CorrelationStore()

        # Add correlation data
        observer.correlation_store.put_entry_ack("12345", {
            'corr_id': 'corr-uuid-1',
            'oco_group_id': 'oco-uuid-1',
            'rid': 'rid-123'
        })

        # Process trades
        observer._process_trades(
            mock_client.get_my_trades.return_value, "binance")

        calls = mock_fsm.emit.call_args_list
        expected_calls = 2 if observer.emit_legacy_fill else 1
        assert len(calls) == expected_calls

        trade_call = calls[0]
        assert trade_call.args[0] == "EVT:TRADE_EXECUTED"
        trade_payload = trade_call.kwargs["payload"]
        assert trade_payload["corr_id"] == 'corr-uuid-1'
        assert trade_payload["link_fill_id"] == '12345'
        assert trade_payload["oco_group_id"] == 'oco-uuid-1'
        assert trade_payload["symbol"] == 'BTCUSDT'

        if observer.emit_legacy_fill:
            legacy_call = calls[1]
            assert legacy_call.args[0] == "EVT:FILL"
            legacy_payload = legacy_call.kwargs["payload"]
            assert legacy_payload == trade_payload

    def test_correlation_persistence(self):
        """Test that correlation IDs persist through the entire flow."""
        # This would be a full integration test with mocked adapter
        # For now, just verify the data structures are correct

        corr_id = "test-corr-123"
        oco_group_id = "test-oco-456"

        # DEC:OPEN should have corr_id and oco_group_id
        dec_msg = Message(
            op="DEC",
            verb="OPEN",
            src="execution_position",
            dst="binance_adapter",
            corr_id=corr_id,
            oco_group_id=oco_group_id,
            pld={"symbol": "BTCUSDT", "side": "BUY", "qty": "0.001"}
        )

        assert dec_msg.corr_id == corr_id
        assert dec_msg.oco_group_id == oco_group_id

        # EVT:FILL should include corr_id
        fill_msg = Message(
            op="EVT",
            verb="FILL",
            src="account_observer",
            dst="decision_making",
            corr_id=corr_id,
            link_fill_id="12345",
            pld={"symbol": "BTCUSDT", "side": "BUY",
                 "qty": "0.001", "price": "50000"}
        )

        assert fill_msg.corr_id == corr_id
        assert fill_msg.link_fill_id == "12345"
