"""
Simulation / Stress Tests

Long-running simulation to verify:
1. Memory stability (no leaks in EpisodicBuffer)
2. Checkpoints are created periodically
3. Shadow intents are generated
4. No BrokenProcessPool errors
"""

import pytest
import asyncio
import numpy as np
import gc
import sys
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path
import tempfile

from apps.reference.domains.neocortex.config_models import NeocortexConfig, IngestConfig, SystemConfig, NeuroConfig, VAEConfig, PPOConfig, WorldModelConfig
from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser
from apps.reference.domains.neocortex.logic.amygdala.valuation import ValuationEngine
from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter

BASE_TS = 1_700_100_000.0


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def stress_config(temp_dir):
    """Configuration for stress testing."""
    return NeocortexConfig(
        system=SystemConfig(
            data_dir=str(temp_dir / "data"),
            checkpoint_dir=str(temp_dir / "checkpoints"),
            brain_workers=1,
            queue_maxsize=100,
            log_level="WARNING",  # Reduce log spam
            log_to_file=False
        ),
        ingest=IngestConfig(
            feature_list=["f1", "f2", "f3", "f4", "f5"],
            normalization_method="zscore",
            normalization_window=100,
            buffer_size=500,  # Limited for memory testing
            min_samples_before_ready=10,
            nan_strategy="zero"
        ),
        neuro=NeuroConfig(
            vae=VAEConfig(
                input_dim=5,
                hidden_dims=[16],
                latent_dim=4,
                learning_rate=0.001,
                beta=1.0,
                batch_size=16,
                use_mean=True
            ),
            world_model=WorldModelConfig(
                hidden_dim=16,
                num_layers=1,
                dropout=0.0,
                learning_rate=0.001,
                sequence_length=8
            ),
            ppo=PPOConfig(
                state_dim=8,
                action_dim=3,
                hidden_dims=[16],
                learning_rate=0.001,
                gamma=0.99,
                gae_lambda=0.95,
                clip_epsilon=0.2,
                rollout_length=32,
                num_epochs=1,
                minibatch_size=8
            ),
            checkpoint_every_n_steps=10,
            keep_last_n_checkpoints=3
        )
    )


# =============================================================================
# HELPER
# =============================================================================

def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def generate_random_walk_tick(t: int, prev_price: float, num_features: int = 5) -> dict:
    """Generate a random walk market tick."""
    # Random walk for price
    price_change = np.random.randn() * 0.01  # 1% volatility
    new_price = prev_price * (1 + price_change)
    
    # Generate random features
    features = {f"f{i+1}": str(np.random.randn()) for i in range(num_features)}
    
    ts = BASE_TS + float(t)
    return {
        "timestamp": ts,
        "ts": ts,
        "event_ts_ms": int(round(ts * 1000.0)),
        "symbol": "SIMULATED",
        "mid_price": str(new_price),
        "features": features,
        "reward_signal": str(np.random.randn() * 0.1)  # Small random reward
    }


# =============================================================================
# TESTS
# =============================================================================

def test_buffer_memory_stability(stress_config):
    """
    Verify EpisodicBuffer memory doesn't grow unbounded.
    
    Test: Add 2x capacity items, verify memory usage is stable.
    """
    from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
    
    buffer = EpisodicBuffer(capacity=500)
    
    # Force garbage collection and get baseline
    gc.collect()
    
    # Add 1000 items (2x capacity)
    for i in range(1000):
        obs = MarketObservation(
            ts=float(i),
            mid_price=100.0,
            volatility=0.1,
            obi=0.0,
            features_vector=np.random.randn(5).astype(np.float32)
        )
        buffer.add(obs, 1.0)
    
    # Buffer should cap at 500
    assert len(buffer) == 500, f"Buffer should cap at 500, got {len(buffer)}"
    
    # Verify oldest items were evicted (FIFO)
    batch = buffer.get_batch(500)
    timestamps = [item[0].ts for item in batch]
    assert min(timestamps) == 500.0, f"Oldest should be 500, got {min(timestamps)}"
    assert max(timestamps) == 999.0, f"Newest should be 999, got {max(timestamps)}"


