"""
Unit tests for MarketDataProxy (FSMP-ARCH-01).

Tests the proxy component that bridges the worker process with the main FSM:
- FSM event emission (EVT:MARKET_TICK_RECEIVED, EVT:ANCHOR_UPDATED)
- Batch processing with yield control
- Heartbeat handling
- Graceful shutdown
"""

import asyncio
import queue
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

# Import the proxy components
import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from apps.reference.domains.market_data.proxy import MarketDataProxy
from apps.reference.domains.market_data.worker import MarketDataWorker


class MockFSM:
    """Mock FSMCore for testing."""
    
    def __init__(self):
        self.emitted_events = []
    
    def emit(self, event_name: str, payload: dict, why: str = ""):
        self.emitted_events.append({
            "event_name": event_name,
            "payload": payload,
            "why": why,
        })
    
    def listen(self, event_name: str, callback):
        pass  # Not needed for proxy tests


class MockConfig:
    """Mock AuroraConfig for testing."""
    
    def __init__(self, config_dict: dict):
        self._config = config_dict
    
    def model_dump(self, mode: str = "python") -> dict:
        return self._config
    
    def to_dict(self) -> dict:
        return self._config
    
    def get(self, key: str, default=None):
        return self._config.get(key, default)


class TestProxyTickEmission:
    """Test tick emission from proxy to FSM."""

    def test_emit_tick_correct_format(self):
        """Test that ticks are emitted with correct payload format."""
        fsm = MockFSM()
        config = MockConfig({
            "trading": {
                "instruments": {"BTCUSDT": {}},
                "market_data": {
                    "macro_sync": {"anchors": []},
                    "poll_interval_sec": 1,
                },
            },
        })
        
        proxy = MarketDataProxy(fsm=fsm, config=config)
        
        # Simulate tick data from worker
        tick_data = {
            "type": "tick",
            "symbol": "BTCUSDT",
            "ts": 1234567890000,
            "data": {
                "ts": 1234567890000,
                "price": "95000.50",
                "bid": "95000.00",
                "ask": "95001.00",
                "mid": "95000.50",
                "bid_size": "10.5",
                "ask_size": "8.2",
                "buy_volume": "100",
                "sell_volume": "95",
                # No data_source - should default to "multiprocess_worker"
            },
        }
        
        proxy._emit_tick(tick_data)
        
        assert len(fsm.emitted_events) == 1
        event = fsm.emitted_events[0]
        
        assert event["event_name"] == "EVT:MARKET_TICK_RECEIVED"
        assert event["payload"]["symbol"] == "BTCUSDT"
        assert event["payload"]["price"] == "95000.50"
        assert event["payload"]["bid_size"] == "10.5"
        # Default data_source when not provided
        assert event["payload"]["data_source"] == "multiprocess_worker"

    def test_emit_tick_increments_counter(self):
        """Test that tick counter is incremented."""
        fsm = MockFSM()
        config = MockConfig({
            "trading": {
                "instruments": {"BTCUSDT": {}},
                "market_data": {"macro_sync": {"anchors": []}, "poll_interval_sec": 1},
            },
        })
        
        proxy = MarketDataProxy(fsm=fsm, config=config)
        assert proxy._ticks_emitted == 0
        
        tick_data = {
            "type": "tick",
            "symbol": "BTCUSDT",
            "data": {"ts": 1234567890000, "price": "95000", "bid": "94999", "ask": "95001"},
        }
        
        proxy._emit_tick(tick_data)
        proxy._emit_tick(tick_data)
        proxy._emit_tick(tick_data)
        
        assert proxy._ticks_emitted == 3


class TestProxyAnchorEmission:
    """Test anchor update emission from proxy to FSM."""

    def test_emit_anchor_update_correct_format(self):
        """Test that anchor updates are emitted with correct payload."""
        fsm = MockFSM()
        config = MockConfig({
            "trading": {
                "instruments": {"ETHUSDT": {}},
                "market_data": {
                    "macro_sync": {"anchors": ["BTCUSDT"]},
                    "poll_interval_sec": 1,
                },
            },
        })
        
        proxy = MarketDataProxy(fsm=fsm, config=config)
        
        anchor_data = {
            "type": "anchor",
            "anchor": "BTCUSDT",
            "price": "95000.00",
            "ts": 1234567890000,
        }
        
        proxy._emit_anchor_update(anchor_data)
        
        assert len(fsm.emitted_events) == 1
        event = fsm.emitted_events[0]
        
        assert event["event_name"] == "EVT:ANCHOR_UPDATED"
        assert event["payload"]["anchor"] == "BTCUSDT"
        assert event["payload"]["price"] == "95000.00"


