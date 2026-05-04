"""
Sequence semantics contract tests for P5.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from apps.reference.domains.neocortex.config_models import NeuroConfig, load_config
from apps.reference.domains.neocortex.logic.brain.core import BrainCore
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter


@pytest.fixture
def neuro_config() -> NeuroConfig:
    return NeuroConfig(
        vae={
            "input_dim": 6,
            "hidden_dims": [8, 4],
            "latent_dim": 4,
            "learning_rate": 0.001,
            "beta": 1.0,
            "free_bits_per_dim": 0.0,
            "batch_size": 8,
            "use_mean": True,
            "regime_aux": {"enabled": False},
        },
        world_model={
            "hidden_dim": 16,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.001,
            "sequence_length": 8,
        },
        ppo={
            "state_dim": 4,
            "action_dim": 3,
            "hidden_dims": [16],
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
                "on_invalid": "sanitize",
            },
            "rollout_length": 32,
            "num_epochs": 2,
            "minibatch_size": 8,
        },
        sequence={
            "inference_mode": "stateless_per_event",
            "representation_training_mode": "independent_rows",
            "reset_on_replay_start": True,
            "reset_on_symbol_switch": True,
            "reset_on_objective_family_switch": True,
            "reset_on_episode_boundary": True,
        },
        dataset={
            "manifest_version": 1,
            "split": {
                "train_ratio": 0.7,
                "val_ratio": 0.15,
                "test_ratio": 0.15,
            },
        },
        evaluation={
            "report_version": 1,
            "calibration_bins": 5,
            "confidence_bucket_edges": [0.25, 0.5, 0.75, 0.9],
            "missing_confidence_policy": "not_available",
            "advisory_status": "forbidden",
        },
        performance={
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
        shadow_gates={
            "gate_set_version": 1,
            "startup_enforcement": "strict",
            "allow_advisory_influence": False,
            "allow_live_authority": False,
            "allow_policy_training_reenable": False,
            "require_domain_manifest_contracts": True,
        },
        checkpoint_every_n_steps=50,
        keep_last_n_checkpoints=1,
        dream_episode_threshold=1,
    )


def test_yaml_config_enforces_explicit_sequence_narrowing():
    config = load_config(Path("apps/reference/domains/neocortex/config"))

    assert config.neuro.sequence.inference_mode == "stateless_per_event"
    assert config.neuro.sequence.representation_training_mode == "independent_rows"
    assert config.neuro.sequence.reset_on_replay_start is True
    assert config.neuro.sequence.reset_on_symbol_switch is True
    assert config.neuro.sequence.reset_on_objective_family_switch is True
    assert config.neuro.sequence.reset_on_episode_boundary is True


def test_get_action_resets_hidden_before_each_call_in_stateless_mode(neuro_config: NeuroConfig):
    core = BrainCore(neuro_config, device="cpu")

    class _StatefulFakePPO:
        def __init__(self):
            self.hidden_counter = 9
            self.reset_masks = []
            self.num_envs = 1

        def reset_hidden(self, done_mask):
            self.reset_masks.append(np.asarray(done_mask, dtype=bool).tolist())
            self.hidden_counter = 0

        def act(self, z, deterministic=False):
            self.hidden_counter += 1
            return np.array([1]), np.array([float(self.hidden_counter)]), np.array([0.25])

    core.ppo_agent = _StatefulFakePPO()

    first = core.get_action(np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32))
    second = core.get_action(np.array([0.4, 0.3, 0.2, 0.1], dtype=np.float32))

    assert first["value"] == pytest.approx(1.0)
    assert second["value"] == pytest.approx(1.0)
    assert first["sequence_inference_mode"] == "stateless_per_event"
    assert second["sequence_inference_mode"] == "stateless_per_event"
    assert core.ppo_agent.reset_masks == [[True], [True]]


def test_reset_sequence_state_records_replay_start_reason(neuro_config: NeuroConfig):
    core = BrainCore(neuro_config, device="cpu")

    class _ResettableFakePPO:
        def __init__(self):
            self.num_envs = 1
            self.reset_masks = []

        def reset_hidden(self, done_mask):
            self.reset_masks.append(np.asarray(done_mask, dtype=bool).tolist())

    core.ppo_agent = _ResettableFakePPO()

    result = core.reset_sequence_state(reason="replay_start")

    assert result["status"] == "reset"
    assert result["reason"] == "replay_start"
    assert result["sequence_inference_mode"] == "stateless_per_event"
    assert result["sequence_resets"] == 1
    assert core.ppo_agent.reset_masks == [[True]]


def test_representation_training_rejects_sequence_batches_in_independent_rows_mode():
    ok, error = BrainCore._validate_representation_batch_ndim(
        3,
        training_mode="independent_rows",
    )

    assert ok is False
    assert error == "sequence_batch_unsupported:independent_rows"


@pytest.mark.asyncio
async def test_adapter_start_resets_sequence_state_at_replay_start(tmp_path: Path):
    adapter = object.__new__(NeocortexAdapter)
    adapter.config = SimpleNamespace(
        system=SimpleNamespace(checkpoint_dir=tmp_path),
        neuro=SimpleNamespace(
            sequence=SimpleNamespace(reset_on_replay_start=True),
        ),
    )
    adapter.brain_bridge = SimpleNamespace(
        start=AsyncMock(return_value=True),
        reset_sequence_state_async=AsyncMock(return_value={"status": "reset"}),
        load_async=AsyncMock(return_value=False),
    )
    adapter._emit_alert = MagicMock()
    adapter._validate_checkpoint_metadata = MagicMock()

    await NeocortexAdapter.start(adapter)

    adapter.brain_bridge.start.assert_awaited_once()
    adapter.brain_bridge.reset_sequence_state_async.assert_awaited_once_with(
        reason="adapter_start"
    )
