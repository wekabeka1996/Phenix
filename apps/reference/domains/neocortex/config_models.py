"""
Neocortex Configuration Models (Pydantic V2)

PHILOSOPHY:
- Fail-closed: extra='forbid' on all models
- No defaults for business parameters (hidden defaults cause production incidents)
- Explicit is better than implicit
- Early validation prevents runtime surprises
"""

from pathlib import Path
from typing import Dict, List, Literal, Optional
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

DEFAULT_RNG_SEED = 42


# =============================================================================
# SYSTEM CONFIGURATION
# =============================================================================

class SystemConfig(BaseModel):
    """System-level settings (paths, multiprocessing, logging)."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    # Paths
    data_dir: Path = Field(
        json_schema_extra={"default_class": "structural_safe"},
        description="Directory for logs, checkpoints, embeddings"
    )
    checkpoint_dir: Path = Field(
        json_schema_extra={"default_class": "structural_safe"},
        description="Model checkpoint storage"
    )

    # Multiprocessing
    brain_workers: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=8,
        description="Number of brain worker processes for ML inference"
    )
    queue_maxsize: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=10, le=10000,
        description="Max size of inter-process queues"
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        json_schema_extra={"default_class": "structural_safe"},
        description="Logging verbosity"
    )
    log_to_file: bool = Field(
        json_schema_extra={"default_class": "structural_safe"},
        description="Whether to write logs to file"
    )

    # Run Mode
    run_mode: Literal["live", "backtest"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Execution mode: 'live' (real logs) or 'backtest' (historical/simulated logs)"
    )

    # Reproducibility
    rng_seed: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=0,
        description="Global RNG seed for reproducible runs"
    )

    @field_validator('data_dir', 'checkpoint_dir', mode='before')
    @classmethod
    def resolve_paths(cls, v):
        """Convert strings to absolute paths."""
        return Path(v).resolve()


# =============================================================================
# INGESTION CONFIGURATION
# =============================================================================

class IngestConfig(BaseModel):
    """Data ingestion and normalization settings."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    # Feature selection
    feature_list: List[str] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        min_length=1,
        description="Ordered list of features to ingest from EVT:FEATURES_CALCULATED"
    )

    # Normalization (NO DEFAULTS - must be explicitly chosen)
    normalization_method: Literal["zscore", "minmax", "robust"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Feature scaling method"
    )
    normalization_window: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=10, le=10000,
        description="Rolling window size for normalization statistics"
    )
    normalization_scope: Literal["global", "per_symbol"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Normalization scope for running statistics."
    )
    price_feature_mode: Literal["raw", "log", "drop"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="How to represent `price` for ML input."
    )
    delta_price_mode: Literal["raw", "pct"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="How to represent `delta_price` for ML input."
    )
    feature_clip_abs: Dict[str, float] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Optional per-feature absolute clipping bounds before normalization."
    )

    # Buffering
    buffer_size: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=100, le=100000,
        description="Max observations to keep in memory buffer"
    )

    # Timestep handling
    min_samples_before_ready: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1,
        description="Minimum samples required before marking ingest as 'ready'"
    )

    # Robustness
    nan_strategy: Literal["zero", "ignore", "ffill"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Strategy for handling NaN/None values in features"
    )

    @field_validator('feature_list')
    @classmethod
    def validate_features(cls, v):
        """Ensure no duplicate feature names."""
        if len(v) != len(set(v)):
            raise ValueError("feature_list contains duplicates")
        return v

    @field_validator('feature_clip_abs')
    @classmethod
    def validate_feature_clip_abs(cls, v):
        """Ensure clip bounds are positive finite numbers."""
        for key, value in v.items():
            if not isinstance(key, str) or not key:
                raise ValueError(
                    "feature_clip_abs keys must be non-empty strings")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(
                    f"feature_clip_abs['{key}'] must be numeric")
            f_value = float(value)
            if f_value <= 0.0:
                raise ValueError(
                    f"feature_clip_abs['{key}'] must be > 0")
            if f_value != f_value or f_value in (float("inf"), float("-inf")):
                raise ValueError(
                    f"feature_clip_abs['{key}'] must be finite")
        return v


# =============================================================================
# NEURO CONFIGURATION (VAE + PPO)
# =============================================================================

