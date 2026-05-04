"""
Dataset hygiene and eligibility tests for P6.
"""

from pathlib import Path
from collections import Counter, deque
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import AsyncMock

import numpy as np
import pytest

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.logic.datasets.hygiene import DatasetPolicyEngine
from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter


def _engine(policy_training_mode: str = "disabled") -> DatasetPolicyEngine:
    config = load_config(Path("apps/reference/domains/neocortex/config"))
    return DatasetPolicyEngine(
        config.neuro.dataset,
        policy_training_mode=policy_training_mode,
        representation_training_mode=config.neuro.sequence.representation_training_mode,
        sequence_inference_mode=config.neuro.sequence.inference_mode,
    )


def _adapter_stub():
    config = load_config(Path("apps/reference/domains/neocortex/config"))
    adapter = object.__new__(NeocortexAdapter)
    adapter.config = config
    adapter.parser = SimpleNamespace(
        parse=lambda payload: MarketObservation(
            ts=payload["event_ts_ms"] / 1000.0,
            mid_price=100.0,
            volatility=0.1,
            obi=0.2,
            features_vector=np.asarray(
                [0.0] * len(config.ingest.feature_list),
                dtype=np.float32,
            ),
            normalized=False,
        )
    )
    adapter.amygdala = SimpleNamespace(update=lambda obs, reward: 0.5)

    class _Buffer:
        def __init__(self):
            self.added = []

        def add(self, obs, importance):
            self.added.append((obs, importance))

        def __len__(self):
            return len(self.added)

    adapter.buffer = _Buffer()
    adapter.telemetry = MagicMock()
    adapter.brain_bridge = None
    adapter._emit_alert = MagicMock()
    adapter._extract_raw_feature_map = lambda payload: {}
    adapter._normalize_features_for_symbol = (
        lambda symbol, raw_features_vector: np.asarray(raw_features_vector, dtype=np.float32)
    )
    adapter._generate_shadow_intent = AsyncMock()
    adapter._maybe_train = AsyncMock()
    adapter._samples_since_last_train = 0
    adapter._train_batch_size = config.neuro.vae.batch_size
    adapter._max_inflight_training_tasks = 1
    adapter._inflight_training_tasks = 0
    adapter._backpressure_threshold = 999999
    adapter._backpressure_events = 0
    adapter.dream_threshold = 20
    adapter._dream_in_progress = False
    adapter._dreams_triggered = 0
    adapter._ppo_trains_triggered = 0
    adapter._waiting_for_reward_source = False
    adapter._shadow_intents_emitted = 0
    adapter._total_train_steps = 0
    adapter._objective_split_enforced = True
    adapter._policy_training_mode = config.neuro.ppo.policy_training_mode
    adapter._sequence_inference_mode = config.neuro.sequence.inference_mode
    adapter._representation_training_mode = config.neuro.sequence.representation_training_mode
    adapter._reset_sequence_on_replay_start = config.neuro.sequence.reset_on_replay_start
    adapter._reward_mode = config.neuro.ppo.reward_mode
    adapter._oracle_settlements = 0
    adapter._regime_supervision_samples = []
    adapter._execution_quality_samples = []
    adapter._policy_samples = []
    adapter._representation_samples = deque()
    adapter._evaluated_samples_by_family = {
        "representation": deque(),
        "regime_supervision": deque(),
        "execution_quality": deque(),
        "policy": deque(),
    }
    adapter._dataset_policy = _engine(policy_training_mode=config.neuro.ppo.policy_training_mode)
    adapter._dataset_status_counts = Counter()
    adapter._dataset_exclusion_counts = Counter()
    adapter._dataset_quarantine_counts = Counter()
    adapter._objective_rejections = 0
    adapter._policy_training_rejections = 0
    return adapter


def test_magicmock_contaminated_sample_is_quarantined():
    engine = _engine()
    sample = {
        "event_ts_ms": 1_700_000_000_100,
        "symbol": "BTCUSDT",
        "trade_id": MagicMock(name="trade_id_mock"),
        "reward_complete": True,
    }

    evaluated = engine.evaluate_sample(
        sample,
        objective_family="execution_quality",
        source_type="episode_close",
        source_ref="close:btc:1",
        source_event_type="POSITION_CLOSED",
        ingestion_mode="replay",
    )

    assert evaluated.eligibility_status == "quarantined"
    assert "magicmock_contamination" in evaluated.provenance.quarantine_reasons


