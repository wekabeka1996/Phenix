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

from apps.reference.utils.accessors import aget

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
    
    def __init__(self, fsm: "FSMCore", config: Any) -> None:
        """
        Initialize the proxy.
        
        Args:
            fsm: FSM core for event emission
            config: AuroraConfig object (will be serialized for worker)
        """
        self._fsm = fsm
        if isinstance(config, dict):
            raise TypeError("MarketDataProxy requires AuroraConfig, got dict")
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

        # System-level market data settings.
        # Intentionally NOT validated/loaded here:
        # - runtime config must come from YAML + resolver + pydantic validation
        # - unit/runtime smoke tests may construct MarketDataProxy with a light stub config
        # Strict validation happens when starting the worker (start_async).
        self._queue_maxsize: Optional[int] = None
        self._batch_size: Optional[int] = None
        self._queue_get_timeout_sec: Optional[float] = None
        self._idle_sleep_sec: Optional[float] = None

        # If config already carries system.market_data (e.g. real runtime config or unit-test MockConfig),
        # we can load settings immediately. This keeps strict validation and avoids any defaults.
        if hasattr(self._config, "system") and hasattr(getattr(self._config, "system"), "market_data"):
            self._load_system_market_data_settings()
        
        # Extract symbols for logging
        instruments = getattr(self._config, "instruments", {}) if self._config is not None else {}
        if isinstance(instruments, dict):
            self._symbols = list(instruments.keys())
        else:
            self._symbols = []
        
        LOG.info(
            f"MarketDataProxy initialized: symbols={self._symbols}, "
            "system.market_data settings pending (loaded on start_async)"
        )

    def _load_system_market_data_settings(self) -> None:
        """Load and validate system.market_data settings strictly.

        Must be backed by YAML-resolved, pydantic-validated config in real runtime.
        """
        try:
            system_md = self._config.system.market_data
        except Exception as e:
            raise ValueError("Missing required config path: system.market_data") from e

        qms = getattr(system_md, "queue_maxsize", None)
        pbs = getattr(system_md, "proxy_batch_size", None)
        qto = getattr(system_md, "proxy_queue_get_timeout_sec", None)
        iss = getattr(system_md, "proxy_idle_sleep_sec", None)

        if not isinstance(qms, int) or qms <= 0:
            raise ValueError("Invalid required config: system.market_data.queue_maxsize (must be int > 0)")
        if not isinstance(pbs, int) or pbs <= 0:
            raise ValueError("Invalid required config: system.market_data.proxy_batch_size (must be int > 0)")
        if not isinstance(qto, (int, float)) or qto <= 0:
            raise ValueError("Invalid required config: system.market_data.proxy_queue_get_timeout_sec (must be > 0)")
        if not isinstance(iss, (int, float)) or iss <= 0:
            raise ValueError("Invalid required config: system.market_data.proxy_idle_sleep_sec (must be > 0)")

        self._queue_maxsize = int(qms)
        self._batch_size = int(pbs)
        self._queue_get_timeout_sec = float(qto)
        self._idle_sleep_sec = float(iss)
    
    def _get_config_dict(self) -> Dict[str, Any]:
        """Convert config to dict for serialization to worker process.
        
        CFG-RUNTIME-BOOTSTRAP-07: Add metadata for diagnostic logging.
        """
        if not hasattr(self._config, "model_dump"):
            raise TypeError(f"MarketDataProxy requires Pydantic config with model_dump(), got {type(self._config)}")

        config_dict = self._config.model_dump(mode="json")
        
        # CFG-RUNTIME-BOOTSTRAP-07: Add metadata for worker diagnostic logging
        # This allows worker to log WHERE config came from (bootstrap proof)
        config_name = None
        config_dir = None
        try:
            raw_name = aget(self._config, "_config_name", None)
            if isinstance(raw_name, str) and raw_name:
                config_name = raw_name
            raw_dir = aget(self._config, "_config_dir", None)
            if isinstance(raw_dir, str) and raw_dir:
                config_dir = raw_dir
        except Exception:
            pass

        if config_name is None or config_dir is None:
            try:
                raw_name = self._config.system_meta.runtime.config_name
                if isinstance(raw_name, str) and raw_name:
                    config_name = raw_name
                raw_dir = self._config.system_meta.runtime.config_dir
                if isinstance(raw_dir, str) and raw_dir:
                    config_dir = raw_dir
            except Exception:
                pass
        config_dict["_config_name"] = config_name or "aurora"
        config_dict["_config_dir"] = config_dir or "config/aurora"
        
        return config_dict
    
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
            symbol = tick_data.get("symbol")
            if symbol is None:
                symbol = "UNKNOWN"
            data = tick_data.get("data")
            if data is None:
                data = tick_data
            
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
                # Optional trade metadata (TASK31 additive)
                "buy_count": data.get("buy_count"),
                "sell_count": data.get("sell_count"),
                "buy_notional": data.get("buy_notional"),
                "sell_notional": data.get("sell_notional"),
                "trades_dropped_out_of_order": data.get("trades_dropped_out_of_order"),
                "data_type": "market_tick_aggregated",
                "data_source": data.get("data_source") if data.get("data_source") is not None else "multiprocess_worker",
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
            ts_ms = anchor_data.get("ts_ms")
            if ts_ms is None:
                ts_ms = anchor_data.get("ts")
            if ts_ms is None:
                raise ValueError("Anchor update missing required ts_ms (exchange timestamp)")
            
            self._fsm.emit(
                event_name="EVT:ANCHOR_UPDATED",
                payload={"anchor": anchor, "price": price, "ts_ms": int(ts_ms)},
                why=f"Anchor price update for {anchor} from worker process"
            )
            
        except Exception as e:
            LOG.error(f"Error emitting anchor update: {e}")
    
    def _handle_heartbeat(self, heartbeat_data: Dict[str, Any]) -> None:
        """Process worker heartbeat."""
        ts = heartbeat_data.get("ts")
        self._last_heartbeat_ts = int(ts) if ts is not None else 0
        self._worker_alive = True
        
        metrics = heartbeat_data.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
        queue_size = metrics.get("queue_size")
        ticks_received = metrics.get("ticks_received")
        ticks_dropped = metrics.get("ticks_dropped")
        LOG.debug(
            f"Worker heartbeat: queue_size={queue_size if queue_size is not None else -1}, "
            f"ticks_received={ticks_received if ticks_received is not None else 0}, "
            f"ticks_dropped={ticks_dropped if ticks_dropped is not None else 0}"
        )
    
    def _consume_queue_sync(self) -> None:
        """
        Consume messages from the IPC queue in a dedicated thread.
        
        This runs in a separate thread to avoid blocking the guardian_loop
        which handles OrderGuardian polling.
        """
        LOG.info("Queue consumer thread started")

        if self._batch_size is None or self._queue_get_timeout_sec is None or self._idle_sleep_sec is None:
            raise RuntimeError(
                "MarketDataProxy system.market_data settings are not loaded. "
                "Provide YAML->Pydantic config with system.market_data or call start_async()."
            )
        empty_cycles = 0
        
        while self._running:
            batch_start = time.perf_counter()
            items_processed = 0
            
            # Process up to configured batch size
            while items_processed < self._batch_size:
                try:
                    # Blocking get with config-driven timeout for faster response
                    msg = self._ipc_queue.get(timeout=self._queue_get_timeout_sec)
                    msg_type = msg.get("type")
                    
                    # DIAG: Log first 10 messages for debugging
                    if self._ticks_emitted < 10:
                        LOG.info(f"📬 Queue received: type={msg_type}, symbol={msg.get('symbol')}")
                    
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
                time.sleep(self._idle_sleep_sec)
        
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

        # Strict config validation/loading from YAML-resolved pydantic config.
        # If config is a stub (tests), start_async should not be called.
        self._load_system_market_data_settings()

        assert self._queue_maxsize is not None
        assert self._batch_size is not None
        assert self._queue_get_timeout_sec is not None
        assert self._idle_sleep_sec is not None
        
        # Create IPC queue with maxsize for backpressure
        self._ipc_queue = Queue(maxsize=self._queue_maxsize)
        
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
