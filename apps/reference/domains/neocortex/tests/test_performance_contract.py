"""
Performance/replay contract tests for P7.
"""

import csv
from pathlib import Path

import pytest

from apps.reference.domains.neocortex.config_models import (
    PerformanceConfig,
    load_config,
)
from apps.reference.domains.neocortex.logic.telemetry import TelemetryLogger


def _read_rows(path: Path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_yaml_config_enforces_explicit_performance_contract():
    config = load_config(Path("apps/reference/domains/neocortex/config"))

    assert config.neuro.performance.operating_mode == "offline_replay"
    assert config.neuro.performance.shadow_intent_emit_policy == "decimate_observational"
    assert config.neuro.performance.shadow_intent_decimation_stride >= 1
    assert config.neuro.performance.shadow_jsonl_write_policy == "buffered"
    assert config.neuro.performance.telemetry_write_policy == "buffered"


def test_live_shadow_mode_rejects_shadow_decimation():
    with pytest.raises(ValueError, match="live_shadow"):
        PerformanceConfig(
            operating_mode="live_shadow",
            shadow_intent_emit_policy="decimate_observational",
            shadow_intent_decimation_stride=2,
        )


def test_buffered_telemetry_flush_threshold_preserves_order(tmp_path: Path):
    logger = TelemetryLogger(
        log_dir=tmp_path,
        write_policy="buffered",
        flush_threshold=2,
        flush_interval_ms=60_000,
        pending_limit=16,
        overflow_policy="drop_oldest",
    )

    logger.log_shadow_intent(action=0, action_name="BUY", confidence=0.1, value=1.0)
    assert _read_rows(logger.filepath) == []

    logger.log_shadow_intent(action=1, action_name="SELL", confidence=0.2, value=2.0)
    rows = _read_rows(logger.filepath)

    assert [row["shadow_action_name"] for row in rows] == ["BUY", "SELL"]
    assert logger.stats["flush_count"] == 1
    assert logger.stats["rows_dropped"] == 0


def test_buffered_telemetry_overload_uses_explicit_drop_policy(tmp_path: Path):
    logger = TelemetryLogger(
        log_dir=tmp_path,
        write_policy="buffered",
        flush_threshold=10,
        flush_interval_ms=60_000,
        pending_limit=1,
        overflow_policy="drop_oldest",
    )

    logger.log_shadow_intent(action=0, action_name="BUY", confidence=0.1, value=1.0)
    logger.log_shadow_intent(action=1, action_name="SELL", confidence=0.2, value=2.0)
    logger.flush()

    rows = _read_rows(logger.filepath)
    assert [row["shadow_action_name"] for row in rows] == ["SELL"]
    assert logger.stats["rows_dropped"] == 1
    assert logger.stats["flush_count"] == 1
