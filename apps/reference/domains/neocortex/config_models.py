"""
Neocortex Configuration Models (Pydantic V2)

PHILOSOPHY:
- Fail-closed: extra='forbid' on all models
- No defaults for business parameters (hidden defaults cause production incidents)
- Explicit is better than implicit
- Early validation prevents runtime surprises
"""

from pathlib import Path
from typing import List, Literal, Optional
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


# =============================================================================
# NEURO CONFIGURATION (VAE + PPO)
# =============================================================================

class VAEConfig(BaseModel):
    """Variational Autoencoder hyperparameters."""
    
    model_config = ConfigDict(extra='forbid', frozen=True)
    
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
        description="Action space dimension (e.g., 3 for [LONG, SHORT, FLAT])"
    )
    hidden_dims: List[int] = Field(
        min_length=1,
        description="Policy/Value network hidden layers, e.g. [256, 128]"
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
    
    # Pydantic validation (fail on extra fields, missing fields, type errors)
    if replay_data is not None:
        return NeocortexConfig(
            system=system_data,
            ingest=ingest_data,
            neuro=neuro_data,
            replay=replay_data
        )
    else:
        return NeocortexConfig(
            system=system_data,
            ingest=ingest_data,
            neuro=neuro_data
        )


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