class VAEConfig(BaseModel):
    """Variational Autoencoder hyperparameters."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    class RegimeAuxConfig(BaseModel):
        """Optional auxiliary regime classification head over latent mean."""

        model_config = ConfigDict(extra='forbid', frozen=True)

        class AlphaScheduleConfig(BaseModel):
            """Linear warmup schedule for auxiliary alpha weight."""

            model_config = ConfigDict(extra='forbid', frozen=True)

            start: float = Field(
                json_schema_extra={"default_class": "runtime_behavior"},
                ge=0.0, le=50.0,
                description="Initial alpha value at step 0."
            )
            end: float = Field(
                json_schema_extra={"default_class": "runtime_behavior"},
                ge=0.0, le=50.0,
                description="Final alpha value after `steps` updates."
            )
            steps: int = Field(
                json_schema_extra={"default_class": "runtime_behavior"},
                ge=1, le=10_000_000,
                description="Number of update steps for linear interpolation."
            )

        enabled: bool = Field(
            json_schema_extra={"default_class": "runtime_behavior"},
            description="Enable auxiliary regime-classification head on latent mean."
        )
        alpha: float = Field(
            json_schema_extra={"default_class": "structural_safe"},
            default=0.2,
            ge=0.0, le=10.0,
            description="Auxiliary CE weight in total VAE loss."
        )
        num_classes: int = Field(
            json_schema_extra={"default_class": "structural_safe"},
            default=5,
            ge=2, le=64,
            description="Number of classes for auxiliary regime supervision."
        )
        ema_decay: float = Field(
            json_schema_extra={"default_class": "structural_safe"},
            default=0.99,
            ge=0.0, lt=1.0,
            description="EMA decay for dynamic class-frequency tracking."
        )
        alpha_schedule: Optional[AlphaScheduleConfig] = Field(
            json_schema_extra={"default_class": "structural_safe"},
            default=None,
            description="Optional linear schedule for auxiliary alpha."
        )

    # Architecture (NO DEFAULTS)
    input_dim: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1,
        description="Input feature dimension (must match len(feature_list))"
    )
    hidden_dims: List[int] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        min_length=1,
        description="Encoder/decoder hidden layer sizes, e.g. [128, 64]"
    )
    latent_dim: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=2, le=512,
        description="Latent space dimensionality"
    )

    # Training
    learning_rate: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=0.1,
        description="Adam optimizer learning rate"
    )
    beta: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=10.0,
        description="KL divergence weight in VAE loss"
    )
    free_bits_per_dim: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=0.0, le=10.0,
        description="Per-dimension free-bits floor for KL regularization."
    )
    batch_size: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=1024,
        description="Training batch size"
    )

    # Inference
    use_mean: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Whether to use mean (True) or sample (False) during encoding"
    )
    regime_aux: RegimeAuxConfig = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default_factory=RegimeAuxConfig,
        description="Auxiliary latent supervision settings."
    )


class WorldModelConfig(BaseModel):
    """World Model (RNN) hyperparameters."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    # Architecture
    hidden_dim: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=16, le=2048,
        description="RNN hidden state dimension"
    )
    num_layers: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=8,
        description="Number of RNN layers"
    )
    dropout: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=0.0, le=0.9,
        description="RNN dropout probability"
    )

    # Training
    learning_rate: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=0.01,
        description="Adam optimizer learning rate"
    )
    sequence_length: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=2, le=512,
        description="Training sequence length (BPTT)"
    )


class PPOEntropyScheduleConfig(BaseModel):
    """Entropy coefficient decay schedule."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    start: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=0.0, le=0.5,
        description="Initial entropy coefficient"
    )
    end: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=0.0, le=0.5,
        description="Final entropy coefficient"
    )
    total_steps: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=10_000_000,
        description="Number of update steps over which to linearly decay"
    )

    @field_validator("end")
    @classmethod
    def validate_end_le_start(cls, v, info):
        start = info.data.get("start")
        if start is not None and v > start:
            raise ValueError(
                "entropy_schedule.end must be <= entropy_schedule.start"
            )
        return v


class PPONumericalSafetyConfig(BaseModel):
    """Numerical safety controls for PPO updates."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    gradient_clip_threshold: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=10.0,
        description="Gradient norm threshold used by numerical safety validator"
    )
    on_invalid: Literal["zero_grads", "skip_step", "sanitize"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Recovery strategy for invalid gradients"
    )


