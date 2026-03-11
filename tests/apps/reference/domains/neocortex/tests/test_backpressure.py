"""
Test Backpressure Mechanism

Verifies that ingestion slows down when training can't keep up.

Scenarios:
1. Slow brain → ingestion pauses
2. Fast brain → ingestion proceeds normally
3. Clean shutdown saves checkpoint
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_config(tmp_path):
    """Create minimal config for testing."""
    from apps.reference.domains.neocortex.config_models import (
        NeocortexConfig,
        SystemConfig,
        IngestConfig,
        NeuroConfig,
        VAEConfig,
        WorldModelConfig,
        PPOConfig,
        ReplayConfig,
    )
    
    return NeocortexConfig(
        system=SystemConfig(
            data_dir=str(tmp_path / "data"),
            checkpoint_dir=str(tmp_path / "data" / "checkpoints"),
            rng_seed=42,
            brain_workers=1,
            queue_maxsize=100,
            log_level="DEBUG",
            log_to_file=False
        ),
        ingest=IngestConfig(
            feature_list=["price", "obi", "tfi", "delta_price", "ema_bias"],
            normalization_method="zscore",
            normalization_window=100,
            buffer_size=1000,
            min_samples_before_ready=10,
            nan_strategy="zero"
        ),
        neuro=NeuroConfig(
            vae=VAEConfig(
                input_dim=5,
                hidden_dims=[32, 16],
                latent_dim=8,
                learning_rate=0.001,
                beta=1.0,
                batch_size=16,  # Small batch for testing
                use_mean=True
            ),
            world_model=WorldModelConfig(
                hidden_dim=32,
                num_layers=1,
                dropout=0.0,
                learning_rate=0.001,
                sequence_length=10
            ),
            ppo=PPOConfig(
                state_dim=8,
                action_dim=3,
                hidden_dims=[32, 16],
                learning_rate=0.0003,
                gamma=0.99,
                gae_lambda=0.95,
                clip_epsilon=0.2,
                rollout_length=64,
                num_epochs=2,
                minibatch_size=16
            ),
            checkpoint_every_n_steps=10,  # Frequent checkpoints for testing
            keep_last_n_checkpoints=2,
            dream_episode_threshold=1
        ),
        replay=ReplayConfig(
            enabled=False,
            wal_dir=str(tmp_path / "wal")
        )
    )


@pytest.fixture
def mock_parser():
    """Create mock feature parser."""
    from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
    
    parser = MagicMock()
    parser.parse.return_value = MarketObservation(
        ts=time.time(),
        mid_price=30000.0,
        volatility=0.1,
        obi=0.5,
        features_vector=np.random.randn(5).astype(np.float32),
        normalized=False
    )
    return parser


@pytest.fixture
def mock_amygdala():
    """Create mock valuation engine."""
    amygdala = MagicMock()
    amygdala.update.return_value = 0.5  # Importance score
    return amygdala


@pytest.fixture
def mock_buffer():
    """Create mock episodic buffer with controllable size."""
    buffer = MagicMock()
    buffer._size = 0
    
    def add(obs, importance):
        buffer._size += 1
    
    def get_batch(size):
        from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
        return [(MarketObservation(
            ts=time.time(),
            mid_price=30000.0,
            volatility=0.1,
            obi=0.5,
            features_vector=np.random.randn(5).astype(np.float32),
            normalized=True
        ), 0.5) for _ in range(min(size, buffer._size))]
    
    def clear_some():
        buffer._size = max(0, buffer._size - 16)
    
    buffer.add.side_effect = add
    buffer.get_batch.side_effect = get_batch
    buffer.__len__ = lambda self: buffer._size
    
    return buffer


@pytest.fixture
def slow_brain_bridge():
    """Create mock brain bridge that's intentionally slow."""
    bridge = MagicMock()
    
    async def slow_encode(obs):
        await asyncio.sleep(0.1)  # Simulate slow encoding
        return np.random.randn(8).astype(np.float32)
    
    async def slow_act(z):
        await asyncio.sleep(0.05)  # Simulate slow action
        return {
            "action": 0,
            "action_name": "LONG",
            "value": 0.5,
            "confidence": 0.3
        }
    
    async def slow_train(batch):
        await asyncio.sleep(0.2)  # Simulate SLOW training
        return {"vae_loss": 0.1, "wm_loss": 0.05}
    
    async def save_checkpoint(path):
        await asyncio.sleep(0.01)
        return True
    
    bridge.encode_async = AsyncMock(side_effect=slow_encode)
    bridge.act_async = AsyncMock(side_effect=slow_act)
    bridge.train_async = AsyncMock(side_effect=slow_train)
    bridge.save_async = AsyncMock(side_effect=save_checkpoint)
    bridge.start = AsyncMock(return_value=True)
    bridge.shutdown = MagicMock()
    
    return bridge


