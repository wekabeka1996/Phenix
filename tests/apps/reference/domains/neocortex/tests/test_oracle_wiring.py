"""
Unit tests for Regime Oracle wiring (REGIME_PIVOT_PLAN Phase 2).

Tests that the NeocortexAdapter correctly:
- Initializes oracle components when reward_mode='regime_oracle'
- Skips oracle initialization when reward_mode='pnl'
- Passes raw features through settlement pipeline
- Creates episodes after horizon bars elapse
- Computes correct reward and regime label
- Reports oracle stats
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from apps.reference.domains.neocortex.config_models import (
    IngestConfig,
    NeocortexConfig,
    NeuroConfig,
    OracleConfig,
    PPOConfig,
    SystemConfig,
    VAEConfig,
    WorldModelConfig,
)
from apps.reference.domains.neocortex.logic.reward.regime_labeler import (
    EXHAUSTION,
    HIGH_VOLATILITY,
    MEAN_REVERSION,
    REGIME_NAMES,
    TREND_DOWN,
    TREND_UP,
)
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter


# =============================================================================
# Fixtures
# =============================================================================

FEATURE_LIST = [
    "volatility_atr_pct",
    "delta_price",
    "ema_bias",
    "volatility_range_pct",
    "spread_pct",
    "obi",
    "mid_price",
    "volatility",
    "price",
    "volatility_state",
]


def _make_system_config(tmp_path: Path) -> dict:
    return {
        "data_dir": str(tmp_path / "data"),
        "checkpoint_dir": str(tmp_path / "checkpoints"),
        "brain_workers": 1,
        "queue_maxsize": 100,
        "log_level": "DEBUG",
        "log_to_file": False,
        "run_mode": "backtest",
        "rng_seed": 42,
    }


def _make_ingest_config() -> dict:
    return {
        "feature_list": FEATURE_LIST,
        "normalization_method": "zscore",
        "normalization_window": 100,
        "buffer_size": 1000,
        "min_samples_before_ready": 1,
        "nan_strategy": "zero",
    }


def _make_neuro_config(reward_mode: str = "pnl", action_dim: int = 3) -> dict:
    return {
        "vae": {
            "input_dim": len(FEATURE_LIST),
            "hidden_dims": [32],
            "latent_dim": 8,
            "learning_rate": 0.001,
            "beta": 0.1,
            "batch_size": 16,
            "use_mean": True,
        },
        "world_model": {
            "hidden_dim": 32,
            "num_layers": 1,
            "dropout": 0.0,
            "learning_rate": 0.001,
            "sequence_length": 10,
        },
        "ppo": {
            "state_dim": 8,
            "action_dim": action_dim,
            "hidden_dims": [32],
            "learning_rate": 0.0003,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "clip_epsilon": 0.2,
            "rollout_length": 64,
            "num_epochs": 4,
            "minibatch_size": 16,
            "reward_mode": reward_mode,
        },
        "checkpoint_every_n_steps": 100,
        "keep_last_n_checkpoints": 3,
        "dream_episode_threshold": 1,
    }


def _make_oracle_config() -> dict:
    return {
        "horizon_bars": 5,
        "high_vol_threshold": 0.8,
        "exhaustion_vol_now_threshold": 0.5,
        "exhaustion_vol_future_threshold": 0.1,
        "trend_delta_pct_threshold": 0.0002,
        "trend_ema_threshold": 0.0008,
        "mr_delta_pct_threshold": 0.0001,
        "reward_correct": 1.0,
        "reward_wrong": -0.5,
        "reward_matrix_enabled": False,
        "class_weights": {
            "PREDICT_TREND_UP": 1.5,
            "PREDICT_TREND_DOWN": 1.5,
            "PREDICT_MEAN_REVERSION": 0.7,
            "PREDICT_HIGH_VOLATILITY": 2.0,
            "PREDICT_EXHAUSTION": 2.5,
        },
    }


def _build_config(
    tmp_path: Path,
    reward_mode: str = "pnl",
    action_dim: int = 3,
    include_oracle: bool = False,
) -> NeocortexConfig:
    """Build a minimal NeocortexConfig for testing."""
    kwargs = {
        "system": _make_system_config(tmp_path),
        "ingest": _make_ingest_config(),
        "neuro": _make_neuro_config(reward_mode, action_dim),
    }
    if include_oracle:
        kwargs["oracle"] = _make_oracle_config()
    return NeocortexConfig(**kwargs)


class MockParser:
    """Mock FeatureParser that returns a MarketObservation-like object."""

    def __init__(self, feature_dim: int):
        self.feature_dim = feature_dim

    def parse(self, payload):
        from apps.reference.domains.neocortex.logic.ingest.observation import (
            MarketObservation,
        )

        features = payload.get("features", {})
        vec = np.array(
            [float(features.get(name, 0.0) or 0.0) for name in FEATURE_LIST],
            dtype=np.float32,
        )
        return MarketObservation(
            ts=float(payload.get("timestamp", 0.0)),
            mid_price=float(features.get("mid_price", 100.0) or 100.0),
            volatility=float(features.get("volatility", 0.01) or 0.01),
            obi=float(features.get("obi", 0.0) or 0.0),
            features_vector=vec,
            normalized=False,
        )


class MockBrainBridge:
    """Mock BrainBridge that returns deterministic encode/act results."""

    def __init__(self, action: int = 2, confidence: float = -0.5, value: float = 0.1):
        self.action = action
        self.confidence = confidence
        self.value = value
        self._train_ppo_calls: List[Any] = []
        self.action_names_5 = [
            "TREND_UP", "TREND_DOWN", "MEAN_REVERSION",
            "HIGH_VOLATILITY", "EXHAUSTION",
        ]
        self.action_names_3 = ["LONG", "SHORT", "FLAT"]

    async def encode_async(self, obs):
        return np.zeros(8, dtype=np.float32)

    async def act_async(self, z):
        action_names = (
            self.action_names_5 if self.action < 5 else self.action_names_3
        )
        name = action_names[self.action] if self.action < len(
            action_names) else "FLAT"
        return {
            "action": self.action,
            "action_name": name,
            "value": self.value,
            "confidence": self.confidence,
        }

    async def train_async(self, batch):
        return {"vae_loss": 0.01, "wm_loss": 0.01}

    async def train_ppo_async(self, episodes):
        self._train_ppo_calls.append(episodes)
        return {"loss_pi": 0.1, "loss_v": 0.2, "entropy": 0.5, "episodes_processed": len(episodes)}

    async def save_async(self, path):
        return True

    async def load_async(self, path):
        return True

    async def start(self):
        return True

    def shutdown(self):
        pass


class MockBuffer:
    """Mock EpisodicBuffer."""

    def __init__(self):
        self._items = []

    def add(self, obs, importance):
        self._items.append((obs, importance))

    def __len__(self):
        return len(self._items)

    def get_batch(self, n):
        return self._items[:n]


class MockAmygdala:
    """Mock ValuationEngine."""

    def update(self, obs, reward):
        return 1.0  # constant importance


def _make_features_payload(
    symbol: str = "BTCUSDT",
    timestamp: float = 0.0,
    atr_pct: float = 0.001,
    delta_price: float = 0.0,
    ema_bias: float = 0.5,
    range_pct: float = 0.001,
    price: float = 100.0,
    volatility_state: float = 0.0,
) -> Dict[str, Any]:
    """Build a minimal features payload for handle_features."""
    return {
        "symbol": symbol,
        "timestamp": timestamp,
        "reward_signal": 0.0,
        "features": {
            "volatility_atr_pct": atr_pct,
            "delta_price": delta_price,
            "ema_bias": ema_bias,
            "volatility_range_pct": range_pct,
            "spread_pct": 0.0001,
            "obi": 0.0,
            "mid_price": 100.0,
            "volatility": 0.01,
            "price": price,
            "volatility_state": volatility_state,
        },
    }


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temp directory and ensure data/logs dirs exist."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "checkpoints").mkdir(parents=True, exist_ok=True)
    return tmp_path


# =============================================================================
# Test: Oracle initialization
# =============================================================================

class TestOracleInitialization:

    def test_pnl_mode_no_oracle_components(self, tmp_dir):
        """When reward_mode='pnl', oracle components should not be initialized."""
        config = _build_config(tmp_dir, reward_mode="pnl")
        adapter = NeocortexAdapter(
            config=config,
            parser=MockParser(len(FEATURE_LIST)),
            amygdala=MockAmygdala(),
            buffer=MockBuffer(),
        )
        assert adapter._reward_mode == "pnl"
        assert adapter._oracle_ring_buffer is None
        assert adapter._oracle_labeler is None
        assert adapter._oracle_reward_calc is None

    def test_oracle_mode_initializes_components(self, tmp_dir):
        """When reward_mode='regime_oracle', all oracle components must exist."""
        config = _build_config(
            tmp_dir, reward_mode="regime_oracle", action_dim=5, include_oracle=True
        )
        adapter = NeocortexAdapter(
            config=config,
            parser=MockParser(len(FEATURE_LIST)),
            amygdala=MockAmygdala(),
            buffer=MockBuffer(),
        )
        assert adapter._reward_mode == "regime_oracle"
        assert adapter._oracle_ring_buffer is not None
        assert adapter._oracle_labeler is not None
        assert adapter._oracle_reward_calc is not None
        assert adapter._oracle_ring_buffer.horizon_bars == 5

    def test_oracle_mode_without_config_raises(self, tmp_dir):
        """reward_mode='regime_oracle' without oracle config raises ValueError."""
        config = _build_config(
            tmp_dir, reward_mode="regime_oracle", action_dim=5, include_oracle=False
        )
        with pytest.raises(ValueError, match="reward_mode='regime_oracle' requires oracle config"):
            NeocortexAdapter(
                config=config,
                parser=MockParser(len(FEATURE_LIST)),
                amygdala=MockAmygdala(),
                buffer=MockBuffer(),
            )


# =============================================================================
# Test: Oracle settlement flow
# =============================================================================

class TestOracleSettlement:

    @pytest.fixture
    def oracle_adapter(self, tmp_dir):
        """Create an adapter in regime_oracle mode with a mock brain bridge."""
        config = _build_config(
            tmp_dir, reward_mode="regime_oracle", action_dim=5, include_oracle=True
        )
        bridge = MockBrainBridge(action=HIGH_VOLATILITY)
        adapter = NeocortexAdapter(
            config=config,
            parser=MockParser(len(FEATURE_LIST)),
            amygdala=MockAmygdala(),
            buffer=MockBuffer(),
            brain_bridge=bridge,
        )
        return adapter

    @pytest.mark.asyncio
    async def test_warmup_no_episodes(self, oracle_adapter):
        """During warmup (first H bars), no episodes should be created."""
        adapter = oracle_adapter
        # Feed 5 bars (horizon=5, need 6 for first settlement)
        for i in range(5):
            payload = _make_features_payload(
                timestamp=float(i), atr_pct=0.001
            )
            await adapter.handle_features(payload)

        assert len(adapter._completed_episodes) == 0
        assert adapter._oracle_settlements == 0

    @pytest.mark.asyncio
    async def test_settlement_on_sixth_bar(self, oracle_adapter):
        """6th bar triggers first settlement and creates an episode."""
        adapter = oracle_adapter
        # Feed 6 bars: first 5 are calm, 6th has vol spike
        for i in range(5):
            payload = _make_features_payload(
                timestamp=float(i), volatility_state=0.1
            )
            await adapter.handle_features(payload)

        # 6th bar: vol spike
        payload_6 = _make_features_payload(
            timestamp=5.0, volatility_state=0.95
        )
        await adapter.handle_features(payload_6)

        assert adapter._oracle_settlements == 1
        # Dream threshold is 1, so episode should have been consumed by _maybe_dream
        # and _completed_episodes cleared. Check that dreams were triggered.
        assert adapter._dreams_triggered >= 1

    @pytest.mark.asyncio
    async def test_correct_prediction_gets_positive_reward(self, tmp_dir):
        """A correct HIGH_VOLATILITY prediction yields positive reward."""
        config = _build_config(
            tmp_dir, reward_mode="regime_oracle", action_dim=5, include_oracle=True
        )
        # PPO predicts HIGH_VOLATILITY (action=3)
        bridge = MockBrainBridge(action=HIGH_VOLATILITY)
        adapter = NeocortexAdapter(
            config=config,
            parser=MockParser(len(FEATURE_LIST)),
            amygdala=MockAmygdala(),
            buffer=MockBuffer(),
            brain_bridge=bridge,
        )
        # Patch _maybe_dream to capture episodes before they're consumed
        captured_episodes = []
        original_maybe_dream = adapter._maybe_dream

        async def capture_dream():
            captured_episodes.extend(list(adapter._completed_episodes))
            await original_maybe_dream()

        adapter._maybe_dream = capture_dream

        # Feed 5 calm bars + 1 vol spike bar
        for i in range(5):
            await adapter.handle_features(
                _make_features_payload(timestamp=float(i), volatility_state=0.1)
            )
        # 6th bar: vol spike -> realized regime = HIGH_VOLATILITY (volatility_state > 0.8)
        await adapter.handle_features(
            _make_features_payload(timestamp=5.0, volatility_state=0.95)
        )

        assert len(captured_episodes) >= 1
        ep = captured_episodes[0]
        assert ep["action"] == HIGH_VOLATILITY
        # Correct prediction gets positive reward (1.0 * 2.0 = 2.0)
        assert ep["reward"] > 0

    @pytest.mark.asyncio
    async def test_wrong_prediction_gets_negative_reward(self, tmp_dir):
        """A wrong prediction yields negative reward."""
        config = _build_config(
            tmp_dir, reward_mode="regime_oracle", action_dim=5, include_oracle=True
        )
        # PPO predicts TREND_UP (action=0) but market stays calm (MR)
        bridge = MockBrainBridge(action=TREND_UP)
        adapter = NeocortexAdapter(
            config=config,
            parser=MockParser(len(FEATURE_LIST)),
            amygdala=MockAmygdala(),
            buffer=MockBuffer(),
            brain_bridge=bridge,
        )
        captured_episodes = []
        original_maybe_dream = adapter._maybe_dream

        async def capture_dream():
            captured_episodes.extend(list(adapter._completed_episodes))
            await original_maybe_dream()

        adapter._maybe_dream = capture_dream

        # Feed 6 calm bars -> realized = MEAN_REVERSION, predicted = TREND_UP
        for i in range(6):
            await adapter.handle_features(
                _make_features_payload(
                    timestamp=float(i),
                    atr_pct=0.001,
                    delta_price=0.0001,
                    range_pct=0.001,
                )
            )

        assert len(captured_episodes) >= 1
        ep = captured_episodes[0]
        assert ep["action"] == TREND_UP
        assert ep["reward"] < 0  # Wrong prediction: -0.5

    @pytest.mark.asyncio
    async def test_multiple_settlements(self, oracle_adapter):
        """After warmup, each new bar produces a settlement."""
        adapter = oracle_adapter
        # Patch _maybe_dream to just clear episodes (no actual PPO training)

        async def noop_dream():
            adapter._completed_episodes.clear()

        adapter._maybe_dream = noop_dream

        # Feed 8 bars
        for i in range(8):
            await adapter.handle_features(
                _make_features_payload(timestamp=float(i), atr_pct=0.001)
            )

        # Bars 0-4: warmup (0 settlements)
        # Bar 5: settlement #1 (pairs t=0 with t=5)
        # Bar 6: settlement #2 (pairs t=1 with t=6)
        # Bar 7: settlement #3 (pairs t=2 with t=7)
        assert adapter._oracle_settlements == 3


# =============================================================================
# Test: Stats property
# =============================================================================

class TestOracleStats:

    def test_pnl_mode_stats_has_reward_mode(self, tmp_dir):
        """PnL mode stats include reward_mode but no oracle fields."""
        config = _build_config(tmp_dir, reward_mode="pnl")
        adapter = NeocortexAdapter(
            config=config,
            parser=MockParser(len(FEATURE_LIST)),
            amygdala=MockAmygdala(),
            buffer=MockBuffer(),
        )
        stats = adapter.stats
        assert stats["reward_mode"] == "pnl"
        assert "oracle_settlements" not in stats

    def test_oracle_mode_stats_includes_oracle_fields(self, tmp_dir):
        """Oracle mode stats include settlement count and warmup info."""
        config = _build_config(
            tmp_dir, reward_mode="regime_oracle", action_dim=5, include_oracle=True
        )
        adapter = NeocortexAdapter(
            config=config,
            parser=MockParser(len(FEATURE_LIST)),
            amygdala=MockAmygdala(),
            buffer=MockBuffer(),
        )
        stats = adapter.stats
        assert stats["reward_mode"] == "regime_oracle"
        assert stats["oracle_settlements"] == 0
        assert isinstance(stats["oracle_warmup_symbols"], dict)


# =============================================================================
# Test: PnL mode backward compatibility
# =============================================================================

class TestPnlModeUnchanged:

    @pytest.mark.asyncio
    async def test_pnl_mode_handle_features_no_oracle(self, tmp_dir):
        """In pnl mode, handle_features works without oracle side effects."""
        config = _build_config(tmp_dir, reward_mode="pnl")
        bridge = MockBrainBridge(action=2)  # FLAT
        adapter = NeocortexAdapter(
            config=config,
            parser=MockParser(len(FEATURE_LIST)),
            amygdala=MockAmygdala(),
            buffer=MockBuffer(),
            brain_bridge=bridge,
        )
        for i in range(10):
            await adapter.handle_features(
                _make_features_payload(timestamp=float(i))
            )

        # Oracle should not have been touched
        assert adapter._oracle_settlements == 0
        assert adapter._oracle_ring_buffer is None
        # Shadow intents should still work
        assert adapter._shadow_intents_emitted == 10

    @pytest.mark.asyncio
    async def test_pnl_mode_add_episode_still_works(self, tmp_dir):
        """In pnl mode, add_completed_episode still buffers episodes."""
        config = _build_config(tmp_dir, reward_mode="pnl")
        adapter = NeocortexAdapter(
            config=config,
            parser=MockParser(len(FEATURE_LIST)),
            amygdala=MockAmygdala(),
            buffer=MockBuffer(),
        )
        episode = {
            "symbol": "BTCUSDT",
            "timestamp": 1.0,
            "side": "LONG",
            "reward": 0.5,
            "pnl": 10.0,
            "features": {"mid_price": 100.0},
        }
        await adapter.add_completed_episode(episode)
        # dream_threshold is 1, so it should have triggered dream
        assert adapter._dreams_triggered >= 1


# =============================================================================
# Test: Event emission
# =============================================================================

class TestEventEmission:

    @pytest.mark.asyncio
    async def test_oracle_emits_regime_prediction_event(self, tmp_dir):
        """In oracle mode, shadow intent emits EVT:NEOCORTEX_REGIME_PREDICTION."""
        config = _build_config(
            tmp_dir, reward_mode="regime_oracle", action_dim=5, include_oracle=True
        )
        bridge = MockBrainBridge(action=MEAN_REVERSION)
        emitted_events = []

        def capture_emit(event_type, payload):
            emitted_events.append((event_type, payload))

        adapter = NeocortexAdapter(
            config=config,
            parser=MockParser(len(FEATURE_LIST)),
            amygdala=MockAmygdala(),
            buffer=MockBuffer(),
            brain_bridge=bridge,
            event_emitter=capture_emit,
        )

        await adapter.handle_features(
            _make_features_payload(timestamp=0.0)
        )

        event_types = [e[0] for e in emitted_events]
        assert "EVT:NEOCORTEX_REGIME_PREDICTION" in event_types
        # Legacy event should also be emitted during migration window
        assert "EVT:NEOCORTEX_SHADOW_INTENT" in event_types

    @pytest.mark.asyncio
    async def test_pnl_emits_shadow_intent_proposed(self, tmp_dir):
        """In pnl mode, shadow intent emits EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED."""
        config = _build_config(tmp_dir, reward_mode="pnl")
        bridge = MockBrainBridge(action=2)
        emitted_events = []

        def capture_emit(event_type, payload):
            emitted_events.append((event_type, payload))

        adapter = NeocortexAdapter(
            config=config,
            parser=MockParser(len(FEATURE_LIST)),
            amygdala=MockAmygdala(),
            buffer=MockBuffer(),
            brain_bridge=bridge,
            event_emitter=capture_emit,
        )

        await adapter.handle_features(
            _make_features_payload(timestamp=0.0)
        )

        event_types = [e[0] for e in emitted_events]
        assert "EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED" in event_types
        assert "EVT:NEOCORTEX_REGIME_PREDICTION" not in event_types
