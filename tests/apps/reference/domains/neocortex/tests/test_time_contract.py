"""
Canonical time contract tests for P1.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from pydantic import ValidationError

from apps.reference.domains.neocortex.config_models import (
    IngestConfig,
    NeocortexConfig,
    NeuroConfig,
    PerformanceConfig,
    PPOConfig,
    ReplayConfig,
    SystemConfig,
    VAEConfig,
    WorldModelConfig,
)
from apps.reference.domains.neocortex.logic.amygdala.valuation import ValuationEngine
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.ingest.parser import FeatureParser
from apps.reference.domains.neocortex.logic.ingest.parsers import (
    parse_core_log_line,
    parse_feature_log_line,
    parse_order_log_line,
)
from apps.reference.domains.neocortex.logic.ingest.multi_tailer import (
    Episode,
    MultiSourceConfig,
    MultiTailer,
)
from apps.reference.domains.neocortex.logic.memory.buffer import EpisodicBuffer
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter


def _full_config(tmp_path: Path) -> NeocortexConfig:
    return NeocortexConfig(
        trust_enabled=True,
        authority={
            "mode": "shadow",
            "deadline_ms": 50,
            "fallback_policy": "baseline_yaml",
            "max_inflight_per_symbol": 1,
            "modulation_allowlist": ["decision_making.signal_threshold_bias"],
            "signal_threshold_bias_bounds": [-0.1, 0.1],
            "cooldown_mult_bounds": [1.0, 3.0],
        },
        system=SystemConfig(
            data_dir=str(tmp_path / "data"),
            checkpoint_dir=str(tmp_path / "checkpoints"),
            run_mode="backtest",
            rng_seed=42,
            brain_workers=1,
            queue_maxsize=100,
            log_level="INFO",
            log_to_file=False,
        ),
        ingest=IngestConfig(
            feature_list=["rsi", "obi", "vol"],
            normalization_method="zscore",
            normalization_window=100,
            normalization_scope="per_symbol",
            buffer_size=1000,
            min_samples_before_ready=1,
            nan_strategy="zero",
            price_feature_mode="raw",
            delta_price_mode="raw",
            feature_clip_abs={},
        ),
        neuro=NeuroConfig(
            vae=VAEConfig(
                input_dim=3,
                hidden_dims=[16, 8],
                latent_dim=4,
                learning_rate=0.001,
                beta=1.0,
                free_bits_per_dim=0.0,
                batch_size=2,
                use_mean=True,
                regime_aux={
                    "enabled": True,
                    "alpha": 0.2,
                    "num_classes": 5,
                    "ema_decay": 0.99,
                },
            ),
            world_model=WorldModelConfig(
                hidden_dim=16,
                num_layers=1,
                dropout=0.0,
                learning_rate=0.001,
                sequence_length=5,
            ),
            ppo=PPOConfig(
                state_dim=8,
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
                minibatch_size=2,
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
            },
            evaluation={
                "report_version": 1,
                "calibration_bins": 5,
                "confidence_bucket_edges": [0.25, 0.5, 0.75, 0.9],
                "missing_confidence_policy": "not_available",
                "advisory_status": "forbidden",
            },
            performance=PerformanceConfig(
                operating_mode="live_shadow",
                shadow_intent_emit_policy="emit_all",
                shadow_intent_decimation_stride=1,
                shadow_jsonl_write_policy="buffered",
                telemetry_write_policy="buffered",
                non_critical_queue_limit=2048,
                shadow_log_flush_threshold=64,
                telemetry_flush_threshold=64,
                flush_interval_ms=1000,
                non_critical_overflow_policy="drop_oldest",
            ),
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
            poll_interval=0.1,
            feature_missing_timestamp_policy="fail_closed",
        ),
    )


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_feature_log_full_line_normalizes_to_event_ts_ms_int():
    line = (
        "2026-01-09 12:58:42,585 - FeatureEngineering - INFO - "
        'Calculated features for BTCUSDT: {"obi": "-0.68", "rsi": "45.5", "vol": "0.03"}'
    )

    entry = parse_feature_log_line(line)

    assert entry is not None
    assert isinstance(entry.event_ts_ms, int)
    assert entry.event_ts_ms == 1767956322585
    assert entry.timestamp == pytest.approx(entry.event_ts_ms / 1000.0)
    assert entry.time_is_causal is False
    assert entry.time_provenance == CausalTimeProvenance.CAPTURED_WALLCLOCK


def test_feature_log_pure_json_without_timestamp_fails_closed_by_default():
    line = '{"obi": "0.1", "rsi": "45.5", "vol": "0.03"}'

    entry = parse_feature_log_line(line, symbol="BTCUSDT")

    assert entry is None


def test_feature_log_legacy_non_causal_mode_is_explicit_and_marked():
    line = '{"obi": "0.1", "rsi": "45.5", "vol": "0.03"}'

    entry = parse_feature_log_line(
        line,
        symbol="BTCUSDT",
        missing_timestamp_policy="legacy_non_causal_file_offset",
        synthetic_event_ts_ms=1_772_916_000_123,
    )

    assert entry is not None
    assert entry.event_ts_ms == 1_772_916_000_123
    assert entry.time_is_causal is False
    assert entry.time_source == "legacy_non_causal_file_offset"
    assert entry.time_provenance == CausalTimeProvenance.FILE_OFFSET_LEGACY


def test_order_log_timestamp_seconds_normalized_to_ms_int():
    line = (
        '{"event_type": "ORDER_PLACED", "symbol": "BTCUSDT", "side": "BUY", '
        '"quantity": 0.5, "order_id": "12345", "timestamp": 1736380000.0}'
    )

    entry = parse_order_log_line(line)

    assert entry is not None
    assert entry.event_ts_ms == 1736380000000
    assert entry.timestamp == pytest.approx(1736380000.0)


def test_order_log_timestamp_ms_preserved():
    line = (
        '{"event_type": "ORDER_PLACED", "symbol": "BTCUSDT", "side": "BUY", '
        '"quantity": 0.5, "order_id": "12345", "timestamp": 1772916600129}'
    )

    entry = parse_order_log_line(line)

    assert entry is not None
    assert entry.event_ts_ms == 1772916600129
    assert entry.timestamp == pytest.approx(1772916600.129)


def test_core_log_timestamp_normalized_to_ms_int():
    line = (
        "2026-01-10 05:16:44,365 - aurora_handler.aurora - INFO - "
        "[ETHUSDT] Position closed (neutral). Starting re-entry cooldown."
    )

    entry = parse_core_log_line(line)

    assert entry is not None
    assert entry.event_ts_ms == 1768015004365
    assert entry.timestamp == pytest.approx(entry.event_ts_ms / 1000.0)


def test_core_log_structured_close_prefers_close_ts_ms_as_event_ts_ms():
    line = (
        "2026-01-10 03:10:42,580 - execution_position.fsm - INFO - "
        "EVT:POSITION_CLOSED symbol=BTCUSDT trade_id=BTCUSDT:1700000001000:1 "
        "close_ts_ms=1700000001000 realized_pnl_net=3.5 fees=0.1"
    )

    entry = parse_core_log_line(line)

    assert entry is not None
    assert entry.event_ts_ms == 1700000001000
    assert entry.timestamp == pytest.approx(1700000001.0)


def test_replay_config_legacy_feature_policy_requires_explicit_base_ts_ms():
    with pytest.raises(ValidationError):
        ReplayConfig(
            enabled=True,
            features_dir="logs/features",
            orders_file="logs/order_log_v1.jsonl",
            core_log="logs/aurora_core.log",
            feature_missing_timestamp_policy="legacy_non_causal_file_offset",
        )


def test_stale_cleanup_compares_canonical_ms_only(tmp_path: Path):
    tailer = MultiTailer(
        config=MultiSourceConfig(
            enabled=True,
            features_dir=tmp_path / "features",
            orders_file=tmp_path / "order_log_v1.jsonl",
            core_log=tmp_path / "aurora_core.log",
            symbols=["BTCUSDT"],
        ),
        feature_handler=AsyncMock(),
        state_path=tmp_path / "state.json",
    )

    tailer._pending_episodes["episode:btc:1"] = Episode(
        symbol="BTCUSDT",
        timestamp=1700000000.0,
        event_ts_ms=1_700_000_000_000,
        features={"rsi": 50.0},
        side="BUY",
    )

    tailer._cleanup_stale_episodes(
        current_event_ts_ms=1_700_000_000_500, ttl_ms=1_000)
    assert "episode:btc:1" in tailer._pending_episodes

    tailer._cleanup_stale_episodes(
        current_event_ts_ms=1_700_000_002_500, ttl_ms=1_000)
    assert "episode:btc:1" not in tailer._pending_episodes


def test_shadow_intent_idempotent_key_uses_canonical_event_ts_ms_not_wallclock(tmp_path: Path):
    emitted = []

    def emitter(event_type, payload):
        emitted.append((event_type, payload))

    mock_bridge = MagicMock()
    mock_bridge.start = AsyncMock(return_value=True)
    mock_bridge.encode_async = AsyncMock(
        return_value=np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    )
    mock_bridge.act_async = AsyncMock(
        return_value={
            "action": 0,
            "action_name": "LONG",
            "value": 0.5,
            "confidence": 0.8,
        }
    )
    mock_bridge.train_async = AsyncMock(return_value={})
    mock_bridge.save_async = AsyncMock(return_value=True)
    mock_bridge.load_async = AsyncMock(return_value=False)
    mock_bridge.shutdown = MagicMock()

    config = _full_config(tmp_path)
    parser = FeatureParser(config.ingest)
    amygdala = ValuationEngine()
    buffer = EpisodicBuffer(config.ingest.buffer_size)
    adapter = NeocortexAdapter(
        config=config,
        parser=parser,
        amygdala=amygdala,
        buffer=buffer,
        brain_bridge=mock_bridge,
        event_emitter=emitter,
    )

    async def run_test():
        await adapter.start()
        payload = {
            "event_ts_ms": 1_700_000_000_123,
            "symbol": "BTCUSDT",
            "features": {"rsi": "50", "obi": "0.1", "vol": "0.5"},
        }
        await adapter.handle_features(dict(payload))
        await adapter.handle_features(dict(payload))
        await adapter.shutdown_async()

    _run_async(run_test())

    canonical_payloads = [
        payload
        for event_type, payload in emitted
        if event_type == "EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED"
    ]
    assert len(canonical_payloads) >= 2
    assert canonical_payloads[0]["idempotent_key"] == canonical_payloads[1]["idempotent_key"]
    assert canonical_payloads[0]["event_ts_ms"] == 1_700_000_000_123
