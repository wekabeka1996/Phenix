"""
Integration Tests

Verify end-to-end data flow:
Adapter -> Buffer -> Bridge -> Worker -> Result

Note: Uses asyncio.run() to avoid pytest-asyncio dependency.
"""

import pytest
import asyncio
import numpy as np
from unittest.mock import MagicMock, AsyncMock

from apps.reference.domains.neocortex.config_models import NeocortexConfig, IngestConfig, SystemConfig, NeuroConfig, VAEConfig, PPOConfig, WorldModelConfig, ReplayConfig
from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser
from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
from apps.reference.domains.neocortex.logic.amygdala.valuation import ValuationEngine
from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def full_config():
    """Complete valid configuration."""
    return NeocortexConfig(
        trust_enabled=False,
        system=SystemConfig(
            data_dir="/tmp/neocortex_test",
            checkpoint_dir="/tmp/neocortex_test/checkpoints",
            run_mode="backtest",
            rng_seed=42,
            brain_workers=1,
            queue_maxsize=100,
            log_level="DEBUG",
            log_to_file=False
        ),
        ingest=IngestConfig(
            feature_list=["rsi", "obi", "vol"],
            normalization_method="zscore",
            normalization_window=100,
            normalization_scope="per_symbol",
            buffer_size=1000,
            min_samples_before_ready=5,  # Low for testing
            nan_strategy="zero",
            price_feature_mode="raw",
            delta_price_mode="raw",
            feature_clip_abs={}
        ),
        neuro=NeuroConfig(
            vae=VAEConfig(
                input_dim=3,
                hidden_dims=[16, 8],
                latent_dim=2,
                learning_rate=0.001,
                beta=1.0,
                free_bits_per_dim=0.0,
                batch_size=4,  # Small for testing
                use_mean=True
            ),
            world_model=WorldModelConfig(
                hidden_dim=16,  # Minimum is 16
                num_layers=1,
                dropout=0.0,
                learning_rate=0.001,
                sequence_length=5
            ),
            ppo=PPOConfig(
                state_dim=4,
                action_dim=3,
                hidden_dims=[16],
                reward_mode="pnl",
                objective_split_enforced=True,
                policy_training_mode="disabled",
                learning_rate=0.001,
                gamma=0.99,
                gae_lambda=0.95,
                clip_epsilon=0.2,
                entropy_coef=0.01,
                max_grad_norm=0.5,
                numerical_safety={
                    "gradient_clip_threshold": 1.0,
                    "on_invalid": "sanitize",
                },
                rollout_length=10,
                num_epochs=1,
                minibatch_size=4
            ),
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
            checkpoint_every_n_steps=100,
            keep_last_n_checkpoints=1,
            dream_episode_threshold=1,
        ),
        replay=ReplayConfig(
            enabled=False,
            wal_dir="/tmp/neocortex_test/wal",
            poll_interval=0.1,
            feature_missing_timestamp_policy="fail_closed",
        ),
        authority={
            "mode": "shadow",
            "deadline_ms": 10,
            "fallback_policy": "baseline_yaml",
            "max_inflight_per_symbol": 1,
            "modulation_allowlist": ["decision_making.signal_threshold_bias"],
            "signal_threshold_bias_bounds": [-0.1, 0.1],
            "cooldown_mult_bounds": [1.0, 3.0],
        },
        evidence_capture={
            "mode": "disabled",
            "collect_observation": False,
            "collect_authority_request": False,
            "collect_authority_response": False,
            "emit_shadow_decision_logged": False,
        },
    )


@pytest.fixture
def parser(full_config):
    return FeatureParser(full_config.ingest)


@pytest.fixture
def buffer(full_config):
    return EpisodicBuffer(full_config.ingest.buffer_size)


@pytest.fixture
def amygdala():
    return ValuationEngine()


# =============================================================================
# HELPER
# =============================================================================

