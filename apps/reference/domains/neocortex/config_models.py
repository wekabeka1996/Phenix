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
from pydantic import BaseModel, Field, field_validator, ConfigDict

DEFAULT_RNG_SEED = 42


# =============================================================================
# SYSTEM CONFIGURATION
# =============================================================================

class SystemConfig(BaseModel):
    """System-level settings (paths, multiprocessing, logging)."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    # Paths
    data_dir: Path = Field(
        description="Directory for logs, checkpoints, embeddings"
    )
    checkpoint_dir: Path = Field(
        description="Model checkpoint storage"
    )

    # Multiprocessing
    brain_workers: int = Field(
        ge=1, le=8,
        description="Number of brain worker processes for ML inference"
    )
    queue_maxsize: int = Field(
        ge=10, le=10000,
        description="Max size of inter-process queues"
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        description="Logging verbosity"
    )
    log_to_file: bool = Field(
        description="Whether to write logs to file"
    )

    # Run Mode
    run_mode: Literal["live", "backtest"] = Field(
        default="backtest",
        description="Execution mode: 'live' (real logs) or 'backtest' (historical/simulated logs)"
    )

    # Reproducibility
    rng_seed: int = Field(
        default=DEFAULT_RNG_SEED,
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
        min_length=1,
        description="Ordered list of features to ingest from EVT:FEATURES_CALCULATED"
    )

    # Normalization (NO DEFAULTS - must be explicitly chosen)
    normalization_method: Literal["zscore", "minmax", "robust"] = Field(
        description="Feature scaling method"
    )
    normalization_window: int = Field(
        ge=10, le=10000,
        description="Rolling window size for normalization statistics"
    )
    normalization_scope: Literal["global", "per_symbol"] = Field(
        default="per_symbol",
        description="Normalization scope for running statistics."
    )
    price_feature_mode: Literal["raw", "log", "drop"] = Field(
        default="log",
        description="How to represent `price` for ML input."
    )
    delta_price_mode: Literal["raw", "pct"] = Field(
        default="pct",
        description="How to represent `delta_price` for ML input."
    )
    feature_clip_abs: Dict[str, float] = Field(
        default_factory=dict,
        description="Optional per-feature absolute clipping bounds before normalization."
    )

    # Buffering
    buffer_size: int = Field(
        ge=100, le=100000,
        description="Max observations to keep in memory buffer"
    )

    # Timestep handling
    min_samples_before_ready: int = Field(
        ge=1,
        description="Minimum samples required before marking ingest as 'ready'"
    )

    # Robustness
    nan_strategy: Literal["zero", "ignore", "ffill"] = Field(
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

        enabled: bool = Field(
            default=False,
            description="Enable auxiliary regime-classification head on latent mean."
        )
        alpha: float = Field(
            default=0.2,
            ge=0.0, le=10.0,
            description="Auxiliary CE weight in total VAE loss."
        )
        num_classes: int = Field(
            default=5,
            ge=2, le=64,
            description="Number of classes for auxiliary regime supervision."
        )

    # Architecture (NO DEFAULTS)
    input_dim: int = Field(
        ge=1,
        description="Input feature dimension (must match len(feature_list))"
    )
    hidden_dims: List[int] = Field(
        min_length=1,
        description="Encoder/decoder hidden layer sizes, e.g. [128, 64]"
    )
    latent_dim: int = Field(
        ge=2, le=512,
        description="Latent space dimensionality"
    )

    # Training
    learning_rate: float = Field(
        gt=0.0, le=0.1,
        description="Adam optimizer learning rate"
    )
    beta: float = Field(
        gt=0.0, le=10.0,
        description="KL divergence weight in VAE loss"
    )
    batch_size: int = Field(
        ge=1, le=1024,
        description="Training batch size"
    )

    # Inference
    use_mean: bool = Field(
        description="Whether to use mean (True) or sample (False) during encoding"
    )
    regime_aux: RegimeAuxConfig = Field(
        default_factory=RegimeAuxConfig,
        description="Auxiliary latent supervision settings."
    )


class WorldModelConfig(BaseModel):
    """World Model (RNN) hyperparameters."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    # Architecture
    hidden_dim: int = Field(
        ge=16, le=2048,
        description="RNN hidden state dimension"
    )
    num_layers: int = Field(
        ge=1, le=8,
        description="Number of RNN layers"
    )
    dropout: float = Field(
        ge=0.0, le=0.9,
        description="RNN dropout probability"
    )

    # Training
    learning_rate: float = Field(
        gt=0.0, le=0.01,
        description="Adam optimizer learning rate"
    )
    sequence_length: int = Field(
        ge=2, le=512,
        description="Training sequence length (BPTT)"
    )


