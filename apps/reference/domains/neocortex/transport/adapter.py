"""
Neocortex Transport Adapter

Bridges the internal domain logic with the external Aurora Event Bus.
Acting as the 'Senses' input port.

Phase 4: Added Shadow Intent emission and checkpointing.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path

from config_models import NeocortexConfig
from logic.ingest.parser import FeatureParser
from logic.ingest.observation import MarketObservation
from logic.ingest.normalizer import WelfordNormalizer
from logic.amygdala.valuation import ValuationEngine
from logic.memory.buffer import EpisodicBuffer
from logic.brain.bridge import BrainBridge
from logic.telemetry import TelemetryLogger

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
        
        # Shadow intent JSONL logging
        self._shadow_intent_log_path = self.config.system.data_dir / "shadow_intents.jsonl"
        self._shadow_intent_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._shadow_intent_log: Optional[Any] = None
        try:
            self._shadow_intent_log = open(self._shadow_intent_log_path, "a")
            logger.info(f"Shadow intent log opened: {self._shadow_intent_log_path}")
        except Exception as e:
            logger.warning(f"Failed to open shadow intent log: {e}")

        # Online feature normalization (z-score) to stabilize VAE training.
        self._normalizer_state_path = self.config.system.data_dir / "normalizer_state.npz"
        self._normalizer = WelfordNormalizer(dim=len(self.config.ingest.feature_list), eps=1e-8)
        try:
            loaded = self._normalizer.load_state(self._normalizer_state_path)
            if loaded:
                logger.info(
                    "Loaded normalizer state: count=%s path=%s",
                    self._normalizer.count,
                    self._normalizer_state_path,
                )
        except Exception as e:
            logger.warning("Failed to load normalizer state (starting fresh): %s", e, exc_info=True)

        # Phase R1.5/R2: Episode collection + dream/PPO trigger
        # Configurable via neuro.yaml, default=1 for immediate PPO training in backtest
        self.dream_threshold = getattr(config.neuro, 'dream_episode_threshold', 1)
        self._completed_episodes: List[Dict[str, Any]] = []
        self._dream_in_progress = False
        self._dreams_triggered = 0
        self._ppo_trains_triggered = 0
        
        # Backpressure control
        self._backpressure_threshold = self._train_batch_size * 2
        self._backpressure_sleep_sec = 0.01
        self._backpressure_events = 0
        
        # Pending async tasks for clean shutdown
        self._pending_tasks: List[asyncio.Task] = []
        
        # Telemetry logging
        self.telemetry = TelemetryLogger(log_dir=self.config.system.data_dir.parent / "logs")
        logger.info(f"Telemetry CSV: {self.telemetry.filepath_str}")
        
        logger.info("Neocortex Adapter initialized (Phase 4: Shadow Intents + Checkpointing)")

    async def handle_features(self, payload: Dict[str, Any]):
        """
        Callback for EVT:FEATURES_CALCULATED.
        
        Full pipeline:
        0. Backpressure (wait if buffer overloaded)
        1. Parse -> MarketObservation
        2. Value -> Importance
        3. Memorize -> Buffer
        4. Encode -> Latent z
        5. Act -> Shadow Intent
        6. Train -> Background
        """
        try:
            # 0. Backpressure: Wait if buffer is too full (prevents ingestion outpacing training)
            while len(self.buffer) > self._backpressure_threshold:
                self._backpressure_events += 1
                if self._backpressure_events % 100 == 1:
                    logger.debug(
                        f"Backpressure active: buffer={len(self.buffer)} > threshold={self._backpressure_threshold}"
                    )
                await asyncio.sleep(self._backpressure_sleep_sec)
            
            # 1. Parse (String -> Float32 Typed Observation)
            obs = self.parser.parse(payload)

            # 1.5 Normalize features online for stable ML training
            self._normalizer.update(obs.features_vector)
            norm_vec = self._normalizer.normalize(obs.features_vector)
            obs = MarketObservation(
                ts=obs.ts,
                mid_price=obs.mid_price,
                volatility=obs.volatility,
                obi=obs.obi,
                features_vector=norm_vec,
                normalized=True,
            )
            
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

    async def add_completed_episode(self, episode: Any) -> None:
        """
        Called when an RL episode completes (typically on trade close).

        Intentionally lightweight: append + log + condition check.
        """
        try:
            episode_dict = self._episode_to_dict(episode)

            self._completed_episodes.append(episode_dict)
            logger.info(
                "Episode added. Buffer size: %s / Threshold: %s",
                len(self._completed_episodes),
                self.dream_threshold,
            )

            await self._maybe_dream()
        except Exception as e:
            logger.error(f"Failed to add completed episode: {e}", exc_info=True)

    async def train_ppo_now(self) -> None:
        """Manual debug hook to force PPO training on whatever is buffered."""
        try:
            episodes_to_process = list(self._completed_episodes)
            self._completed_episodes.clear()

            if not episodes_to_process:
                logger.info("train_ppo_now: no episodes buffered; skipping")
                return

            logger.info("train_ppo_now: forcing PPO train on %d episodes", len(episodes_to_process))
            await self._trigger_ppo_training(episodes_to_process)
        except Exception as e:
            logger.error(f"train_ppo_now failed: {e}", exc_info=True)

    def _episode_to_dict(self, episode: Any) -> Dict[str, Any]:
        """
        Normalize episode input (dataclass or dict) into a worker-picklable dict.
        """
        if isinstance(episode, dict):
            raw = episode
        else:
            raw = {
                "symbol": getattr(episode, "symbol", None),
                "timestamp": getattr(episode, "timestamp", None),
                "features": getattr(episode, "features", None),
                "side": getattr(episode, "side", None),
                "reward": getattr(episode, "reward", None),
                "pnl": getattr(episode, "pnl", None),
            }

        reward = raw.get("reward", 0.0)
        if reward is None:
            logger.warning("Episode reward is None; forcing 0.0 (episode=%s)", raw.get("symbol"))
            reward = 0.0

        features = raw.get("features") or {}
        features_vector = [
            float(features.get(name, 0.0) or 0.0) for name in self.config.ingest.feature_list
        ]

        return {
            "symbol": raw.get("symbol"),
            "timestamp": raw.get("timestamp"),
            "side": raw.get("side") or "FLAT",
            "reward": float(reward),
            "pnl": raw.get("pnl"),
            "features_vector": features_vector,
        }

    async def _maybe_dream(self) -> None:
        """
        Decide whether to trigger dream consolidation / PPO training.
        """
        logger.debug("Checking dream condition...")

        if self._dream_in_progress:
            return

        if len(self._completed_episodes) < self.dream_threshold:
            return

        logger.info("TRIGGERING DREAM SEQUENCE NOW!")

        episodes_to_process = list(self._completed_episodes)
        self._completed_episodes.clear()

        self._dream_in_progress = True
        self._dreams_triggered += 1

        asyncio.create_task(self._run_dream_sequence(episodes_to_process))

    async def _run_dream_sequence(self, episodes_to_process: List[Dict[str, Any]]) -> None:
        try:
            await self._trigger_ppo_training(episodes_to_process)
        except Exception as e:
            logger.error(f"Dream sequence failed: {e}", exc_info=True)
        finally:
            self._dream_in_progress = False

    async def _trigger_ppo_training(self, episodes_to_process: List[Dict[str, Any]]) -> None:
        if self.brain_bridge is None:
            logger.warning("PPO training skipped: BrainBridge not available")
            return

        self._ppo_trains_triggered += 1
        logger.info("PPO training triggered on %d episodes", len(episodes_to_process))

        result = await self.brain_bridge.train_ppo_async(episodes_to_process)
        if not result:
            logger.warning("PPO training returned empty result (likely PPO disabled); skipping")
        elif "error" in result:
            logger.warning("PPO training error: %s", result.get("error"))
        else:
            logger.info("PPO update complete: %s", result)

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
            
            # Persist to JSONL file
            if self._shadow_intent_log is not None:
                try:
                    self._shadow_intent_log.write(json.dumps(shadow_intent) + "\n")
                    self._shadow_intent_log.flush()
                except Exception as log_err:
                    logger.warning(f"Failed to write shadow intent to JSONL: {log_err}")
            
            # Log to telemetry CSV
            self.telemetry.log_shadow_intent(
                action=action_result["action"],
                action_name=action_result["action_name"],
                confidence=action_result["confidence"],
                value=action_result["value"]
            )
            
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
                
                # Log to telemetry CSV
                self.telemetry.log_training(
                    vae_loss=losses.get('vae_loss'),
                    vae_mse=losses.get('vae_mse'),
                    vae_kld=losses.get('vae_kld'),
                    wm_loss=losses.get('wm_loss'),
                    train_step=self._total_train_steps
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
                self._save_normalizer_state()
            else:
                logger.warning(f"Checkpoint save failed at step {self._total_train_steps}")

    def _save_normalizer_state(self) -> None:
        try:
            self._normalizer.save_state(self._normalizer_state_path)
        except Exception as e:
            logger.warning("Failed to save normalizer state: %s", e, exc_info=True)

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

    async def shutdown_async(self):
        """
        Async graceful shutdown with final checkpoint save.
        
        This ensures all pending training completes and weights are persisted.
        """
        logger.info("NeocortexAdapter: Starting async shutdown...")
        
        # 1. Wait for pending training tasks
        if self._pending_tasks:
            logger.info(f"Waiting for {len(self._pending_tasks)} pending tasks...")
            pending_valid = [t for t in self._pending_tasks if not t.done()]
            if pending_valid:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*pending_valid, return_exceptions=True),
                        timeout=10.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for pending tasks")
        
        # 2. Force final PPO training if episodes are buffered
        if self._completed_episodes and self.brain_bridge is not None:
            logger.info(f"Final PPO training on {len(self._completed_episodes)} buffered episodes...")
            try:
                await self._trigger_ppo_training(list(self._completed_episodes))
                self._completed_episodes.clear()
            except Exception as e:
                logger.warning(f"Final PPO training failed: {e}")
        
        # 3. Save final checkpoint (CRITICAL)
        if self.brain_bridge is not None:
            checkpoint_dir = self.config.system.checkpoint_dir
            logger.info(f"Saving final checkpoint at step {self._total_train_steps}...")
            try:
                success = await self.brain_bridge.save_async(str(checkpoint_dir))
                if success:
                    logger.info(f"✓ Final checkpoint saved at step {self._total_train_steps}")
                else:
                    logger.warning("Final checkpoint save returned False")
            except Exception as e:
                logger.error(f"Final checkpoint save failed: {e}")
        
        # 4. Save normalizer state
        self._save_normalizer_state()
        
        # 5. Close shadow intent log
        if self._shadow_intent_log is not None:
            try:
                self._shadow_intent_log.close()
            except Exception:
                pass
        
        # 6. Shutdown brain bridge
        if self.brain_bridge is not None:
            self.brain_bridge.shutdown()
        
        logger.info(
            f"NeocortexAdapter async shutdown complete: "
            f"TrainSteps={self._total_train_steps} "
            f"ShadowIntents={self._shadow_intents_emitted} "
            f"BackpressureEvents={self._backpressure_events}"
        )
    
    def shutdown(self):
        """
        Sync shutdown fallback (prefer shutdown_async when possible).
        """
        logger.warning("Using sync shutdown - checkpoint may not be saved!")
        self._save_normalizer_state()
        if self._shadow_intent_log is not None:
            try:
                self._shadow_intent_log.close()
            except Exception:
                pass
        if self.brain_bridge is not None:
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
            "samples_since_train": self._samples_since_last_train,
            "episodes_buffered": len(self._completed_episodes),
            "dream_threshold": self.dream_threshold,
            "dreams_triggered": self._dreams_triggered,
            "ppo_trains_triggered": self._ppo_trains_triggered,
        }
