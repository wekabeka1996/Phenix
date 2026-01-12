"""
Brain Bridge

Orchestrates communication between Main Process (AsyncIO) and 
Brain Worker Process (PyTorch/BrainCore).

Architecture:
    Main Process                    Worker Process
    ─────────────                   ──────────────
    BrainBridge                     _brain_core (global)
        │                                │
        ├─ train_async() ───────────────►│ _brain_train_task()
        │      │                          │       │
        │      └─ Future ◄────────────────┘───────┘
        │
        └─ encode_async() ──────────────► _brain_encode_task()
"""

from typing import List, Dict, Any, Optional
import asyncio
import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, Future, BrokenExecutor
import numpy as np

from config_models import NeuroConfig
from logic.ingest.observation import MarketObservation
from logic.brain.worker import (
    _brain_worker_init,
    _brain_train_task,
    _brain_train_ppo_task,
    _brain_encode_task,
    _brain_act_task,
    _brain_save_task,
    _brain_load_task
)

logger = logging.getLogger(__name__)


class BrainBridge:
    """
    Bridge between AsyncIO main loop and PyTorch worker process.
    """
    
    def __init__(self, config: NeuroConfig, max_workers: int = 1, rng_seed: int = 0):
        self.config = config
        self.max_workers = max_workers
        self.rng_seed = int(rng_seed)
        self._executor: Optional[ProcessPoolExecutor] = None
        self._initialized = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
    async def start(self) -> bool:
        """
        Start the worker pool and initialize BrainCore in worker.
        
        Returns:
            True if started successfully
        """
        try:
            self._loop = asyncio.get_running_loop()
            
            # Use 'spawn' context for PyTorch compatibility
            # (fork can cause issues with CUDA)
            ctx = mp.get_context("spawn")
            
            self._executor = ProcessPoolExecutor(
                max_workers=self.max_workers,
                mp_context=ctx
            )
            
            # Submit initialization task
            # Convert Pydantic model to dict for pickling
            config_dict = self.config.model_dump()
            
            future = self._executor.submit(_brain_worker_init, config_dict, self.rng_seed)
            
            # Wait for init to complete (blocking is OK here, it's startup)
            result = await self._loop.run_in_executor(None, future.result, 30.0)
            
            if result:
                self._initialized = True
                logger.info("BrainBridge started successfully")
                return True
            else:
                logger.error("BrainBridge initialization returned False")
                return False
                
        except Exception as e:
            logger.error(f"BrainBridge start failed: {e}", exc_info=True)
            return False

    async def train_async(self, batch: List[MarketObservation]) -> Dict[str, float]:
        """
        Submit training task asynchronously.
        
        Args:
            batch: List of MarketObservation dataclasses
            
        Returns:
            Dictionary of loss metrics
        """
        if not self._initialized or self._executor is None:
            logger.warning("BrainBridge not initialized, skipping training")
            return {"error": "not_initialized"}
        
        try:
            # Convert list of dataclasses to numpy array
            # Stack feature vectors
            batch_data = np.stack([obs.features_vector for obs in batch])
            
            # Submit to worker pool
            future = self._executor.submit(_brain_train_task, batch_data)
            
            # Await result without blocking event loop
            result = await self._loop.run_in_executor(None, future.result)
            
            return result
            
        except BrokenExecutor as e:
            logger.error(f"Worker process crashed: {e}")
            self._initialized = False
            return {"error": "worker_crashed"}
            
        except Exception as e:
            logger.error(f"Training task failed: {e}", exc_info=True)
            return {"error": str(e)}

    async def train_ppo_async(self, episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Submit PPO training task asynchronously.

        Args:
            episodes: List of episode dicts (worker-picklable)

        Returns:
            Dictionary of PPO metrics or {"error": "..."}
        """
        if not self._initialized or self._executor is None:
            logger.warning("BrainBridge not initialized, skipping PPO training")
            return {"error": "not_initialized"}

        try:
            future = self._executor.submit(_brain_train_ppo_task, episodes)
            result = await self._loop.run_in_executor(None, future.result)
            return result

        except BrokenExecutor as e:
            logger.error(f"Worker process crashed during PPO train: {e}")
            self._initialized = False
            return {"error": "worker_crashed"}

        except Exception as e:
            logger.error(f"PPO training task failed: {e}", exc_info=True)
            return {"error": str(e)}

    async def encode_async(self, obs: MarketObservation) -> np.ndarray:
        """
        Submit encoding task asynchronously.
        
        Args:
            obs: Single MarketObservation
            
        Returns:
            Latent vector z
        """
        if not self._initialized or self._executor is None:
            logger.warning("BrainBridge not initialized, returning zeros")
            return np.zeros(self.config.vae.latent_dim, dtype=np.float32)
        
        try:
            obs_data = obs.features_vector
            
            future = self._executor.submit(_brain_encode_task, obs_data)
            result = await self._loop.run_in_executor(None, future.result)
            
            return result
            
        except BrokenExecutor as e:
            logger.error(f"Worker process crashed during encoding: {e}")
            self._initialized = False
            return np.zeros(self.config.vae.latent_dim, dtype=np.float32)
            
        except Exception as e:
            logger.error(f"Encoding task failed: {e}", exc_info=True)
            return np.zeros(self.config.vae.latent_dim, dtype=np.float32)

    def shutdown(self):
        """Gracefully shutdown worker pool."""
        if self._executor is not None:
            logger.info("Shutting down BrainBridge...")
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None
            self._initialized = False
            logger.info("BrainBridge shutdown complete")

    async def act_async(self, z: np.ndarray) -> Dict[str, Any]:
        """
        Get action from PPO agent given latent state.
        
        Args:
            z: Latent vector from VAE
            
        Returns:
            Dict with action, action_name, value, confidence
        """
        if not self._initialized or self._executor is None:
            return {
                "action": 2,
                "action_name": "FLAT",
                "value": 0.0,
                "confidence": 0.0,
                "error": "not_initialized"
            }
        
        try:
            future = self._executor.submit(_brain_act_task, z)
            result = await self._loop.run_in_executor(None, future.result)
            return result
            
        except BrokenExecutor as e:
            logger.error(f"Worker crashed during act: {e}")
            self._initialized = False
            return {"action": 2, "action_name": "FLAT", "value": 0.0, "confidence": 0.0}
            
        except Exception as e:
            logger.error(f"Act task failed: {e}")
            return {"action": 2, "action_name": "FLAT", "value": 0.0, "confidence": 0.0}

    async def save_async(self, path: str) -> bool:
        """
        Save checkpoint asynchronously.
        
        Args:
            path: Directory path to save checkpoint
            
        Returns:
            True if successful
        """
        if not self._initialized or self._executor is None:
            logger.warning("BrainBridge not initialized, cannot save")
            return False
        
        try:
            future = self._executor.submit(_brain_save_task, path)
            result = await self._loop.run_in_executor(None, future.result)
            return result
            
        except Exception as e:
            logger.error(f"Save task failed: {e}")
            return False

    async def load_async(self, path: str) -> bool:
        """
        Load checkpoint asynchronously.
        
        Args:
            path: Path to checkpoint file or directory
            
        Returns:
            True if successful
        """
        if not self._initialized or self._executor is None:
            logger.warning("BrainBridge not initialized, cannot load")
            return False
        
        try:
            future = self._executor.submit(_brain_load_task, path)
            result = await self._loop.run_in_executor(None, future.result)
            return result
            
        except Exception as e:
            logger.error(f"Load task failed: {e}")
            return False