def run_async(coro):
    """Run async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# TESTS
# =============================================================================

def test_adapter_buffer_integration(full_config, parser, amygdala, buffer):
    """Test that adapter correctly populates buffer."""

    adapter = NeocortexAdapter(
        config=full_config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=None  # No bridge for this test
    )

    async def run_test():
        # Simulate 10 feature events
        base_ts = 1_700_000_000.0
        for i in range(10):
            payload = {
                "timestamp": base_ts + float(i),
                "symbol": "BTCUSDT",
                "features": {
                    "rsi": str(50 + i),
                    "obi": "0.1",
                    "vol": "0.5"
                }
            }
            await adapter.handle_features(payload)

        return len(buffer)

    result = run_async(run_test())

    # Verify buffer populated
    assert result == 10

    # Verify order preserved
    batch = buffer.get_batch(10)
    timestamps = [item[0].ts for item in batch]
    assert timestamps == [1_700_000_000_000.0 +
                          (i * 1000.0) for i in range(10)]


def test_training_trigger_without_bridge(full_config, parser, amygdala, buffer):
    """Test that training is gracefully skipped when no bridge is available."""

    adapter = NeocortexAdapter(
        config=full_config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=None
    )

    async def run_test():
        # Simulate enough events to trigger training
        base_ts = 1_700_000_100.0
        for i in range(20):
            payload = {
                "timestamp": base_ts + float(i),
                "symbol": "BTCUSDT",
                "features": {"rsi": "50", "obi": "0.1", "vol": "0.5"}
            }
            await adapter.handle_features(payload)
        return adapter._total_train_steps

    result = run_async(run_test())

    # No crash, training was simply skipped
    assert result == 0


def test_batch_extraction_correct_shape(full_config, parser, amygdala, buffer):
    """Test that batch extracted from buffer has correct numpy shape."""

    adapter = NeocortexAdapter(
        config=full_config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=None
    )

    async def run_test():
        # Add observations
        base_ts = 1_700_000_200.0
        for i in range(10):
            payload = {
                "timestamp": base_ts + float(i),
                "symbol": "BTCUSDT",
                "features": {"rsi": "50", "obi": "0.1", "vol": "0.5"}
            }
            await adapter.handle_features(payload)

    run_async(run_test())

    # Manually extract batch like adapter.train_async would
    batch_items = buffer.get_batch(4)
    batch_obs = [item[0] for item in batch_items]

    # Stack into numpy
    batch_data = np.stack([obs.features_vector for obs in batch_obs])

    assert batch_data.shape == (4, 3)  # 4 samples, 3 features
    assert batch_data.dtype == np.float32


def test_mock_bridge_training():
    """Test training flow with mocked bridge."""

    # Create mock bridge
    mock_bridge = MagicMock()
    mock_bridge.train_async = AsyncMock(return_value={
        "vae_loss": 0.5,
        "wm_loss": 0.1
    })
    mock_bridge.start = AsyncMock(return_value=True)
    mock_bridge.shutdown = MagicMock()

    # Create minimal config
    config = NeocortexConfig(
        trust_enabled=False,
        system=SystemConfig(
            data_dir="/tmp/test",
            checkpoint_dir="/tmp/test/cp",
            run_mode="backtest",
            rng_seed=42,
            brain_workers=1,
            queue_maxsize=10,
            log_level="INFO",
            log_to_file=False
        ),
        ingest=IngestConfig(
            feature_list=["a", "b"],
            normalization_method="zscore",
            normalization_window=10,
            normalization_scope="per_symbol",
            buffer_size=100,
            min_samples_before_ready=2,
            nan_strategy="zero",
            price_feature_mode="raw",
            delta_price_mode="raw",
            feature_clip_abs={}
        ),
        neuro=NeuroConfig(
            vae=VAEConfig(
                input_dim=2,
                hidden_dims=[16],
                latent_dim=2,
                learning_rate=0.001,
                beta=1.0,
                free_bits_per_dim=0.0,
                batch_size=2,
                use_mean=True
            ),
            world_model=WorldModelConfig(
                hidden_dim=16,
                num_layers=1,
                dropout=0.0,
                learning_rate=0.001,
                sequence_length=2
            ),
            ppo=PPOConfig(
                state_dim=2,
                action_dim=2,
                hidden_dims=[16],
                reward_mode="pnl",
                objective_split_enforced=True,
                policy_training_mode="disabled",
                learning_rate=0.001,
                gamma=0.99,
                gae_lambda=0.95,
                clip_epsilon=0.2,
                entropy_coef=0.01,
                max_grad_norm=0.5,
                numerical_safety={
                    "gradient_clip_threshold": 1.0,
                    "on_invalid": "sanitize",
                },
                rollout_length=10,
                num_epochs=1,
                minibatch_size=2
            ),
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
            checkpoint_every_n_steps=10,
            keep_last_n_checkpoints=1,
            dream_episode_threshold=1,
        ),
        replay=ReplayConfig(
            enabled=False,
            wal_dir="/tmp/test/wal",
            poll_interval=0.1,
            feature_missing_timestamp_policy="fail_closed",
        ),
        authority={
            "mode": "shadow",
            "deadline_ms": 10,
            "fallback_policy": "baseline_yaml",
            "max_inflight_per_symbol": 1,
            "modulation_allowlist": ["decision_making.signal_threshold_bias"],
            "signal_threshold_bias_bounds": [-0.1, 0.1],
            "cooldown_mult_bounds": [1.0, 3.0],
        },
        evidence_capture={
            "mode": "disabled",
            "collect_observation": False,
            "collect_authority_request": False,
            "collect_authority_response": False,
            "emit_shadow_decision_logged": False,
        },
    )

    parser = FeatureParser(config.ingest)
    amygdala = ValuationEngine()
    buffer = EpisodicBuffer(config.ingest.buffer_size)

    adapter = NeocortexAdapter(
        config=config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=mock_bridge
    )

    async def run_test():
        # Start adapter (initializes bridge)
        await adapter.start()
        base_ts = 1_700_000_300.0

        # Simulate events to trigger training
        for i in range(6):
            await adapter.handle_features({
                "timestamp": base_ts + float(i),
                "symbol": "BTCUSDT",
                "features": {"a": "1.0", "b": "2.0"}
            })

        # Allow async training task to complete
        await asyncio.sleep(0.1)

        return adapter._total_train_steps, mock_bridge.train_async.called

    train_steps, training_called = run_async(run_test())

    # Verify training was triggered
    assert training_called, "train_async should have been called"
    assert train_steps >= 1


def test_observation_picklable():
    """Verify MarketObservation can be pickled for multiprocessing."""
    import pickle

    obs = MarketObservation(
        ts=100.0,
        mid_price=50000.0,
        volatility=0.1,
        obi=0.5,
        features_vector=np.array([1.0, 2.0, 3.0], dtype=np.float32)
    )

    # Pickle and unpickle
    data = pickle.dumps(obs)
    restored = pickle.loads(data)

    assert restored.ts == obs.ts
    assert restored.mid_price == obs.mid_price
    np.testing.assert_array_equal(
        restored.features_vector, obs.features_vector)