class PPOConfig(BaseModel):
    """Proximal Policy Optimization hyperparameters."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    # Network architecture (NO DEFAULTS)
    state_dim: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1,
        description="State dimension (typically VAE latent_dim + market context)"
    )
    action_dim: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1,
        description="Action space dimension (3 for [LONG, SHORT, FLAT] or 5 for regime oracle)"
    )
    hidden_dims: List[int] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        min_length=1,
        description="Policy/Value network hidden layers, e.g. [256, 128]"
    )

    # Reward mode: pnl (legacy) or regime_oracle (REGIME_PIVOT_PLAN)
    reward_mode: Literal["pnl", "regime_oracle"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Reward source: 'pnl' (trade PnL) or 'regime_oracle' (self-supervised regime prediction)"
    )
    objective_split_enforced: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Reject mixed objective families and enforce explicit routing for regime, execution, and policy samples"
    )
    policy_training_mode: Literal["disabled", "execution_only"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description=(
            "Whether PPO policy is enabled for training.\n"
            "'disabled' fail-closes policy training until a clean PolicySample producer exists. "
            "'execution_only' allows only explicit policy-family samples."
        )
    )

    # Training
    learning_rate: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=0.01,
        description="Adam optimizer learning rate"
    )
    gamma: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=1.0,
        description="Discount factor for future rewards"
    )
    gae_lambda: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=1.0,
        description="GAE lambda for advantage estimation"
    )
    clip_epsilon: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=0.5,
        description="PPO clipping epsilon"
    )

    # Entropy bonus coefficient (prevents policy collapse)
    entropy_coef: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=0.0, le=0.5,
        description="Entropy bonus coefficient. Higher values encourage exploration and prevent mode collapse"
    )
    entropy_schedule: Optional[PPOEntropyScheduleConfig] = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default=None,
        description="Optional linear schedule for entropy_coef"
    )
    max_grad_norm: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=10.0,
        description="Gradient clipping norm passed to PPO updater"
    )
    numerical_safety: PPONumericalSafetyConfig = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Numerical safety settings passed into PPO SafetyConfig"
    )

    # Rollout
    rollout_length: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=10000,
        description="Steps to collect before policy update"
    )
    num_epochs: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=100,
        description="Optimization epochs per rollout"
    )
    minibatch_size: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=1024,
        description="Minibatch size for PPO updates"
    )


class SequenceConfig(BaseModel):
    """Canonical sequence semantics contract for runtime inference/training."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    inference_mode: Literal["stateless_per_event"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description=(
            "How sequences are processed at inference time.\n"
            "'stateless_per_event' resets hidden state before every event to forbid cross-symbol "
            "and cross-objective leakage until a clean per-stream sequence owner exists."
        ),
    )
    representation_training_mode: Literal["independent_rows"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description=(
            "How representation learning is batched.\n"
            "'independent_rows' forbids treating arbitrary recent batches as one temporal sequence "
            "until explicit sequence-owner metadata exists."
        ),
    )
    reset_on_replay_start: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Reset sequence state deterministically at replay/adapter start."
    )
    reset_on_symbol_switch: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Symbol switches are reset-worthy boundaries under the canonical sequence contract."
    )
    reset_on_objective_family_switch: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Objective-family switches are reset-worthy boundaries under the canonical sequence contract."
    )
    reset_on_episode_boundary: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Episode/lifecycle terminal boundaries are reset-worthy under the canonical sequence contract."
    )


class DatasetSplitConfig(BaseModel):
    """Deterministic split-by-time configuration for dataset manifests."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    train_ratio: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, lt=1.0,
        description="Ratio of data for training set"
    )
    val_ratio: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=0.0, lt=1.0,
        description="Ratio of data for validation set"
    )
    test_ratio: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=0.0, lt=1.0,
        description="Ratio of data for testing set"
    )

    @model_validator(mode="after")
    def validate_sum_to_one(self):
        total = float(self.train_ratio + self.val_ratio + self.test_ratio)
        if abs(total - 1.0) > 1e-6:
            raise ValueError("dataset.split ratios must sum to 1.0")
        return self


class DatasetConfig(BaseModel):
    """Canonical dataset hygiene / provenance settings."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    manifest_version: int = Field(
        json_schema_extra={"default_class": "structural_safe"},
        ge=1,
        description="Dataset manifest schema version."
    )
    split: DatasetSplitConfig = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Deterministic split-by-time configuration."
    )


