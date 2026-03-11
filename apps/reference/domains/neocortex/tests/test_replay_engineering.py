"""
Replay engineering and hot-path observational side-effect tests for P7.
"""

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from apps.reference.domains.neocortex.config_models import PerformanceConfig, load_config
from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation
from apps.reference.domains.neocortex.logic.telemetry import TelemetryLogger
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter


def _stub_adapter(
    tmp_path: Path,
    *,
    operating_mode: str,
    shadow_intent_decimation_stride: int,
    shadow_jsonl_write_policy: str = "buffered",
    shadow_log_flush_threshold: int = 10,
    non_critical_queue_limit: int = 16,
    non_critical_overflow_policy: str = "drop_oldest",
):
    config = load_config(Path("apps/reference/domains/neocortex/config"))
    performance = config.neuro.performance.model_copy(
        update={
            "operating_mode": operating_mode,
            "shadow_intent_emit_policy": (
                "emit_all" if operating_mode == "live_shadow" else "decimate_observational"
            ),
            "shadow_intent_decimation_stride": shadow_intent_decimation_stride,
            "shadow_jsonl_write_policy": shadow_jsonl_write_policy,
            "telemetry_write_policy": "buffered",
            "shadow_log_flush_threshold": shadow_log_flush_threshold,
            "telemetry_flush_threshold": 10,
            "non_critical_queue_limit": non_critical_queue_limit,
            "flush_interval_ms": 60_000,
            "non_critical_overflow_policy": non_critical_overflow_policy,
        }
    )

    adapter = object.__new__(NeocortexAdapter)
    adapter.config = SimpleNamespace(
        system=SimpleNamespace(run_mode="backtest", data_dir=tmp_path, checkpoint_dir=tmp_path),
        ingest=config.ingest,
        neuro=SimpleNamespace(
            performance=performance,
            dataset=config.neuro.dataset,
            ppo=config.neuro.ppo,
            sequence=config.neuro.sequence,
            vae=config.neuro.vae,
        ),
    )
    adapter.brain_bridge = SimpleNamespace(
        encode_async=AsyncMock(return_value=np.asarray([0.1, 0.2], dtype=np.float32)),
        act_async=AsyncMock(
            return_value={
                "action": 1,
                "action_name": "SELL",
                "value": 0.3,
                "confidence": 0.4,
            }
        ),
    )
    adapter.event_emitter = MagicMock()
    adapter.telemetry = TelemetryLogger(
        log_dir=tmp_path / "telemetry",
        write_policy=performance.telemetry_write_policy,
        flush_threshold=performance.telemetry_flush_threshold,
        flush_interval_ms=performance.flush_interval_ms,
        pending_limit=performance.non_critical_queue_limit,
        overflow_policy=performance.non_critical_overflow_policy,
    )
    adapter._reward_mode = "regime_oracle"
    adapter._oracle_ring_buffer = object()
    adapter._handle_oracle_settlement = AsyncMock()
    adapter._shadow_intent_log_path = tmp_path / "shadow_intents.jsonl"
    adapter._shadow_intent_log_max_bytes = 1024 * 1024
    adapter._shadow_intent_log_backups = 1
    adapter._shadow_intent_log_path.parent.mkdir(parents=True, exist_ok=True)
    adapter._shadow_intents_emitted = 0
    adapter._shadow_intents_generated = 0
    adapter._shadow_intents_decimated = 0
    adapter._shadow_intent_log_flushes = 0
    adapter._shadow_intent_log_rows_dropped = 0
    adapter._shadow_intent_log_rows_buffered = 0
    adapter._non_critical_overload_events = 0
    adapter._shadow_intent_log_buffer = []
    adapter._operating_mode = performance.operating_mode
    adapter._shadow_intent_emit_policy = performance.shadow_intent_emit_policy
    adapter._shadow_intent_decimation_stride = performance.shadow_intent_decimation_stride
    adapter._shadow_jsonl_write_policy = performance.shadow_jsonl_write_policy
    adapter._telemetry_write_policy = performance.telemetry_write_policy
    adapter._shadow_log_flush_threshold = performance.shadow_log_flush_threshold
    adapter._telemetry_flush_threshold = performance.telemetry_flush_threshold
    adapter._non_critical_queue_limit = performance.non_critical_queue_limit
    adapter._non_critical_overflow_policy = performance.non_critical_overflow_policy
    adapter._flush_interval_ms = performance.flush_interval_ms
    adapter._last_non_critical_flush_ts_ms = int(time.time() * 1000.0)
    adapter._total_train_steps = 0
    return adapter


