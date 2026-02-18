"""
Neocortex Transport Adapter

Bridges the internal domain logic with the external Aurora Event Bus.
Acting as the 'Senses' input port.

Phase 4: Added Shadow Intent emission and checkpointing.
"""

import asyncio
import hashlib
import json
import logging
import time
from typing import Dict, Any, Optional, Callable, List, Awaitable
from pathlib import Path

from apps.reference.domains.neocortex.config_models import NeocortexConfig
from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser
from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
from apps.reference.domains.neocortex.logic.ingest.normalizer import WelfordNormalizer
from apps.reference.domains.neocortex.logic.amygdala.valuation import ValuationEngine
from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
from apps.reference.domains.neocortex.logic.brain.bridge import BrainBridge
from apps.reference.domains.neocortex.logic.telemetry import TelemetryLogger

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
        self._samples_since_last_train = 0
        self._train_batch_size = config.neuro.vae.batch_size
        self._total_train_steps = 0
        self._last_checkpoint_step = 0
        self._checkpoint_interval = config.neuro.checkpoint_every_n_steps
        self._max_inflight_training_tasks = max(1, int(getattr(config.system, "brain_workers", 1)))
        self._inflight_training_tasks = 0
        self._waiting_for_reward_source = False
        
        # Shadow intent control
        self._shadow_intents_emitted = 0
        
        # Shadow intent JSONL logging
        self._shadow_intent_log_path = self.config.system.data_dir / "shadow_intents.jsonl"
        self._shadow_intent_log_max_bytes = 10 * 1024 * 1024
        self._shadow_intent_log_backups = 5
        self._shadow_intent_log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Shadow intent log configured: {self._shadow_intent_log_path}")

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
        if self.config.system.run_mode == "live" and self.dream_threshold < 5:
            logger.warning(
                "dream_episode_threshold=%s is too low for live mode; forcing to 5",
                self.dream_threshold,
            )
            self.dream_threshold = 5
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
            # 0. Non-blocking backpressure signal (never block ingestion loop)
            if (
                len(self.buffer) > self._backpressure_threshold
                and self._inflight_training_tasks >= self._max_inflight_training_tasks
            ):
                self._backpressure_events += 1
                if self._backpressure_events % 100 == 1:
                    logger.debug(
                        "Backpressure signal: buffer=%s threshold=%s inflight=%s max_inflight=%s",
                        len(self.buffer),
                        self._backpressure_threshold,
                        self._inflight_training_tasks,
                        self._max_inflight_training_tasks,
                    )
                    self._emit_alert(
                        severity="WARN",
                        code="BACKPRESSURE_SUSTAINED",
                        message="Buffer pressure sustained while training queue saturated",
                        details={
                            "buffer_size": len(self.buffer),
                            "threshold": self._backpressure_threshold,
                            "inflight_tasks": self._inflight_training_tasks,
                            "max_inflight_tasks": self._max_inflight_training_tasks,
                        },
                    )
            
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
            if not bool(episode_dict.get("reward_missing", False)):
                self.telemetry.log_episode(
                    reward=float(episode_dict.get("reward", 0.0)),
                    pnl=episode_dict.get("pnl"),
                )

            self.telemetry.log_buffer_stats(
                buffer_size=len(self.buffer),
                episodes_collected=len(self._completed_episodes),
                episodes_processed=0,
                samples_since_train=self._samples_since_last_train,
            )
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
        reward_missing = reward is None
        if reward is None:
            logger.warning(
                "No structured reward for episode %s; moving training to waiting_for_reward_source",
                raw.get("symbol"),
            )
            self._emit_alert(
                severity="WARN",
                code="NO_STRUCTURED_REWARD_RECEIVED",
                message="Structured reward missing; training gated until reward source is available",
                details={
                    "symbol": raw.get("symbol"),
                    "timestamp": raw.get("timestamp"),
                },
            )
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
            "reward_missing": reward_missing,
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

        episodes_to_process = [
            ep for ep in self._completed_episodes if not bool(ep.get("reward_missing", False))
        ]
        self._completed_episodes.clear()

        if not episodes_to_process:
            self._waiting_for_reward_source = True
            logger.warning(
                "No trainable episodes in buffer (structured reward missing). "
                "State=waiting_for_reward_source"
            )
            self._emit_alert(
                severity="WARN",
                code="NO_STRUCTURED_REWARD_RECEIVED",
                message=(
                    "No fallback policy active: training is waiting for structured reward source "
                    "while ingestion remains active"
                ),
                details={
                    "state": "waiting_for_reward_source",
                    "dream_threshold": self.dream_threshold,
                },
            )
            return

        self._waiting_for_reward_source = False
        self._dream_in_progress = True
        self._dreams_triggered += 1

        self._track_task(self._run_dream_sequence(episodes_to_process), "dream_sequence")

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
            self._emit_alert(
                severity="WARN",
                code="BRAIN_BRIDGE_UNAVAILABLE",
                message="BrainBridge not available; training skipped in degraded mode",
            )
            return

        self._ppo_trains_triggered += 1
        logger.info("PPO training triggered on %d episodes", len(episodes_to_process))

        result = await self.brain_bridge.train_ppo_async(episodes_to_process)
        if not result:
            logger.warning("PPO training returned empty result (likely PPO disabled); skipping")
        elif "error" in result:
            logger.warning("PPO training error: %s", result.get("error"))
        else:
            def _get_float(*keys: str) -> Optional[float]:
                for key in keys:
                    if key not in result:
                        continue
                    value = result.get(key)
                    if value is None:
                        continue
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        logger.warning("Invalid PPO metric value for key '%s': %r", key, value)
                return None

            ppo_loss_pi = _get_float("loss_pi", "policy_loss", "ppo_loss_pi")
            ppo_loss_v = _get_float("loss_v", "value_loss", "ppo_loss_v")
            ppo_entropy = _get_float("entropy", "ppo_entropy")
            episodes_processed_raw = result.get("episodes_processed")
            try:
                episodes_processed = (
                    int(episodes_processed_raw)
                    if episodes_processed_raw is not None
                    else len(episodes_to_process)
                )
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid episodes_processed value in PPO result: %r",
                    episodes_processed_raw,
                )
                episodes_processed = len(episodes_to_process)
            train_step_raw = result.get("train_step")
            try:
                train_step = (
                    int(train_step_raw)
                    if train_step_raw is not None
                    else self._total_train_steps
                )
            except (TypeError, ValueError):
                train_step = self._total_train_steps
            available_metrics = {
                "ppo_loss_pi": ppo_loss_pi,
                "ppo_loss_v": ppo_loss_v,
                "ppo_entropy": ppo_entropy,
            }
            if any(v is not None for v in available_metrics.values()):
                self.telemetry.log_training(
                    ppo_loss_pi=ppo_loss_pi,
                    ppo_loss_v=ppo_loss_v,
                    ppo_entropy=ppo_entropy,
                    train_step=train_step,
                )
            else:
                logger.warning(
                    "PPO result has no recognized telemetry keys: keys=%s",
                    sorted(result.keys()),
                )

            self.telemetry.log_buffer_stats(
                buffer_size=len(self.buffer),
                episodes_collected=len(self._completed_episodes),
                episodes_processed=episodes_processed,
                samples_since_train=self._samples_since_last_train,
            )
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
            
            intent_ts = time.time()
            symbol = str(original_payload.get("symbol", "UNKNOWN"))
            action_name = str(action_result.get("action_name", "FLAT"))
            source_ts = float(obs.ts)
            idempotent_seed = f"{symbol}|{action_name}|{source_ts:.6f}|{self._total_train_steps}"
            idempotent_hash = hashlib.sha256(idempotent_seed.encode("utf-8")).hexdigest()[:16]
            idempotent_key = (
                f"neocortex:r2:{symbol}:{action_name}:{int(source_ts * 1000)}:{idempotent_hash}"
            )

            # Build canonical shadow intent payload (dual emit with legacy event name).
            shadow_intent = {
                "event_type": "EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED",
                "schema_version": "1.0.0",
                "timestamp": intent_ts,
                "symbol": symbol,
                "action": action_result["action"],
                "action_name": action_name,
                "value": action_result["value"],
                "confidence": action_result["confidence"],
                "latent_state": z.tolist() if hasattr(z, 'tolist') else list(z),
                "source_ts": source_ts,
                "train_steps": self._total_train_steps,
                "idempotent_key": idempotent_key,
                "why": [
                    f"confidence={float(action_result.get('confidence', 0.0)):.6f}",
                    f"value={float(action_result.get('value', 0.0)):.6f}",
                ],
            }

            # Emit canonical + legacy events during migration window.
            if self.event_emitter is not None:
                canonical_payload = dict(shadow_intent)
                legacy_payload = dict(shadow_intent)
                legacy_payload["event_type"] = "EVT:NEOCORTEX_SHADOW_INTENT"
                self.event_emitter("EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED", canonical_payload)
                self.event_emitter("EVT:NEOCORTEX_SHADOW_INTENT", legacy_payload)
            
            self._shadow_intents_emitted += 1
            
            # Persist to JSONL file
            try:
                self._rotate_shadow_intent_log_if_needed()
                with open(self._shadow_intent_log_path, "a", encoding="utf-8") as shadow_log:
                    shadow_log.write(json.dumps(shadow_intent) + "\n")
                    shadow_log.flush()
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
            
        if len(self.buffer) < self.config.ingest.min_samples_before_ready:
            return
            
        if self._samples_since_last_train < self._train_batch_size:
            return

        if self._inflight_training_tasks >= self._max_inflight_training_tasks:
            self._backpressure_events += 1
            if self._backpressure_events % 100 == 1:
                logger.debug(
                    "Training queue saturated: inflight=%s max_inflight=%s",
                    self._inflight_training_tasks,
                    self._max_inflight_training_tasks,
                )
                self._emit_alert(
                    severity="WARN",
                    code="TRAINING_QUEUE_SATURATED",
                    message="Training queue saturated; delaying new training batches",
                    details={
                        "inflight_tasks": self._inflight_training_tasks,
                        "max_inflight_tasks": self._max_inflight_training_tasks,
                    },
                )
            return
            
        try:
            batch_items = self.buffer.get_batch(self._train_batch_size)
            batch_obs = [item[0] for item in batch_items]
            self._inflight_training_tasks += 1
            self._track_task(self._run_training(batch_obs), "train_batch")
            self._samples_since_last_train = 0
            
        except Exception as e:
            logger.error(f"Failed to start training: {e}", exc_info=True)
            self._inflight_training_tasks = max(0, self._inflight_training_tasks - 1)

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
            self._inflight_training_tasks = max(0, self._inflight_training_tasks - 1)

    def _track_task(self, coro: Awaitable[Any], task_name: str) -> asyncio.Task:
        """
        Register background task for graceful shutdown and leak detection.
        """
        task = asyncio.create_task(coro)
        self._pending_tasks.append(task)

        def _on_done(done_task: asyncio.Task) -> None:
            try:
                self._pending_tasks.remove(done_task)
            except ValueError:
                pass

            if done_task.cancelled():
                return

            try:
                exc = done_task.exception()
            except Exception:
                exc = None

            if exc is not None:
                logger.error("Background task '%s' failed: %s", task_name, exc, exc_info=True)

        task.add_done_callback(_on_done)
        return task

    def _emit_alert(
        self,
        severity: str,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "event_type": "EVT:NEOCORTEX_ALERT",
            "timestamp": time.time(),
            "severity": severity,
            "code": code,
            "message": message,
            "details": details or {},
        }
        logger.warning("[%s] %s", code, message)
        if self.event_emitter is not None:
            try:
                self.event_emitter("EVT:NEOCORTEX_ALERT", payload)
            except Exception as emit_err:
                logger.error("Failed to emit EVT:NEOCORTEX_ALERT: %s", emit_err)

    def _rotate_shadow_intent_log_if_needed(self) -> None:
        try:
            if not self._shadow_intent_log_path.exists():
                return
            if self._shadow_intent_log_path.stat().st_size < self._shadow_intent_log_max_bytes:
                return

            for idx in range(self._shadow_intent_log_backups - 1, 0, -1):
                src = Path(f"{self._shadow_intent_log_path}.{idx}")
                dst = Path(f"{self._shadow_intent_log_path}.{idx + 1}")
                if src.exists():
                    src.replace(dst)

            rotated = Path(f"{self._shadow_intent_log_path}.1")
            self._shadow_intent_log_path.replace(rotated)
            logger.info(
                "Rotated shadow intent log: %s -> %s",
                self._shadow_intent_log_path,
                rotated,
            )
        except Exception as e:
            logger.warning("Failed to rotate shadow intent log: %s", e, exc_info=True)

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
                self._emit_alert(
                    severity="WARN",
                    code="BRAIN_BRIDGE_UNAVAILABLE",
                    message="BrainBridge start failed; ingestion stays active, training disabled",
                )
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
        
        # 5. Shutdown brain bridge
        if self.brain_bridge is not None:
            self.brain_bridge.shutdown()
        
        logger.info(
            f"NeocortexAdapter async shutdown complete: "
            f"TrainSteps={self._total_train_steps} "
            f"ShadowIntents={self._shadow_intents_emitted} "
            f"BackpressureEvents={self._backpressure_events} "
            f"InflightTasks={self._inflight_training_tasks}"
        )
    
    def shutdown(self):
        """
        Sync shutdown fallback (prefer shutdown_async when possible).
        """
        logger.warning("Using sync shutdown - checkpoint may not be saved!")
        self._save_normalizer_state()
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
            "inflight_tasks": self._inflight_training_tasks,
            "backpressure_events": self._backpressure_events,
            "episodes_buffered": len(self._completed_episodes),
            "dream_threshold": self.dream_threshold,
            "dreams_triggered": self._dreams_triggered,
            "ppo_trains_triggered": self._ppo_trains_triggered,
            "waiting_for_reward_source": self._waiting_for_reward_source,
        }