class PerformanceConfig(BaseModel):
    """Operating/performance contract for live shadow and offline replay."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    operating_mode: Literal["live_shadow", "offline_replay"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description=(
            "Operating shape for hot-path behavior. "
            "'live_shadow' prioritizes low-latency observational fidelity with no decimation. "
            "'offline_replay' allows bounded buffering and observational decimation."
        ),
    )
    shadow_intent_emit_policy: Literal["emit_all", "decimate_observational"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description=(
            "Policy for non-critical shadow observational outputs. "
            "'emit_all' keeps every shadow output. "
            "'decimate_observational' allows deterministic stride-based decimation in offline replay."
        ),
    )
    shadow_intent_decimation_stride: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=100000,
        description="Deterministic stride for observational shadow decimation in offline replay."
    )
    shadow_jsonl_write_policy: Literal["immediate", "buffered"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Write policy for non-critical shadow JSONL observational logs."
    )
    telemetry_write_policy: Literal["immediate", "buffered"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Write policy for non-critical telemetry CSV rows."
    )
    non_critical_queue_limit: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=100000,
        description="Max buffered non-critical rows before explicit overflow policy applies."
    )
    shadow_log_flush_threshold: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=100000,
        description="Buffered shadow JSONL rows before flush."
    )
    telemetry_flush_threshold: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=100000,
        description="Buffered telemetry rows before flush."
    )
    flush_interval_ms: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=600000,
        description="Time-based flush cadence for buffered non-critical outputs."
    )
    non_critical_overflow_policy: Literal["drop_oldest", "drop_newest"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Explicit overflow policy for non-critical observational buffers."
    )

    @model_validator(mode="after")
    def validate_mode_specific_rules(self):
        if self.operating_mode == "live_shadow":
            if self.shadow_intent_emit_policy != "emit_all":
                raise ValueError(
                    "live_shadow requires shadow_intent_emit_policy='emit_all'"
                )
            if self.shadow_intent_decimation_stride != 1:
                raise ValueError(
                    "live_shadow requires shadow_intent_decimation_stride=1"
                )
        return self


class EvaluationConfig(BaseModel):
    """Offline evaluator / calibration / disagreement contract."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    report_version: int = Field(
        json_schema_extra={"default_class": "structural_safe"},
        ge=1,
        description="Machine-readable evaluator report version."
    )
    calibration_bins: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=100,
        description="Number of equal-width confidence bins for calibration reports."
    )
    confidence_bucket_edges: List[float] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Strictly increasing confidence bucket edges used by disagreement reporting."
    )
    missing_confidence_policy: Literal["not_available"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Missing or unsupported confidence signals must produce an explicit not_available calibration report."
    )
    advisory_status: Literal["forbidden"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="P9 is evaluation-only; advisory remains forbidden."
    )

    @field_validator("confidence_bucket_edges")
    @classmethod
    def validate_confidence_bucket_edges(cls, v):
        if not v:
            raise ValueError("confidence_bucket_edges must not be empty")
        cleaned = [float(item) for item in v]
        prev = 0.0
        for item in cleaned:
            if item <= 0.0 or item >= 1.0:
                raise ValueError(
                    "confidence_bucket_edges must be strictly between 0 and 1"
                )
            if item <= prev:
                raise ValueError(
                    "confidence_bucket_edges must be strictly increasing"
                )
            prev = item
        return cleaned