def test_simulation_1000_ticks(stress_config):
    """
    Run 1000 tick simulation with mocked bridge.
    Verify:
    - No crashes
    - Shadow intents generated
    - Checkpoints triggered
    - Training executed
    """
    
    emitted_events = []
    save_count = [0]
    train_count = [0]
    
    def mock_emitter(event_type, payload):
        emitted_events.append((event_type, payload))
    
    mock_bridge = MagicMock()
    mock_bridge.start = AsyncMock(return_value=True)
    mock_bridge.encode_async = AsyncMock(return_value=np.random.randn(4).astype(np.float32))
    mock_bridge.act_async = AsyncMock(return_value={
        "action": np.random.randint(0, 3),
        "action_name": ["LONG", "SHORT", "FLAT"][np.random.randint(0, 3)],
        "value": np.random.randn(),
        "confidence": np.random.randn()
    })
    
    async def mock_train(batch):
        train_count[0] += 1
        await asyncio.sleep(0.001)  # Simulate small delay
        return {"vae_loss": np.random.rand(), "wm_loss": np.random.rand()}
    
    mock_bridge.train_async = AsyncMock(side_effect=mock_train)
    
    async def mock_save(path):
        save_count[0] += 1
        return True
    
    mock_bridge.save_async = AsyncMock(side_effect=mock_save)
    mock_bridge.load_async = AsyncMock(return_value=False)
    mock_bridge.shutdown = MagicMock()
    
    parser = FeatureParser(stress_config.ingest)
    amygdala = ValuationEngine()
    buffer = EpisodicBuffer(stress_config.ingest.buffer_size)
    
    adapter = NeocortexAdapter(
        config=stress_config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=mock_bridge,
        event_emitter=mock_emitter
    )
    
    async def run_simulation():
        await adapter.start()
        
        prev_price = 100.0
        
        for t in range(1000):
            tick = generate_random_walk_tick(t, prev_price, num_features=5)
            prev_price = float(tick["mid_price"])
            
            await adapter.handle_features(tick)
            
            # Yield to allow async training to process
            if t % 100 == 0:
                await asyncio.sleep(0.01)
        
        # Final wait for async tasks
        await asyncio.sleep(0.1)
        await adapter.shutdown_async()
        
        return adapter.stats
    
    stats = run_async(run_simulation())
    
    # Assertions
    assert stats["buffer_size"] == 500, f"Buffer should cap at 500, got {stats['buffer_size']}"
    assert stats["shadow_intents_generated"] >= 900, \
        f"Expected ~1000 generated shadow intents, got {stats['shadow_intents_generated']}"
    assert stats["shadow_intents_emitted"] >= 90, \
        f"Expected decimated emissions, got {stats['shadow_intents_emitted']}"
    assert stats["total_train_steps"] >= 5, \
        f"Expected training to occur, got {stats['total_train_steps']}"
    
    # Verify shadow intent events (dual emit compatibility).
    shadow_events_legacy = [e for e in emitted_events if e[0] == "EVT:NEOCORTEX_SHADOW_INTENT"]
    shadow_events_canonical = [e for e in emitted_events if e[0] == "EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED"]
    assert len(shadow_events_canonical) >= 90, (
        f"Expected decimated canonical shadow events, got {len(shadow_events_canonical)}"
    )
    assert len(shadow_events_legacy) >= 90, (
        f"Expected decimated legacy shadow events during migration, got {len(shadow_events_legacy)}"
    )
    
    # Verify checkpoints were triggered (at least once)
    assert save_count[0] >= 1, f"Expected at least one save, got {save_count[0]}"


def test_no_broken_pool_errors(stress_config):
    """
    Verify BrokenProcessPool is handled gracefully.
    """
    from concurrent.futures import BrokenExecutor
    
    mock_bridge = MagicMock()
    mock_bridge.start = AsyncMock(return_value=True)
    mock_bridge.load_async = AsyncMock(return_value=False)
    mock_bridge.shutdown = MagicMock()
    
    call_count = [0]
    
    async def flaky_encode(obs):
        call_count[0] += 1
        if call_count[0] == 3:
            # Simulate crash on 3rd call
            raise BrokenExecutor("Worker died")
        return np.zeros(4, dtype=np.float32)
    
    mock_bridge.encode_async = AsyncMock(side_effect=flaky_encode)
    mock_bridge.act_async = AsyncMock(return_value={
        "action": 2, "action_name": "FLAT", "value": 0.0, "confidence": 0.0
    })
    mock_bridge.train_async = AsyncMock(return_value={"vae_loss": 0.1, "wm_loss": 0.1})
    mock_bridge.save_async = AsyncMock(return_value=True)
    
    parser = FeatureParser(stress_config.ingest)
    amygdala = ValuationEngine()
    buffer = EpisodicBuffer(stress_config.ingest.buffer_size)
    
    adapter = NeocortexAdapter(
        config=stress_config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=mock_bridge
    )
    
    async def run_test():
        await adapter.start()
        
        # Send 10 ticks - should survive the crash on tick 3
        for t in range(10):
            ts = BASE_TS + float(t)
            await adapter.handle_features({
                "timestamp": ts,
                "ts": ts,
                "event_ts_ms": int(round(ts * 1000.0)),
                "symbol": "SIMULATED",
                "features": {f"f{i+1}": "1.0" for i in range(5)}
            })

        await adapter.shutdown_async()
        return len(buffer)
    
    # Should not raise, should handle gracefully
    buffer_size = run_async(run_test())
    
    assert buffer_size == 10, f"All 10 ticks should be processed, got {buffer_size}"


def test_random_walk_data_quality():
    """
    Verify random walk generator produces valid data.
    """
    prev_price = 100.0
    prices = []
    
    for t in range(100):
        tick = generate_random_walk_tick(t, prev_price, num_features=5)
        prev_price = float(tick["mid_price"])
        prices.append(prev_price)
    
    # Price should have moved (not all same)
    assert len(set(prices)) > 1, "Prices should vary"
    
    # Price shouldn't explode or collapse too much
    assert min(prices) > 50, f"Price collapsed too much: {min(prices)}"
    assert max(prices) < 200, f"Price exploded too much: {max(prices)}"
    
    # Verify tick structure
    tick = generate_random_walk_tick(0, 100.0, 5)
    assert "timestamp" in tick
    assert "features" in tick
    assert len(tick["features"]) == 5


