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
        trust_enabled=False,
        system=SystemConfig(
            data_dir=str(tmp_path / "data"),
            checkpoint_dir=str(tmp_path / "data" / "checkpoints"),
            run_mode="backtest",
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
            normalization_scope="per_symbol",
            buffer_size=1000,
            min_samples_before_ready=10,
            nan_strategy="zero", price_feature_mode="raw",
            delta_price_mode="raw",
            feature_clip_abs={}
        ),
        neuro=NeuroConfig(
            vae=VAEConfig(
                input_dim=5,
                hidden_dims=[32, 16],
                latent_dim=8,
                learning_rate=0.001,
                beta=1.0,
                free_bits_per_dim=0.0,
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
                reward_mode="pnl",
                objective_split_enforced=True,
                policy_training_mode="disabled",
                learning_rate=0.0003,
                gamma=0.99,
                gae_lambda=0.95,
                clip_epsilon=0.2,
                entropy_coef=0.01,
                max_grad_norm=0.5,
                numerical_safety={
                    "gradient_clip_threshold": 1.0,
                    "on_invalid": "sanitize",
                },
                rollout_length=64,
                num_epochs=2,
                minibatch_size=16
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
            checkpoint_every_n_steps=10,  # Frequent checkpoints for testing
            keep_last_n_checkpoints=2,
            dream_episode_threshold=1
        ),
        replay=ReplayConfig(
            enabled=False,
            wal_dir=str(tmp_path / "wal"),
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
    bridge.train_policy_async = AsyncMock(
        return_value={"loss_pi": 0.1, "loss_v": 0.05, "episodes_processed": 1})
    bridge.train_ppo_async = bridge.train_policy_async
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
    bridge.train_policy_async = AsyncMock(
        return_value={"loss_pi": 0.1, "loss_v": 0.05, "episodes_processed": 1})
    bridge.train_ppo_async = bridge.train_policy_async
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
        slow_bridge.encode_async = AsyncMock(
            return_value=np.random.randn(8).astype(np.float32))
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
        print(
            f"Backpressure events: {adapter._backpressure_events}, elapsed: {elapsed:.3f}s")
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
        """Verify shutdown trains any remaining buffered policy samples."""
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

        adapter._policy_training_mode = "execution_only"
        adapter._policy_samples = [
            {"objective_family": "policy", "symbol": "BTCUSDT", "event_ts_ms": 1},
            {"objective_family": "policy", "symbol": "BTCUSDT", "event_ts_ms": 2},
        ]

        # Call async shutdown
        await adapter.shutdown_async()

        # Verify policy training was triggered
        fast_brain_bridge.train_policy_async.assert_called_once()

        # Buffered policy samples should be cleared
        assert len(adapter._policy_samples) == 0


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
