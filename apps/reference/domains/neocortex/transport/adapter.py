"""
Neocortex Transport Adapter

Bridges the internal domain logic with the external Aurora Event Bus.
Acting as the 'Senses' input port.

Phase 4: Added Shadow Intent emission and checkpointing.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path

from config_models import NeocortexConfig
from logic.ingest.parser import FeatureParser
from logic.ingest.observation import MarketObservation
from logic.amygdala.valuation import ValuationEngine
from logic.memory.buffer import EpisodicBuffer
from logic.brain.bridge import BrainBridge

logger = logging.getLogger(__name__)


class NeocortexAdapter:
    """
    Orchestrates the data flow:
    Raw Event -> FeatureParser -> Amygdala -> EpisodicBuffer -> BrainBridge -> Shadow Intent
    
    Phase 4: Emits EVT:NEOCORTEX_SHADOW_INTENT
    """
    
    def __init__(
        self, 
        config: NeocortexConfig,
        parser: FeatureParser,
        amygdala: ValuationEngine,
        buffer: EpisodicBuffer,
        brain_bridge: Optional[BrainBridge] = None,
        event_emitter: Optional[Callable[[str, Dict], None]] = None,
        fsm_core: Any = None
    ):
        self.config = config
        self.parser = parser
        self.amygdala = amygdala
        self.buffer = buffer
        self.brain_bridge = brain_bridge
        self.event_emitter = event_emitter
        self.fsm_core = fsm_core
        
        # Training control
        self._training_in_progress = False
        self._samples_since_last_train = 0
        self._train_batch_size = config.neuro.vae.batch_size
        self._total_train_steps = 0
        self._last_checkpoint_step = 0
        self._checkpoint_interval = config.neuro.checkpoint_every_n_steps
        
        # Shadow intent control
        self._shadow_intents_emitted = 0
        
        logger.info("Neocortex Adapter initialized (Phase 4: Shadow Intents + Checkpointing)")

    async def handle_features(self, payload: Dict[str, Any]):
        """
        Callback for EVT:FEATURES_CALCULATED.
        
        Full pipeline:
        1. Parse -> MarketObservation
        2. Value -> Importance
        3. Memorize -> Buffer
        4. Encode -> Latent z
        5. Act -> Shadow Intent
        6. Train -> Background
        """
        try:
            # 1. Parse (String -> Float32 Typed Observation)
            obs = self.parser.parse(payload)
            
            # 2. Value (Calculate Importance)
            reward = float(payload.get('reward_signal', 0.0))
            importance = self.amygdala.update(obs, reward)
            
            # 3. Memorize (Store in Buffer)
            self.buffer.add(obs, importance)
            self._samples_since_last_train += 1
            
            # 4. Log Debug
            logger.debug(
                f"Ingested tick TS={obs.ts:.3f} Imp={importance:.4f} "
                f"Dim={obs.feature_dim} BufferLen={len(self.buffer)}"
            )
            
            # 5. Generate Shadow Intent (if bridge available)
            await self._generate_shadow_intent(obs, payload)
            
            # 6. Trigger Training (if ready)
            await self._maybe_train()
            
        except Exception as e:
            logger.error(f"Failed to ingest feature event: {e}", exc_info=True)

    async def _generate_shadow_intent(self, obs: MarketObservation, original_payload: Dict):
        """
        Encode observation and generate shadow trading intent.
        """
        if self.brain_bridge is None:
            return
            
        try:
            # Encode observation to latent space
            z = await self.brain_bridge.encode_async(obs)
            
            # Get action from PPO
            action_result = await self.brain_bridge.act_async(z)
            
            # Build shadow intent event
            shadow_intent = {
                "event_type": "EVT:NEOCORTEX_SHADOW_INTENT",
                "timestamp": time.time(),
                "symbol": original_payload.get("symbol", "UNKNOWN"),
                "action": action_result["action"],
                "action_name": action_result["action_name"],
                "value": action_result["value"],
                "confidence": action_result["confidence"],
                "latent_state": z.tolist() if hasattr(z, 'tolist') else list(z),
                "source_ts": obs.ts,
                "train_steps": self._total_train_steps
            }
            
            # Emit event
            if self.event_emitter is not None:
                self.event_emitter("EVT:NEOCORTEX_SHADOW_INTENT", shadow_intent)
            
            self._shadow_intents_emitted += 1
            
            # Log shadow intent
            logger.info(
                f"Shadow Intent: {action_result['action_name']} "
                f"(conf={action_result['confidence']:.3f}, val={action_result['value']:.3f})"
            )
            
        except Exception as e:
            logger.error(f"Shadow intent generation failed: {e}", exc_info=True)

    async def _maybe_train(self):
        """
        Check if we should trigger a training step.
        """
        if self.brain_bridge is None:
            return
        if self._training_in_progress:
            return
            
        if len(self.buffer) < self.config.ingest.min_samples_before_ready:
            return
            
        if self._samples_since_last_train < self._train_batch_size:
            return
            
        self._training_in_progress = True
        
        try:
            batch_items = self.buffer.get_batch(self._train_batch_size)
            batch_obs = [item[0] for item in batch_items]
            
            asyncio.create_task(self._run_training(batch_obs))
            
            self._samples_since_last_train = 0
            
        except Exception as e:
            logger.error(f"Failed to start training: {e}", exc_info=True)
            self._training_in_progress = False

    async def _run_training(self, batch_obs: List[MarketObservation]):
        """
        Execute training in background, checkpoint if needed.
        """
        try:
            losses = await self.brain_bridge.train_async(batch_obs)
            
            self._total_train_steps += 1
            
            if "error" in losses:
                logger.warning(f"Training step {self._total_train_steps} error: {losses['error']}")
            else:
                logger.info(
                    f"Training step {self._total_train_steps}: "
                    f"VAE={losses.get('vae_loss', 0):.4f} "
                    f"WM={losses.get('wm_loss', 0):.4f}"
                )
            
            # Check if checkpoint needed
            await self._maybe_checkpoint()
                
        except Exception as e:
            logger.error(f"Training execution failed: {e}", exc_info=True)
            
        finally:
            self._training_in_progress = False

    async def _maybe_checkpoint(self):
        """
        Save checkpoint if interval reached.
        """
        steps_since_checkpoint = self._total_train_steps - self._last_checkpoint_step
        
        if steps_since_checkpoint >= self._checkpoint_interval:
            checkpoint_dir = self.config.system.checkpoint_dir
            success = await self.brain_bridge.save_async(str(checkpoint_dir))
            
            if success:
                self._last_checkpoint_step = self._total_train_steps
                logger.info(f"Checkpoint saved at step {self._total_train_steps}")
            else:
                logger.warning(f"Checkpoint save failed at step {self._total_train_steps}")

    async def start(self):
        """
        Start the adapter and its dependencies.
        """
        if self.brain_bridge is not None:
            logger.info("Starting BrainBridge...")
            success = await self.brain_bridge.start()
            if not success:
                logger.warning("BrainBridge start failed, continuing without neural training")
                self.brain_bridge = None
            else:
                # Try to load existing checkpoint
                checkpoint_dir = self.config.system.checkpoint_dir
                if (checkpoint_dir / "checkpoint_latest.pt").exists():
                    loaded = await self.brain_bridge.load_async(str(checkpoint_dir))
                    if loaded:
                        logger.info("Restored from checkpoint")

    def shutdown(self):
        """
        Graceful shutdown with final checkpoint.
        """
        if self.brain_bridge is not None:
            # Note: Can't do async save in sync shutdown
            # In production, would convert to async shutdown
            self.brain_bridge.shutdown()
        logger.info(
            f"NeocortexAdapter shutdown: "
            f"TrainSteps={self._total_train_steps} "
            f"ShadowIntents={self._shadow_intents_emitted}"
        )

    @property
    def stats(self) -> Dict[str, Any]:
        """Get adapter statistics."""
        return {
            "total_train_steps": self._total_train_steps,
            "shadow_intents_emitted": self._shadow_intents_emitted,
            "buffer_size": len(self.buffer),
            "samples_since_train": self._samples_since_last_train
        }