def _obs(event_ts_ms: int) -> MarketObservation:
    return MarketObservation(
        ts=event_ts_ms / 1000.0,
        mid_price=100.0,
        volatility=0.1,
        obi=0.2,
        features_vector=np.asarray([0.1, 0.2], dtype=np.float32),
        normalized=True,
    )


def _payload(event_ts_ms: int):
    return {
        "event_ts_ms": event_ts_ms,
        "timestamp": event_ts_ms / 1000.0,
        "symbol": "BTCUSDT",
        "event_id": f"evt:{event_ts_ms}",
    }


@pytest.mark.asyncio
async def test_offline_replay_decimates_only_observational_shadow_outputs(tmp_path: Path):
    adapter = _stub_adapter(
        tmp_path,
        operating_mode="offline_replay",
        shadow_intent_decimation_stride=2,
    )

    await NeocortexAdapter._generate_shadow_intent(adapter, _obs(1_700_000_000_100), _payload(1_700_000_000_100))
    await NeocortexAdapter._generate_shadow_intent(adapter, _obs(1_700_000_000_200), _payload(1_700_000_000_200))

    assert adapter._handle_oracle_settlement.await_count == 2
    assert adapter._shadow_intents_generated == 2
    assert adapter._shadow_intents_emitted == 1
    assert adapter._shadow_intents_decimated == 1
    assert adapter.event_emitter.call_count == 2


@pytest.mark.asyncio
async def test_buffered_shadow_log_flush_preserves_deterministic_order(tmp_path: Path):
    adapter = _stub_adapter(
        tmp_path,
        operating_mode="offline_replay",
        shadow_intent_decimation_stride=1,
        shadow_log_flush_threshold=10,
    )

    await NeocortexAdapter._generate_shadow_intent(adapter, _obs(1_700_000_000_100), _payload(1_700_000_000_100))
    await NeocortexAdapter._generate_shadow_intent(adapter, _obs(1_700_000_000_200), _payload(1_700_000_000_200))
    adapter._flush_shadow_intent_buffer(force=True)

    with open(adapter._shadow_intent_log_path, "r", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]

    assert [row["event_ts_ms"] for row in rows] == [1_700_000_000_100, 1_700_000_000_200]
    assert adapter._shadow_intent_log_flushes == 1


@pytest.mark.asyncio
async def test_noncritical_shadow_overload_is_explicit_and_counted(tmp_path: Path):
    adapter = _stub_adapter(
        tmp_path,
        operating_mode="offline_replay",
        shadow_intent_decimation_stride=1,
        shadow_log_flush_threshold=10,
        non_critical_queue_limit=1,
        non_critical_overflow_policy="drop_oldest",
    )

    await NeocortexAdapter._generate_shadow_intent(adapter, _obs(1_700_000_000_100), _payload(1_700_000_000_100))
    await NeocortexAdapter._generate_shadow_intent(adapter, _obs(1_700_000_000_200), _payload(1_700_000_000_200))
    adapter._flush_shadow_intent_buffer(force=True)

    with open(adapter._shadow_intent_log_path, "r", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]

    assert [row["event_ts_ms"] for row in rows] == [1_700_000_000_200]
    assert adapter._shadow_intent_log_rows_dropped == 1
    assert adapter._non_critical_overload_events == 1
