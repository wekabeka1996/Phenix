"""
Unit tests for MarketDataWorker (FSMP-ARCH-01).

Tests the isolated market data worker process:
- IPC queue communication
- Backpressure (drop-oldest policy)
- Message types (tick, anchor, heartbeat)

Note: Uses queue.Queue instead of multiprocessing.Queue for unit tests
because multiprocessing.Queue requires separate processes to function correctly.
"""

import queue
import time
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

# Import the worker components
import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from apps.reference.domains.market_data.worker import (
    MarketDataWorker,
    _configure_worker_logging,
)


class MockQueue:
    """
    Mock queue that mimics multiprocessing.Queue interface.
    Uses threading queue internally for unit testing.
    """
    def __init__(self, maxsize: int = 0):
        self._queue = queue.Queue(maxsize=maxsize)
        self._maxsize = maxsize
    
    def put_nowait(self, item):
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            raise queue.Full()
    
    def get_nowait(self):
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            raise queue.Empty()
    
    def qsize(self):
        return self._queue.qsize()
    
    def empty(self):
        return self._queue.empty()
    
    def full(self):
        return self._queue.full()


class TestWorkerBackpressure:
    """Test backpressure mechanism (drop-oldest policy)."""

    def test_put_with_backpressure_normal(self):
        """Test normal put when queue has space."""
        q = MockQueue(maxsize=10)
        
        # Create minimal config
        config = {
            "instruments": {"BTCUSDT": {}},
            "system": {
                "market_data": {
                    "ws_heartbeat_sec": 20.0,
                    "ws_receive_timeout_sec": 60.0,
                }
            },
            "trading": {
                "market_data": {
                    "macro_sync": {"anchors": []},
                    "poll_interval_sec": 1,
                },
                "domain_configuration": {
                    "market_data": {"trading_mode": "testnet"}
                },
            },
            "binance_api": {},
        }
        
        logger = MagicMock()
        worker = MarketDataWorker(q, config, logger)
        
        # Put a tick
        tick = {"type": "tick", "symbol": "BTCUSDT", "ts": 1234567890}
        result = worker._put_with_backpressure(tick)
        
        assert result is True
        assert q.qsize() == 1
        
        # Get it back
        item = q.get_nowait()
        assert item["symbol"] == "BTCUSDT"

    def test_put_with_backpressure_drops_oldest(self):
        """Test that oldest item is dropped when queue is full."""
        q = MockQueue(maxsize=3)
        
        config = {
            "instruments": {"BTCUSDT": {}},
            "system": {
                "market_data": {
                    "ws_heartbeat_sec": 20.0,
                    "ws_receive_timeout_sec": 60.0,
                }
            },
            "trading": {
                "market_data": {
                    "macro_sync": {"anchors": []},
                    "poll_interval_sec": 1,
                },
                "domain_configuration": {
                    "market_data": {"trading_mode": "testnet"}
                },
            },
            "binance_api": {},
        }
        
        logger = MagicMock()
        worker = MarketDataWorker(q, config, logger)
        
        # Fill the queue
        for i in range(3):
            tick = {"type": "tick", "symbol": "BTCUSDT", "ts": i}
            q.put_nowait(tick)
        
        assert q.qsize() == 3
        
        # Put a new tick - should drop oldest (ts=0)
        new_tick = {"type": "tick", "symbol": "BTCUSDT", "ts": 999}
        result = worker._put_with_backpressure(new_tick)
        
        assert result is True
        assert q.qsize() == 3
        assert worker._ticks_dropped == 1
        
        # Verify oldest was dropped
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        
        timestamps = [item["ts"] for item in items]
        assert 0 not in timestamps  # Oldest was dropped
        assert 999 in timestamps    # New was added


