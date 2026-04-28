import pytest
import yaml
from pathlib import Path
from pydantic import ValidationError

from apps.reference.domains.neocortex.config_models import load_config, NeocortexConfig

def write_yaml(path: Path, filename: str, content: dict):
    with open(path / filename, "w", encoding="utf-8") as f:
        yaml.dump(content, f)

@pytest.fixture
def valid_config_dir(tmp_path: Path):
    system = {
        "trust_enabled": False,
        "authority": {
            "mode": "shadow",
            "deadline_ms": 100,
            "fallback_policy": "baseline_yaml",
            "max_inflight_per_symbol": 2,
            "modulation_allowlist": ["signal_threshold_bias"],
            "signal_threshold_bias_bounds": [-0.5, 0.5],
            "cooldown_mult_bounds": [0.5, 2.0]
        },
        "data_dir": "/tmp/neo",
        "checkpoint_dir": "/tmp/neo/checkpoints",
        "brain_workers": 2,
        "queue_maxsize": 1000,
        "log_level": "INFO",
        "log_to_file": False,
        "run_mode": "backtest",
        "rng_seed": 42
    }
    
    ingest = {
        "feature_list": ["price"],
        "normalization_method": "zscore",
        "normalization_window": 100,
        "normalization_scope": "global",
        "price_feature_mode": "raw",
        "delta_price_mode": "raw",
        "feature_clip_abs": {"price": 10.0},
        "buffer_size": 1000,
        "min_samples_before_ready": 10,
        "nan_strategy": "zero"
    }
    
    neuro = {
        "vae": {
            "input_dim": 1,
            "hidden_dims": [32],
            "latent_dim": 4,
            "learning_rate": 0.001,
            "beta": 1.0,
            "free_bits_per_dim": 0.0,
            "batch_size": 32,
            "use_mean": False,
            "regime_aux": {
                "enabled": False,
                "alpha": 1.0,
                "num_classes": 3,
                "ema_decay": 0.99,
                "alpha_schedule": {
                    "start": 1.0,
                    "end": 0.1,
                    "steps": 1000
                }
            }
        },
        "world_model": {
            "hidden_dim": 32,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.001,
            "sequence_length": 10
        },
        "ppo": {
            "state_dim": 4,
            "action_dim": 2,
            "hidden_dims": [32],
            "reward_mode": "pnl",
            "objective_split_enforced": True,
            "policy_training_mode": "disabled",
            "learning_rate": 0.001,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "clip_epsilon": 0.2,
            "entropy_coef": 0.01,
            "max_grad_norm": 0.5,
            "numerical_safety": {
                "gradient_clip_threshold": 1.0,
                "on_invalid": "sanitize"
            },
            "rollout_length": 100,
            "num_epochs": 3,
            "minibatch_size": 32
        },
        "sequence": {
            "inference_mode": "stateless_per_event",
            "representation_training_mode": "independent_rows",
            "reset_on_replay_start": True,
            "reset_on_symbol_switch": True,
            "reset_on_objective_family_switch": True,
            "reset_on_episode_boundary": True
        },
        "dataset": {
            "manifest_version": 1,
            "split": {
                "train_ratio": 0.7,
                "val_ratio": 0.15,
                "test_ratio": 0.15
            }
        },
        "evaluation": {
            "report_version": 1,
            "calibration_bins": 5,
            "confidence_bucket_edges": [0.25, 0.5, 0.75, 0.9],
            "missing_confidence_policy": "not_available",
            "advisory_status": "forbidden"
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
            "non_critical_overflow_policy": "drop_oldest"
        },
        "shadow_gates": {
            "gate_set_version": 1,
            "startup_enforcement": "strict",
            "allow_advisory_influence": False,
            "allow_live_authority": False,
            "allow_policy_training_reenable": False,
            "require_domain_manifest_contracts": True
        },
        "checkpoint_every_n_steps": 1000,
        "keep_last_n_checkpoints": 5,
        "dream_episode_threshold": 1
    }
    
    replay = {
        "enabled": False,
        "wal_dir": "/tmp/wal",
        "wal_glob": "*.log",
        "filter_verb": "ALL",
        "features_dir": "/tmp/neo/features",
        "orders_file": "/tmp/neo/orders.log",
        "core_log": "/tmp/neo/core.log",
        "symbols": ["BTC-USD"],
        "batch_size": 100,
        "poll_interval": 1.0,
        "max_feature_lines_total_per_cycle": 100,
        "max_feature_lines_per_symbol_per_cycle": 100,
        "max_order_lines_per_cycle": 100,
        "max_core_lines_per_cycle": 100,
        "feature_missing_timestamp_policy": "fail_closed",
        "legacy_feature_base_ts_ms": 1000000
    }

    write_yaml(tmp_path, "system.yaml", system)
    write_yaml(tmp_path, "ingest.yaml", ingest)
    write_yaml(tmp_path, "neuro.yaml", neuro)
    write_yaml(tmp_path, "replay.yaml", replay)
    return tmp_path

def test_load_config_success(valid_config_dir):
    config = load_config(str(valid_config_dir))
    assert isinstance(config, NeocortexConfig)
    assert config.trust_enabled is False
    assert config.authority.mode == "shadow"
    assert config.replay.enabled is False
    assert config.neuro.vae.regime_aux.enabled is False

def test_load_config_missing_trust_enabled(valid_config_dir):
    with open(valid_config_dir / "system.yaml") as f:
        data = yaml.safe_load(f)
    del data["trust_enabled"]
    write_yaml(valid_config_dir, "system.yaml", data)

    with pytest.raises(ValueError, match="Missing required key 'trust_enabled' in system.yaml"):
        load_config(str(valid_config_dir))

def test_load_config_missing_authority(valid_config_dir):
    with open(valid_config_dir / "system.yaml") as f:
        data = yaml.safe_load(f)
    del data["authority"]
    write_yaml(valid_config_dir, "system.yaml", data)

    with pytest.raises(ValueError, match="Missing required key 'authority' in system.yaml"):
        load_config(str(valid_config_dir))

def test_load_config_missing_replay(valid_config_dir):
    (valid_config_dir / "replay.yaml").unlink()
    
    with pytest.raises(FileNotFoundError, match="Missing required replay config"):
        load_config(str(valid_config_dir))

def test_load_config_invalid_authority_bounds(valid_config_dir):
    with open(valid_config_dir / "system.yaml") as f:
        data = yaml.safe_load(f)
    data["authority"]["cooldown_mult_bounds"] = [-1.0, 2.0] # min <= 0 is invalid
    write_yaml(valid_config_dir, "system.yaml", data)

    with pytest.raises(ValidationError):
        load_config(str(valid_config_dir))

def test_load_config_missing_neuro_field(valid_config_dir):
    with open(valid_config_dir / "neuro.yaml") as f:
        data = yaml.safe_load(f)
    # remove required field dream_episode_threshold
    del data["dream_episode_threshold"]
    write_yaml(valid_config_dir, "neuro.yaml", data)

    with pytest.raises(ValidationError):
        load_config(str(valid_config_dir))