class ShadowGateConfig(BaseModel):
    """Production-shadow startup/runtime gate configuration."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    gate_set_version: int = Field(
        json_schema_extra={"default_class": "structural_safe"},
        ge=1,
        description="Machine-readable production-shadow gate set version."
    )
    startup_enforcement: Literal["strict", "report_only"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description=(
            "Startup gate enforcement mode. "
            "'strict' blocks startup on any blocking gate failure. "
            "'report_only' emits readiness report without blocking."
        ),
    )
    allow_advisory_influence: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Forbidden in production shadow. Must remain false until a future advisory-hardening package."
    )
    allow_live_authority: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Forbidden in production shadow. Must remain false."
    )
    allow_policy_training_reenable: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Forbidden in production shadow. Policy training stays blocked until a future package re-opens it."
    )
    require_domain_manifest_contracts: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Require domain.yaml to expose the canonical contract sections needed for production shadow."
    )


class NeuroConfig(BaseModel):
    """Combined ML configuration."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    vae: VAEConfig = Field(
        json_schema_extra={"default_class": "structural_safe"})
    world_model: WorldModelConfig = Field(
        json_schema_extra={"default_class": "structural_safe"})
    ppo: PPOConfig = Field(
        json_schema_extra={"default_class": "structural_safe"})
    sequence: SequenceConfig = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default_factory=SequenceConfig,
        description="Canonical sequence semantics configuration."
    )
    dataset: DatasetConfig = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default_factory=DatasetConfig,
        description="Canonical dataset hygiene / provenance configuration."
    )
    evaluation: EvaluationConfig = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default_factory=EvaluationConfig,
        description="Offline evaluator / calibration / disagreement configuration."
    )
    performance: PerformanceConfig = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default_factory=PerformanceConfig,
        description="Performance/replay operating contract."
    )
    shadow_gates: ShadowGateConfig = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default_factory=ShadowGateConfig,
        description="Production-shadow startup/runtime gate configuration."
    )

    # Checkpointing (NO DEFAULTS)
    checkpoint_every_n_steps: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1,
        description="Save model checkpoint every N steps"
    )
    keep_last_n_checkpoints: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=100,
        description="Number of recent checkpoints to retain"
    )

    # Dream / PPO Training Trigger
    dream_episode_threshold: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1,
        description="Number of completed episodes before triggering PPO training. 1=immediate (backtest), 10+=batched (prod)"
    )


# =============================================================================
# REPLAY CONFIGURATION (Historical Data)
# =============================================================================

