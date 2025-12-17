"""
Market Data Worker Process (FSMP-ARCH-01).

Isolated process that handles high-frequency WebSocket market data.
Communicates with the main process via multiprocessing.Queue.

This module runs in a SEPARATE OS process with its own:
- asyncio event loop
- logging configuration
- WebSocket connections

It does NOT have access to:
- FSMCore (main process only)
- Any shared memory with main process
- Direct method calls to other domains
"""

import asyncio
import json
import logging
import os
import queue
import signal
import sys
import time
from multiprocessing import Queue
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

# Try to use orjson for faster JSON parsing (recommended)
try:
    import orjson
    USE_ORJSON = True
except ImportError:
    USE_ORJSON = False

# Add project root for imports
project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from apps.reference.domains.market_data.websocket_aggregator import WebSocketAggregator


def _configure_worker_logging(log_dir: Path) -> logging.Logger:
    """
    Configure logging for the worker process.
    
    CRITICAL: Worker MUST write to a separate log file to avoid
    file lock conflicts with the main process.
    """
    log_file = log_dir / "aurora_market_data.log"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create formatter with PID for debugging
    formatter = logging.Formatter(
        "%(asctime)s [PID:%(process)d] %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    
    # File handler (rotating)
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler (for debugging)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Configure root logger for this process
    logger = logging.getLogger("market_data_worker")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


class MarketDataWorker:
    """
    Isolated market data worker that runs in a separate process.
    
    Responsibilities:
    - Connect to Binance WebSocket
    - Parse and aggregate market data
    - Put processed ticks into IPC queue (with backpressure)
    - Send heartbeats to indicate liveness
    """
    
    # Message types for IPC
    MSG_TYPE_TICK = "tick"
    MSG_TYPE_ANCHOR = "anchor"
    MSG_TYPE_HEARTBEAT = "heartbeat"
    
    # WebSocket URLs
    WS_URL_LIVE = "wss://fstream.binance.com/ws"
    WS_URL_TESTNET = "wss://stream.binancefuture.com/ws"
    
    def __init__(
        self,
        ipc_queue: Queue,
        config_dict: Dict[str, Any],
        logger: logging.Logger
    ):
        """
        Initialize the worker.
        
        Args:
            ipc_queue: multiprocessing.Queue for sending data to main process
            config_dict: Serialized configuration (must be picklable)
            logger: Pre-configured logger for this process
        """
        self._queue = ipc_queue
        self._config = config_dict
        self._logger = logger
        self._running = False
        self._tasks: list = []  # Store task references for cancellation
        self._loop: Optional[asyncio.AbstractEventLoop] = None  # Event loop reference
        
        # Metrics
        self._ticks_received = 0
        self._ticks_emitted = 0
        self._ticks_dropped = 0
        self._last_heartbeat = 0
        
        # Parse config
        trading = config_dict.get("trading", {})
        instruments = trading.get("instruments", {})
        self._symbols = list(instruments.keys())
        
        market_data_cfg = trading.get("market_data", {})
        macro_sync = market_data_cfg.get("macro_sync", {})
        self._anchors = macro_sync.get("anchors", [])
        self._poll_interval = market_data_cfg.get("poll_interval_sec", 1)
        
        # Determine mode (live vs testnet)
        config_dict.get("binance_api", {})
        domain_config = trading.get("domain_configuration", {})
        md_config = domain_config.get("market_data", {})
        self._mode = md_config.get("trading_mode", "testnet")
        
        # CFG-TRADING-YAML-BURN-DOWN-02: Fail-fast validation for symbols
        if not self._symbols:
            raise ValueError(
                "No symbols configured! Please check config/aurora/instruments.yaml (SSOT)."
            )
        
        # Initialize aggregator
        self._aggregator = WebSocketAggregator(
            symbols=self._symbols,
            window_seconds=60,
            anchors=self._anchors
        )
        
        # WebSocket state
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        
        self._logger.info(
            f"MarketDataWorker initialized: symbols={self._symbols}, "
            f"anchors={self._anchors}, mode={self._mode}, "
            f"orjson={USE_ORJSON}"
        )
    
    def _get_ws_url(self) -> str:
        """Get WebSocket URL based on mode."""
        if self._mode == "live":
            return self.WS_URL_LIVE
        return self.WS_URL_TESTNET
    
    def _make_subscribe_payload(self) -> dict:
        """Create WebSocket subscription payload."""
        streams = []
        for symbol in self._symbols:
            symbol_lower = symbol.lower()
            streams.append(f"{symbol_lower}@bookTicker")
            streams.append(f"{symbol_lower}@aggTrade")
        
        # Add anchors if different from trading symbols
        for anchor in self._anchors:
            if anchor not in self._symbols:
                anchor_lower = anchor.lower()
                streams.append(f"{anchor_lower}@bookTicker")
                streams.append(f"{anchor_lower}@aggTrade")
        
        return {"method": "SUBSCRIBE", "params": streams, "id": 1}
    
    def _put_with_backpressure(self, msg: Dict[str, Any]) -> bool:
        """
        Put message into queue with drop-oldest backpressure.
        
        Returns True if message was queued, False if dropped.
        """
        try:
            self._queue.put_nowait(msg)
            return True
        except queue.Full:
            # Drop oldest and insert new (we want LATEST data)
            try:
                dropped = self._queue.get_nowait()
                self._ticks_dropped += 1
                # THROTTLED LOGGING: Only log every 1000 drops to avoid I/O overhead
                if self._ticks_dropped % 1000 == 0:
                    self._logger.warning(
                        f"Queue full, dropped {self._ticks_dropped} total "
                        f"(latest: type={dropped.get('type')} symbol={dropped.get('symbol')})"
                    )
                self._queue.put_nowait(msg)
                return True
            except queue.Empty:
                # Race condition: queue became empty
                self._queue.put_nowait(msg)
                return True
        except Exception as e:
            self._logger.error(f"Failed to put message in queue: {e}")
            return False
    
    def _handle_message(self, msg: Dict[str, Any]) -> None:
        """Parse and dispatch WebSocket message - REAL-TIME STREAMING MODE."""
        # Handle combined stream wrapper ({"stream":"...", "data":{...}})
        if "stream" in msg and "data" in msg:
            msg = msg["data"]
        
        event_type = msg.get("e")
        if not event_type:
            # Debug: log first few unknown messages
            if self._ticks_received < 5:
                self._logger.debug(f"Message without event type: {list(msg.keys())[:5]}")
            return
        
        try:
            symbol = msg.get("s", "")
            
            if event_type == "bookTicker":
                self._aggregator.on_book_ticker(
                    symbol=symbol,
                    bid_price=msg.get("b", "0"),
                    bid_size=msg.get("B", "0"),
                    ask_price=msg.get("a", "0"),
                    ask_size=msg.get("A", "0"),
                    ts=msg.get("E", int(time.time() * 1000))
                )
                # State updated, periodic_emit will handle emission
                
            elif event_type == "aggTrade":
                self._aggregator.on_trade(
                    symbol=symbol,
                    price=msg.get("p", "0"),
                    quantity=msg.get("q", "0"),
                    is_buyer_maker=msg.get("m", False),
                    ts=msg.get("T", int(time.time() * 1000)),
                    trade_id=msg.get("a")
                )
                self._ticks_received += 1
                # State updated, periodic_emit will handle emission
                
                if self._ticks_received % 1000 == 0:
                    self._logger.info(f"WS messages processed: {self._ticks_received}, emitted: {self._ticks_emitted}")
                    
        except Exception as e:
            self._logger.error(f"Error handling message: {e}")
    
    async def _send_heartbeat(self) -> None:
        """Send periodic heartbeat to indicate worker is alive."""
        while self._running:
            msg = {
                "type": self.MSG_TYPE_HEARTBEAT,
                "ts": int(time.time() * 1000),
                "metrics": {
                    "ticks_received": self._ticks_received,
                    "ticks_emitted": self._ticks_emitted,
                    "ticks_dropped": self._ticks_dropped,
                    "queue_size": self._queue.qsize() if hasattr(self._queue, 'qsize') else -1
                }
            }
            self._put_with_backpressure(msg)
            self._last_heartbeat = time.time()
            await asyncio.sleep(5)  # Heartbeat every 5 seconds
    
    async def _ws_loop(self) -> None:
        """Maintain WebSocket connection with reconnection logic."""
        retry_delay = 1.0
        
        while self._running:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession()
            
            ws_url = self._get_ws_url()
            self._logger.info(f"Connecting to WebSocket: {ws_url}")
            
            try:
                async with self._session.ws_connect(ws_url) as ws:
                    self._ws = ws
                    self._logger.info(f"✅ Connected to Binance WebSocket ({ws_url})")
                    
                    # Subscribe
                    payload = self._make_subscribe_payload()
                    await ws.send_json(payload)
                    self._logger.info(f"✅ Subscribed to {len(payload['params'])} streams")
                    
                    retry_delay = 1.0
                    
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                if USE_ORJSON:
                                    data = orjson.loads(msg.data)
                                else:
                                    data = json.loads(msg.data)
                                self._handle_message(data)
                            except Exception as e:
                                self._logger.error(f"Failed to parse message: {e}")
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            self._logger.error(f"WebSocket error: {ws.exception()}")
                            break
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            self._logger.info("WebSocket closed by server")
                            break
            
            except asyncio.CancelledError:
                self._logger.info("WebSocket loop cancelled")
                break
            except Exception as e:
                self._logger.error(f"WebSocket error: {e}, retrying in {retry_delay}s")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30.0)
            finally:
                self._ws = None
        
        self._logger.info("WebSocket loop ended")
    
    async def _cleanup(self) -> None:
        """Clean up resources."""
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._session:
            await self._session.close()
            self._session = None
    
    async def _periodic_emit(self) -> None:
        """
        Periodically emit market ticks for all symbols.
        
        This follows the same pattern as Test_MyPC branch:
        - WebSocket updates state continuously
        - This task emits aggregated ticks at poll_interval
        """
        self._logger.info(f"Periodic emit started: interval={self._poll_interval}s, symbols={self._symbols}")
        
        while self._running:
            try:
                # Emit trading symbol ticks
                for symbol in self._symbols:
                    tick = self._aggregator.get_market_tick(symbol)
                    if tick:
                        msg = {
                            "type": self.MSG_TYPE_TICK,
                            "symbol": symbol,
                            "ts": tick.get("ts"),
                            "data": tick
                        }
                        if self._put_with_backpressure(msg):
                            self._ticks_emitted += 1
                
                # Emit anchor updates
                for anchor in self._anchors:
                    if anchor in self._aggregator.state:
                        price = self._aggregator.state[anchor].get("latest_price")
                        if price:
                            anchor_msg = {
                                "type": self.MSG_TYPE_ANCHOR,
                                "anchor": anchor,
                                "price": str(price),
                                "ts": int(time.time() * 1000)
                            }
                            self._put_with_backpressure(anchor_msg)
                
                await asyncio.sleep(self._poll_interval)
                
            except asyncio.CancelledError:
                self._logger.info("Periodic emit cancelled")
                break
            except Exception as e:
                self._logger.error(f"Error in periodic_emit: {e}")
                await asyncio.sleep(self._poll_interval)
        
        self._logger.info("Periodic emit stopped")
    
    async def run(self) -> None:
        """Main worker loop (periodic emit mode - like Test_MyPC)."""
        self._running = True
        self._loop = asyncio.get_running_loop()
        
        self._logger.info(f"Worker starting (PID: {os.getpid()}) - periodic emit mode (interval={self._poll_interval}s)")
        
        # Start tasks: WebSocket loop (collects data) + periodic emit + heartbeat
        self._tasks = [
            asyncio.create_task(self._ws_loop()),
            asyncio.create_task(self._periodic_emit()),
            asyncio.create_task(self._send_heartbeat())
        ]
        
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            self._logger.info("Worker tasks cancelled")
        finally:
            await self._cleanup()
            self._logger.info("Worker stopped")
    
    def stop(self) -> None:
        """Signal the worker to stop (thread-safe)."""
        self._running = False
        self._logger.info("Stop signal received, scheduling task cancellation...")
        
        def _cancel_tasks():
            """Cancel all tasks from within the event loop."""
            for task in self._tasks:
                if task and not task.done():
                    task.cancel()
            # Close WebSocket if open
            if self._ws and not self._ws.closed:
                asyncio.create_task(self._ws.close())
        
        # Thread-safe scheduling of task cancellation
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(_cancel_tasks)
        else:
            # Fallback: try direct cancellation
            for task in self._tasks:
                if task and not task.done():
                    task.cancel()


def worker_entrypoint(
    ipc_queue: Queue,
    config_dict: Dict[str, Any],
    log_dir: str = "logs"
) -> None:
    """
    Entry point for the worker process.
    
    This function is called by multiprocessing.Process.
    It sets up a new asyncio event loop and runs the worker.
    
    Args:
        ipc_queue: Queue for IPC with main process
        config_dict: Serialized configuration
        log_dir: Directory for worker logs
    """
    # Configure logging for this process
    log_path = Path(log_dir)
    logger = _configure_worker_logging(log_path)
    
    logger.info(f"Worker process starting (PID: {os.getpid()})")
    
    # Create worker
    try:
        worker = MarketDataWorker(ipc_queue, config_dict, logger)
    except Exception as e:
        logger.critical(f"Failed to create worker: {e}")
        return
    
    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, stopping worker...")
        worker.stop()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run the worker
    try:
        asyncio.run(worker.run())
    except Exception as e:
        logger.critical(f"Worker crashed: {e}", exc_info=True)
    finally:
        logger.info("Worker process exiting")
