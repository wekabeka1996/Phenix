"""
EP-01.5 + EP-01.6: WS-path GTX EXPIRED / 0 fill -> MAKER_ONLY_REJECT Tests

Tests:
1. GTX order EXPIRED with 0 fill -> MAKER_ONLY_REJECT detected
2. Non-GTX EXPIRED should NOT trigger MAKER_ONLY_REJECT
3. Non-ENTRY EXPIRED should NOT trigger MAKER_ONLY_REJECT
4. FILLED GTX should NOT trigger MAKER_ONLY_REJECT
5. EP-01.6: filled_qty="" or None doesn't crash
6. EP-01.6: order_kind="ENTRY" without "ENTRY" in clientOrderId works
7. EP-01.6: exit order with tif=GTX EXPIRED 0 fill doesn't trigger

USAGE: pytest tests/integration/test_ep01_5_ws_expired_maker_reject.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
import time


class MockOrderRef:
    """Mock order reference for testing."""
    def __init__(self, rid: str, idempotent_key: str, order_kind: str = None, 
                 clientOrderId: str = None, order_type: str = None):
        self.rid = rid
        self.idempotent_key = idempotent_key
        self.created_ts = time.time() - 10  # 10 seconds ago
        # EP-01.6: Add order_kind field
        self.order_kind = order_kind
        self.clientOrderId = clientOrderId
        self.order_type = order_type


class MockOrderIndex:
    """Mock order index for testing."""
    def __init__(self, order_ref: MockOrderRef = None):
        self._order_ref = order_ref
    
    def get(self, clientOrderId=None, exchangeOrderId=None):
        return self._order_ref
    
    def mark_terminal(self, ref):
        pass


# ============================================================================
# Test 1: GTX EXPIRED with 0 fill → MAKER_ONLY_REJECT
# ============================================================================

class TestGtxExpiredMakerOnlyReject:
    """Tests for GTX EXPIRED detection."""
    
    def test_gtx_expired_zero_fill_is_maker_only_reject(self):
        """GTX order EXPIRED with 0 fill should be detected as MAKER_ONLY_REJECT."""
        from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
        
        # Setup mock FSM core
        mock_fsm = MagicMock()
        mock_order_ref = MockOrderRef(
            rid="test_rid_123", 
            idempotent_key="idem_key_123",
            order_kind="ENTRY",  # EP-01.6: explicit order_kind
            clientOrderId="ENTRY_BTC_123"
        )
        mock_fsm.order_index = MockOrderIndex(mock_order_ref)
        mock_fsm.emit = MagicMock()
        
        # Create WS client
        ws_client = BinanceWebSocketClient(
            api_key="test_key",
            base_url="https://testnet.binancefuture.com",
            use_testnet=True,
            fsm_core=mock_fsm
        )
        
        # Simulate WS message: GTX order EXPIRED with 0 fill
        ws_msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": int(time.time() * 1000),
            "o": {
                "s": "BTCUSDT",
                "c": "ENTRY_BTC_123",  # Client order ID contains ENTRY
                "i": "12345678",  # Exchange order ID
                "X": "EXPIRED",  # Status
                "S": "BUY",  # Side
                "o": "LIMIT",  # Order type
                "z": "0",  # Filled qty = 0
                "f": "GTX",  # timeInForce = GTX (post-only)
                "q": "0.01",  # Original qty
                "p": "42000.00",  # Price
            }
        }
        
        # Process message
        ws_client._handle_order_trade_update(ws_msg)
        
        # Verify emit was called with EVT:ORDER_REJECTED
        mock_fsm.emit.assert_called_once()
        call_args = mock_fsm.emit.call_args
        
        assert call_args[0][0] == "EVT:ORDER_REJECTED"
        payload = call_args[0][1]
        assert payload["reason"] == "MAKER_ONLY_REJECT"
        assert payload["reject_reason"] == "MAKER_ONLY_REJECT"
        assert payload["reject_reason_normalized"] == "MAKER_ONLY_REJECT"
        assert payload["reject_reason_source"] == "reason"
        assert payload["fallback"] == "NONE"
        assert payload["time_in_force"] == "GTX"
        assert payload["status"] == "EXPIRED"
        assert payload["terminal_non_fill"] is True
        assert payload["terminal_state_kind"] == "REJECTED"
        assert payload["identity_quality"] == "order_identity_exact"
        assert payload["order_id"] == "12345678"
        assert payload["client_order_id"] == "ENTRY_BTC_123"
        assert payload["event_ts_ms"] == payload["ts_ms"]
        assert payload["compatibility_aliases_retained"] is True


# ============================================================================
# Test 2: Non-GTX EXPIRED should NOT trigger MAKER_ONLY_REJECT
# ============================================================================

class TestNonGtxExpiredNoMakerReject:
    """Non-GTX EXPIRED should not be MAKER_ONLY_REJECT."""
    
    def test_gtc_expired_is_not_maker_only_reject(self):
        """GTC order EXPIRED should NOT be MAKER_ONLY_REJECT."""
        from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
        
        mock_fsm = MagicMock()
        mock_order_ref = MockOrderRef(
            rid="test_rid_456", 
            idempotent_key="idem_key_456",
            order_kind="ENTRY",
            clientOrderId="ENTRY_BTC_456"
        )
        mock_fsm.order_index = MockOrderIndex(mock_order_ref)
        mock_fsm.emit = MagicMock()
        
        ws_client = BinanceWebSocketClient(
            api_key="test_key",
            base_url="https://testnet.binancefuture.com",
            use_testnet=True,
            fsm_core=mock_fsm
        )
        
        # Simulate WS message: GTC (not GTX) order EXPIRED
        ws_msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": int(time.time() * 1000),
            "o": {
                "s": "BTCUSDT",
                "c": "ENTRY_BTC_456",
                "i": "12345679",
                "X": "EXPIRED",
                "S": "BUY",
                "o": "LIMIT",
                "z": "0",
                "f": "GTC",  # NOT GTX
                "q": "0.01",
                "p": "42000.00",
            }
        }
        
        ws_client._handle_order_trade_update(ws_msg)
        
        # Should emit ORDER_STATE_CHANGED, NOT ORDER_REJECTED
        mock_fsm.emit.assert_called_once()
        call_args = mock_fsm.emit.call_args
        
        assert call_args[0][0] == "EVT:ORDER_STATE_CHANGED"
        payload = call_args[0][1]
        assert payload.get("reason") is None  # No MAKER_ONLY_REJECT reason


# ============================================================================
# Test 3: Non-ENTRY EXPIRED should NOT trigger MAKER_ONLY_REJECT
# ============================================================================

class TestNonEntryExpiredNoMakerReject:
    """Non-ENTRY orders should not trigger MAKER_ONLY_REJECT."""
    
    def test_tp_expired_gtx_is_not_maker_only_reject(self):
        """TP order (not ENTRY) EXPIRED with GTX should NOT be MAKER_ONLY_REJECT."""
        from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
        
        mock_fsm = MagicMock()
        mock_order_ref = MockOrderRef(
            rid="test_rid_789", 
            idempotent_key="idem_key_789",
            order_kind="TP",  # EP-01.6: not ENTRY
            clientOrderId="TP_BTC_789"
        )
        mock_fsm.order_index = MockOrderIndex(mock_order_ref)
        mock_fsm.emit = MagicMock()
        
        ws_client = BinanceWebSocketClient(
            api_key="test_key",
            base_url="https://testnet.binancefuture.com",
            use_testnet=True,
            fsm_core=mock_fsm
        )
        
        # Simulate WS message: TP (not ENTRY) order EXPIRED with GTX
        ws_msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": int(time.time() * 1000),
            "o": {
                "s": "BTCUSDT",
                "c": "TP_BTC_789",  # TP order, NOT ENTRY
                "i": "12345680",
                "X": "EXPIRED",
                "S": "SELL",
                "o": "LIMIT",
                "z": "0",
                "f": "GTX",
                "q": "0.01",
                "p": "45000.00",
            }
        }
        
        ws_client._handle_order_trade_update(ws_msg)
        
        # Should emit ORDER_STATE_CHANGED, NOT ORDER_REJECTED
        mock_fsm.emit.assert_called_once()
        call_args = mock_fsm.emit.call_args
        
        assert call_args[0][0] == "EVT:ORDER_STATE_CHANGED"


# ============================================================================
# Test 4: GTX FILLED should NOT trigger MAKER_ONLY_REJECT
# ============================================================================

class TestGtxFilledNoMakerReject:
    """GTX FILLED orders should not be MAKER_ONLY_REJECT."""
    
    def test_gtx_filled_is_not_maker_only_reject(self):
        """GTX order that got FILLED should NOT be MAKER_ONLY_REJECT."""
        from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
        
        mock_fsm = MagicMock()
        mock_order_ref = MockOrderRef(
            rid="test_rid_aaa", 
            idempotent_key="idem_key_aaa",
            order_kind="ENTRY",
            clientOrderId="ENTRY_BTC_AAA"
        )
        mock_fsm.order_index = MockOrderIndex(mock_order_ref)
        mock_fsm.emit = MagicMock()
        
        ws_client = BinanceWebSocketClient(
            api_key="test_key",
            base_url="https://testnet.binancefuture.com",
            use_testnet=True,
            fsm_core=mock_fsm
        )
        
        # Simulate WS message: GTX order FILLED (not EXPIRED)
        ws_msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": int(time.time() * 1000),
            "o": {
                "s": "BTCUSDT",
                "c": "ENTRY_BTC_AAA",
                "i": "12345681",
                "X": "FILLED",  # FILLED, not EXPIRED
                "S": "BUY",
                "o": "LIMIT",
                "z": "0.01",  # Filled qty > 0
                "f": "GTX",
                "q": "0.01",
                "p": "42000.00",
            }
        }
        
        ws_client._handle_order_trade_update(ws_msg)
        
        # Should emit TRADE_EXECUTED, NOT ORDER_REJECTED
        mock_fsm.emit.assert_called_once()
        call_args = mock_fsm.emit.call_args
        
        assert call_args[0][0] == "EVT:TRADE_EXECUTED"


# ============================================================================
# Test 5: Reason SSOT usage
# ============================================================================

class TestReasonSSOTUsage:
    """Tests that MAKER_ONLY_REJECT uses SSOT constant."""
    
    def test_reason_constant_imported(self):
        """MAKER_ONLY_REJECT should be importable from reasons module."""
        from apps.reference.domains.execution_position.reasons import MAKER_ONLY_REJECT
        
        assert MAKER_ONLY_REJECT == "MAKER_ONLY_REJECT"


# ============================================================================
# EP-01.6: Edge case tests
# ============================================================================

class TestEP016EdgeCases:
    """EP-01.6: Edge cases for robust maker-only detection."""
    
    def test_filled_qty_empty_string_no_crash(self):
        """filled_qty="" should not crash WS handler (fail-closed, no maker-only reject)."""
        from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
        
        mock_fsm = MagicMock()
        mock_order_ref = MockOrderRef(
            rid="test_rid_edge1", 
            idempotent_key="idem_key_edge1",
            order_kind="ENTRY",
            clientOrderId="ENTRY_EDGE_1"
        )
        mock_fsm.order_index = MockOrderIndex(mock_order_ref)
        mock_fsm.emit = MagicMock()
        
        ws_client = BinanceWebSocketClient(
            api_key="test_key",
            base_url="https://testnet.binancefuture.com",
            use_testnet=True,
            fsm_core=mock_fsm
        )
        
        # Simulate WS message: filled_qty is empty string
        ws_msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": int(time.time() * 1000),
            "o": {
                "s": "BTCUSDT",
                "c": "ENTRY_EDGE_1",
                "i": "12345682",
                "X": "EXPIRED",
                "S": "BUY",
                "o": "LIMIT",
                "z": "",  # Empty string - edge case
                "f": "GTX",
                "q": "0.01",
                "p": "42000.00",
            }
        }
        
        # Should NOT crash
        ws_client._handle_order_trade_update(ws_msg)
        
        # Should emit ORDER_STATE_CHANGED (fail-closed: empty qty = no maker-only reject)
        mock_fsm.emit.assert_called_once()
        call_args = mock_fsm.emit.call_args
        assert call_args[0][0] == "EVT:ORDER_STATE_CHANGED"
    
    def test_order_kind_entry_without_entry_in_clientorderid(self):
        """order_kind='ENTRY' without 'ENTRY' in clientOrderId should trigger maker-only reject."""
        from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
        
        mock_fsm = MagicMock()
        # EP-01.6: order_kind=ENTRY but clientOrderId doesn't contain "ENTRY"
        mock_order_ref = MockOrderRef(
            rid="test_rid_edge2", 
            idempotent_key="idem_key_edge2",
            order_kind="ENTRY",  # SSOT: this is an ENTRY order
            clientOrderId="BTC_LIMIT_ORDER_123"  # No "ENTRY" in name
        )
        mock_fsm.order_index = MockOrderIndex(mock_order_ref)
        mock_fsm.emit = MagicMock()
        
        ws_client = BinanceWebSocketClient(
            api_key="test_key",
            base_url="https://testnet.binancefuture.com",
            use_testnet=True,
            fsm_core=mock_fsm
        )
        
        # Simulate WS message
        ws_msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": int(time.time() * 1000),
            "o": {
                "s": "BTCUSDT",
                "c": "BTC_LIMIT_ORDER_123",  # No "ENTRY" - but order_kind says ENTRY
                "i": "12345683",
                "X": "EXPIRED",
                "S": "BUY",
                "o": "LIMIT",
                "z": "0",
                "f": "GTX",
                "q": "0.01",
                "p": "42000.00",
            }
        }
        
        ws_client._handle_order_trade_update(ws_msg)
        
        # Should detect as MAKER_ONLY_REJECT via order_kind
        mock_fsm.emit.assert_called_once()
        call_args = mock_fsm.emit.call_args
        assert call_args[0][0] == "EVT:ORDER_REJECTED"
        assert call_args[0][1]["reason"] == "MAKER_ONLY_REJECT"
    
    def test_exit_order_gtx_expired_no_maker_reject(self):
        """Exit order (order_kind='EXIT') with GTX EXPIRED 0 fill should NOT trigger MAKER_ONLY_REJECT."""
        from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
        
        mock_fsm = MagicMock()
        mock_order_ref = MockOrderRef(
            rid="test_rid_edge3", 
            idempotent_key="idem_key_edge3",
            order_kind="EXIT",  # Not ENTRY
            clientOrderId="EXIT_BTC_123"
        )
        mock_fsm.order_index = MockOrderIndex(mock_order_ref)
        mock_fsm.emit = MagicMock()
        
        ws_client = BinanceWebSocketClient(
            api_key="test_key",
            base_url="https://testnet.binancefuture.com",
            use_testnet=True,
            fsm_core=mock_fsm
        )
        
        ws_msg = {
            "e": "ORDER_TRADE_UPDATE",
            "T": int(time.time() * 1000),
            "o": {
                "s": "BTCUSDT",
                "c": "EXIT_BTC_123",
                "i": "12345684",
                "X": "EXPIRED",
                "S": "SELL",
                "o": "LIMIT",
                "z": "0",
                "f": "GTX",
                "q": "0.01",
                "p": "45000.00",
            }
        }
        
        ws_client._handle_order_trade_update(ws_msg)
        
        # Should NOT trigger MAKER_ONLY_REJECT (exit orders are different)
        mock_fsm.emit.assert_called_once()
        call_args = mock_fsm.emit.call_args
        assert call_args[0][0] == "EVT:ORDER_STATE_CHANGED"