class ReplayConfig(BaseModel):
    """Configuration for data ingestion (Phase 6 WAL or Phase 7 Multi-Source)."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    enabled: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Enable data ingestion"
    )

    # =========================================================================
    # Phase 6: WAL Tailing (legacy)
    # =========================================================================
    wal_dir: Path = Field(
        json_schema_extra={"default_class": "legacy_compat"},
        default=Path("ops/wal"),
        description="Directory containing WAL files (Phase 6)"
    )
    wal_glob: str = Field(
        json_schema_extra={"default_class": "legacy_compat"},
        default="",
        description="DEPRECATED: Use wal_dir instead."
    )
    filter_verb: str = Field(
        json_schema_extra={"default_class": "legacy_compat"},
        default="FEATURES_CALCULATED",
        description="Event verb to filter for in WAL (Phase 6)"
    )

    # =========================================================================
    # Phase 7: Multi-Source Ingestion
    # =========================================================================
    features_dir: Optional[Path] = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default=None,
        description="Directory with feature logs per symbol (Phase 7)"
    )
    orders_file: Optional[Path] = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default=None,
        description="Path to order log JSONL file (Phase 7)"
    )
    core_log: Optional[Path] = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default=None,
        description="Path to aurora_core.log for rewards (Phase 7)"
    )
    symbols: Optional[List[str]] = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default=None,
        description="List of symbols to monitor (Phase 7)"
    )

    # =========================================================================
    # Common Settings
    # =========================================================================
    batch_size: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        default=100,
        ge=1, le=10000,
        description="Number of events to process before yielding"
    )
    poll_interval: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=0.01, le=10.0,
        description="Seconds to wait when tailing for new data"
    )
    max_feature_lines_total_per_cycle: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        default=1000,
        ge=1, le=100000,
        description="Hard cap of feature lines processed per run-loop cycle"
    )
    max_feature_lines_per_symbol_per_cycle: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        default=200,
        ge=1, le=100000,
        description="Hard cap of feature lines processed per symbol per cycle"
    )
    max_order_lines_per_cycle: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        default=500,
        ge=1, le=100000,
        description="Hard cap of order log lines processed per run-loop cycle"
    )
    max_core_lines_per_cycle: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        default=500,
        ge=1, le=100000,
        description="Hard cap of core log lines processed per run-loop cycle"
    )
    feature_missing_timestamp_policy: Literal[
        "fail_closed", "legacy_non_causal_file_offset"
    ] = Field(
        json_schema_extra={"default_class": "structural_safe"},
        description=(
            "What to do when features lack causal event_ts_ms (Invariant I3).\n"
            "'fail_closed' rejects the row. "
            "'legacy_non_causal_file_offset' synthesizes deterministic non-causal "
            "event_ts_ms from explicit replay config for compatibility only."
        ),
    )
    legacy_feature_base_ts_ms: Optional[int] = Field(
        json_schema_extra={"default_class": "legacy_compat"},
        default=None,
        ge=1,
        description=(
            "Required only when feature_missing_timestamp_policy="
            "'legacy_non_causal_file_offset'. Base epoch-millisecond used to "
            "derive deterministic synthetic timestamps for legacy feature rows."
        ),
    )

    @field_validator('wal_dir', mode='before')
    @classmethod
    def resolve_wal_dir(cls, v):
        if v is None:
            return Path("ops/wal").resolve()
        return Path(v).resolve()

    @field_validator('features_dir', 'orders_file', 'core_log', mode='before')
    @classmethod
    def resolve_optional_paths(cls, v):
        if v is None:
            return None
        return Path(v).resolve()

    @model_validator(mode='after')
    def validate_legacy_feature_timestamp_policy(self):
        if (
            self.feature_missing_timestamp_policy == "legacy_non_causal_file_offset"
            and self.legacy_feature_base_ts_ms is None
        ):
            raise ValueError(
                "legacy_feature_base_ts_ms is required when "
                "feature_missing_timestamp_policy='legacy_non_causal_file_offset'"
            )
        return self

    @property
    def is_phase7(self) -> bool:
        """Check if Phase 7 (multi-source) is configured."""
        return self.features_dir is not None


# =============================================================================
# ORACLE CONFIGURATION (REGIME_PIVOT_PLAN)
# =============================================================================

class OracleConfig(BaseModel):
    """Regime Oracle reward configuration (self-supervised regime prediction).

    Loaded from config/regime_oracle_reward.yaml.
    REGIME_PIVOT_PLAN Section 3: Self-Supervised Reward Function.
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    # Look-ahead horizon
    horizon_bars: int = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=1, le=50,
        description="Number of bars into the future to evaluate predictions (5 bars = 25min on 5m TF)"
    )

    # Ground-truth labeling thresholds (calibrated for logs/features/*.log)
    # Note: features in logs use pre-normalized values:
    #   delta_price = raw USD (labeler normalizes by price internally)
    #   ema_bias = [0,1] centered at 0.5 (labeler re-centers to 0)
    #   volatility_state = [0,1] where 0=calm, 1=high vol
    high_vol_threshold: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=1.0,
        description="volatility_state(t+H) above which HIGH_VOLATILITY is labeled"
    )
    exhaustion_vol_now_threshold: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=1.0,
        description="volatility_state(t) above which vol is considered 'was high' for exhaustion"
    )
    exhaustion_vol_future_threshold: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=1.0,
        description="volatility_state(t+H) below which vol is considered 'collapsed' for exhaustion"
    )
    trend_delta_pct_threshold: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=0.1,
        description="delta_price/price above which trend is detected (e.g. 0.0003 = 0.03%)"
    )
    trend_ema_threshold: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=0.1,
        description="(ema_bias - 0.5) above which EMA confirms trend direction"
    )
    mr_delta_pct_threshold: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=0.1,
        description="delta_price/price below which mean-reversion is labeled"
    )

    # Reward scaling
    reward_correct: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        gt=0.0, le=10.0,
        description="Reward for correct regime prediction"
    )
    reward_wrong: float = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        ge=-10.0, le=0.0,
        description="Penalty for incorrect regime prediction"
    )

    # Formula B toggle
    reward_matrix_enabled: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Enable confusion-weighted reward matrix (Formula B). False = use Formula A (exact match)"
    )

    # Formula B: explicit reward matrix C[predicted][realized] (5x5)
    reward_matrix: Optional[List[List[float]]] = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default=None,
        description="5x5 confusion reward matrix. Rows=predicted, Cols=realized. Required when reward_matrix_enabled=True"
    )

    # Class weights to counteract label imbalance
    class_weights: Dict[str, float] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Per-action class weights (action_name -> weight). Rare regimes get higher weight"
    )