class TestWorkerMessageTypes:
    """Test different message types produced by worker."""

    def test_tick_message_format(self):
        """Test that tick messages have correct format."""
        q = MockQueue(maxsize=100)
        
        config = {
            "instruments": {"BTCUSDT": {}},
            "system": {
                "market_data": {
                    "ws_heartbeat_sec": 20.0,
                    "ws_receive_timeout_sec": 60.0,
                }
            },
            "trading": {
                "market_data": {
                    "macro_sync": {"anchors": []},
                    "poll_interval_sec": 1,
                },
                "domain_configuration": {
                    "market_data": {"trading_mode": "testnet"}
                },
            },
            "binance_api": {},
        }
        
        logger = MagicMock()
        worker = MarketDataWorker(q, config, logger)
        
        # Simulate tick message
        tick_data = {
            "ts": 1234567890000,
            "price": "95000.50",
            "bid": "95000.00",
            "ask": "95001.00",
        }
        
        msg = {
            "type": worker.MSG_TYPE_TICK,
            "symbol": "BTCUSDT",
            "ts": tick_data["ts"],
            "data": tick_data,
        }
        
        worker._put_with_backpressure(msg)
        
        result = q.get_nowait()
        assert result["type"] == "tick"
        assert result["symbol"] == "BTCUSDT"
        assert "data" in result
        assert result["data"]["price"] == "95000.50"

    def test_anchor_message_format(self):
        """Test that anchor update messages have correct format."""
        q = MockQueue(maxsize=100)
        
        config = {
            "instruments": {"ETHUSDT": {}},
            "system": {
                "market_data": {
                    "ws_heartbeat_sec": 20.0,
                    "ws_receive_timeout_sec": 60.0,
                }
            },
            "trading": {
                "market_data": {
                    "macro_sync": {"anchors": ["BTCUSDT"]},
                    "poll_interval_sec": 1,
                },
                "domain_configuration": {
                    "market_data": {"trading_mode": "testnet"}
                },
            },
            "binance_api": {},
        }
        
        logger = MagicMock()
        worker = MarketDataWorker(q, config, logger)
        
        msg = {
            "type": worker.MSG_TYPE_ANCHOR,
            "anchor": "BTCUSDT",
            "price": "95000.00",
            "ts_ms": int(time.time() * 1000),
        }
        
        worker._put_with_backpressure(msg)
        
        result = q.get_nowait()
        assert result["type"] == "anchor"
        assert result["anchor"] == "BTCUSDT"
        assert result["price"] == "95000.00"

    def test_heartbeat_message_format(self):
        """Test that heartbeat messages have correct format."""
        q = MockQueue(maxsize=100)
        
        config = {
            "instruments": {"BTCUSDT": {}},
            "system": {
                "market_data": {
                    "ws_heartbeat_sec": 20.0,
                    "ws_receive_timeout_sec": 60.0,
                }
            },
            "trading": {
                "market_data": {
                    "macro_sync": {"anchors": []},
                    "poll_interval_sec": 1,
                },
                "domain_configuration": {
                    "market_data": {"trading_mode": "testnet"}
                },
            },
            "binance_api": {},
        }
        
        logger = MagicMock()
        worker = MarketDataWorker(q, config, logger)
        
        # Simulate heartbeat
        msg = {
            "type": worker.MSG_TYPE_HEARTBEAT,
            "ts": int(time.time() * 1000),
            "metrics": {
                "ticks_received": 100,
                "ticks_dropped": 5,
                "queue_size": 42,
            },
        }
        
        worker._put_with_backpressure(msg)
        
        result = q.get_nowait()
        assert result["type"] == "heartbeat"
        assert "ts" in result
        assert "metrics" in result
        assert result["metrics"]["ticks_received"] == 100


