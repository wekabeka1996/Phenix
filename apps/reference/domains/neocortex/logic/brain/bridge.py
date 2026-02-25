"""
Brain Bridge (Service Client)

Orchestrates communication with the persistent Brain Service Worker.
Replaces ProcessPoolExecutor with explicit Task/Result queues.
"""

import asyncio
import logging
import multiprocessing as mp
import threading
import uuid
import time
from typing import List, Dict, Any, Optional
from concurrent.futures import Future

import numpy as np

from config_models import NeuroConfig
from logic.ingest.observation import MarketObservation
from logic.brain.worker import brain_service_worker, BridgeTask, BridgeResult

logger = logging.getLogger(__name__)


class BrainBridge:
    """
    Client for the Brain Service Worker.
    Maintains the Task/Result queues and a background listener thread.
    """
    
    def __init__(self, config: NeuroConfig, rng_seed: int = 0):
        self.config = config
        self.rng_seed = int(rng_seed)
        
        # State
        self._process: Optional[mp.Process] = None
        self._task_queue: Optional[mp.Queue] = None
        self._result_queue: Optional[mp.Queue] = None
        
        self._futures: Dict[str, asyncio.Future] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._initialized = False

    async def start(self) -> bool:
        """
        Spawn the worker process and wait for initialization.
        """
        if self._initialized:
            return True
            
        try:
            self._loop = asyncio.get_running_loop()
            
            # Use spawn context (PyTorch requirement)
            ctx = mp.get_context("spawn")
            self._task_queue = ctx.Queue()
            self._result_queue = ctx.Queue()
            
            # Convert config to dict
            config_dict = self.config.model_dump()
            
            # Spawn
            logger.info("Spawning Brain Service Worker...")
            self._process = ctx.Process(
                target=brain_service_worker,
                args=(self._task_queue, self._result_queue, config_dict, self.rng_seed),
                daemon=True # Kill if parent dies
            )
            self._process.start()
            
            # Wait for INIT response (blocking get, execute in thread)
            logger.info("Waiting up to 300s for BrainCore initialization (PyTorch/CUDA)...")
            init_result = await self._loop.run_in_executor(None, self._wait_for_init)
            
            if init_result and init_result.success:
                logger.info("BrainBridge: Worker Initialized Successfully")
                self._initialized = True
                
                # Start listener thread
                self._shutdown_event.clear()
                self._listener_thread = threading.Thread(target=self._result_listener, daemon=True)
                self._listener_thread.start()
                return True
            else:
                err = init_result.error if init_result else "Timeout"
                logger.error(f"BrainBridge Init Failed: {err}")
                self._kill()
                return False
                
        except Exception as e:
            logger.error(f"BrainBridge start exception: {e}", exc_info=True)
            self._kill()
            return False

    def _wait_for_init(self) -> Optional[BridgeResult]:
        """Blocking wait for INIT message."""
        try:
            # 300s timeout for PyTorch/CUDA model loading
            if self._result_queue:
                return self._result_queue.get(block=True, timeout=300.0)
        except Exception:
            return None
        return None

    def _result_listener(self):
        """Background thread to route results to Futures."""
        while not self._shutdown_event.is_set():
            try:
                # Poll with short timeout to allow shutdown check
                if self._result_queue is None:
                    break
                    
                try:
                    result: BridgeResult = self._result_queue.get(timeout=0.1)
                except Exception: # Empty
                    continue
                    
                # Schedule future resolution on main loop
                if self._loop and not self._loop.is_closed():
                    self._loop.call_soon_threadsafe(self._complete_future, result)
                    
            except Exception as e:
                logger.error(f"BrainBridge Listener Error: {e}")
                time.sleep(1)

    def _complete_future(self, result: BridgeResult):
        """Complete the asyncio future (runs on main loop)."""
        future = self._futures.pop(result.task_id, None)
        if future and not future.done():
            if result.success:
                future.set_result(result.data)
            else:
                # return error as dict if expected, or raise exception?
                # The existing code expects dict return for errors often.
                # Let's standardize on returning exceptions implies failure logic upstream.
                # BUT existing logic handled `{"error": ...}` return values in many cases.
                # Let's verify callers.
                # train_async returns Dict. If error, returns {"error": ...}
                pass
                # Actually, Future should hold the result.
                # If the worker returned an error object/string in data, we pass it?
                # No, BridgeResult has .error field.
                
                # If it's a "soft" error, maybe we should resolve with the error dict if that is the contract.
                # Legacy code returned {"error": str(e)}.
                # So we can construct that here if needed, or raise.
                # Let's raise Exception, and catch in _submit wrapper?
                # Or just resolve with error dict?
                # Let's try to mimic legacy:
                # If result.error is present, return {"error": result.error} (?)
                # Wait, acts return dict. Train returns dict.
                # But encode returns ndarray.
                
                # I should handle this in the specific methods or here.
                # Simpler: raise Exception from Future, and let methods catch and format.
                future.set_exception(RuntimeError(result.error))

    def _submit(self, type: str, payload: Any) -> asyncio.Future:
        """Internal submit helper."""
        if not self._initialized or self._task_queue is None:
            f = self._loop.create_future()
            f.set_exception(RuntimeError("BrainBridge not initialized"))
            return f

        task_id = str(uuid.uuid4())
        task = BridgeTask(id=task_id, type=type, payload=payload)
        
        future = self._loop.create_future()
        self._futures[task_id] = future
        
        try:
            self._task_queue.put(task)
        except Exception as e:
            del self._futures[task_id]
            future.set_exception(e)
            
        return future

    # --- Public API (Matches Legacy Interface) ---

    async def train_async(self, batch: List[MarketObservation]) -> Dict[str, float]:
        try:
            # Stack features
            batch_data = np.stack([obs.features_vector for obs in batch])
            return await self._submit("TRAIN", batch_data)
        except Exception as e:
            logger.error(f"train_async failed: {e}")
            return {"error": str(e)}

    async def train_ppo_async(self, episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            return await self._submit("TRAIN_PPO", episodes)
        except Exception as e:
            logger.error(f"train_ppo_async failed: {e}")
            return {"error": str(e)}

    async def encode_async(self, obs: MarketObservation) -> np.ndarray:
        try:
            return await self._submit("ENCODE", obs.features_vector)
        except Exception as e:
            logger.error(f"encode_async failed: {e}")
            return np.zeros(self.config.vae.latent_dim, dtype=np.float32)

    async def act_async(self, z: np.ndarray) -> Dict[str, Any]:
        try:
            return await self._submit("ACT", z)
        except Exception as e:
            logger.error(f"act_async failed: {e}")
            return {"action": 2, "action_name": "FLAT", "value": 0.0, "confidence": 0.0, "error": str(e)}

    async def save_async(self, path: str) -> bool:
        try:
            return await self._submit("SAVE", str(path))
        except Exception:
            return False

    async def load_async(self, path: str) -> bool:
        try:
            return await self._submit("LOAD", str(path))
        except Exception:
            return False

    def shutdown(self):
        logger.info("Shutting down BrainBridge...")
        self._shutdown_event.set()
        self._initialized = False
        
        if self._task_queue:
            try:
                self._task_queue.put(BridgeTask(id="SHUTDOWN", type="SHUTDOWN", payload=None))
            except Exception:
                pass
                
        # Wait logic?
        if self._listener_thread:
            self._listener_thread.join(timeout=1.0)
            
        self._kill()
        logger.info("BrainBridge shutdown complete")

    def _kill(self):
        """Force cleanup."""
        if self._process:
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=1.0)
            self._process = None
        
        # Close queues?
        # In python mp.Queue, strict cleanup is tricky, but letting GC handle it usually works if process dead.
        self._task_queue = None
        self._result_queue = None