# =============================================================================
# AUTHORITY CONFIGURATION (06 §6.2 mandatory keys)
# =============================================================================

class AuthorityConfig(BaseModel):
    """Neocortex Authority Seam configuration (Phase 5 consumer: NeocortexAuthorityBridge).

    All fields are runtime_behavior and required from YAML.
    Declared but not consumed until Phase 5.
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    mode: Literal["shadow", "advisory", "gated"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Authority operating mode. 'shadow'=observe-only, 'advisory'=influence, 'gated'=hard gate.",
    )
    deadline_ms: int = Field(
        ge=1, le=1000,
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Max milliseconds authority may take before fallback is applied (invariant I6).",
    )
    fallback_policy: Literal["baseline_yaml"] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Policy when authority deadline is missed. 'baseline_yaml'=use existing Aurora baseline.",
    )
    max_inflight_per_symbol: int = Field(
        ge=1, le=10,
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Max concurrent authority requests per symbol (invariant I6).",
    )
    modulation_allowlist: List[str] = Field(
        min_length=1,
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Canonical overlay knobs permitted for modulation. Non-empty list.",
    )
    signal_threshold_bias_bounds: List[float] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="[min, max] inclusive bounds for signal_threshold_bias overlay.",
    )
    cooldown_mult_bounds: List[float] = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="[min, max] inclusive bounds for cooldown_mult overlay. min must be > 0.",
    )

    @model_validator(mode="after")
    def validate_bounds_contract(self):
        stb = self.signal_threshold_bias_bounds
        if len(stb) != 2:
            raise ValueError(
                "signal_threshold_bias_bounds must have exactly 2 elements [min, max]")
        if stb[0] > stb[1]:
            raise ValueError(
                "signal_threshold_bias_bounds[0] must be <= signal_threshold_bias_bounds[1]")

        cm = self.cooldown_mult_bounds
        if len(cm) != 2:
            raise ValueError(
                "cooldown_mult_bounds must have exactly 2 elements [min, max]")
        if cm[0] <= 0:
            raise ValueError("cooldown_mult_bounds[0] must be > 0")
        if cm[0] > cm[1]:
            raise ValueError(
                "cooldown_mult_bounds[0] must be <= cooldown_mult_bounds[1]")

        return self


# =============================================================================
# ROOT CONFIGURATION
# =============================================================================

class NeocortexConfig(BaseModel):
    """Root configuration for Neocortex domain."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    # §6.2 global kill-switch — separate from authority.mode
    trust_enabled: bool = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Global Neocortex kill-switch (neocortex.trust_enabled per §6.2). "
                    "false=authority disabled; fallback=baseline YAML.",
    )
    system: SystemConfig
    ingest: IngestConfig
    neuro: NeuroConfig
    # replay is required from YAML (no implicit default — Phase 2 I2)
    replay: ReplayConfig = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Historical WAL replay / multi-source ingestion settings. Required from YAML."
    )
    oracle: Optional[OracleConfig] = Field(
        json_schema_extra={"default_class": "structural_safe"},
        default=None,
        description="Regime Oracle reward config (loaded from regime_oracle_reward.yaml). "
                    "Required when neuro.ppo.reward_mode='regime_oracle'"
    )
    # §6.2 authority seam config (declared_not_consumed_yet — Phase 5)
    authority: AuthorityConfig = Field(
        json_schema_extra={"default_class": "runtime_behavior"},
        description="Authority seam configuration (§6.2). Consumer: Phase 5 NeocortexAuthorityBridge.",
    )

    @field_validator('neuro', mode='after')
    @classmethod
    def validate_dimensions(cls, v, info):
        """Cross-validate dimensions across configs."""
        ingest = info.data.get('ingest')
        if ingest is None:
            return v

        # VAE input_dim must match feature count
        expected_dim = len(ingest.feature_list)
        if v.vae.input_dim != expected_dim:
            raise ValueError(
                f"VAE input_dim ({v.vae.input_dim}) must match "
                f"len(feature_list) ({expected_dim})"
            )

        # PPO state_dim should be >= VAE latent_dim (at minimum)
        if v.ppo.state_dim < v.vae.latent_dim:
            raise ValueError(
                f"PPO state_dim ({v.ppo.state_dim}) should be >= "
                f"VAE latent_dim ({v.vae.latent_dim})"
            )

        return v

    @model_validator(mode='after')
    def validate_operating_mode(self):
        if (
            self.system.run_mode == "live"
            and self.neuro.performance.operating_mode != "live_shadow"
        ):
            raise ValueError(
                "system.run_mode='live' requires neuro.performance.operating_mode='live_shadow'"
            )
        if (
            self.system.run_mode == "live"
            and self.neuro.shadow_gates.startup_enforcement != "strict"
        ):
            raise ValueError(
                "system.run_mode='live' requires neuro.shadow_gates.startup_enforcement='strict'"
            )
        return self