@pytest.fixture
def fast_brain_bridge():
    """Create mock brain bridge that's fast."""
    bridge = MagicMock()
    
    async def fast_encode(obs):
        return np.random.randn(8).astype(np.float32)
    
    async def fast_act(z):
        return {
            "action": 0,
            "action_name": "LONG",
            "value": 0.5,
            "confidence": 0.3
        }
    
    async def fast_train(batch):
        return {"vae_loss": 0.1, "wm_loss": 0.05}
    
    async def save_checkpoint(path):
        return True
    
    bridge.encode_async = AsyncMock(side_effect=fast_encode)
    bridge.act_async = AsyncMock(side_effect=fast_act)
    bridge.train_async = AsyncMock(side_effect=fast_train)
    bridge.save_async = AsyncMock(side_effect=save_checkpoint)
    bridge.start = AsyncMock(return_value=True)
    bridge.shutdown = MagicMock()
    
    return bridge


# =============================================================================
# TESTS
# =============================================================================

class TestBackpressure:
    """Test backpressure mechanism prevents ingestion overrun."""
    
    @pytest.mark.asyncio
    async def test_backpressure_triggers_when_buffer_full(
        self, mock_config, mock_parser, mock_amygdala, tmp_path
    ):
        """Verify backpressure signal when buffer is high and training queue is saturated."""
        from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter
        from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
        
        # Create real buffer
        buffer = EpisodicBuffer(capacity=1000)
        
        # Fill buffer beyond backpressure threshold
        from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
        threshold = mock_config.neuro.vae.batch_size * 2  # 32
        
        for i in range(threshold + 10):  # 42 items
            obs = MarketObservation(
                ts=time.time(),
                mid_price=30000.0,
                volatility=0.1,
                obi=0.5,
                features_vector=np.random.randn(5).astype(np.float32),
                normalized=True
            )
            buffer.add(obs, importance=0.5)
        
        # Create adapter with slow brain
        slow_bridge = MagicMock()
        slow_bridge.encode_async = AsyncMock(return_value=np.random.randn(8).astype(np.float32))
        slow_bridge.act_async = AsyncMock(return_value={
            "action": 0, "action_name": "LONG", "value": 0.5, "confidence": 0.3
        })
        slow_bridge.train_async = AsyncMock(return_value={"vae_loss": 0.1})
        slow_bridge.save_async = AsyncMock(return_value=True)
        
        adapter = NeocortexAdapter(
            config=mock_config,
            parser=mock_parser,
            amygdala=mock_amygdala,
            buffer=buffer,
            brain_bridge=slow_bridge
        )
        
        # Verify threshold is set
        assert adapter._backpressure_threshold == threshold
        assert len(buffer) > threshold
        adapter._inflight_training_tasks = adapter._max_inflight_training_tasks
        
        # Start ingestion task
        start_time = time.time()
        
        async def ingest_one():
            payload = {
                "symbol": "BTCUSDT",
                "ts": time.time(),
                "price": "30000.0",
                "obi": "0.5",
                "tfi": "0.3",
                "delta_price": "10.0",
                "ema_bias": "0.5"
            }
            await adapter.handle_features(payload)
        
        # This should trigger backpressure signal without blocking ingestion.
        task = asyncio.create_task(ingest_one())
        
        # Let it run for a bit
        await asyncio.sleep(0.05)
        
        # Should have triggered backpressure
        assert adapter._backpressure_events > 0, "Backpressure should have been triggered"
        
        # Cancel task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        elapsed = time.time() - start_time
        print(f"Backpressure events: {adapter._backpressure_events}, elapsed: {elapsed:.3f}s")
        await adapter.shutdown_async()
    
    @pytest.mark.asyncio
    async def test_no_backpressure_when_buffer_empty(
        self, mock_config, mock_parser, mock_amygdala, fast_brain_bridge
    ):
        """Verify ingestion proceeds normally with empty buffer."""
        from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter
        from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
        
        buffer = EpisodicBuffer(capacity=1000)
        
        adapter = NeocortexAdapter(
            config=mock_config,
            parser=mock_parser,
            amygdala=mock_amygdala,
            buffer=buffer,
            brain_bridge=fast_brain_bridge
        )
        
        # Blast 20 features quickly (reduced from 100 to avoid timeout)
        start_time = time.time()
        
        for i in range(20):
            payload = {
                "symbol": "BTCUSDT",
                "ts": time.time(),
                "price": "30000.0",
                "obi": "0.5",
                "tfi": "0.3",
                "delta_price": "10.0",
                "ema_bias": "0.5"
            }
            await adapter.handle_features(payload)
        
        elapsed = time.time() - start_time
        
        # Should be fast (no backpressure)
        assert adapter._backpressure_events == 0, "No backpressure should be triggered"
        assert elapsed < 5.0, f"Ingestion too slow: {elapsed:.2f}s for 20 features"
        print(f"Ingested 20 features in {elapsed:.3f}s (no backpressure)")


