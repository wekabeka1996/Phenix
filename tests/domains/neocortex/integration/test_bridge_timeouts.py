import pytest
import asyncio
from unittest.mock import patch
import numpy as np

from apps.reference.domains.neocortex.config_models import NeuroConfig, VAEConfig, WorldModelConfig, PPOConfig
from apps.reference.domains.neocortex.logic.brain.bridge import BrainBridge


@pytest.fixture
def neuro_config():
    return NeuroConfig(
        vae=VAEConfig(input_dim=10, hidden_dims=[
                      32], latent_dim=4, learning_rate=0.001, beta=1.0, free_bits_per_dim=0.0, batch_size=32, use_mean=False, regime_aux={"enabled": False, "alpha": 1.0, "num_classes": 3, "ema_decay": 0.99, "alpha_schedule": {"start": 1.0, "end": 0.1, "steps": 1000}}),
        world_model=WorldModelConfig(
            hidden_dim=32, num_layers=1, dropout=0.0, learning_rate=0.001, sequence_length=10),
        ppo=PPOConfig(state_dim=4, action_dim=2, hidden_dims=[
                      32], reward_mode="pnl", objective_split_enforced=True, policy_training_mode="disabled", learning_rate=0.001, gamma=0.99, gae_lambda=0.95, clip_epsilon=0.2, entropy_coef=0.01, max_grad_norm=0.5, numerical_safety={"gradient_clip_threshold": 1.0, "on_invalid": "sanitize"}, rollout_length=100, num_epochs=3, minibatch_size=32),
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
            "cutover": {
                "min_real_executed_rows": 1,
                "allow_synthetic_fallback": False,
                "max_non_causal_rows": 0,
                "require_reward_methodology": True,
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
        checkpoint_every_n_steps=1000,
        keep_last_n_checkpoints=5,
        dream_episode_threshold=1,
    )


@pytest.mark.asyncio
async def test_bridge_act_async_timeout(neuro_config):
    bridge = BrainBridge(neuro_config)

    # Mock _submit to raise asyncio.TimeoutError
    async def mock_submit(*args, **kwargs):
        raise asyncio.TimeoutError("Simulated timeout")

    with patch.object(bridge, '_submit', side_effect=mock_submit):
        z = np.zeros(4, dtype=np.float32)
        with pytest.raises(RuntimeError, match="no synthetic FLAT action"):
            await bridge.act_async(z)


@pytest.mark.asyncio
async def test_bridge_encode_async_timeout(neuro_config):
    bridge = BrainBridge(neuro_config)

    async def mock_submit(*args, **kwargs):
        raise asyncio.TimeoutError("Simulated timeout")

    with patch.object(bridge, '_submit', side_effect=mock_submit):
        # Create a dummy observation
        from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
        obs = MarketObservation(
            ts=1000.0,
            mid_price=10.0,
            volatility=1.0,
            obi=0.0,
            features_vector=np.zeros(10, dtype=np.float32)
        )
        with pytest.raises(RuntimeError, match="no synthetic latent"):
            await bridge.encode_async(obs)


@pytest.mark.asyncio
async def test_bridge_train_async_timeout(neuro_config):
    bridge = BrainBridge(neuro_config)

    async def mock_submit(*args, **kwargs):
        raise asyncio.TimeoutError("Simulated timeout")

    with patch.object(bridge, '_submit', side_effect=mock_submit):
        from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
        obs = MarketObservation(ts=1000.0, mid_price=10.0, volatility=1.0,
                                obi=0.0, features_vector=np.zeros(10, dtype=np.float32))
        result = await bridge.train_async([obs])
        assert "Simulated timeout" in result.get("error", "")


def test_bridge_shutdown(neuro_config):
    bridge = BrainBridge(neuro_config)
    bridge._initialized = True
    # Test safe shutdown even if queue is not present
    bridge.shutdown()
    assert not bridge._initialized