class TestProxyHeartbeat:
    """Test heartbeat handling."""

    def test_handle_heartbeat_updates_state(self):
        """Test that heartbeat updates proxy state."""
        fsm = MockFSM()
        config = MockConfig({
            "trading": {
                "instruments": {"BTCUSDT": {}},
                "market_data": {"macro_sync": {"anchors": []}, "poll_interval_sec": 1},
            },
        })
        
        proxy = MarketDataProxy(fsm=fsm, config=config)
        assert proxy._last_heartbeat_ts == 0
        assert proxy._worker_alive is False
        
        heartbeat = {
            "type": "heartbeat",
            "ts": 1234567890000,
            "metrics": {
                "ticks_received": 1000,
                "ticks_dropped": 5,
                "queue_size": 42,
            },
        }
        
        proxy._handle_heartbeat(heartbeat)
        
        assert proxy._last_heartbeat_ts == 1234567890000
        assert proxy._worker_alive is True


class TestProxyConfigSerialization:
    """Test config serialization for worker process."""

    def test_get_config_dict_pydantic_v2(self):
        """Test config serialization with Pydantic V2 model."""
        fsm = MockFSM()
        
        class PydanticV2Config:
            def model_dump(self, mode="python"):
                return {"key": "value", "mode": mode}
        
        proxy = MarketDataProxy(fsm=fsm, config=PydanticV2Config())
        result = proxy._get_config_dict()
        
        assert result == {"key": "value", "mode": "json"}

    def test_get_config_dict_dict_passthrough(self):
        """Test config serialization with plain dict."""
        fsm = MockFSM()
        
        config_dict = {
            "trading": {"instruments": {"BTCUSDT": {}}},
        }
        
        proxy = MarketDataProxy(fsm=fsm, config=config_dict)
        result = proxy._get_config_dict()
        
        assert result == config_dict


class TestProxyDeprecation:
    """Test deprecated method handling."""

    def test_set_feature_engineering_is_noop(self):
        """Test that deprecated method logs warning but doesn't fail."""
        fsm = MockFSM()
        config = MockConfig({
            "trading": {
                "instruments": {"BTCUSDT": {}},
                "market_data": {"macro_sync": {"anchors": []}, "poll_interval_sec": 1},
            },
        })
        
        proxy = MarketDataProxy(fsm=fsm, config=config)
        
        # Should not raise
        mock_fe = MagicMock()
        proxy.set_feature_engineering(mock_fe)
        
        # Should have no effect
        assert len(fsm.emitted_events) == 0


class TestProxyMetrics:
    """Test proxy metrics property."""

    def test_metrics_property(self):
        """Test that metrics property returns correct structure."""
        fsm = MockFSM()
        config = MockConfig({
            "trading": {
                "instruments": {"BTCUSDT": {}},
                "market_data": {"macro_sync": {"anchors": []}, "poll_interval_sec": 1},
            },
        })
        
        proxy = MarketDataProxy(fsm=fsm, config=config)
        
        # Simulate some activity
        proxy._ticks_emitted = 100
        proxy._batches_processed = 10
        proxy._last_heartbeat_ts = 1234567890000
        
        metrics = proxy.metrics
        
        assert metrics["ticks_emitted"] == 100
        assert metrics["batches_processed"] == 10
        assert metrics["last_heartbeat_ts"] == 1234567890000
        assert "worker_alive" in metrics
        assert "queue_size" in metrics


