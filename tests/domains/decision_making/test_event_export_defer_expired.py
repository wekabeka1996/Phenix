import pytest
from unittest.mock import MagicMock
from apps.reference.domains.decision_making.md_amr_handler import MDAMRHandler

class DummyExecution:
    gtx_retry_max = 2
    emit_market_fallback_marker_on_retry_exhaustion = True

class DummyMDAMRConfig:
    enabled = False
    timeframe_sec = 900
    defer_ttl_sec = 60
    execution = DummyExecution()
    assets = {}

class DummyStrategies:
    md_amr = DummyMDAMRConfig()

class DummyConfig:
    execution = DummyExecution()
    strategies = DummyStrategies()

class TestEventExportDeferExpired:
    
    @pytest.fixture
    def mock_fsm(self):
        return MagicMock()

    @pytest.fixture
    def handler(self, mock_fsm):
        h = MDAMRHandler(config=DummyConfig(), fsm=mock_fsm)
        # Override enablement
        h._enabled = True
        h._enabled_symbols = {"BTCUSDT"}
        h._cfg = DummyMDAMRConfig()
        return h

    def test_feature_defer_expired_emitted(self, handler, mock_fsm):
        """
        Prove that when a deferred feature state exceeds its TTL,
        the md_amr_handler emits EVT:FEATURE_DEFER_EXPIRED to clear it.
        """
        symbol = "BTCUSDT"
        now_ms = 1000000
        
        # 1. Register a defer
        handler._register_defer(symbol=symbol, rid="RID-123", missing_fields=["orderbook_imbalance"], now_ms=now_ms)
        
        # Should be stored in memory
        assert symbol in handler._deferred
        assert handler._deferred[symbol]["expires_ts_ms"] == now_ms + (60 * 1000)
        
        # 2. Try expiring before TTL
        handler._expire_defer_if_needed(symbol, now_ms=now_ms + 1000)
        mock_fsm.emit.assert_not_called()
        assert symbol in handler._deferred # still there
        
        # 3. Fast forward beyond TTL 
        handler._expire_defer_if_needed(symbol, now_ms=now_ms + 61000)
        
        # 4. Verify emit
        mock_fsm.emit.assert_called_once()
        args, kwargs = mock_fsm.emit.call_args
        assert args[0] == "EVT:FEATURE_DEFER_EXPIRED"
        
        payload = args[1] if len(args) > 1 else kwargs.get("payload", {})
        assert payload["symbol"] == "BTCUSDT"
        assert payload["rid"] == "RID-123"
        assert payload["reason_code"] == "FEATURE_DEFER_EXPIRED"
        assert "orderbook_imbalance" in payload["missing_fields"]
        
        # Assert memory cleared
        assert symbol not in handler._deferred