class TestWorkerConfig:
    """Test worker configuration handling."""

    def test_worker_extracts_symbols_from_config(self):
        """Test that worker correctly extracts symbols from config."""
        q = MockQueue(maxsize=100)
        
        config = {
            "instruments": {
                "BTCUSDT": {"step_size": "0.001"},
                "ETHUSDT": {"step_size": "0.01"},
            },
            "system": {
                "market_data": {
                    "ws_heartbeat_sec": 20.0,
                    "ws_receive_timeout_sec": 60.0,
                }
            },
            "trading": {
                "market_data": {
                    "macro_sync": {"anchors": ["BTCUSDT"]},
                    "poll_interval_sec": 2,
                },
                "domain_configuration": {
                    "market_data": {"trading_mode": "live"}
                },
            },
            "binance_api": {},
        }
        
        logger = MagicMock()
        worker = MarketDataWorker(q, config, logger)
        
        assert set(worker._symbols) == {"BTCUSDT", "ETHUSDT"}
        assert worker._anchors == ["BTCUSDT"]
        assert worker._poll_interval == 2
        assert worker._mode == "live"

    def test_worker_raises_on_empty_symbols(self):
        """Test that worker raises error when no symbols configured."""
        q = MockQueue(maxsize=100)
        
        config = {
            "instruments": {},  # Empty!
            "system": {
                "market_data": {
                    "ws_heartbeat_sec": 20.0,
                    "ws_receive_timeout_sec": 60.0,
                }
            },
            "trading": {
                "market_data": {
                    "macro_sync": {"anchors": []},
                    "poll_interval_sec": 1,
                },
                "domain_configuration": {
                    "market_data": {"trading_mode": "testnet"}
                },
            },
            "binance_api": {},
        }
        
        logger = MagicMock()
        
        with pytest.raises(ValueError, match="No symbols configured"):
            MarketDataWorker(q, config, logger)


    def test_worker_defaults_to_testnet(self):
        """Test that worker defaults to testnet mode."""
        q = MockQueue(maxsize=100)
        
        config = {
            "instruments": {"BTCUSDT": {}},
            "system": {
                "market_data": {
                    "ws_heartbeat_sec": 20.0,
                    "ws_receive_timeout_sec": 60.0,
                }
            },
            "trading": {
                "market_data": {
                    "macro_sync": {"anchors": []},
                    "poll_interval_sec": 1,
                },
                "domain_configuration": {},  # No market_data config
            },
            "binance_api": {},
        }
        
        logger = MagicMock()
        worker = MarketDataWorker(q, config, logger)
        
        assert worker._mode == "testnet"
        assert worker._get_ws_url() == worker.WS_URL_TESTNET


class TestWorkerWebSocket:
    """Test WebSocket URL and subscription payload generation."""

    def test_ws_url_live(self):
        """Test WebSocket URL for live mode."""
        q = MockQueue(maxsize=100)
        
        config = {
            "instruments": {"BTCUSDT": {}},
            "system": {
                "market_data": {
                    "ws_heartbeat_sec": 20.0,
                    "ws_receive_timeout_sec": 60.0,
                }
            },
            "trading": {
                "market_data": {
                    "macro_sync": {"anchors": []},
                    "poll_interval_sec": 1,
                },
                "domain_configuration": {
                    "market_data": {"trading_mode": "live"}
                },
            },
            "binance_api": {},
        }
        
        logger = MagicMock()
        worker = MarketDataWorker(q, config, logger)
        
        assert worker._get_ws_url() == "wss://fstream.binance.com/ws"

    def test_subscribe_payload_format(self):
        """Test WebSocket subscription payload format."""
        q = MockQueue(maxsize=100)
        
        config = {
            "instruments": {"BTCUSDT": {}, "ETHUSDT": {}},
            "system": {
                "market_data": {
                    "ws_heartbeat_sec": 20.0,
                    "ws_receive_timeout_sec": 60.0,
                }
            },
            "trading": {
                "market_data": {
                    "macro_sync": {"anchors": ["SOLUSDT"]},  # Extra anchor
                    "poll_interval_sec": 1,
                },
                "domain_configuration": {
                    "market_data": {"trading_mode": "testnet"}
                },
            },
            "binance_api": {},
        }
        
        logger = MagicMock()
        worker = MarketDataWorker(q, config, logger)
        
        payload = worker._make_subscribe_payload()
        
        assert payload["method"] == "SUBSCRIBE"
        assert payload["id"] == 1
        
        streams = payload["params"]
        # Should have bookTicker and aggTrade for each symbol + anchor
        expected_streams = [
            "btcusdt@bookTicker", "btcusdt@aggTrade",
            "ethusdt@bookTicker", "ethusdt@aggTrade",
            "solusdt@bookTicker", "solusdt@aggTrade",  # Anchor
        ]
        
        for expected in expected_streams:
            assert expected in streams, f"Missing stream: {expected}"