class PPOEntropyScheduleConfig(BaseModel):
    """Entropy coefficient decay schedule."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    start: float = Field(
        ge=0.0, le=0.5,
        description="Initial entropy coefficient"
    )
    end: float = Field(
        ge=0.0, le=0.5,
        description="Final entropy coefficient"
    )
    total_steps: int = Field(
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
        default=1.0,
        gt=0.0, le=10.0,
        description="Gradient norm threshold used by numerical safety validator"
    )
    on_invalid: Literal["zero_grads", "skip_step", "sanitize"] = Field(
        default="sanitize",
        description="Recovery strategy for invalid gradients"
    )


class PPOConfig(BaseModel):
    """Proximal Policy Optimization hyperparameters."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    # Network architecture (NO DEFAULTS)
    state_dim: int = Field(
        ge=1,
        description="State dimension (typically VAE latent_dim + market context)"
    )
    action_dim: int = Field(
        ge=1,
        description="Action space dimension (3 for [LONG, SHORT, FLAT] or 5 for regime oracle)"
    )
    hidden_dims: List[int] = Field(
        min_length=1,
        description="Policy/Value network hidden layers, e.g. [256, 128]"
    )

    # Reward mode: pnl (legacy) or regime_oracle (REGIME_PIVOT_PLAN)
    reward_mode: Literal["pnl", "regime_oracle"] = Field(
        default="pnl",
        description="Reward source: 'pnl' (trade PnL) or 'regime_oracle' (self-supervised regime prediction)"
    )

    # Training
    learning_rate: float = Field(
        gt=0.0, le=0.01,
        description="Adam optimizer learning rate"
    )
    gamma: float = Field(
        gt=0.0, le=1.0,
        description="Discount factor for future rewards"
    )
    gae_lambda: float = Field(
        gt=0.0, le=1.0,
        description="GAE lambda for advantage estimation"
    )
    clip_epsilon: float = Field(
        gt=0.0, le=0.5,
        description="PPO clipping epsilon"
    )

    # Entropy bonus coefficient (prevents policy collapse)
    entropy_coef: float = Field(
        default=0.01,
        ge=0.0, le=0.5,
        description="Entropy bonus coefficient. Higher values encourage exploration and prevent mode collapse"
    )
    entropy_schedule: Optional[PPOEntropyScheduleConfig] = Field(
        default=None,
        description="Optional linear schedule for entropy_coef"
    )
    max_grad_norm: float = Field(
        default=0.5,
        gt=0.0, le=10.0,
        description="Gradient clipping norm passed to PPO updater"
    )
    numerical_safety: PPONumericalSafetyConfig = Field(
        default_factory=PPONumericalSafetyConfig,
        description="Numerical safety settings passed into PPO SafetyConfig"
    )

    # Rollout
    rollout_length: int = Field(
        ge=1, le=10000,
        description="Steps to collect before policy update"
    )
    num_epochs: int = Field(
        ge=1, le=100,
        description="Optimization epochs per rollout"
    )
    minibatch_size: int = Field(
        ge=1, le=1024,
        description="Minibatch size for PPO updates"
    )


