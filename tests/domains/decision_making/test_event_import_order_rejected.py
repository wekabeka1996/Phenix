import pytest
from unittest.mock import MagicMock
from vfoundation.core.protocol import Message
from apps.reference.domains.strategies.runtimes.md_amr.handler import MDAMRHandler

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

class TestEventImportOrderRejected:
    
    @pytest.fixture
    def handler(self):
        config = DummyConfig()
        
        fsm_mock = MagicMock()
        h = MDAMRHandler(config=config, fsm=fsm_mock)
        h._enabled = True
        h._enabled_symbols = {"BTCUSDT"}
        return h

    def test_order_rejected_unrelated_reason_ignored(self, handler):
        event = Message(
            name="EVT:ORDER_REJECTED", op="EVT", verb="ORDER_REJECTED", src="execution", dst="decision_making",
            pld={
                "symbol": "BTCUSDT",
                "reject_reason": "INSUFFICIENT_FUNDS"
            }
        )
        handler._on_order_rejected(event)
        assert handler._gtx_retries.get("BTCUSDT", 0) == 0

    def test_order_rejected_gtx_retry_incremented(self, handler):
        event = Message(
            name="EVT:ORDER_REJECTED", op="EVT", verb="ORDER_REJECTED", src="execution", dst="decision_making",
            pld={
                "symbol": "BTCUSDT",
                "reject_reason": "POST_ONLY_REJECT"
            }
        )
        # Retry 1
        handler._on_order_rejected(event)
        assert handler._gtx_retries.get("BTCUSDT") == 1

        # Retry 2
        handler._on_order_rejected(event)
        assert handler._gtx_retries.get("BTCUSDT") == 2

    def test_order_rejected_gtx_fallback_resets_retries(self, handler):
        event = Message(
            name="EVT:ORDER_REJECTED", op="EVT", verb="ORDER_REJECTED", src="execution", dst="decision_making",
            pld={
                "symbol": "BTCUSDT",
                "reject_reason": "POST_ONLY_REJECT"
            }
        )
        # max_retries is 2
        handler._on_order_rejected(event) # retry = 1
        handler._on_order_rejected(event) # retry = 2
        
        # This one trips the fallback block
        handler._on_order_rejected(event) 
        # Fallback tracking resets to 0
        assert handler._gtx_retries.get("BTCUSDT") == 0

    def test_order_rejected_gtx_no_fallback_resets_retries(self, handler):
        handler._cfg.execution.emit_market_fallback_marker_on_retry_exhaustion = False
        event = Message(
            name="EVT:ORDER_REJECTED", op="EVT", verb="ORDER_REJECTED", src="execution", dst="decision_making",
            pld={
                "symbol": "BTCUSDT",
                "reject_reason": "POST_ONLY_REJECT"
            }
        )
        handler._gtx_retries["BTCUSDT"] = 2
        handler._on_order_rejected(event) 
        assert handler._gtx_retries.get("BTCUSDT") == 0