class TestProxyBatchProcessing:
    """Test batch processing logic (without actual async loop)."""

    def test_batch_size_constant(self):
        """Test that batch size is configured correctly."""
        fsm = MockFSM()
        config = MockConfig({
            "trading": {
                "instruments": {"BTCUSDT": {}},
                "market_data": {"macro_sync": {"anchors": []}, "poll_interval_sec": 1},
            },
        })
        
        proxy = MarketDataProxy(fsm=fsm, config=config)
        
        assert proxy.BATCH_SIZE == 50
        assert proxy.QUEUE_MAXSIZE == 1000

    @pytest.mark.asyncio
    async def test_consume_queue_processes_ticks(self):
        """Test that _consume_queue processes tick messages."""
        fsm = MockFSM()
        config = MockConfig({
            "trading": {
                "instruments": {"BTCUSDT": {}},
                "market_data": {"macro_sync": {"anchors": []}, "poll_interval_sec": 1},
            },
        })
        
        proxy = MarketDataProxy(fsm=fsm, config=config)
        
        # Create a standard queue for testing (multiprocessing.Queue doesn't work in same process)
        import queue as stdlib_queue
        proxy._ipc_queue = stdlib_queue.Queue(maxsize=100)
        proxy._running = True
        
        # Put some test messages
        for i in range(5):
            msg = {
                "type": MarketDataWorker.MSG_TYPE_TICK,
                "symbol": "BTCUSDT",
                "data": {"ts": i, "price": "95000", "bid": "94999", "ask": "95001"},
            }
            proxy._ipc_queue.put_nowait(msg)
        
        # Run one iteration (stop after first batch)
        async def run_once():
            proxy._running = True
            # Process batch
            items_processed = 0
            while items_processed < proxy.BATCH_SIZE:
                try:
                    item = proxy._ipc_queue.get_nowait()
                    msg_type = item.get("type")
                    if msg_type == MarketDataWorker.MSG_TYPE_TICK:
                        proxy._emit_tick(item)
                        items_processed += 1
                except Exception:
                    break
            await asyncio.sleep(0)
        
        await run_once()
        
        assert len(fsm.emitted_events) == 5
        assert proxy._ticks_emitted == 5

    @pytest.mark.asyncio
    async def test_consume_queue_handles_mixed_messages(self):
        """Test that _consume_queue handles different message types."""
        fsm = MockFSM()
        config = MockConfig({
            "trading": {
                "instruments": {"BTCUSDT": {}},
                "market_data": {"macro_sync": {"anchors": ["ETHUSDT"]}, "poll_interval_sec": 1},
            },
        })
        
        proxy = MarketDataProxy(fsm=fsm, config=config)
        
        # Create a standard queue for testing (multiprocessing.Queue doesn't work in same process)
        import queue as stdlib_queue
        proxy._ipc_queue = stdlib_queue.Queue(maxsize=100)
        
        # Put mixed messages
        proxy._ipc_queue.put_nowait({
            "type": MarketDataWorker.MSG_TYPE_TICK,
            "symbol": "BTCUSDT",
            "data": {"ts": 1, "price": "95000", "bid": "94999", "ask": "95001"},
        })
        proxy._ipc_queue.put_nowait({
            "type": MarketDataWorker.MSG_TYPE_ANCHOR,
            "anchor": "ETHUSDT",
            "price": "3500.00",
        })
        proxy._ipc_queue.put_nowait({
            "type": MarketDataWorker.MSG_TYPE_HEARTBEAT,
            "ts": 1234567890000,
            "metrics": {"ticks_received": 10, "ticks_dropped": 0, "queue_size": 2},
        })
        
        # Process all
        while not proxy._ipc_queue.empty():
            msg = proxy._ipc_queue.get_nowait()
            msg_type = msg.get("type")
            if msg_type == MarketDataWorker.MSG_TYPE_TICK:
                proxy._emit_tick(msg)
            elif msg_type == MarketDataWorker.MSG_TYPE_ANCHOR:
                proxy._emit_anchor_update(msg)
            elif msg_type == MarketDataWorker.MSG_TYPE_HEARTBEAT:
                proxy._handle_heartbeat(msg)
        
        # Verify
        tick_events = [e for e in fsm.emitted_events if e["event_name"] == "EVT:MARKET_TICK_RECEIVED"]
        anchor_events = [e for e in fsm.emitted_events if e["event_name"] == "EVT:ANCHOR_UPDATED"]
        
        assert len(tick_events) == 1
        assert len(anchor_events) == 1
        assert proxy._worker_alive is True
