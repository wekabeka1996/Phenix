# QUARANTINED: legacy_runtime
"""
Neocortex Transport Adapter

Bridges the internal domain logic with the external Aurora Event Bus.
Acting as the 'Senses' input port.

Phase 4: Added Shadow Intent emission and checkpointing.
"""
__quarantined__ = True

import asyncio
import hashlib
import inspect
import json
import logging
import threading
import time
from collections import Counter, deque
from contextlib import nullcontext
from dataclasses import asdict, is_dataclass
from typing import Dict, Any, Optional, Callable, List, Awaitable
from pathlib import Path
import numpy as np

from apps.reference.domains.neocortex.config_models import NeocortexConfig
from apps.reference.domains.neocortex.logic.datasets.hygiene import DatasetPolicyEngine
from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser
from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
from apps.reference.domains.neocortex.logic.ingest.normalizer import (
    MultiSymbolWelfordNormalizer,
    WelfordNormalizer,
    sanitize_symbol,
)
from apps.reference.domains.neocortex.logic.amygdala.valuation import ValuationEngine
from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
from apps.reference.domains.neocortex.logic.brain.bridge import BrainBridge
from apps.reference.domains.neocortex.logic.telemetry import TelemetryLogger
from apps.reference.domains.neocortex.logic.reward.feature_buffer import FeatureRingBuffer
from apps.reference.domains.neocortex.logic.reward.regime_labeler import RegimeLabeler, REGIME_NAMES
from apps.reference.domains.neocortex.logic.reward.reward_calculator import RegimeRewardCalculator

logger = logging.getLogger(__name__)


OBJECTIVE_FAMILY_REPRESENTATION = "representation"
OBJECTIVE_FAMILY_REGIME_SUPERVISION = "regime_supervision"
OBJECTIVE_FAMILY_EXECUTION_QUALITY = "execution_quality"
OBJECTIVE_FAMILY_POLICY = "policy"
OBJECTIVE_FAMILY_ALLOWED = {
    OBJECTIVE_FAMILY_REPRESENTATION,
    OBJECTIVE_FAMILY_REGIME_SUPERVISION,
    OBJECTIVE_FAMILY_EXECUTION_QUALITY,
    OBJECTIVE_FAMILY_POLICY,
}


