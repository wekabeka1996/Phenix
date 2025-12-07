"""
Market Data Proxy (FSMP-ARCH-01).

Bridge component that runs in the MAIN process and:
- Spawns the MarketDataWorker in a separate process
- Consumes ticks from the IPC queue in a dedicated thread
- Emits FSM events (EVT:MARKET_TICK_RECEIVED, EVT:ANCHOR_UPDATED)

This module provides the same interface as MarketDataConnector
for seamless integration with existing code.
"""

import asyncio
import atexit
import logging
import queue
import threading
import time
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from vfoundation.core import FSMCore

from .worker import worker_entrypoint, MarketDataWorker

LOG = logging.getLogger(__name__)


class MarketDataProxy:
    """
    Proxy for market data that runs the actual data collection in a separate process.
    
    This class provides the same interface as MarketDataConnector but:
    - Runs data collection in an isolated OS process (no GIL contention)
    - Uses multiprocessing.Queue for IPC
    - Consumes data in batches to avoid blocking the main event loop
    
    Interface compatibility:
    - start() / stop() - lifecycle management
    - set_feature_engineering() - DEPRECATED (no-op for backward compatibility)
    """
    
    # Batch processing configuration
    BATCH_SIZE = 100  # Process up to 100 items before yielding (was 50)
    QUEUE_MAXSIZE = 10000  # Maximum queue size (increased for burst handling)
    
    def __init__(self, fsm: "FSMCore", config: Any) -> None:
        """
        Initialize the proxy.
        
        Args:
            fsm: FSM core for event emission
            config: AuroraConfig object (will be serialized for worker)
        """
        self._fsm = fsm
        self._config = config
        self._running = False
        
        # Worker process and IPC
        self._worker_process: Optional[Process] = None
        self._ipc_queue: Optional[Queue] = None
        self._consume_task: Optional[asyncio.Task] = None
        self._consume_thread: Optional[threading.Thread] = None
        
        # Metrics
        self._ticks_emitted = 0
        self._batches_processed = 0
        self._last_heartbeat_ts = 0
        self._worker_alive = False
        
        # Extract symbols for logging
        trading = self._get_config_dict().get("trading", {})
        instruments = trading.get("instruments", {})
        self._symbols = list(instruments.keys())
        
        LOG.info(
            f"MarketDataProxy initialized: symbols={self._symbols}, "
            f"batch_size={self.BATCH_SIZE}, queue_maxsize={self.QUEUE_MAXSIZE}"
        )
    
    def _get_config_dict(self) -> Dict[str, Any]:
        """Convert config to dict for serialization to worker process."""
        if hasattr(self._config, "model_dump"):
            # Pydantic V2
            return self._config.model_dump(mode="json")
        elif hasattr(self._config, "dict"):
            # Pydantic V1
            return self._config.dict()
        elif hasattr(self._config, "to_dict"):
            return self._config.to_dict()
        elif isinstance(self._config, dict):
            return self._config
        else:
            raise ValueError(f"Cannot serialize config of type {type(self._config)}")
    
    def set_feature_engineering(self, fe: Any) -> None:
        """
        DEPRECATED: This method is a no-op for backward compatibility.
        
        Anchor updates are now handled via EVT:ANCHOR_UPDATED events.
        """
        LOG.warning(
            "⚠️ set_feature_engineering() is DEPRECATED. "
            "Anchor updates are event-driven (EVT:ANCHOR_UPDATED)."
        )
    
    def _emit_tick(self, tick_data: Dict[str, Any]) -> None:
        """Emit a market tick event to FSM."""
        try:
            symbol = tick_data.get("symbol", "UNKNOWN")
            data = tick_data.get("data", tick_data)
            
            payload = {
                "ts": data.get("ts"),
                "symbol": symbol,
                "price": data.get("price"),
                "bid": data.get("bid"),
                "ask": data.get("ask"),
                "mid": data.get("mid"),
                "bid_size": data.get("bid_size"),
                "ask_size": data.get("ask_size"),
                "buy_volume": data.get("buy_volume"),
                "sell_volume": data.get("sell_volume"),
                "data_type": "market_tick_aggregated",
                "data_source": data.get("data_source", "multiprocess_worker"),
            }
            
            self._fsm.emit(
                event_name="EVT:MARKET_TICK_RECEIVED",
                payload=payload,
                why=f"Market tick for {symbol} from worker process"
            )
            self._ticks_emitted += 1
            
        except Exception as e:
            LOG.error(f"Error emitting tick: {e}")
    
    def _emit_anchor_update(self, anchor_data: Dict[str, Any]) -> None:
        """Emit an anchor price update event to FSM."""
        try:
            anchor = anchor_data.get("anchor")
            price = anchor_data.get("price")
            
            self._fsm.emit(
                event_name="EVT:ANCHOR_UPDATED",
                payload={"anchor": anchor, "price": price},
                why=f"Anchor price update for {anchor} from worker process"
            )
            
        except Exception as e:
            LOG.error(f"Error emitting anchor update: {e}")
    
    def _handle_heartbeat(self, heartbeat_data: Dict[str, Any]) -> None:
        """Process worker heartbeat."""
        self._last_heartbeat_ts = heartbeat_data.get("ts", 0)
        self._worker_alive = True
        
        metrics = heartbeat_data.get("metrics", {})
        LOG.debug(
            f"Worker heartbeat: queue_size={metrics.get('queue_size', -1)}, "
            f"ticks_received={metrics.get('ticks_received', 0)}, "
            f"ticks_dropped={metrics.get('ticks_dropped', 0)}"
        )
    
    def _consume_queue_sync(self) -> None:
        """
        Consume messages from the IPC queue in a dedicated thread.
        
        This runs in a separate thread to avoid blocking the guardian_loop
        which handles OrderGuardian polling.
        """
        LOG.info("Queue consumer thread started")
        empty_cycles = 0
        
        while self._running:
            batch_start = time.perf_counter()
            items_processed = 0
            
            # Process up to BATCH_SIZE items
            while items_processed < self.BATCH_SIZE:
                try:
                    # Blocking get with shorter timeout for faster response
                    msg = self._ipc_queue.get(timeout=0.01)  # 10ms timeout (was 100ms)
                    msg_type = msg.get("type")
                    
                    if msg_type == MarketDataWorker.MSG_TYPE_TICK:
                        self._emit_tick(msg)
                        items_processed += 1
                    elif msg_type == MarketDataWorker.MSG_TYPE_ANCHOR:
                        self._emit_anchor_update(msg)
                        items_processed += 1
                    elif msg_type == MarketDataWorker.MSG_TYPE_HEARTBEAT:
                        self._handle_heartbeat(msg)
                    else:
                        LOG.warning(f"Unknown message type: {msg_type}")
                        
                except queue.Empty:
                    break
                except Exception as e:
                    LOG.error(f"Error processing queue message: {e}")
                    break
            
            # Track empty cycles for diagnostics
            if items_processed == 0:
                empty_cycles += 1
                if empty_cycles % 100 == 0:
                    qsize = self._ipc_queue.qsize() if hasattr(self._ipc_queue, 'qsize') else -1
                    LOG.debug(f"No messages in queue for {empty_cycles} cycles (qsize={qsize})")
            else:
                empty_cycles = 0
            
            # Log batch metrics
            if items_processed > 0:
                batch_duration_ms = (time.perf_counter() - batch_start) * 1000
                self._batches_processed += 1
                
                if self._batches_processed % 100 == 0:
                    LOG.info(
                        f"Batch #{self._batches_processed}: {items_processed} items in {batch_duration_ms:.1f}ms, "
                        f"total emitted: {self._ticks_emitted}"
                    )
            
            # Small sleep to avoid busy-waiting when queue is empty
            if items_processed == 0:
                time.sleep(0.01)  # 10ms when idle
        
        LOG.info("Queue consumer thread stopped")
    
    def _cleanup_worker(self) -> None:
        """Clean up worker process (called at exit)."""
        if self._worker_process is None:
            return
            
        if self._worker_process.is_alive():
            LOG.info(f"Terminating worker process (PID: {self._worker_process.pid})...")
            
            # Send SIGTERM first (graceful shutdown)
            try:
                self._worker_process.terminate()
                self._worker_process.join(timeout=3)
            except Exception as e:
                LOG.warning(f"Error during terminate: {e}")
            
            # If still alive, force kill
            if self._worker_process.is_alive():
                LOG.warning("Worker didn't terminate gracefully, killing...")
                try:
                    self._worker_process.kill()
                    self._worker_process.join(timeout=2)
                except Exception as e:
                    LOG.error(f"Error during kill: {e}")
                    
            if self._worker_process.is_alive():
                LOG.error(f"Worker process {self._worker_process.pid} could not be terminated!")
            else:
                LOG.info("Worker process terminated successfully")
        else:
            LOG.info("Worker process already stopped")
    
    async def start_async(self) -> None:
        """Start the proxy and spawn worker process (async version)."""
        if self._running:
            LOG.warning("MarketDataProxy already running")
            return
        
        LOG.info("Starting MarketDataProxy...")
        
        # Create IPC queue with maxsize for backpressure
        self._ipc_queue = Queue(maxsize=self.QUEUE_MAXSIZE)
        
        # Serialize config for worker
        config_dict = self._get_config_dict()
        
        # Determine log directory
        log_dir = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "logs")
        
        # Spawn worker process
        # NOTE: daemon=False to allow proper IPC Queue communication
        # We handle cleanup via atexit and signal handlers
        self._worker_process = Process(
            target=worker_entrypoint,
            args=(self._ipc_queue, config_dict, log_dir),
            name="MarketDataWorker",
            daemon=False  # Must be False for Queue to work properly
        )
        self._worker_process.start()
        LOG.info(f"Worker process spawned (PID: {self._worker_process.pid})")
        
        # Register cleanup handler
        atexit.register(self._cleanup_worker)
        
        # Start queue consumer in a dedicated thread (not in guardian_loop!)
        # This is critical to avoid blocking OrderGuardian and other async tasks
        self._running = True
        self._consume_thread = threading.Thread(
            target=self._consume_queue_sync,
            name="MarketDataConsumer",
            daemon=True
        )
        self._consume_thread.start()
        LOG.info("Queue consumer thread started")
        
        LOG.info("✅ MarketDataProxy started")
    
    def start(self) -> None:
        """Start the proxy (sync wrapper for async start)."""
        try:
            loop = asyncio.get_running_loop()
            # Already in async context, create task
            loop.create_task(self.start_async())
        except RuntimeError:
            # No running loop, run synchronously
            asyncio.run(self.start_async())
    
    def stop(self) -> None:
        """Stop the proxy and worker process."""
        if not self._running:
            LOG.warning("MarketDataProxy is not running")
            return
        
        LOG.info("Stopping MarketDataProxy...")
        self._running = False
        
        # Wait for consumer thread to finish
        if self._consume_thread and self._consume_thread.is_alive():
            self._consume_thread.join(timeout=2)
            self._consume_thread = None
        
        # Stop worker process
        self._cleanup_worker()
        
        # Clean up queue
        self._ipc_queue = None
        
        LOG.info("✅ MarketDataProxy stopped")
    
    @property
    def is_worker_alive(self) -> bool:
        """Check if worker process is alive."""
        if self._worker_process:
            return self._worker_process.is_alive()
        return False
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """Get proxy metrics for monitoring."""
        return {
            "ticks_emitted": self._ticks_emitted,
            "batches_processed": self._batches_processed,
            "last_heartbeat_ts": self._last_heartbeat_ts,
            "worker_alive": self.is_worker_alive,
            "queue_size": self._ipc_queue.qsize() if self._ipc_queue else 0,
        }
