"""
Configuration Contract Tests

Verify strict fail-closed behavior:
- Valid config loads successfully
- Missing required fields -> ValidationError
- Extra unknown fields -> ValidationError
- Type mismatches -> ValidationError
- Cross-field validation works
"""

import pytest
from pathlib import Path
import tempfile
import yaml
from pydantic import ValidationError

import sys

from apps.reference.domains.neocortex.config_models import (
    load_config,
    NeocortexConfig,
    SystemConfig,
    IngestConfig,
    NeuroConfig,
    VAEConfig,
    PPOConfig,
    WorldModelConfig
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def valid_system_config():
    """Valid system configuration."""
    return {
        "data_dir": "/tmp/neocortex/data",
        "checkpoint_dir": "/tmp/neocortex/checkpoints",
        "rng_seed": 42,
        "brain_workers": 2,
        "queue_maxsize": 500,
        "log_level": "INFO",
        "log_to_file": True,
        "run_mode": "backtest",
        "trust_enabled": False,
        "authority": {
            "mode": "shadow",
            "deadline_ms": 10,
            "fallback_policy": "baseline_yaml",
            "max_inflight_per_symbol": 1,
            "modulation_allowlist": ["decision_making.signal_threshold_bias"],
            "signal_threshold_bias_bounds": [-0.1, 0.1],
            "cooldown_mult_bounds": [1.0, 3.0],
        },
        "evidence_capture": {
            "mode": "disabled",
            "collect_observation": False,
            "collect_authority_request": False,
            "collect_authority_response": False,
            "emit_shadow_decision_logged": False,
        },
    }


@pytest.fixture
def valid_ingest_config():
    """Valid ingestion configuration."""
    return {
        "feature_list": ["rsi", "bb_percent", "obi"],
        "normalization_method": "zscore",
        "normalization_window": 200,
        "normalization_scope": "per_symbol",
        "price_feature_mode": "log",
        "delta_price_mode": "pct",
        "feature_clip_abs": {"rsi": 100.0},
        "buffer_size": 5000,
        "min_samples_before_ready": 50,
        "nan_strategy": "zero"
    }


@pytest.fixture
def valid_vae_config():
    """Valid VAE configuration."""
    return {
        "input_dim": 3,  # Matches 3 features
        "hidden_dims": [64, 32],
        "latent_dim": 8,
        "learning_rate": 0.001,
        "beta": 1.0,
        "free_bits_per_dim": 0.0,
        "batch_size": 32,
        "use_mean": True
    }


@pytest.fixture
def valid_ppo_config():
    """Valid PPO configuration."""
    return {
        "state_dim": 10,  # >= latent_dim
        "action_dim": 3,
        "hidden_dims": [128, 64],
        "reward_mode": "pnl",
        "objective_split_enforced": True,
        "policy_training_mode": "disabled",
        "learning_rate": 0.0003,
        "gamma": 0.99,
        "gae_lambda": 0.95,
        "clip_epsilon": 0.2,
        "entropy_coef": 0.01,
        "max_grad_norm": 0.5,
        "numerical_safety": {
            "gradient_clip_threshold": 1.0,
            "on_invalid": "sanitize",
        },
        "rollout_length": 1024,
        "num_epochs": 5,
        "minibatch_size": 32
    }


@pytest.fixture
def valid_world_model_config():
    """Valid World Model configuration."""
    return {
        "hidden_dim": 64,
        "num_layers": 1,
        "dropout": 0.1,
        "learning_rate": 0.001,
        "sequence_length": 32
    }


@pytest.fixture
def valid_neuro_config(valid_vae_config, valid_ppo_config, valid_world_model_config):
    """Valid neuro configuration."""
    return {
        "vae": valid_vae_config,
        "ppo": valid_ppo_config,
        "world_model": valid_world_model_config,
        "sequence": {
            "inference_mode": "stateless_per_event",
            "representation_training_mode": "independent_rows",
            "reset_on_replay_start": True,
            "reset_on_symbol_switch": True,
            "reset_on_objective_family_switch": True,
            "reset_on_episode_boundary": True,
        },
        "dataset": {
            "manifest_version": 1,
            "split": {
                "train_ratio": 0.7,
                "val_ratio": 0.15,
                "test_ratio": 0.15,
            },
            "cutover": {
                "min_real_executed_rows": 1,
                "allow_synthetic_fallback": False,
                "max_non_causal_rows": 0,
                "require_reward_methodology": True,
            },
        },
        "evaluation": {
            "report_version": 1,
            "calibration_bins": 5,
            "confidence_bucket_edges": [0.25, 0.5, 0.75, 0.9],
            "missing_confidence_policy": "not_available",
            "advisory_status": "forbidden",
        },
        "performance": {
            "operating_mode": "offline_replay",
            "shadow_intent_emit_policy": "decimate_observational",
            "shadow_intent_decimation_stride": 10,
            "shadow_jsonl_write_policy": "buffered",
            "telemetry_write_policy": "buffered",
            "non_critical_queue_limit": 2048,
            "shadow_log_flush_threshold": 64,
            "telemetry_flush_threshold": 64,
            "flush_interval_ms": 1000,
            "non_critical_overflow_policy": "drop_oldest",
        },
        "shadow_gates": {
            "gate_set_version": 1,
            "startup_enforcement": "strict",
            "allow_advisory_influence": False,
            "allow_live_authority": False,
            "allow_policy_training_reenable": False,
            "require_domain_manifest_contracts": True,
        },
        "checkpoint_every_n_steps": 500,
        "keep_last_n_checkpoints": 3,
        "dream_episode_threshold": 1,
    }


@pytest.fixture
def valid_replay_config(tmp_path):
    """Valid replay configuration."""
    return {
        "enabled": False,
        "wal_dir": str(tmp_path / "wal"),
        "poll_interval": 0.1,
        "feature_missing_timestamp_policy": "fail_closed",
    }


def _write_config_files(config_dir, system_config, ingest_config, neuro_config, replay_config):
    with open(config_dir / "system.yaml", "w") as f:
        yaml.dump(system_config, f)
    with open(config_dir / "ingest.yaml", "w") as f:
        yaml.dump(ingest_config, f)
    with open(config_dir / "neuro.yaml", "w") as f:
        yaml.dump(neuro_config, f)
    with open(config_dir / "replay.yaml", "w") as f:
        yaml.dump(replay_config, f)


# =============================================================================
# TEST 1: Valid Configuration Loads Successfully
# =============================================================================

def test_valid_config_loads(valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config, tmp_path):
    """Test that a fully valid configuration loads without errors."""

    # Create temporary config directory
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Write YAML files
    _write_config_files(config_dir, valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config)

    # Load and validate
    config = load_config(config_dir)

    # Assertions
    assert isinstance(config, NeocortexConfig)
    assert config.system.brain_workers == 2
    assert len(config.ingest.feature_list) == 3
    assert config.neuro.vae.latent_dim == 8
    assert config.neuro.ppo.state_dim == 10
    assert config.ingest.normalization_scope in {"global", "per_symbol"}
    assert config.ingest.price_feature_mode in {"raw", "log", "drop"}
    assert config.ingest.delta_price_mode in {"raw", "pct"}


def test_feature_clip_abs_validation(valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config, tmp_path):
    """feature_clip_abs must be positive finite values."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    invalid_ingest = valid_ingest_config.copy()
    invalid_ingest["feature_clip_abs"] = {"delta_price": -1.0}

    _write_config_files(config_dir, valid_system_config, invalid_ingest, valid_neuro_config, valid_replay_config)

    with pytest.raises(ValidationError):
        load_config(config_dir)


def test_vae_regime_aux_schedule_and_ema_validation(valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config, tmp_path):
    """Regime aux schedule/EMA fields should parse and enforce bounds."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    neuro = valid_neuro_config.copy()
    neuro["vae"] = dict(neuro["vae"])
    neuro["vae"]["free_bits_per_dim"] = 0.2
    neuro["vae"]["regime_aux"] = {
        "enabled": True,
        "alpha": 2.0,
        "num_classes": 5,
        "ema_decay": 0.99,
        "alpha_schedule": {
            "start": 0.5,
            "end": 2.0,
            "steps": 1000,
        },
    }

    _write_config_files(config_dir, valid_system_config, valid_ingest_config, neuro, valid_replay_config)

    loaded = load_config(config_dir)
    assert loaded.neuro.vae.free_bits_per_dim == pytest.approx(0.2)
    assert loaded.neuro.vae.regime_aux.ema_decay == pytest.approx(0.99)
    assert loaded.neuro.vae.regime_aux.alpha_schedule is not None
    assert loaded.neuro.vae.regime_aux.alpha_schedule.start == pytest.approx(
        0.5)


# =============================================================================
# TEST 2: Missing Required Field -> ValidationError
# =============================================================================

def test_missing_required_field_fails(valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config, tmp_path):
    """Test that missing required field raises ValidationError."""

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create config with missing field (remove 'latent_dim' from VAE)
    invalid_neuro = valid_neuro_config.copy()
    invalid_vae = invalid_neuro["vae"].copy()
    del invalid_vae["latent_dim"]  # Required field
    invalid_neuro["vae"] = invalid_vae

    _write_config_files(config_dir, valid_system_config, valid_ingest_config, invalid_neuro, valid_replay_config)

    # Should raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
        load_config(config_dir)

    # Verify error mentions missing field
    assert "latent_dim" in str(exc_info.value).lower()


# =============================================================================
# TEST 3: Extra Unknown Field -> ValidationError
# =============================================================================

def test_extra_field_fails(valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config, tmp_path):
    """Test that extra unknown field raises ValidationError (extra='forbid')."""

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Add unknown field to system config
    invalid_system = valid_system_config.copy()
    invalid_system["unknown_magic_parameter"] = 42  # Not in schema

    _write_config_files(config_dir, invalid_system, valid_ingest_config, valid_neuro_config, valid_replay_config)

    # Should raise ValidationError due to extra='forbid'
    with pytest.raises(ValidationError) as exc_info:
        load_config(config_dir)

    # Verify error mentions extra field
    error_str = str(exc_info.value).lower()
    assert "extra" in error_str or "unknown_magic_parameter" in error_str


# =============================================================================
# TEST 4: Type Mismatch -> ValidationError
# =============================================================================

def test_type_mismatch_fails(valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config, tmp_path):
    """Test that wrong types raise ValidationError."""

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Wrong type: brain_workers should be int, not string
    invalid_system = valid_system_config.copy()
    invalid_system["brain_workers"] = "two"  # String instead of int

    _write_config_files(config_dir, invalid_system, valid_ingest_config, valid_neuro_config, valid_replay_config)

    with pytest.raises(ValidationError) as exc_info:
        load_config(config_dir)

    assert "brain_workers" in str(exc_info.value).lower()


# =============================================================================
# TEST 5: Cross-Field Validation (VAE input_dim vs feature_list)
# =============================================================================

def test_cross_field_validation_vae_input_dim(valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config, tmp_path):
    """Test that VAE input_dim must match len(feature_list)."""

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Mismatch: feature_list has 3 items, but VAE input_dim=5
    invalid_neuro = valid_neuro_config.copy()
    invalid_neuro["vae"]["input_dim"] = 5  # Mismatch!

    _write_config_files(config_dir, valid_system_config, valid_ingest_config, invalid_neuro, valid_replay_config)

    with pytest.raises(ValidationError) as exc_info:
        load_config(config_dir)

    error_str = str(exc_info.value).lower()
    assert "input_dim" in error_str and "feature_list" in error_str


# =============================================================================
# TEST 6: Cross-Field Validation (PPO state_dim vs VAE latent_dim)
# =============================================================================

def test_cross_field_validation_ppo_state_dim(valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config, tmp_path):
    """Test that PPO state_dim must be >= VAE latent_dim."""

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Invalid: PPO state_dim (5) < VAE latent_dim (8)
    invalid_neuro = valid_neuro_config.copy()
    invalid_neuro["ppo"]["state_dim"] = 5  # Less than latent_dim=8

    _write_config_files(config_dir, valid_system_config, valid_ingest_config, invalid_neuro, valid_replay_config)

    with pytest.raises(ValidationError) as exc_info:
        load_config(config_dir)

    error_str = str(exc_info.value).lower()
    assert "state_dim" in error_str and "latent_dim" in error_str


# =============================================================================
# TEST 7: Missing Config File -> FileNotFoundError
# =============================================================================

def test_missing_config_file_fails(tmp_path):
    """Test that missing config file raises FileNotFoundError."""

    config_dir = tmp_path / "empty_config"
    config_dir.mkdir()

    # Don't create any YAML files

    with pytest.raises(FileNotFoundError) as exc_info:
        load_config(config_dir)

    assert "system.yaml" in str(
        exc_info.value) or "system config" in str(exc_info.value).lower()


# =============================================================================
# TEST 8: Duplicate Features in feature_list
# =============================================================================

def test_duplicate_features_fails(valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config, tmp_path):
    """Test that duplicate feature names are rejected."""

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Add duplicate feature
    invalid_ingest = valid_ingest_config.copy()
    invalid_ingest["feature_list"] = ["rsi", "obi", "rsi"]  # Duplicate 'rsi'

    _write_config_files(config_dir, valid_system_config, invalid_ingest, valid_neuro_config, valid_replay_config)

    with pytest.raises(ValidationError) as exc_info:
        load_config(config_dir)

    assert "duplicate" in str(exc_info.value).lower()


# =============================================================================
# TEST 9: Frozen Config (Immutability)
# =============================================================================

def test_config_is_frozen(valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config, tmp_path):
    """Test that config models are immutable (frozen=True)."""

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    _write_config_files(config_dir, valid_system_config, valid_ingest_config, valid_neuro_config, valid_replay_config)

    config = load_config(config_dir)

    # Attempt to modify should raise ValidationError (frozen models)
    with pytest.raises(ValidationError):
        config.system.brain_workers = 99


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