def test_reward_incomplete_execution_sample_is_diagnostics_only():
    engine = _engine()
    sample = {
        "event_ts_ms": 1_700_000_000_200,
        "symbol": "BTCUSDT",
        "trade_id": "trade-1",
        "lifecycle_id": "life-1",
        "reward_complete": False,
        "reward_missing": True,
    }

    evaluated = engine.evaluate_sample(
        sample,
        objective_family="execution_quality",
        source_type="episode_close",
        source_ref="close:btc:2",
        source_event_type="POSITION_CLOSED",
        ingestion_mode="replay",
    )

    assert evaluated.eligibility_status == "diagnostics_only"
    assert "reward_incomplete" in evaluated.provenance.exclusion_reasons


def test_unresolved_execution_sample_is_not_trainable():
    engine = _engine()
    sample = {
        "event_ts_ms": 1_700_000_000_300,
        "symbol": "ETHUSDT",
        "trade_id": "trade-2",
        "unresolved_lifecycle": True,
        "reward_complete": True,
    }

    evaluated = engine.evaluate_sample(
        sample,
        objective_family="execution_quality",
        source_type="episode_close",
        source_ref="close:eth:1",
        source_event_type="POSITION_CLOSED",
        ingestion_mode="replay",
    )

    assert evaluated.eligibility_status == "quarantined"
    assert "unresolved_lifecycle" in evaluated.provenance.quarantine_reasons


def test_legacy_non_causal_sample_is_not_trainable_for_regime_supervision():
    engine = _engine()
    sample = {
        "event_ts_ms": 1_700_000_000_400,
        "symbol": "SOLUSDT",
        "predicted_regime": 1,
        "realized_regime": 2,
        "time_is_causal": False,
        "time_source": "legacy_non_causal_file_offset",
    }

    evaluated = engine.evaluate_sample(
        sample,
        objective_family="regime_supervision",
        source_type="oracle_settlement",
        source_ref="oracle:sol:1",
        source_event_type="EVT:NEOCORTEX_REGIME_PREDICTION",
        ingestion_mode="replay",
    )

    assert evaluated.eligibility_status == "rejected"
    assert "legacy_non_causal_not_allowed" in evaluated.provenance.exclusion_reasons


def test_policy_family_is_rejected_when_training_disabled():
    engine = _engine(policy_training_mode="disabled")
    sample = {
        "event_ts_ms": 1_700_000_000_500,
        "symbol": "BTCUSDT",
        "trade_id": "trade-3",
        "lifecycle_id": "life-3",
        "reward_complete": True,
        "sequence_contract_mode": "stateless_per_event",
        "action": 0,
        "reward": 1.0,
    }

    evaluated = engine.evaluate_sample(
        sample,
        objective_family="policy",
        source_type="policy_candidate",
        source_ref="policy:btc:1",
        source_event_type="ORDER_FILLED",
        ingestion_mode="replay",
    )

    assert evaluated.eligibility_status == "rejected"
    assert "policy_training_disabled" in evaluated.provenance.exclusion_reasons


def test_unknown_family_or_missing_source_provenance_rejects_fail_closed():
    engine = _engine()
    sample = {
        "event_ts_ms": 1_700_000_000_600,
        "symbol": "BTCUSDT",
    }

    evaluated = engine.evaluate_sample(
        sample,
        objective_family="unknown_family",
        source_type="",
        source_ref="",
        source_event_type="",
        ingestion_mode="replay",
    )

    assert evaluated.eligibility_status == "rejected"
    assert "unknown_objective_family" in evaluated.provenance.exclusion_reasons
    assert "missing_source_provenance" in evaluated.provenance.exclusion_reasons


@pytest.mark.asyncio
async def test_legacy_non_causal_representation_row_is_not_admitted_to_train_buffer():
    adapter = _adapter_stub()

    await NeocortexAdapter.handle_features(
        adapter,
        {
            "event_ts_ms": 1_700_000_001_000,
            "symbol": "BTCUSDT",
            "time_is_causal": False,
            "time_source": "legacy_non_causal_file_offset",
        },
    )

    assert len(adapter.buffer.added) == 0
    assert adapter._samples_since_last_train == 0
    assert list(adapter._representation_samples) == []
    assert adapter._dataset_status_counts["eval_only"] == 1
    assert adapter._dataset_exclusion_counts["legacy_non_causal_representation"] == 1


@pytest.mark.asyncio
async def test_quarantined_execution_episode_is_not_buffered():
    adapter = _adapter_stub()

    await NeocortexAdapter.add_completed_episode(
        adapter,
        {
            "episode_id": "episode-1",
            "event_ts_ms": 1_700_000_001_500,
            "symbol": "ETHUSDT",
            "trade_id": "trade-eth-1",
            "reward_complete": True,
            "reward_missing": False,
            "unresolved_reason": "ambiguous_close",
            "reward": 0.5,
            "pnl": 1.2,
        },
    )

    assert adapter._execution_quality_samples == []
    assert adapter._dataset_status_counts["quarantined"] == 1
    assert adapter._dataset_quarantine_counts["unresolved_lifecycle"] == 1