# =============================================================================
# CONFIGURATION LOADER
# =============================================================================

def load_config(config_dir: Path) -> NeocortexConfig:
    """
    Load and validate Neocortex configuration from YAML files.

    FAIL-CLOSED CONTRACT:
    - Missing required file -> FileNotFoundError
    - Invalid YAML syntax -> yaml.YAMLError
    - Schema violation -> pydantic.ValidationError
    - Extra unknown fields -> pydantic.ValidationError

    Args:
        config_dir: Directory containing system.yaml, neuro.yaml, ingest.yaml

    Returns:
        Validated NeocortexConfig instance

    Raises:
        FileNotFoundError: If any required config file is missing
        yaml.YAMLError: If YAML is malformed
        pydantic.ValidationError: If config violates schema
    """
    config_dir = Path(config_dir).resolve()

    # Load individual YAML files (fail if missing)
    system_path = config_dir / "system.yaml"
    ingest_path = config_dir / "ingest.yaml"
    neuro_path = config_dir / "neuro.yaml"

    if not system_path.exists():
        raise FileNotFoundError(f"Missing system config: {system_path}")
    if not ingest_path.exists():
        raise FileNotFoundError(f"Missing ingest config: {ingest_path}")
    if not neuro_path.exists():
        raise FileNotFoundError(f"Missing neuro config: {neuro_path}")

    with open(system_path) as f:
        system_data = yaml.safe_load(f)
    with open(ingest_path) as f:
        ingest_data = yaml.safe_load(f)
    with open(neuro_path) as f:
        neuro_data = yaml.safe_load(f)

    # Extract §6.2 top-level keys from system.yaml before passing to SystemConfig.
    # trust_enabled and authority live in system.yaml but are root-level NeocortexConfig fields.
    trust_enabled = system_data.pop("trust_enabled", None)
    authority_data = system_data.pop("authority", None)

    if trust_enabled is None:
        raise ValueError(
            "Missing required key 'trust_enabled' in system.yaml (neocortex.trust_enabled per §6.2)"
        )
    if authority_data is None:
        raise ValueError(
            "Missing required key 'authority' in system.yaml (neocortex.authority.* per §6.2)"
        )

    # Load required replay config (Phase 2 I2: no implicit default)
    replay_path = config_dir / "replay.yaml"
    if not replay_path.exists():
        raise FileNotFoundError(
            f"Missing required replay config: {replay_path}. "
            "Create replay.yaml with at least 'enabled: false' to satisfy I2."
        )
    with open(replay_path) as f:
        replay_data = yaml.safe_load(f)

    # Load optional oracle config (REGIME_PIVOT_PLAN)
    oracle_path = config_dir / "regime_oracle_reward.yaml"
    oracle_data = None
    if oracle_path.exists():
        with open(oracle_path) as f:
            oracle_data = yaml.safe_load(f)

    # Pydantic validation (fail on extra fields, missing fields, type errors)
    kwargs: dict = {
        "trust_enabled": trust_enabled,
        "authority": authority_data,
        "system": system_data,
        "ingest": ingest_data,
        "neuro": neuro_data,
        "replay": replay_data,
    }
    if oracle_data is not None:
        kwargs["oracle"] = oracle_data

    return NeocortexConfig(**kwargs)


# =============================================================================
# USAGE EXAMPLE
# =============================================================================

if __name__ == "__main__":  # pragma: no cover
    # Example: Load from config directory
    config = load_config(Path(__file__).parent / "config")
    print(f"✓ Config loaded successfully")
    print(f"  Features: {len(config.ingest.feature_list)}")
    print(f"  VAE latent_dim: {config.neuro.vae.latent_dim}")
    print(f"  PPO state_dim: {config.neuro.ppo.state_dim}")
