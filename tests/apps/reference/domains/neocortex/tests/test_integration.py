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

from apps.reference.domains.neocortex.config_models import NeocortexConfig, IngestConfig, SystemConfig, NeuroConfig, VAEConfig, PPOConfig, WorldModelConfig
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
        system=SystemConfig(
            data_dir="/tmp/neocortex_test",
            checkpoint_dir="/tmp/neocortex_test/checkpoints",
            brain_workers=1,
            queue_maxsize=100,
            log_level="DEBUG",
            log_to_file=False
        ),
        ingest=IngestConfig(
            feature_list=["rsi", "obi", "vol"],
            normalization_method="zscore",
            normalization_window=100,
            buffer_size=1000,
            min_samples_before_ready=5,  # Low for testing
            nan_strategy="zero"
        ),
        neuro=NeuroConfig(
            vae=VAEConfig(
                input_dim=3,
                hidden_dims=[16, 8],
                latent_dim=2,
                learning_rate=0.001,
                beta=1.0,
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
                learning_rate=0.001,
                gamma=0.99,
                gae_lambda=0.95,
                clip_epsilon=0.2,
                rollout_length=10,
                num_epochs=1,
                minibatch_size=4
            ),
            checkpoint_every_n_steps=100,
            keep_last_n_checkpoints=1
        )
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
    return asyncio.get_event_loop().run_until_complete(coro)


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
        for i in range(10):
            payload = {
                "timestamp": 1000.0 + i,
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
    assert timestamps == [1000.0 + i for i in range(10)]


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
        for i in range(20):
            payload = {
                "timestamp": 1000.0 + i,
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
        for i in range(10):
            payload = {
                "timestamp": float(i),
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
        system=SystemConfig(
            data_dir="/tmp/test",
            checkpoint_dir="/tmp/test/cp",
            brain_workers=1,
            queue_maxsize=10,
            log_level="INFO",
            log_to_file=False
        ),
        ingest=IngestConfig(
            feature_list=["a", "b"],
            normalization_method="zscore",
            normalization_window=10,
            buffer_size=100,
            min_samples_before_ready=2,
            nan_strategy="zero"
        ),
        neuro=NeuroConfig(
            vae=VAEConfig(
                input_dim=2,
                hidden_dims=[16],
                latent_dim=2,
                learning_rate=0.001,
                beta=1.0,
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
                learning_rate=0.001,
                gamma=0.99,
                gae_lambda=0.95,
                clip_epsilon=0.2,
                rollout_length=10,
                num_epochs=1,
                minibatch_size=2
            ),
            checkpoint_every_n_steps=10,
            keep_last_n_checkpoints=1
        )
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
        
        # Simulate events to trigger training
        for i in range(6):
            await adapter.handle_features({
                "timestamp": float(i),
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
    np.testing.assert_array_equal(restored.features_vector, obs.features_vector)

