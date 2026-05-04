"""
Objective split contract tests for P4.
"""

from collections import Counter, deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.logic.brain.core import BrainCore
from apps.reference.domains.neocortex.logic.datasets.hygiene import DatasetPolicyEngine
from apps.reference.domains.neocortex.logic.ingest.multi_tailer import Episode, EpisodeReward
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter


def _stub_adapter(*, policy_training_mode: str = "disabled"):
    full_config = load_config(Path("apps/reference/domains/neocortex/config"))
    adapter = object.__new__(NeocortexAdapter)
    adapter.config = full_config
    adapter.buffer = []
    adapter.telemetry = MagicMock()
    adapter.brain_bridge = MagicMock()
    adapter._emit_alert = MagicMock()
    adapter._samples_since_last_train = 0
    adapter.dream_threshold = 20
    adapter._dream_in_progress = False
    adapter._dreams_triggered = 0
    adapter._ppo_trains_triggered = 0
    adapter._waiting_for_reward_source = False
    adapter._reward_mode = "regime_oracle"
    adapter._oracle_settlements = 0
    adapter._objective_split_enforced = True
    adapter._policy_training_mode = policy_training_mode
    adapter._sequence_inference_mode = full_config.neuro.sequence.inference_mode
    adapter._representation_training_mode = full_config.neuro.sequence.representation_training_mode
    adapter._dataset_policy = DatasetPolicyEngine(
        full_config.neuro.dataset,
        policy_training_mode=policy_training_mode,
        representation_training_mode=full_config.neuro.sequence.representation_training_mode,
        sequence_inference_mode=full_config.neuro.sequence.inference_mode,
    )
    adapter._representation_samples = deque()
    adapter._regime_supervision_samples = []
    adapter._execution_quality_samples = []
    adapter._policy_samples = []
    adapter._evaluated_samples_by_family = {
        "representation": deque(),
        "regime_supervision": deque(),
        "execution_quality": deque(),
        "policy": deque(),
    }
    adapter._dataset_status_counts = Counter()
    adapter._dataset_exclusion_counts = Counter()
    adapter._dataset_quarantine_counts = Counter()
    adapter._objective_rejections = 0
    adapter._policy_training_rejections = 0
    adapter._track_task = MagicMock()
    adapter._pending_tasks = []
    adapter._shadow_intents_emitted = 0
    adapter._total_train_steps = 0
    adapter._backpressure_events = 0
    adapter._inflight_training_tasks = 0
    adapter._maybe_dream = AsyncMock()
    return adapter


def _completed_episode() -> Episode:
    episode = Episode(
        symbol="BTCUSDT",
        timestamp=1_700_000_000.2,
        event_ts_ms=1_700_000_000_200,
        episode_id="trade:BTCUSDT:trade:1",
        trade_id="BTCUSDT:trade:1",
        features={"rsi": 50.0, "obi": 0.2},
        side="BUY",
        entry_price=100.0,
        reward=0.4,
        pnl=4.9,
        reward_complete=True,
        executed_entry=True,
        entry_anchor_event="ORDER_FILLED",
        lifecycle_state="CLOSED",
        fill_count=1,
        filled_quantity=0.5,
        close_event_ts_ms=1_700_000_000_900,
    )
    episode.episode_reward = EpisodeReward(
        episode_id="trade:BTCUSDT:trade:1",
        trade_id="BTCUSDT:trade:1",
        symbol="BTCUSDT",
        side="BUY",
        entry_ts_ms=1_700_000_000_200,
        close_ts_ms=1_700_000_000_900,
        duration_ms=700,
        entry_price=100.0,
        close_price=110.0,
        quantity=0.5,
        realized_pnl=5.0,
        fees=0.1,
        net_pnl=4.9,
        entry_event="ORDER_FILLED",
        close_event="POSITION_CLOSED",
        reward_complete=True,
    )
    return episode


def test_yaml_config_enforces_explicit_objective_split_policy_mode():
    config = load_config(Path("apps/reference/domains/neocortex/config"))

    assert config.neuro.ppo.objective_split_enforced is True
    assert config.neuro.ppo.policy_training_mode == "disabled"


@pytest.mark.asyncio
async def test_completed_trade_episode_routes_only_to_execution_quality_buffer():
    adapter = _stub_adapter(policy_training_mode="disabled")

    await NeocortexAdapter.add_completed_episode(adapter, _completed_episode())

    assert len(adapter._execution_quality_samples) == 1
    assert adapter._execution_quality_samples[0]["objective_family"] == "execution_quality"
    assert adapter._execution_quality_samples[0]["policy_eligible"] is False
    assert adapter._execution_quality_samples[0]["eligibility_status"] == "trainable"
    assert adapter._execution_quality_samples[0]["dataset_provenance"]["objective_family"] == "execution_quality"
    assert adapter._regime_supervision_samples == []
    assert adapter._policy_samples == []


@pytest.mark.asyncio
async def test_oracle_settlement_routes_only_to_regime_supervision_buffer():
    adapter = _stub_adapter(policy_training_mode="disabled")
    adapter._oracle_ring_buffer = SimpleNamespace(
        push_and_settle=lambda **kwargs: SimpleNamespace(
            timestamp_t=1_700_000_000.0,
            predicted_action=2,
            features_t={"rsi": 50.0, "obi": 0.2},
            features_t_plus_h={"rsi": 51.0, "obi": 0.1},
            model_features_t=np.asarray([0.5, 0.2], dtype=np.float32),
        )
    )
    adapter._oracle_labeler = SimpleNamespace(
        compute_realized_regime=lambda current, future: 1
    )
    adapter._oracle_reward_calc = SimpleNamespace(
        compute_reward=lambda predicted, realized: 0.75
    )

    await NeocortexAdapter._handle_oracle_settlement(
        adapter,
        symbol="BTCUSDT",
        source_ts=1_700_000_000.0,
        z=np.asarray([0.1, 0.2], dtype=np.float32),
        action_result={"action": 2, "action_name": "MEAN_REVERSION"},
        raw_features_for_labeler={"rsi": 50.0, "obi": 0.2},
        model_features_vector=np.asarray([0.5, 0.2], dtype=np.float32),
    )

    assert len(adapter._regime_supervision_samples) == 1
    sample = adapter._regime_supervision_samples[0]
    assert sample["objective_family"] == "regime_supervision"
    assert sample["predicted_regime"] == 2
    assert sample["realized_regime"] == 1
    assert sample["policy_eligible"] is False
    assert sample["eligibility_status"] == "trainable"
    assert sample["dataset_provenance"]["objective_family"] == "regime_supervision"
    assert adapter._execution_quality_samples == []
    assert adapter._policy_samples == []


@pytest.mark.asyncio
async def test_policy_sample_rejected_when_policy_training_disabled():
    adapter = _stub_adapter(policy_training_mode="disabled")

    accepted = await NeocortexAdapter.add_policy_sample(
        adapter,
        {
            "objective_family": "policy",
            "features_vector": [0.1, 0.2],
            "action": 0,
            "reward": 1.0,
        },
    )

    assert accepted is False
    assert adapter._policy_training_rejections == 1
    assert adapter._policy_samples == []


def test_brain_core_rejects_mixed_objective_batch_fail_closed():
    ok, error = BrainCore._validate_objective_batch(
        [
            {"objective_family": "regime_supervision", "realized_regime": 1},
            {"objective_family": "policy", "action": 0},
        ],
        expected_family="policy",
    )

    assert ok is False
    assert error == "mixed_objective_family"