def _normalize_epoch_to_ms(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric) or numeric <= 0.0:
        return None
    if numeric >= 1e11:
        return int(round(numeric))
    if numeric >= 1e9:
        return int(round(numeric * 1000.0))
    return None


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
        self._max_inflight_training_tasks = max(
            1, int(getattr(config.system, "brain_workers", 1)))
        self._inflight_training_tasks = 0
        self._waiting_for_reward_source = False

        # Shadow intent control
        self._shadow_intents_emitted = 0

        # Shadow intent JSONL logging
        self._shadow_intent_log_path = self.config.system.data_dir / "shadow_intents.jsonl"
        self._shadow_intent_log_max_bytes = 10 * 1024 * 1024
        self._shadow_intent_log_backups = 5
        self._shadow_intent_log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"Shadow intent log configured: {self._shadow_intent_log_path}")

        # Online feature normalization (z-score) to stabilize VAE training.
        self._normalization_scope = str(
            getattr(self.config.ingest, "normalization_scope", "global")
        ).lower()
        self._normalizer_state_path = self.config.system.data_dir / "normalizer_state.npz"
        self._normalizer_states_dir = self.config.system.data_dir / "normalizer_states"
        self._normalizer = None
        self._normalizers_by_symbol: Optional[MultiSymbolWelfordNormalizer] = None
        self._init_normalizers()

        # Checkpoint-side metadata (used to detect preprocessing mismatch).
        self._checkpoint_metadata_path = (
            self.config.system.checkpoint_dir / "checkpoint_metadata.json"
        )

        # Phase R1.5/R2: Episode collection + dream/PPO trigger
        # Configurable via neuro.yaml, default=1 for immediate PPO training in backtest
        self.dream_threshold = getattr(
            config.neuro, 'dream_episode_threshold', 1)
        if self.config.system.run_mode == "live" and self.dream_threshold < 5:
            logger.warning(
                "dream_episode_threshold=%s is too low for live mode; forcing to 5",
                self.dream_threshold,
            )
            self.dream_threshold = 5
        self._objective_split_enforced = bool(
            getattr(config.neuro.ppo, "objective_split_enforced", True)
        )
        self._policy_training_mode = str(
            getattr(config.neuro.ppo, "policy_training_mode", "disabled")
        ).lower()
        self._sequence_inference_mode = str(
            getattr(config.neuro.sequence,
                    "inference_mode", "stateless_per_event")
        ).lower()
        self._representation_training_mode = str(
            getattr(config.neuro.sequence,
                    "representation_training_mode", "independent_rows")
        ).lower()
        self._reset_sequence_on_replay_start = bool(
            getattr(config.neuro.sequence, "reset_on_replay_start", True)
        )
        self._dataset_policy = DatasetPolicyEngine(
            config.neuro.dataset,
            policy_training_mode=self._policy_training_mode,
            representation_training_mode=self._representation_training_mode,
            sequence_inference_mode=self._sequence_inference_mode,
        )
        self._representation_samples = deque(maxlen=4096)
        self._regime_supervision_samples = deque(maxlen=4096)
        self._execution_quality_samples = deque(maxlen=4096)
        self._policy_samples: List[Dict[str, Any]] = []
        self._evaluated_samples_by_family = {
            OBJECTIVE_FAMILY_REPRESENTATION: deque(maxlen=4096),
            OBJECTIVE_FAMILY_REGIME_SUPERVISION: deque(maxlen=4096),
            OBJECTIVE_FAMILY_EXECUTION_QUALITY: deque(maxlen=4096),
            OBJECTIVE_FAMILY_POLICY: deque(maxlen=4096),
        }
        self._dataset_status_counts = Counter()
        self._dataset_exclusion_counts = Counter()
        self._dataset_quarantine_counts = Counter()
        performance_cfg = config.neuro.performance
        self._operating_mode = str(
            getattr(performance_cfg, "operating_mode", "offline_replay")
        ).lower()
        self._shadow_intent_emit_policy = str(
            getattr(performance_cfg, "shadow_intent_emit_policy", "emit_all")
        ).lower()
        self._shadow_intent_decimation_stride = int(
            getattr(performance_cfg, "shadow_intent_decimation_stride", 1)
        )
        self._shadow_jsonl_write_policy = str(
            getattr(performance_cfg, "shadow_jsonl_write_policy", "immediate")
        ).lower()
        self._telemetry_write_policy = str(
            getattr(performance_cfg, "telemetry_write_policy", "immediate")
        ).lower()
        self._shadow_log_flush_threshold = int(
            getattr(performance_cfg, "shadow_log_flush_threshold", 1)
        )
        self._telemetry_flush_threshold = int(
            getattr(performance_cfg, "telemetry_flush_threshold", 1)
        )
        self._non_critical_queue_limit = int(
            getattr(performance_cfg, "non_critical_queue_limit", 1024)
        )
        self._flush_interval_ms = int(
            getattr(performance_cfg, "flush_interval_ms", 1000)
        )
        self._non_critical_overflow_policy = str(
            getattr(performance_cfg, "non_critical_overflow_policy", "drop_oldest")
        ).lower()
        self._shadow_intent_log_buffer: List[str] = []
        self._shadow_intent_io_lock = threading.RLock()
        self._shadow_intents_generated = 0
        self._shadow_intents_decimated = 0
        self._shadow_intent_log_rows_buffered = 0
        self._shadow_intent_log_rows_dropped = 0
        self._shadow_intent_log_flushes = 0
        self._non_critical_overload_events = 0
        self._last_non_critical_flush_ts_ms = int(time.time() * 1000.0)
        self._dream_in_progress = False
        self._dreams_triggered = 0
        self._ppo_trains_triggered = 0
        self._objective_rejections = 0
        self._policy_training_rejections = 0

        # Backpressure control
        self._backpressure_threshold = self._train_batch_size * 2
        self._backpressure_sleep_sec = 0.01
        self._backpressure_events = 0

        # Pending async tasks for clean shutdown
        self._pending_tasks: List[asyncio.Task] = []

        # Telemetry logging
        self.telemetry = TelemetryLogger(
            log_dir=self.config.system.data_dir.parent / "logs",
            write_policy=self._telemetry_write_policy,
            flush_threshold=self._telemetry_flush_threshold,
            flush_interval_ms=self._flush_interval_ms,
            pending_limit=self._non_critical_queue_limit,
            overflow_policy=self._non_critical_overflow_policy,
        )
        logger.info(f"Telemetry CSV: {self.telemetry.filepath_str}")

        # Regime Oracle infrastructure (REGIME_PIVOT_PLAN Phase 2)
        self._reward_mode = getattr(config.neuro.ppo, "reward_mode", "pnl")
        self._oracle_ring_buffer: Optional[FeatureRingBuffer] = None
        self._oracle_labeler: Optional[RegimeLabeler] = None
        self._oracle_reward_calc: Optional[RegimeRewardCalculator] = None
        self._oracle_settlements = 0

        if self._reward_mode == "regime_oracle":
            oracle_cfg = config.oracle
            if oracle_cfg is None:
                raise ValueError(
                    "reward_mode='regime_oracle' requires oracle config "
                    "(config/regime_oracle_reward.yaml)"
                )
            self._oracle_ring_buffer = FeatureRingBuffer(
                horizon_bars=oracle_cfg.horizon_bars
            )
            self._oracle_labeler = RegimeLabeler.from_config(oracle_cfg)
            self._oracle_reward_calc = RegimeRewardCalculator.from_config(
                oracle_cfg)
            logger.info(
                "Regime Oracle initialized: horizon=%d, reward_mode=%s",
                oracle_cfg.horizon_bars,
                self._reward_mode,
            )

        logger.info(
            "Neocortex Adapter initialized (Phase 4: Shadow Intents + Checkpointing)")

    def _init_normalizers(self) -> None:
        """Initialize global/per-symbol normalizers with backward-compat fallback."""
        dim = len(self.config.ingest.feature_list)
        if self._normalization_scope == "per_symbol":
            self._normalizers_by_symbol = MultiSymbolWelfordNormalizer(
                dim=dim, eps=1e-8)
            loaded_count = 0
            try:
                loaded_count = self._normalizers_by_symbol.load_states(
                    self._normalizer_states_dir)
            except Exception as e:
                logger.warning(
                    "Failed to load per-symbol normalizer states (starting fresh): %s",
                    e,
                    exc_info=True,
                )
            if loaded_count > 0:
                logger.info(
                    "Loaded %d per-symbol normalizer states from %s",
                    loaded_count,
                    self._normalizer_states_dir,
                )
            elif self._normalizer_state_path.exists():
                # Do not silently migrate old global stats into per-symbol mode.
                logger.warning(
                    "Legacy global normalizer state found at %s while normalization_scope=per_symbol. "
                    "Starting fresh per-symbol states.",
                    self._normalizer_state_path,
                )
            return

        self._normalizer = WelfordNormalizer(dim=dim, eps=1e-8)
        try:
            loaded = self._normalizer.load_state(self._normalizer_state_path)
            if loaded:
                logger.info(
                    "Loaded global normalizer state: count=%s path=%s",
                    self._normalizer.count,
                    self._normalizer_state_path,
                )
        except Exception as e:
            logger.warning(
                "Failed to load global normalizer state (starting fresh): %s", e, exc_info=True)

    def _normalize_features_for_symbol(
        self,
        symbol: str,
        raw_features_vector,
    ):
        """Update + normalize features using current normalization scope."""
        vec = np.asarray(raw_features_vector, dtype=np.float32).reshape(-1)
        if self._normalization_scope == "per_symbol":
            symbol_key = sanitize_symbol(symbol)
            if self._normalizers_by_symbol is not None:
                self._normalizers_by_symbol.update(symbol_key, vec)
                return self._normalizers_by_symbol.normalize(symbol_key, vec)
            return vec

        if self._normalizer is not None:
            self._normalizer.update(vec)
            return self._normalizer.normalize(vec)
        return vec

    def _extract_raw_feature_map(self, payload: Dict[str, Any]) -> Dict[str, float]:
        """
        Extract raw feature map from payload for oracle labeling.
        Keeps raw values (before parser transforms) to preserve label semantics.
        """
        features = payload.get("features")
        if not isinstance(features, dict):
            features = payload
        flat_features: Dict[str, Any] = {}
        if isinstance(features, dict):
            def _emit(key: str, value: Any) -> None:
                if key not in flat_features:
                    flat_features[key] = value

            def _recurse(prefix: list[str], obj: Any) -> None:
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        parts = str(k).split(".") if isinstance(
                            k, str) and "." in k else [str(k)]
                        _recurse(prefix + [p for p in parts if p], v)
                    return
                key = "_".join([p for p in prefix if p])
                _emit(key, obj)

            _recurse([], features)
        else:
            flat_features = {}

        raw_map: Dict[str, float] = {}
        for name in self.config.ingest.feature_list:
            if name not in flat_features:
                continue
            value = flat_features[name]
            try:
                f_value = float(value)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(f_value):
                continue
            raw_map[name] = f_value
        return raw_map

    def _build_preprocessing_metadata(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "timestamp": time.time(),
            "feature_list": list(self.config.ingest.feature_list),
            "preprocessing": {
                "normalization_scope": self._normalization_scope,
                "price_feature_mode": getattr(self.config.ingest, "price_feature_mode", "raw"),
                "delta_price_mode": getattr(self.config.ingest, "delta_price_mode", "raw"),
                "normalization_method": self.config.ingest.normalization_method,
                "normalization_window": self.config.ingest.normalization_window,
            },
        }

    def _save_checkpoint_metadata(self) -> None:
        try:
            self._checkpoint_metadata_path.parent.mkdir(
                parents=True, exist_ok=True)
            metadata = self._build_preprocessing_metadata()
            with open(self._checkpoint_metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=True, indent=2)
        except Exception as e:
            logger.warning(
                "Failed to write checkpoint metadata: %s", e, exc_info=True)

    def _validate_checkpoint_metadata(self) -> None:
        if not self._checkpoint_metadata_path.exists():
            return
        try:
            with open(self._checkpoint_metadata_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            loaded_prep = loaded.get("preprocessing", {})
            current = self._build_preprocessing_metadata()["preprocessing"]
            mismatch = {
                key: (loaded_prep.get(key), current.get(key))
                for key in current.keys()
                if loaded_prep.get(key) != current.get(key)
            }
            loaded_features = loaded.get("feature_list", [])
            current_features = list(self.config.ingest.feature_list)
            if loaded_features != current_features:
                mismatch["feature_list"] = ("<different>", "<current>")
            if mismatch:
                logger.warning(
                    "Checkpoint preprocessing metadata mismatch detected: %s",
                    mismatch,
                )
                self._emit_alert(
                    severity="WARN",
                    code="CHECKPOINT_PREPROCESSING_MISMATCH",
                    message="Checkpoint metadata does not match current preprocessing config",
                    details={"mismatch": mismatch},
                )
        except Exception as e:
            logger.warning(
                "Failed to read checkpoint metadata: %s", e, exc_info=True)

    def _extract_event_ts_ms(self, payload: Dict[str, Any]) -> int:
        for key in ("event_ts_ms", "timestamp", "ts"):
            event_ts_ms = _normalize_epoch_to_ms(payload.get(key))
            if event_ts_ms is not None:
                return event_ts_ms
        raise ValueError("Feature payload missing canonical causal timestamp")

    def _normalize_feature_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        event_ts_ms = self._extract_event_ts_ms(payload)
        normalized = dict(payload)
        normalized["event_ts_ms"] = event_ts_ms
        normalized["timestamp"] = event_ts_ms / 1000.0
        normalized.setdefault("ts", normalized["timestamp"])
        return normalized

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
            normalized_payload = self._normalize_feature_payload(payload)

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
            obs = self.parser.parse(normalized_payload)
            symbol = str(normalized_payload.get("symbol") or "UNKNOWN")
            raw_feature_map = self._extract_raw_feature_map(normalized_payload)

            # 1.5 Normalize features online for stable ML training
            # Capture raw features BEFORE normalization for Oracle labeler
            raw_features_vector = obs.features_vector
            norm_vec = self._normalize_features_for_symbol(
                symbol=symbol, raw_features_vector=raw_features_vector)
            obs = MarketObservation(
                ts=obs.ts,
                mid_price=obs.mid_price,
                volatility=obs.volatility,
                obi=obs.obi,
                features_vector=norm_vec,
                normalized=True,
            )

            # 2. Value (Calculate Importance)
            reward = float(normalized_payload.get('reward_signal', 0.0))
            importance = self.amygdala.update(obs, reward)

            representation_sample = {
                "event_ts_ms": int(normalized_payload["event_ts_ms"]),
                "symbol": symbol,
                "features_vector": norm_vec.tolist(),
                "time_is_causal": normalized_payload.get("time_is_causal", True),
                "time_source": normalized_payload.get("time_source", "event_ts_ms"),
                "sequence_contract_mode": self._representation_training_mode,
            }
            evaluated = self._evaluate_dataset_candidate(
                representation_sample,
                objective_family=OBJECTIVE_FAMILY_REPRESENTATION,
                source_type="features_event",
                source_ref=str(
                    normalized_payload.get("event_id")
                    or f"features:{symbol}:{normalized_payload['event_ts_ms']}"
                ),
                source_event_type=str(
                    normalized_payload.get(
                        "event_type") or "EVT:FEATURES_CALCULATED"
                ),
            )

            # 3. Memorize (Store in Buffer only when explicitly trainable)
            if evaluated.is_trainable:
                self.buffer.add(obs, importance)
                self._representation_samples.append(
                    self._attach_dataset_provenance(
                        representation_sample,
                        evaluated=evaluated,
                    )
                )
                self._samples_since_last_train += 1

            # 4. Log Debug
            logger.debug(
                f"Ingested tick TS={obs.ts:.3f} Imp={importance:.4f} "
                f"Dim={obs.feature_dim} BufferLen={len(self.buffer)}"
            )

            # 5. Generate Shadow Intent (if bridge available)
            await self._generate_shadow_intent(
                obs,
                normalized_payload,
                raw_features_for_labeler=raw_feature_map,
            )

            # 6. Trigger Training (if ready)
            await self._maybe_train()

        except Exception as e:
            logger.error(f"Failed to ingest feature event: {e}", exc_info=True)

    def _coerce_objective_family(self, sample: Dict[str, Any]) -> Optional[str]:
        raw = sample.get("objective_family")
        if raw is None:
            return None
        family = str(raw).strip().lower()
        return family or None

    def _register_objective_rejection(self, reason: str, sample: Optional[Dict[str, Any]] = None) -> None:
        self._objective_rejections += 1
        logger.warning(
            "Objective sample rejected: reason=%s sample=%s", reason, sample or {})

    def _validate_sample_family(
        self,
        sample: Dict[str, Any],
        *,
        expected_family: str,
    ) -> bool:
        family = self._coerce_objective_family(sample)
        if family is None:
            self._register_objective_rejection(
                "missing_objective_family", sample)
            return False
        if family not in OBJECTIVE_FAMILY_ALLOWED:
            self._register_objective_rejection(
                "unknown_objective_family", sample)
            return False
        if family != expected_family:
            self._register_objective_rejection(
                f"unexpected_objective_family:{family}",
                sample,
            )
            return False
        return True

    def _build_execution_quality_sample(self, episode_dict: Dict[str, Any]) -> Dict[str, Any]:
        sample = dict(episode_dict)
        sample["objective_family"] = OBJECTIVE_FAMILY_EXECUTION_QUALITY
        sample["objective_route"] = "execution_quality_buffer"
        sample["policy_eligible"] = False
        sample["unresolved_lifecycle"] = bool(
            sample.get("unresolved_lifecycle") or sample.get(
                "unresolved_reason")
        )
        return sample

    def _record_dataset_decision(self, evaluated) -> None:
        self._dataset_status_counts[evaluated.eligibility_status] += 1
        self._dataset_exclusion_counts.update(
            evaluated.provenance.exclusion_reasons
        )
        self._dataset_quarantine_counts.update(
            evaluated.provenance.quarantine_reasons
        )
        family_buffer = self._evaluated_samples_by_family.get(
            evaluated.objective_family
        )
        if family_buffer is not None:
            family_buffer.append(evaluated)

    def _evaluate_dataset_candidate(
        self,
        sample: Dict[str, Any],
        *,
        objective_family: str,
        source_type: str,
        source_ref: str,
        source_event_type: str,
    ):
        evaluated = self._dataset_policy.evaluate_sample(
            sample,
            objective_family=objective_family,
            source_type=source_type,
            source_ref=source_ref,
            source_event_type=source_event_type,
            ingestion_mode=str(self.config.system.run_mode),
        )
        self._record_dataset_decision(evaluated)
        return evaluated

    def _attach_dataset_provenance(
        self,
        sample: Dict[str, Any],
        *,
        evaluated,
    ) -> Dict[str, Any]:
        routed = dict(sample)
        routed["dataset_provenance"] = evaluated.provenance.model_dump(
            mode="python")
        routed["eligibility_status"] = evaluated.eligibility_status
        routed["is_trainable"] = evaluated.is_trainable
        return routed

    def _register_non_critical_overload(self, reason: str) -> None:
        self._non_critical_overload_events += 1
        if self._non_critical_overload_events % 100 == 1:
            logger.warning(
                "Non-critical overload: reason=%s events=%s",
                reason,
                self._non_critical_overload_events,
            )

    def _should_emit_observational_shadow_output(self) -> bool:
        if self._shadow_intent_emit_policy == "emit_all":
            return True
        if self._operating_mode != "offline_replay":
            return True
        stride = max(1, int(self._shadow_intent_decimation_stride))
        return ((self._shadow_intents_generated - 1) % stride) == 0

    def _enqueue_shadow_intent_log(self, shadow_intent: Dict[str, Any]) -> None:
        with self._shadow_log_context():
            line = json.dumps(shadow_intent, ensure_ascii=True) + "\n"
            if self._shadow_jsonl_write_policy == "immediate":
                self._rotate_shadow_intent_log_if_needed()
                with open(self._shadow_intent_log_path, "a", encoding="utf-8") as shadow_log:
                    shadow_log.write(line)
                    shadow_log.flush()
                self._shadow_intent_log_flushes += 1
                return

            if len(self._shadow_intent_log_buffer) >= self._non_critical_queue_limit:
                self._shadow_intent_log_rows_dropped += 1
                self._register_non_critical_overload(
                    "shadow_intent_log_buffer_full")
                if self._non_critical_overflow_policy == "drop_oldest":
                    self._shadow_intent_log_buffer.pop(0)
                else:
                    return

            self._shadow_intent_log_buffer.append(line)
            self._shadow_intent_log_rows_buffered += 1
            self._flush_shadow_intent_buffer(force=False)

    def _shadow_log_context(self):
        return getattr(self, "_shadow_intent_io_lock", None) or nullcontext()

    def _flush_shadow_intent_buffer(self, *, force: bool) -> None:
        with self._shadow_log_context():
            if not self._shadow_intent_log_buffer:
                return

            now_ms = int(time.time() * 1000.0)
            should_flush = force
            if self._shadow_jsonl_write_policy == "immediate":
                should_flush = True
            elif len(self._shadow_intent_log_buffer) >= self._shadow_log_flush_threshold:
                should_flush = True
            elif now_ms - self._last_non_critical_flush_ts_ms >= self._flush_interval_ms:
                should_flush = True

            if not should_flush:
                return

            self._rotate_shadow_intent_log_if_needed()
            with open(self._shadow_intent_log_path, "a", encoding="utf-8") as shadow_log:
                shadow_log.writelines(self._shadow_intent_log_buffer)
                shadow_log.flush()
            self._shadow_intent_log_flushes += 1
            self._shadow_intent_log_buffer.clear()
            self._last_non_critical_flush_ts_ms = now_ms

    def _flush_non_critical_outputs(self, *, force: bool) -> None:
        self._flush_shadow_intent_buffer(force=force)
        self.telemetry.flush()

    async def _run_non_critical_io(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(func, *args, **kwargs)

    def _validate_batch_family(
        self,
        samples: List[Dict[str, Any]],
        *,
        expected_family: str,
    ) -> bool:
        if not samples:
            return False
        families = {self._coerce_objective_family(
            sample) for sample in samples}
        if None in families or len(families) != 1 or expected_family not in families:
            self._register_objective_rejection(
                "mixed_or_invalid_batch_family",
                {
                    "expected_family": expected_family,
                    "families": sorted([fam for fam in families if fam is not None]),
                    "samples": len(samples),
                },
            )
            return False
        return True

    def _build_regime_supervision_sample(
        self,
        *,
        symbol: str,
        settled,
        realized_regime: int,
        reward: float,
        confidence: Optional[float],
        model_features: List[float],
    ) -> Dict[str, Any]:
        event_ts_ms = _normalize_epoch_to_ms(settled.timestamp_t)
        return {
            "objective_family": OBJECTIVE_FAMILY_REGIME_SUPERVISION,
            "objective_route": "train_regime_supervision",
            "policy_eligible": False,
            "symbol": symbol,
            "timestamp": settled.timestamp_t,
            "event_ts_ms": event_ts_ms,
            "predicted_regime": int(settled.predicted_action),
            "realized_regime": int(realized_regime),
            "confidence": (
                float(confidence)
                if confidence is not None else None
            ),
            "reward": float(reward),
            "pnl": None,
            "features_vector": model_features,
        }

    async def add_policy_sample(self, sample: Dict[str, Any]) -> bool:
        if not self._validate_sample_family(
            sample,
            expected_family=OBJECTIVE_FAMILY_POLICY,
        ):
            return False

        evaluated = self._evaluate_dataset_candidate(
            sample,
            objective_family=OBJECTIVE_FAMILY_POLICY,
            source_type="policy_candidate",
            source_ref=str(
                sample.get("trade_id")
                or sample.get("lifecycle_id")
                or sample.get("episode_id")
                or f"policy:{sample.get('symbol', 'UNKNOWN')}:{sample.get('event_ts_ms', 0)}"
            ),
            source_event_type=str(
                sample.get("entry_anchor_event")
                or sample.get("source_event_type")
                or "POLICY_SAMPLE"
            ),
        )
        if not evaluated.is_trainable:
            if evaluated.eligibility_status == "rejected":
                self._policy_training_rejections += 1
            logger.warning(
                "Policy sample rejected by dataset contract: status=%s reasons=%s/%s",
                evaluated.eligibility_status,
                evaluated.provenance.exclusion_reasons,
                evaluated.provenance.quarantine_reasons,
            )
            return False

        if self._policy_training_mode == "disabled":
            self._policy_training_rejections += 1
            logger.warning(
                "Policy sample rejected because policy_training_mode=disabled"
            )
            return False

        routed = self._attach_dataset_provenance(
            sample,
            evaluated=evaluated,
        )
        routed["objective_family"] = OBJECTIVE_FAMILY_POLICY
        routed["objective_route"] = "train_policy"
        self._policy_samples.append(routed)
        await self._maybe_dream()
        return True

    async def add_completed_episode(self, episode: Any) -> None:
        """
        Called when an execution/lifecycle episode completes.

        In P4, completed trade episodes route to execution-quality diagnostics,
        not directly into policy PPO training.
        """
        try:
            episode_dict = self._episode_to_dict(episode)
            sample = self._build_execution_quality_sample(episode_dict)
            close_event = None
            episode_reward = sample.get("episode_reward")
            if isinstance(episode_reward, dict):
                close_event = episode_reward.get("close_event")
            evaluated = self._evaluate_dataset_candidate(
                sample,
                objective_family=OBJECTIVE_FAMILY_EXECUTION_QUALITY,
                source_type="episode_close",
                source_ref=str(
                    sample.get("trade_id")
                    or sample.get("lifecycle_id")
                    or sample.get("episode_id")
                    or f"episode:{sample.get('symbol', 'UNKNOWN')}:{sample.get('close_event_ts_ms', sample.get('event_ts_ms', 0))}"
                ),
                source_event_type=str(
                    close_event
                    or sample.get("close_event")
                    or "POSITION_CLOSED"
                ),
            )

            if evaluated.eligibility_status in {"trainable", "eval_only", "diagnostics_only"}:
                routed_sample = self._attach_dataset_provenance(
                    sample,
                    evaluated=evaluated,
                )
                self._execution_quality_samples.append(routed_sample)
                if not bool(routed_sample.get("reward_missing", False)):
                    await self._run_non_critical_io(
                        self.telemetry.log_episode,
                        reward=float(routed_sample.get("reward", 0.0)),
                        pnl=routed_sample.get("pnl"),
                    )

            await self._run_non_critical_io(
                self.telemetry.log_buffer_stats,
                buffer_size=len(self.buffer),
                episodes_collected=len(self._execution_quality_samples),
                episodes_processed=0,
                samples_since_train=self._samples_since_last_train,
            )
            logger.info(
                "Execution-quality sample added. Buffer size: %s / Threshold: %s",
                len(self._execution_quality_samples),
                self.dream_threshold,
            )
        except Exception as e:
            logger.error(
                f"Failed to add completed episode: {e}", exc_info=True)

    async def train_ppo_now(self) -> None:
        """Manual debug hook to force PPO training on whatever is buffered."""
        try:
            if self._policy_training_mode == "disabled":
                logger.warning(
                    "train_ppo_now skipped: policy_training_mode=disabled after objective split"
                )
                return

            episodes_to_process = list(self._policy_samples)
            self._policy_samples.clear()

            if not episodes_to_process:
                logger.info(
                    "train_ppo_now: no policy samples buffered; skipping")
                return

            logger.info("train_ppo_now: forcing PPO train on %d policy samples", len(
                episodes_to_process))
            await self._trigger_policy_training(episodes_to_process)
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
                "event_ts_ms": getattr(episode, "event_ts_ms", None),
                "episode_id": getattr(episode, "episode_id", None),
                "lifecycle_id": getattr(episode, "lifecycle_id", None),
                "trade_id": getattr(episode, "trade_id", None),
                "order_id": getattr(episode, "order_id", None),
                "client_order_id": getattr(episode, "client_order_id", None),
                "lifecycle_state": getattr(episode, "lifecycle_state", None),
                "entry_anchor_event": getattr(episode, "entry_anchor_event", None),
                "executed_entry": getattr(episode, "executed_entry", None),
                "fill_count": getattr(episode, "fill_count", None),
                "filled_quantity": getattr(episode, "filled_quantity", None),
                "close_event_ts_ms": getattr(episode, "close_event_ts_ms", None),
                "unresolved_reason": getattr(episode, "unresolved_reason", None),
                "features": getattr(episode, "features", None),
                "side": getattr(episode, "side", None),
                "entry_price": getattr(episode, "entry_price", None),
                "reward_complete": getattr(episode, "reward_complete", None),
                "episode_reward": getattr(episode, "episode_reward", None),
                "reward": getattr(episode, "reward", None),
                "pnl": getattr(episode, "pnl", None),
                "objective_family": getattr(episode, "objective_family", None),
                "objective_route": getattr(episode, "objective_route", None),
                "policy_eligible": getattr(episode, "policy_eligible", None),
            }

        reward = raw.get("reward")
        episode_reward = raw.get("episode_reward")
        if episode_reward is not None and is_dataclass(episode_reward):
            episode_reward = asdict(episode_reward)
        reward_complete = raw.get("reward_complete")
        if reward_complete is None and isinstance(episode_reward, dict):
            reward_complete = bool(
                episode_reward.get("reward_complete", False))
        if reward_complete is None:
            reward_complete = reward is not None and episode_reward is None
        reward_missing = reward is None or not bool(reward_complete)
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
            reward = None

        features = raw.get("features") or {}
        features_vector = [
            float(features.get(name, 0.0) or 0.0) for name in self.config.ingest.feature_list
        ]
        event_ts_ms = raw.get("event_ts_ms")
        if event_ts_ms is None:
            event_ts_ms = _normalize_epoch_to_ms(raw.get("timestamp"))

        return {
            "symbol": raw.get("symbol"),
            "timestamp": raw.get("timestamp"),
            "event_ts_ms": event_ts_ms,
            "episode_id": raw.get("episode_id"),
            "lifecycle_id": raw.get("lifecycle_id"),
            "trade_id": raw.get("trade_id"),
            "order_id": raw.get("order_id"),
            "client_order_id": raw.get("client_order_id"),
            "lifecycle_state": raw.get("lifecycle_state"),
            "entry_anchor_event": raw.get("entry_anchor_event"),
            "executed_entry": bool(raw.get("executed_entry", False)),
            "fill_count": int(raw.get("fill_count") or 0),
            "filled_quantity": float(raw.get("filled_quantity") or 0.0),
            "close_event_ts_ms": raw.get("close_event_ts_ms"),
            "unresolved_reason": raw.get("unresolved_reason"),
            "side": raw.get("side") or "FLAT",
            "entry_price": raw.get("entry_price"),
            "reward": float(reward) if reward is not None else None,
            "reward_complete": bool(reward_complete),
            "episode_reward": episode_reward,
            "reward_missing": reward_missing,
            "pnl": raw.get("pnl"),
            "objective_family": raw.get("objective_family"),
            "objective_route": raw.get("objective_route"),
            "policy_eligible": bool(raw.get("policy_eligible", False)),
            "features_vector": features_vector,
        }

    async def _maybe_dream(self) -> None:
        """
        Decide whether to trigger objective-specific training.
        """
        logger.debug("Checking dream condition...")

        if self._dream_in_progress:
            return

        if len(self._regime_supervision_samples) >= self.dream_threshold:
            samples_to_process = list(self._regime_supervision_samples)
            self._regime_supervision_samples.clear()
            self._waiting_for_reward_source = False
            self._dream_in_progress = True
            self._dreams_triggered += 1
            self._track_task(
                self._run_regime_supervision_sequence(samples_to_process),
                "regime_supervision_sequence",
            )
            return

        if self._policy_training_mode == "disabled":
            return

        if len(self._policy_samples) < self.dream_threshold:
            return

        logger.info("TRIGGERING POLICY TRAINING SEQUENCE NOW!")
        samples_to_process = list(self._policy_samples)
        self._policy_samples.clear()
        self._dream_in_progress = True
        self._dreams_triggered += 1
        self._track_task(
            self._run_policy_sequence(samples_to_process),
            "policy_sequence",
        )

    async def _run_regime_supervision_sequence(self, samples_to_process: List[Dict[str, Any]]) -> None:
        try:
            await self._trigger_regime_supervision_training(samples_to_process)
        except Exception as e:
            logger.error(
                f"Regime supervision sequence failed: {e}", exc_info=True)
        finally:
            self._dream_in_progress = False

    async def _run_policy_sequence(self, samples_to_process: List[Dict[str, Any]]) -> None:
        try:
            await self._trigger_policy_training(samples_to_process)
        except Exception as e:
            logger.error(f"Policy sequence failed: {e}", exc_info=True)
        finally:
            self._dream_in_progress = False

    async def _trigger_regime_supervision_training(self, samples_to_process: List[Dict[str, Any]]) -> None:
        if self.brain_bridge is None:
            logger.warning(
                "Regime supervision training skipped: BrainBridge not available")
            return
        if not self._validate_batch_family(
            samples_to_process,
            expected_family=OBJECTIVE_FAMILY_REGIME_SUPERVISION,
        ):
            logger.warning(
                "Regime supervision batch rejected before bridge submit")
            return

        logger.info(
            "Regime supervision training triggered on %d samples",
            len(samples_to_process),
        )
        result = await self.brain_bridge.train_regime_supervision_async(samples_to_process)
        if not result:
            logger.warning(
                "Regime supervision returned empty result; skipping")
            return
        if "error" in result:
            logger.warning("Regime supervision error: %s", result.get("error"))
            return

        await self._run_non_critical_io(
            self.telemetry.log_buffer_stats,
            buffer_size=len(self.buffer),
            episodes_collected=len(self._regime_supervision_samples),
            episodes_processed=int(result.get("episodes_processed", 0)),
            samples_since_train=self._samples_since_last_train,
        )
        logger.info("Regime supervision update complete: %s", result)

    async def _trigger_policy_training(self, samples_to_process: List[Dict[str, Any]]) -> None:
        if self.brain_bridge is None:
            logger.warning("PPO training skipped: BrainBridge not available")
            self._emit_alert(
                severity="WARN",
                code="BRAIN_BRIDGE_UNAVAILABLE",
                message="BrainBridge not available; training skipped in degraded mode",
            )
            return
        if not self._validate_batch_family(
            samples_to_process,
            expected_family=OBJECTIVE_FAMILY_POLICY,
        ):
            logger.warning("Policy batch rejected before bridge submit")
            return

        self._ppo_trains_triggered += 1
        logger.info("Policy training triggered on %d policy samples",
                    len(samples_to_process))

        result = await self.brain_bridge.train_policy_async(samples_to_process)
        if not result:
            logger.warning(
                "Policy training returned empty result (likely disabled); skipping")
        elif "error" in result:
            logger.warning("Policy training error: %s", result.get("error"))
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
                        logger.warning(
                            "Invalid PPO metric value for key '%s': %r", key, value)
                return None

            ppo_loss_pi = _get_float("loss_pi", "policy_loss", "ppo_loss_pi")
            ppo_loss_v = _get_float("loss_v", "value_loss", "ppo_loss_v")
            ppo_entropy = _get_float("entropy", "ppo_entropy")
            episodes_processed_raw = result.get("episodes_processed")
            try:
                episodes_processed = (
                    int(episodes_processed_raw)
                    if episodes_processed_raw is not None
                    else len(samples_to_process)
                )
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid episodes_processed value in policy result: %r",
                    episodes_processed_raw,
                )
                episodes_processed = len(samples_to_process)
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
                await self._run_non_critical_io(
                    self.telemetry.log_training,
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

            await self._run_non_critical_io(
                self.telemetry.log_buffer_stats,
                buffer_size=len(self.buffer),
                episodes_collected=len(self._policy_samples),
                episodes_processed=episodes_processed,
                samples_since_train=self._samples_since_last_train,
            )
            logger.info("Policy update complete: %s", result)

    async def _generate_shadow_intent(
        self,
        obs: MarketObservation,
        original_payload: Dict,
        raw_features_for_labeler: Optional[Dict[str, float]] = None,
    ):
        """
        Encode observation and generate shadow trading intent.

        In regime_oracle mode, also pushes to FeatureRingBuffer and handles
        settlement (reward computation) when H bars have elapsed.
        """
        if self.brain_bridge is None:
            return

        try:
            # Encode observation to latent space
            z = await self.brain_bridge.encode_async(obs)

            # Get action from PPO
            action_result = await self.brain_bridge.act_async(z)
            self._shadow_intents_generated += 1

            symbol = str(original_payload.get("symbol", "UNKNOWN"))
            action_name = str(action_result.get("action_name", "FLAT"))
            event_ts_ms = self._extract_event_ts_ms(original_payload)
            source_ts = event_ts_ms / 1000.0
            source_event_id = str(
                original_payload.get("event_id") or f"{symbol}:{event_ts_ms}"
            )
            idempotent_seed = f"{source_event_id}|{action_name}|{event_ts_ms}"
            idempotent_hash = hashlib.sha256(
                idempotent_seed.encode("utf-8")).hexdigest()[:16]
            idempotent_key = (
                f"neocortex:r2:{symbol}:{action_name}:{event_ts_ms}:{idempotent_hash}"
            )

            # Build canonical shadow intent payload (dual emit with legacy event name).
            event_type = (
                "EVT:NEOCORTEX_REGIME_PREDICTION"
                if self._reward_mode == "regime_oracle"
                else "EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED"
            )
            shadow_intent = {
                "event_type": event_type,
                "schema_version": "1.0.0",
                "timestamp": source_ts,
                "event_ts_ms": event_ts_ms,
                "symbol": symbol,
                "action": action_result["action"],
                "action_name": action_name,
                "value": action_result["value"],
                "confidence": action_result["confidence"],
                "latent_state": z.tolist() if hasattr(z, 'tolist') else list(z),
                "source_ts": source_ts,
                "source_event_id": source_event_id,
                "train_steps": self._total_train_steps,
                "idempotent_key": idempotent_key,
                "why": [
                    f"confidence={float(action_result.get('confidence', 0.0)):.6f}",
                    f"value={float(action_result.get('value', 0.0)):.6f}",
                ],
            }

            # --- Regime Oracle: settlement and episode creation ---
            if self._reward_mode == "regime_oracle" and self._oracle_ring_buffer is not None:
                await self._handle_oracle_settlement(
                    symbol=symbol,
                    source_ts=source_ts,
                    z=z,
                    action_result=action_result,
                    raw_features_for_labeler=raw_features_for_labeler,
                    model_features_vector=obs.features_vector,
                )

            if self._should_emit_observational_shadow_output():
                # Emit canonical + legacy events during migration window.
                if self.event_emitter is not None:
                    canonical_payload = dict(shadow_intent)
                    legacy_payload = dict(shadow_intent)
                    legacy_payload["event_type"] = "EVT:NEOCORTEX_SHADOW_INTENT"
                    self.event_emitter(event_type, canonical_payload)
                    self.event_emitter(
                        "EVT:NEOCORTEX_SHADOW_INTENT", legacy_payload)

                self._shadow_intents_emitted += 1

                # Persist to JSONL file
                try:
                    await self._run_non_critical_io(
                        self._enqueue_shadow_intent_log,
                        shadow_intent,
                    )
                except Exception as log_err:
                    logger.warning(
                        f"Failed to queue shadow intent JSONL write: {log_err}")

                # Log to telemetry CSV
                await self._run_non_critical_io(
                    self.telemetry.log_shadow_intent,
                    action=action_result["action"],
                    action_name=action_result["action_name"],
                    confidence=action_result["confidence"],
                    value=action_result["value"],
                )

                # Log shadow intent
                logger.info(
                    f"Shadow Intent: {action_result['action_name']} "
                    f"(conf={action_result['confidence']:.3f}, val={action_result['value']:.3f})"
                )
            else:
                self._shadow_intents_decimated += 1

        except Exception as e:
            logger.error(
                f"Shadow intent generation failed: {e}", exc_info=True)

    async def _handle_oracle_settlement(
        self,
        symbol: str,
        source_ts: float,
        z,
        action_result: Dict[str, Any],
        raw_features_for_labeler: Optional[Dict[str, float]],
        model_features_vector: Optional[np.ndarray],
    ) -> None:
        """
        Push current bar into the FeatureRingBuffer and, if H bars have
        accumulated, settle the oldest prediction by computing the realized
        regime and reward.

        Creates an episode dict and feeds it into the dream/PPO pipeline
        (via _completed_episodes + _maybe_dream).
        """
        feature_names = self.config.ingest.feature_list
        features_dict = dict(raw_features_for_labeler or {})
        if not features_dict:
            logger.debug(
                "Oracle settlement: raw feature map is empty for %s", symbol)

        settled = self._oracle_ring_buffer.push_and_settle(
            symbol=symbol,
            timestamp=source_ts,
            latent_z=z,
            predicted_action=int(action_result["action"]),
            features=features_dict,
            model_features=model_features_vector,
        )

        if settled is None:
            remaining = self._oracle_ring_buffer.warmup_remaining(symbol)
            if remaining > 0:
                logger.debug(
                    "Oracle warmup: %s needs %d more bars before first settlement",
                    symbol, remaining,
                )
            return

        # Compute realized regime from feature pair (t, t+H)
        try:
            realized_regime = self._oracle_labeler.compute_realized_regime(
                settled.features_t, settled.features_t_plus_h
            )
        except ValueError as exc:
            logger.warning(
                "Oracle settlement skipped because realized-regime features are incomplete: symbol=%s error=%s",
                symbol,
                exc,
            )
            self._emit_alert(
                severity="WARN",
                code="ORACLE_LABEL_FEATURES_INCOMPLETE",
                message="Regime oracle settlement skipped; no synthetic regime label emitted",
                details={"symbol": symbol, "error": str(exc)},
            )
            return

        # Compute reward
        reward = self._oracle_reward_calc.compute_reward(
            settled.predicted_action, realized_regime
        )
        correct = settled.predicted_action == realized_regime

        self._oracle_settlements += 1

        # Log to telemetry
        await self._run_non_critical_io(
            self.telemetry.log_oracle_prediction,
            predicted_regime=settled.predicted_action,
            realized_regime=realized_regime,
            oracle_reward=reward,
            oracle_correct=correct,
        )

        logger.info(
            "Oracle settlement #%d: predicted=%s realized=%s reward=%.3f correct=%s",
            self._oracle_settlements,
            REGIME_NAMES.get(settled.predicted_action,
                             str(settled.predicted_action)),
            REGIME_NAMES.get(realized_regime, str(realized_regime)),
            reward,
            correct,
        )

        if settled.model_features_t is not None:
            model_features = settled.model_features_t.astype(
                np.float32, copy=False).tolist()
        else:
            missing_model_features = [
                name for name in feature_names if name not in settled.features_t
            ]
            if missing_model_features:
                logger.warning(
                    "Oracle settlement skipped because model features are incomplete: symbol=%s missing=%s",
                    symbol,
                    missing_model_features,
                )
                self._emit_alert(
                    severity="WARN",
                    code="ORACLE_MODEL_FEATURES_INCOMPLETE",
                    message="Regime oracle settlement skipped; no synthetic model feature vector emitted",
                    details={"symbol": symbol,
                             "missing_features": missing_model_features},
                )
                return
            model_features = [
                float(settled.features_t[name])
                for name in feature_names
            ]

        sample = self._build_regime_supervision_sample(
            symbol=symbol,
            settled=settled,
            realized_regime=realized_regime,
            reward=reward,
            confidence=action_result.get("confidence"),
            model_features=model_features,
        )
        evaluated = self._evaluate_dataset_candidate(
            sample,
            objective_family=OBJECTIVE_FAMILY_REGIME_SUPERVISION,
            source_type="oracle_settlement",
            source_ref=f"oracle:{symbol}:{sample['event_ts_ms']}",
            source_event_type="EVT:NEOCORTEX_REGIME_PREDICTION",
        )
        if evaluated.is_trainable:
            self._regime_supervision_samples.append(
                self._attach_dataset_provenance(
                    sample,
                    evaluated=evaluated,
                )
            )
        await self._run_non_critical_io(
            self.telemetry.log_buffer_stats,
            buffer_size=len(self.buffer),
            episodes_collected=len(self._regime_supervision_samples),
            episodes_processed=0,
            samples_since_train=self._samples_since_last_train,
        )

        await self._maybe_dream()

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
            self._inflight_training_tasks = max(
                0, self._inflight_training_tasks - 1)

    async def _run_training(self, batch_obs: List[MarketObservation]):
        """
        Execute training in background, checkpoint if needed.
        """
        try:
            losses = await self.brain_bridge.train_async(batch_obs)

            self._total_train_steps += 1

            if "error" in losses:
                logger.warning(
                    f"Training step {self._total_train_steps} error: {losses['error']}")
            else:
                logger.info(
                    f"Training step {self._total_train_steps}: "
                    f"VAE={losses.get('vae_loss', 0):.4f} "
                    f"WM={losses.get('wm_loss', 0):.4f}"
                )

                # Log to telemetry CSV
                await self._run_non_critical_io(
                    self.telemetry.log_training,
                    vae_loss=losses.get('vae_loss'),
                    vae_mse=losses.get('vae_mse'),
                    vae_kld=losses.get('vae_kld'),
                    wm_loss=losses.get('wm_loss'),
                    train_step=self._total_train_steps,
                )

            # Check if checkpoint needed
            await self._maybe_checkpoint()

        except Exception as e:
            logger.error(f"Training execution failed: {e}", exc_info=True)

        finally:
            self._inflight_training_tasks = max(
                0, self._inflight_training_tasks - 1)

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
                logger.error("Background task '%s' failed: %s",
                             task_name, exc, exc_info=True)

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
                logger.error(
                    "Failed to emit EVT:NEOCORTEX_ALERT: %s", emit_err)

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
            logger.warning(
                "Failed to rotate shadow intent log: %s", e, exc_info=True)

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
                logger.info(
                    f"Checkpoint saved at step {self._total_train_steps}")
                self._save_normalizer_state()
                self._save_checkpoint_metadata()
            else:
                logger.warning(
                    f"Checkpoint save failed at step {self._total_train_steps}")

    def _save_normalizer_state(self) -> None:
        try:
            if self._normalization_scope == "per_symbol":
                if self._normalizers_by_symbol is not None:
                    saved_count = self._normalizers_by_symbol.save_states(
                        self._normalizer_states_dir
                    )
                    logger.info(
                        "Saved %d per-symbol normalizer states to %s",
                        saved_count,
                        self._normalizer_states_dir,
                    )
            else:
                self._normalizer.save_state(self._normalizer_state_path)
        except Exception as e:
            logger.warning(
                "Failed to save normalizer state: %s", e, exc_info=True)

    async def start(self):
        """
        Start the adapter and its dependencies.
        """
        if self.brain_bridge is not None:
            logger.info("Starting BrainBridge...")
            success = await self.brain_bridge.start()
            if not success:
                logger.warning(
                    "BrainBridge start failed, continuing without neural training")
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
                        self._validate_checkpoint_metadata()
                reset_on_replay_start = bool(
                    getattr(
                        self,
                        "_reset_sequence_on_replay_start",
                        getattr(self.config.neuro.sequence,
                                "reset_on_replay_start", True),
                    )
                )
                if (
                    reset_on_replay_start
                    and hasattr(self.brain_bridge, "reset_sequence_state_async")
                ):
                    reset_call = self.brain_bridge.reset_sequence_state_async(
                        reason="adapter_start"
                    )
                    reset_result = (
                        await reset_call
                        if inspect.isawaitable(reset_call)
                        else reset_call
                    )
                    logger.info(
                        "Sequence state reset at adapter start: %s", reset_result)

    async def shutdown_async(self):
        """
        Async graceful shutdown with final checkpoint save.

        This ensures all pending training completes and weights are persisted.
        """
        logger.info("NeocortexAdapter: Starting async shutdown...")

        # 1. Wait for pending training tasks
        if self._pending_tasks:
            logger.info(
                f"Waiting for {len(self._pending_tasks)} pending tasks...")
            pending_valid = [t for t in self._pending_tasks if not t.done()]
            if pending_valid:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*pending_valid, return_exceptions=True),
                        timeout=10.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("Timeout waiting for pending tasks")

        # 2. Flush remaining regime-supervision samples
        if self._regime_supervision_samples and self.brain_bridge is not None:
            logger.info(
                f"Final regime supervision training on {len(self._regime_supervision_samples)} buffered samples..."
            )
            try:
                await self._trigger_regime_supervision_training(list(self._regime_supervision_samples))
                self._regime_supervision_samples.clear()
            except Exception as e:
                logger.warning(
                    f"Final regime supervision training failed: {e}")

        # 3. Flush remaining policy samples only when explicitly enabled
        if (
            self._policy_samples
            and self.brain_bridge is not None
            and self._policy_training_mode != "disabled"
        ):
            logger.info(
                f"Final policy training on {len(self._policy_samples)} buffered policy samples..."
            )
            try:
                await self._trigger_policy_training(list(self._policy_samples))
                self._policy_samples.clear()
            except Exception as e:
                logger.warning(f"Final policy training failed: {e}")

        # 4. Save final checkpoint (CRITICAL)
        if self.brain_bridge is not None:
            checkpoint_dir = self.config.system.checkpoint_dir
            logger.info(
                f"Saving final checkpoint at step {self._total_train_steps}...")
            try:
                success = await self.brain_bridge.save_async(str(checkpoint_dir))
                if success:
                    logger.info(
                        f"✓ Final checkpoint saved at step {self._total_train_steps}")
                else:
                    logger.warning("Final checkpoint save returned False")
            except Exception as e:
                logger.error(f"Final checkpoint save failed: {e}")

        # 5. Flush non-critical observational buffers
        await self._run_non_critical_io(self._flush_non_critical_outputs, force=True)

        # 6. Save normalizer state
        self._save_normalizer_state()
        self._save_checkpoint_metadata()

        # 7. Shutdown brain bridge
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
        self._flush_non_critical_outputs(force=True)
        self._save_normalizer_state()
        self._save_checkpoint_metadata()
        if self.brain_bridge is not None:
            self.brain_bridge.shutdown()
        logger.info(
            f"NeocortexAdapter shutdown: "
            f"TrainSteps={self._total_train_steps} "
            f"ShadowIntents={self._shadow_intents_emitted}"
        )

    def build_dataset_manifest(self, objective_family: str):
        family = str(objective_family).strip().lower()
        if family not in self._evaluated_samples_by_family:
            raise ValueError(f"Unknown objective family: {objective_family}")
        return self._dataset_policy.build_manifest(
            list(self._evaluated_samples_by_family[family]),
            objective_family=family,
        )

    @property
    def stats(self) -> Dict[str, Any]:
        """Get adapter statistics."""
        telemetry_stats = {}
        try:
            telemetry_stats = dict(getattr(self.telemetry, "stats", {}) or {})
        except Exception as exc:
            logger.warning("Failed to read telemetry stats: %s",
                           exc, exc_info=True)
            telemetry_stats = {}
        base = {
            "total_train_steps": self._total_train_steps,
            "shadow_intents_emitted": self._shadow_intents_emitted,
            "buffer_size": len(self.buffer),
            "samples_since_train": self._samples_since_last_train,
            "inflight_tasks": self._inflight_training_tasks,
            "backpressure_events": self._backpressure_events,
            "regime_supervision_buffered": len(self._regime_supervision_samples),
            "execution_quality_buffered": len(self._execution_quality_samples),
            "policy_samples_buffered": len(self._policy_samples),
            "representation_dataset_buffered": len(self._representation_samples),
            "dream_threshold": self.dream_threshold,
            "dreams_triggered": self._dreams_triggered,
            "ppo_trains_triggered": self._ppo_trains_triggered,
            "waiting_for_reward_source": self._waiting_for_reward_source,
            "reward_mode": self._reward_mode,
            "objective_split_enforced": self._objective_split_enforced,
            "policy_training_mode": self._policy_training_mode,
            "sequence_inference_mode": self._sequence_inference_mode,
            "representation_training_mode": self._representation_training_mode,
            "reset_sequence_on_replay_start": self._reset_sequence_on_replay_start,
            "operating_mode": self._operating_mode,
            "shadow_intent_emit_policy": self._shadow_intent_emit_policy,
            "shadow_intent_decimation_stride": self._shadow_intent_decimation_stride,
            "shadow_jsonl_write_policy": self._shadow_jsonl_write_policy,
            "telemetry_write_policy": self._telemetry_write_policy,
            "non_critical_queue_limit": self._non_critical_queue_limit,
            "non_critical_overflow_policy": self._non_critical_overflow_policy,
            "flush_interval_ms": self._flush_interval_ms,
            "shadow_intents_generated": self._shadow_intents_generated,
            "shadow_intents_decimated": self._shadow_intents_decimated,
            "shadow_intent_log_rows_buffered": self._shadow_intent_log_rows_buffered,
            "shadow_intent_log_rows_dropped": self._shadow_intent_log_rows_dropped,
            "shadow_intent_log_flushes": self._shadow_intent_log_flushes,
            "non_critical_overload_events": self._non_critical_overload_events,
            "objective_rejections": self._objective_rejections,
            "policy_training_rejections": self._policy_training_rejections,
            "dataset_manifest_version": int(self.config.neuro.dataset.manifest_version),
            "dataset_status_counts": dict(sorted(self._dataset_status_counts.items())),
            "dataset_exclusion_counts": dict(sorted(self._dataset_exclusion_counts.items())),
            "dataset_quarantine_counts": dict(sorted(self._dataset_quarantine_counts.items())),
            "telemetry_stats": telemetry_stats,
        }
        if self._reward_mode == "regime_oracle":
            base["oracle_settlements"] = self._oracle_settlements
            base["oracle_warmup_symbols"] = {
                sym: self._oracle_ring_buffer.warmup_remaining(sym)
                for sym in (self._oracle_ring_buffer.symbols if self._oracle_ring_buffer else [])
            }
        return base
