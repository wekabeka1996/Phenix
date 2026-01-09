"""
Brain Worker Process

Contains functions that run INSIDE the worker process.
These are submitted to ProcessPoolExecutor and execute in isolation.

Pattern:
    Main Process: BrainBridge.train_async() -> submit(_brain_train_task)
    Worker Process: _brain_train_task() uses global _brain_core
"""

from typing import Dict, Any, Optional
import logging
import numpy as np

# Global state for worker process
# Initialized once via _brain_worker_init
_brain_core: Optional[Any] = None
_worker_initialized: bool = False

logger = logging.getLogger(__name__)


def _brain_worker_init(config_dict: Dict[str, Any]) -> bool:
    """
    Initialize BrainCore in the worker process.
    
    Called once when the worker pool starts.
    
    Args:
        config_dict: Serialized NeuroConfig dictionary
        
    Returns:
        True if initialization succeeded
    """
    global _brain_core, _worker_initialized
    
    try:
        # Import heavy modules inside worker to avoid main process overhead
        from config_models import NeuroConfig
        from logic.brain.core import BrainCore
        
        # Reconstruct config from dict
        config = NeuroConfig(**config_dict)
        
        # Initialize BrainCore
        _brain_core = BrainCore(config)
        _worker_initialized = True
        
        logger.info("Brain Worker initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Brain Worker initialization failed: {e}", exc_info=True)
        _worker_initialized = False
        return False


def _brain_train_task(batch_data: np.ndarray) -> Dict[str, float]:
    """
    Training task executed in worker process.
    
    Args:
        batch_data: Numpy array of shape (Batch, Features)
        
    Returns:
        Dictionary of loss metrics
    """
    global _brain_core
    
    if not _worker_initialized or _brain_core is None:
        raise RuntimeError("Brain Worker not initialized")
    
    try:
        import torch
        
        # Convert numpy to tensor
        batch_tensor = torch.from_numpy(batch_data).float()
        
        # Train
        losses = _brain_core.train_batch(batch_tensor)
        
        return losses
        
    except Exception as e:
        logger.error(f"Training task failed: {e}", exc_info=True)
        return {"error": str(e), "vae_loss": float('nan'), "wm_loss": float('nan')}


def _brain_encode_task(obs_data: np.ndarray) -> np.ndarray:
    """
    Encoding task executed in worker process.
    
    Args:
        obs_data: Numpy array of shape (Features,) or (Batch, Features)
        
    Returns:
        Latent vector z of shape (Latent,) or (Batch, Latent)
    """
    global _brain_core
    
    if not _worker_initialized or _brain_core is None:
        raise RuntimeError("Brain Worker not initialized")
    
    try:
        z = _brain_core.encode(obs_data)
        return z
        
    except Exception as e:
        logger.error(f"Encoding task failed: {e}", exc_info=True)
        return np.zeros(1, dtype=np.float32)


def _brain_act_task(z: np.ndarray) -> Dict[str, Any]:
    """
    Get action from PPO agent given latent state.
    
    Args:
        z: Latent vector from VAE
        
    Returns:
        Dict with action, action_name, value, confidence
    """
    global _brain_core
    
    if not _worker_initialized or _brain_core is None:
        raise RuntimeError("Brain Worker not initialized")
    
    try:
        result = _brain_core.get_action(z)
        return result
        
    except Exception as e:
        logger.error(f"Act task failed: {e}", exc_info=True)
        return {
            "action": 2,
            "action_name": "FLAT",
            "value": 0.0,
            "confidence": 0.0,
            "error": str(e)
        }


def _brain_save_task(path: str) -> bool:
    """
    Save checkpoint task executed in worker process.
    
    Args:
        path: Directory path to save checkpoint
        
    Returns:
        True if successful
    """
    global _brain_core
    
    if not _worker_initialized or _brain_core is None:
        raise RuntimeError("Brain Worker not initialized")
    
    try:
        from pathlib import Path
        return _brain_core.save_checkpoint(Path(path))
        
    except Exception as e:
        logger.error(f"Save task failed: {e}", exc_info=True)
        return False


def _brain_load_task(path: str) -> bool:
    """
    Load checkpoint task executed in worker process.
    
    Args:
        path: Path to checkpoint file or directory
        
    Returns:
        True if successful
    """
    global _brain_core
    
    if not _worker_initialized or _brain_core is None:
        raise RuntimeError("Brain Worker not initialized")
    
    try:
        from pathlib import Path
        return _brain_core.load_checkpoint(Path(path))
        
    except Exception as e:
        logger.error(f"Load task failed: {e}", exc_info=True)
        return False