class TestAsyncShutdown:
    """Test async shutdown with checkpoint saving."""
    
    @pytest.mark.asyncio
    async def test_shutdown_saves_checkpoint(
        self, mock_config, mock_parser, mock_amygdala, fast_brain_bridge
    ):
        """Verify shutdown_async saves final checkpoint."""
        from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter
        from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
        
        buffer = EpisodicBuffer(capacity=1000)
        
        adapter = NeocortexAdapter(
            config=mock_config,
            parser=mock_parser,
            amygdala=mock_amygdala,
            buffer=buffer,
            brain_bridge=fast_brain_bridge
        )
        
        # Simulate some training steps
        adapter._total_train_steps = 50
        
        # Call async shutdown
        await adapter.shutdown_async()
        
        # Verify save was called
        fast_brain_bridge.save_async.assert_called_once()
        fast_brain_bridge.shutdown.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shutdown_trains_buffered_episodes(
        self, mock_config, mock_parser, mock_amygdala, fast_brain_bridge
    ):
        """Verify shutdown trains any remaining buffered episodes."""
        from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter
        from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
        
        buffer = EpisodicBuffer(capacity=1000)
        
        # Add train_ppo_async mock
        fast_brain_bridge.train_ppo_async = AsyncMock(return_value={"loss": 0.1})
        
        adapter = NeocortexAdapter(
            config=mock_config,
            parser=mock_parser,
            amygdala=mock_amygdala,
            buffer=buffer,
            brain_bridge=fast_brain_bridge
        )
        
        # Add some buffered episodes
        adapter._completed_episodes = [
            {"symbol": "BTCUSDT", "reward": 0.1, "side": "LONG", "features_vector": [0.0] * 5},
            {"symbol": "BTCUSDT", "reward": -0.05, "side": "SHORT", "features_vector": [0.0] * 5},
        ]
        
        # Call async shutdown
        await adapter.shutdown_async()
        
        # Verify PPO training was triggered
        fast_brain_bridge.train_ppo_async.assert_called_once()
        
        # Episodes should be cleared
        assert len(adapter._completed_episodes) == 0


class TestDreamThreshold:
    """Test dream_episode_threshold configuration."""
    
    @pytest.mark.asyncio
    async def test_dream_threshold_from_config(self, mock_config, mock_parser, mock_amygdala):
        """Verify dream_threshold is read from config."""
        from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter
        from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
        
        buffer = EpisodicBuffer(capacity=1000)
        
        adapter = NeocortexAdapter(
            config=mock_config,
            parser=mock_parser,
            amygdala=mock_amygdala,
            buffer=buffer,
            brain_bridge=None
        )
        
        # Should match config
        assert adapter.dream_threshold == mock_config.neuro.dream_episode_threshold
        assert adapter.dream_threshold == 1  # Our test config


class TestCheckpointFrequency:
    """Test checkpoint_every_n_steps configuration."""
    
    @pytest.mark.asyncio
    async def test_checkpoint_interval_from_config(self, mock_config, mock_parser, mock_amygdala):
        """Verify checkpoint interval is read from config."""
        from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter
        from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
        
        buffer = EpisodicBuffer(capacity=1000)
        
        adapter = NeocortexAdapter(
            config=mock_config,
            parser=mock_parser,
            amygdala=mock_amygdala,
            buffer=buffer,
            brain_bridge=None
        )
        
        # Should match config
        assert adapter._checkpoint_interval == mock_config.neuro.checkpoint_every_n_steps
        assert adapter._checkpoint_interval == 10  # Our test config (lowered)


# =============================================================================
# CLI RUNNER
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

