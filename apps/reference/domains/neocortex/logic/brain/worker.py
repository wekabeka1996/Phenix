# QUARANTINED: legacy_runtime
"""
Brain Worker Process (Service Pattern)

Long-running process that maintains BrainCore state (PyTorch model)
and processes requests via Multiprocessing Queues.
"""
__quarantined__ = True

from dataclasses import dataclass
from typing import Any, Dict, Optional, List
import logging
import multiprocessing as mp
import numpy as np
import time
import os

logger = logging.getLogger("brain_worker")

@dataclass
class BridgeTask:
    id: str
    type: str  # TRAIN, TRAIN_POLICY, TRAIN_REGIME_SUPERVISION, TRAIN_PPO, ENCODE, ACT, RESET_SEQUENCE_STATE, SAVE, LOAD, SHUTDOWN
    payload: Any

@dataclass
class BridgeResult:
    task_id: str
    success: bool
    data: Any
    error: Optional[str] = None

def brain_service_worker(
    task_queue: mp.Queue, 
    result_queue: mp.Queue, 
    config_dict: Dict[str, Any], 
    rng_seed: int
):
    """
    Main loop for the Brain Service Worker.
    Keeps BrainCore loaded in memory/GPU.
    """
    # Configure logging for this process
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | WORKER | %(levelname)s | %(message)s'
    )
    
    brain_core = None
    
    try:
        # Lazy import heavy libraries
        import torch
        from apps.reference.domains.neocortex.config_models import NeuroConfig
        from apps.reference.domains.neocortex.logic.brain.core import BrainCore
        
        # Initialize
        config = NeuroConfig(**config_dict)
        requested_device = os.getenv("NEOCORTEX_DEVICE")
        brain_core = BrainCore(config, device=requested_device, rng_seed=int(rng_seed))
        
        logger.info(f"BrainCore Service Ready (Device: {brain_core.device})")
        if str(brain_core.device).startswith("cpu"):
            logger.warning("GPU unavailable or disabled; BrainCore worker running on CPU")
        
        # Send INIT success
        result_queue.put(BridgeResult(task_id="INIT", success=True, data="READY"))
        
    except Exception as e:
        logger.error(f"BrainCore Init Failed: {e}", exc_info=True)
        result_queue.put(BridgeResult(task_id="INIT", success=False, data=None, error=str(e)))
        return

    # Event Loop
    while True:
        try:
            task: BridgeTask = task_queue.get()
            
            if task.type == "SHUTDOWN":
                logger.info("Worker received SHUTDOWN. Exiting.")
                break
            
            result_data = None
            success = True
            error = None
            
            try:
                # --- Dispatch ---
                if task.type == "TRAIN":
                    # payload: numpy array
                    tensor = torch.from_numpy(task.payload).float().to(brain_core.device)
                    result_data = brain_core.train_batch(tensor)
                    
                elif task.type == "TRAIN_PPO":
                    result_data = brain_core.train_ppo(task.payload)

                elif task.type == "TRAIN_POLICY":
                    result_data = brain_core.train_policy(task.payload)

                elif task.type == "TRAIN_REGIME_SUPERVISION":
                    result_data = brain_core.train_regime_supervision(task.payload)
                    
                elif task.type == "ENCODE":
                    # payload: numpy array
                    # encode expects numpy or tensor? Core.encode usually handles numpy
                    # Let's check logic/brain/core.py if needed, but assuming standard interface
                    result_data = brain_core.encode(task.payload)
                    
                elif task.type == "ACT":
                    # payload: latent z (numpy)
                    result_data = brain_core.get_action(task.payload)

                elif task.type == "RESET_SEQUENCE_STATE":
                    reason = "manual"
                    if isinstance(task.payload, dict):
                        reason = str(task.payload.get("reason") or "manual")
                    result_data = brain_core.reset_sequence_state(reason=reason)
                    
                elif task.type == "SAVE":
                    from pathlib import Path
                    save_path = Path(task.payload).resolve()
                    logger.info(f"WORKER: Saving checkpoint to {save_path}...")
                    result_data = brain_core.save_checkpoint(save_path)
                    if result_data:
                        logger.info(f"WORKER: Checkpoint saved successfully to {save_path}")
                    else:
                        logger.warning(f"WORKER: Checkpoint save FAILED at {save_path}")
                    
                elif task.type == "LOAD":
                    from pathlib import Path
                    result_data = brain_core.load_checkpoint(Path(task.payload))
                    
                else:
                    success = False
                    error = f"Unknown task type: {task.type}"
                    
            except Exception as e:
                success = False
                error = str(e)
                # logger.error(f"Task {task.type} error: {e}") # Reduce log spam
                
            # Send result
            result_queue.put(BridgeResult(task.id, success, result_data, error))
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Critical Worker Loop Error: {e}", exc_info=True)
            # Don't crash the loop, try to continue
            time.sleep(1)
