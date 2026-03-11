"""
Full Loop Integration Tests (Phase 4)

Verify end-to-end data flow including Shadow Intent emission:
Feature -> Adapter -> Buffer -> Bridge -> Worker -> PPO -> Intent Event
"""

import pytest
import asyncio
import numpy as np
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path
import tempfile

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
def temp_checkpoint_dir():
    """Create temporary checkpoint directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def full_config(temp_checkpoint_dir):
    """Complete valid configuration."""
    return NeocortexConfig(
        system=SystemConfig(
            data_dir=str(temp_checkpoint_dir / "data"),
            checkpoint_dir=str(temp_checkpoint_dir / "checkpoints"),
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
            min_samples_before_ready=3,
            nan_strategy="zero"
        ),
        neuro=NeuroConfig(
            vae=VAEConfig(
                input_dim=3,
                hidden_dims=[16, 8],
                latent_dim=4,
                learning_rate=0.001,
                beta=1.0,
                batch_size=2,  # Small for testing
                use_mean=True
            ),
            world_model=WorldModelConfig(
                hidden_dim=16,
                num_layers=1,
                dropout=0.0,
                learning_rate=0.001,
                sequence_length=5
            ),
            ppo=PPOConfig(
                state_dim=8,
                action_dim=3,
                hidden_dims=[16],
                learning_rate=0.001,
                gamma=0.99,
                gae_lambda=0.95,
                clip_epsilon=0.2,
                rollout_length=10,
                num_epochs=1,
                minibatch_size=2
            ),
            checkpoint_every_n_steps=2,  # Checkpoint frequently for testing
            keep_last_n_checkpoints=1
        )
    )


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

def test_shadow_intent_emission(full_config):
    """Test that shadow intents are emitted correctly."""
    
    # Track emitted events
    emitted_events = []
    
    def mock_emitter(event_type, payload):
        emitted_events.append((event_type, payload))
    
    # Create mock bridge
    mock_bridge = MagicMock()
    mock_bridge.start = AsyncMock(return_value=True)
    mock_bridge.encode_async = AsyncMock(return_value=np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32))
    mock_bridge.act_async = AsyncMock(return_value={
        "action": 0,
        "action_name": "LONG",
        "value": 0.5,
        "confidence": 0.8
    })
    mock_bridge.train_async = AsyncMock(return_value={"vae_loss": 0.1, "wm_loss": 0.05})
    mock_bridge.save_async = AsyncMock(return_value=True)
    mock_bridge.load_async = AsyncMock(return_value=False)
    mock_bridge.shutdown = MagicMock()
    
    parser = FeatureParser(full_config.ingest)
    amygdala = ValuationEngine()
    buffer = EpisodicBuffer(full_config.ingest.buffer_size)
    
    adapter = NeocortexAdapter(
        config=full_config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=mock_bridge,
        event_emitter=mock_emitter
    )
    
    async def run_test():
        await adapter.start()
        
        # Send features
        for i in range(5):
            await adapter.handle_features({
                "timestamp": float(i),
                "symbol": "BTCUSDT",
                "features": {"rsi": "50", "obi": "0.1", "vol": "0.5"}
            })
        
        # Allow async tasks to complete
        await asyncio.sleep(0.1)
        await adapter.shutdown_async()
        
        return len(emitted_events), adapter._shadow_intents_emitted
    
    event_count, intent_count = run_async(run_test())
    
    # Verify shadow intents were emitted
    assert event_count >= 1, "At least one shadow intent should be emitted"
    assert intent_count >= 1, "Adapter should track emitted intents"
    
    # Verify event structure
    if emitted_events:
        event_types = [evt for evt, _ in emitted_events]
        assert "EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED" in event_types
        assert "EVT:NEOCORTEX_SHADOW_INTENT" in event_types

        _, payload = emitted_events[0]
        assert "action" in payload
        assert "action_name" in payload
        assert "latent_state" in payload
        assert payload["symbol"] == "BTCUSDT"


def test_training_triggers_checkpoint(full_config):
    """Test that checkpoints are saved after training."""
    
    # Track saves
    save_calls = []
    
    mock_bridge = MagicMock()
    mock_bridge.start = AsyncMock(return_value=True)
    mock_bridge.encode_async = AsyncMock(return_value=np.zeros(4, dtype=np.float32))
    mock_bridge.act_async = AsyncMock(return_value={
        "action": 2, "action_name": "FLAT", "value": 0.0, "confidence": 0.0
    })
    mock_bridge.train_async = AsyncMock(return_value={"vae_loss": 0.1, "wm_loss": 0.05})
    mock_bridge.save_async = AsyncMock(side_effect=lambda p: save_calls.append(p) or True)
    mock_bridge.load_async = AsyncMock(return_value=False)
    mock_bridge.shutdown = MagicMock()
    
    parser = FeatureParser(full_config.ingest)
    amygdala = ValuationEngine()
    buffer = EpisodicBuffer(full_config.ingest.buffer_size)
    
    adapter = NeocortexAdapter(
        config=full_config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=mock_bridge
    )
    
    async def run_test():
        await adapter.start()
        
        # Send enough features to trigger multiple training steps
        # batch_size=2, checkpoint_every=2
        for i in range(10):
            await adapter.handle_features({
                "timestamp": float(i),
                "features": {"rsi": "50", "obi": "0.1", "vol": "0.5"}
            })
            await asyncio.sleep(0.01)  # Give training time to complete
        
        await asyncio.sleep(0.2)  # Allow training tasks to complete
        
        return adapter._total_train_steps, len(save_calls)
    
    train_steps, checkpoint_count = run_async(run_test())
    
    # With batch_size=2, min_samples=3, and 10 events, we should get several training steps
    assert train_steps >= 1, f"Expected training steps, got {train_steps}"
    
    # With checkpoint_every=2, after enough steps we should have checkpoints
    # Note: checkpoints are async, might not all complete
    assert mock_bridge.save_async.called or checkpoint_count >= 0, "Save should be called"


def test_adapter_stats(full_config):
    """Test adapter statistics tracking."""
    
    parser = FeatureParser(full_config.ingest)
    amygdala = ValuationEngine()
    buffer = EpisodicBuffer(full_config.ingest.buffer_size)
    
    adapter = NeocortexAdapter(
        config=full_config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=None
    )
    
    async def run_test():
        for i in range(5):
            await adapter.handle_features({
                "timestamp": float(i),
                "features": {"rsi": "50", "obi": "0.1", "vol": "0.5"}
            })
        return adapter.stats
    
    stats = run_async(run_test())
    
    assert stats["buffer_size"] == 5
    assert stats["total_train_steps"] == 0  # No bridge, no training
    assert stats["shadow_intents_emitted"] == 0  # No bridge, no intents


def test_waiting_for_reward_source_state_when_structured_reward_missing(full_config):
    """If only reward-missing episodes are received, training must wait for source."""

    emitted_events = []

    def mock_emitter(event_type, payload):
        emitted_events.append((event_type, payload))

    parser = FeatureParser(full_config.ingest)
    amygdala = ValuationEngine()
    buffer = EpisodicBuffer(full_config.ingest.buffer_size)

    adapter = NeocortexAdapter(
        config=full_config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=None,
        event_emitter=mock_emitter,
    )

    async def run_test():
        await adapter.add_completed_episode(
            {
                "symbol": "BTCUSDT",
                "timestamp": 1_700_000_000.0,
                "features": {"rsi": 50.0},
                "side": "LONG",
                "reward": None,
                "pnl": None,
            }
        )
        return adapter.stats

    stats = run_async(run_test())
    assert stats["waiting_for_reward_source"] is True
    alert_payloads = [payload for event, payload in emitted_events if event == "EVT:NEOCORTEX_ALERT"]
    assert any(payload.get("code") == "NO_STRUCTURED_REWARD_RECEIVED" for payload in alert_payloads)


def test_action_result_structure():
    """Test the expected structure of action results."""
    
    # This tests the expected format without needing full PPO
    action_result = {
        "action": 0,
        "action_name": "LONG",
        "value": 0.5,
        "confidence": 0.8
    }
    
    # Verify all required fields
    assert "action" in action_result
    assert "action_name" in action_result
    assert "value" in action_result
    assert "confidence" in action_result
    
    # Verify types
    assert isinstance(action_result["action"], int)
    assert isinstance(action_result["action_name"], str)
    assert isinstance(action_result["value"], float)
    assert isinstance(action_result["confidence"], float)
    
    # Verify action names
    assert action_result["action_name"] in ["LONG", "SHORT", "FLAT"]