class NeuroConfig(BaseModel):
    """Combined ML configuration."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    vae: VAEConfig
    world_model: WorldModelConfig
    ppo: PPOConfig

    # Checkpointing (NO DEFAULTS)
    checkpoint_every_n_steps: int = Field(
        ge=1,
        description="Save model checkpoint every N steps"
    )
    keep_last_n_checkpoints: int = Field(
        ge=1, le=100,
        description="Number of recent checkpoints to retain"
    )

    # Dream / PPO Training Trigger
    dream_episode_threshold: int = Field(
        default=1,
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
        description="Enable data ingestion"
    )

    # =========================================================================
    # Phase 6: WAL Tailing (legacy)
    # =========================================================================
    wal_dir: Path = Field(
        default=Path("ops/wal"),
        description="Directory containing WAL files (Phase 6)"
    )
    wal_glob: str = Field(
        default="",
        description="DEPRECATED: Use wal_dir instead."
    )
    filter_verb: str = Field(
        default="FEATURES_CALCULATED",
        description="Event verb to filter for in WAL (Phase 6)"
    )

    # =========================================================================
    # Phase 7: Multi-Source Ingestion
    # =========================================================================
    features_dir: Optional[Path] = Field(
        default=None,
        description="Directory with feature logs per symbol (Phase 7)"
    )
    orders_file: Optional[Path] = Field(
        default=None,
        description="Path to order log JSONL file (Phase 7)"
    )
    core_log: Optional[Path] = Field(
        default=None,
        description="Path to aurora_core.log for rewards (Phase 7)"
    )
    symbols: Optional[List[str]] = Field(
        default=None,
        description="List of symbols to monitor (Phase 7)"
    )

    # =========================================================================
    # Common Settings
    # =========================================================================
    batch_size: int = Field(
        default=100,
        ge=1, le=10000,
        description="Number of events to process before yielding"
    )
    poll_interval: float = Field(
        default=0.1,
        ge=0.01, le=10.0,
        description="Seconds to wait when tailing for new data"
    )
    max_feature_lines_total_per_cycle: int = Field(
        default=1000,
        ge=1, le=100000,
        description="Hard cap of feature lines processed per run-loop cycle"
    )
    max_feature_lines_per_symbol_per_cycle: int = Field(
        default=200,
        ge=1, le=100000,
        description="Hard cap of feature lines processed per symbol per cycle"
    )
    max_order_lines_per_cycle: int = Field(
        default=500,
        ge=1, le=100000,
        description="Hard cap of order log lines processed per run-loop cycle"
    )
    max_core_lines_per_cycle: int = Field(
        default=500,
        ge=1, le=100000,
        description="Hard cap of core log lines processed per run-loop cycle"
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
        ge=1, le=50,
        description="Number of bars into the future to evaluate predictions (5 bars = 25min on 5m TF)"
    )

    # Ground-truth labeling thresholds (calibrated for logs/features/*.log)
    # Note: features in logs use pre-normalized values:
    #   delta_price = raw USD (labeler normalizes by price internally)
    #   ema_bias = [0,1] centered at 0.5 (labeler re-centers to 0)
    #   volatility_state = [0,1] where 0=calm, 1=high vol
    high_vol_threshold: float = Field(
        gt=0.0, le=1.0,
        description="volatility_state(t+H) above which HIGH_VOLATILITY is labeled"
    )
    exhaustion_vol_now_threshold: float = Field(
        gt=0.0, le=1.0,
        description="volatility_state(t) above which vol is considered 'was high' for exhaustion"
    )
    exhaustion_vol_future_threshold: float = Field(
        gt=0.0, le=1.0,
        description="volatility_state(t+H) below which vol is considered 'collapsed' for exhaustion"
    )
    trend_delta_pct_threshold: float = Field(
        gt=0.0, le=0.1,
        description="delta_price/price above which trend is detected (e.g. 0.0003 = 0.03%)"
    )
    trend_ema_threshold: float = Field(
        gt=0.0, le=0.1,
        description="(ema_bias - 0.5) above which EMA confirms trend direction"
    )
    mr_delta_pct_threshold: float = Field(
        gt=0.0, le=0.1,
        description="delta_price/price below which mean-reversion is labeled"
    )

    # Reward scaling
    reward_correct: float = Field(
        gt=0.0, le=10.0,
        description="Reward for correct regime prediction"
    )
    reward_wrong: float = Field(
        ge=-10.0, le=0.0,
        description="Penalty for incorrect regime prediction"
    )

    # Formula B toggle
    reward_matrix_enabled: bool = Field(
        default=False,
        description="Enable confusion-weighted reward matrix (Formula B). False = use Formula A (exact match)"
    )

    # Formula B: explicit reward matrix C[predicted][realized] (5x5)
    reward_matrix: Optional[List[List[float]]] = Field(
        default=None,
        description="5x5 confusion reward matrix. Rows=predicted, Cols=realized. Required when reward_matrix_enabled=True"
    )

    # Class weights to counteract label imbalance
    class_weights: Dict[str, float] = Field(
        description="Per-action class weights (action_name -> weight). Rare regimes get higher weight"
    )


# =============================================================================
# ROOT CONFIGURATION
# =============================================================================

class NeocortexConfig(BaseModel):
    """Root configuration for Neocortex domain."""

    model_config = ConfigDict(extra='forbid', frozen=True)

    system: SystemConfig
    ingest: IngestConfig
    neuro: NeuroConfig
    replay: ReplayConfig = Field(
        default_factory=lambda: ReplayConfig(enabled=False),
        description="Historical WAL replay settings"
    )
    oracle: Optional[OracleConfig] = Field(
        default=None,
        description="Regime Oracle reward config (loaded from regime_oracle_reward.yaml). "
                    "Required when neuro.ppo.reward_mode='regime_oracle'"
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

    # Load optional replay config (Phase 6/7 ingestion)
    replay_path = config_dir / "replay.yaml"
    replay_data = None
    if replay_path.exists():
        with open(replay_path) as f:
            replay_data = yaml.safe_load(f)

    # Load optional oracle config (REGIME_PIVOT_PLAN: regime prediction reward)
    oracle_path = config_dir / "regime_oracle_reward.yaml"
    oracle_data = None
    if oracle_path.exists():
        with open(oracle_path) as f:
            oracle_data = yaml.safe_load(f)

    # Pydantic validation (fail on extra fields, missing fields, type errors)
    kwargs: dict = {
        "system": system_data,
        "ingest": ingest_data,
        "neuro": neuro_data,
    }
    if replay_data is not None:
        kwargs["replay"] = replay_data
    if oracle_data is not None:
        kwargs["oracle"] = oracle_data

    return NeocortexConfig(**kwargs)


# =============================================================================
# USAGE EXAMPLE
# =============================================================================

if __name__ == "__main__":
    # Example: Load from config directory
    config = load_config(Path(__file__).parent / "config")
    print(f"✓ Config loaded successfully")
    print(f"  Features: {len(config.ingest.feature_list)}")
    print(f"  VAE latent_dim: {config.neuro.vae.latent_dim}")
    print(f"  PPO state_dim: {config.neuro.ppo.state_dim}")
