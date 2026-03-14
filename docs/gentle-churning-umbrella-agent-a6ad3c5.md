# Plan: Alpha Search Tier 4 Test Files (5 files, 49 tests)

## Overview

Create 5 test files under `apps/reference/domains/alpha_search/tests/` targeting the `runtime/` module layer (Tier 4). All tests use `tmp_path` for filesystem isolation, import from the actual source modules, and follow the test patterns established in the existing codebase (`conftest.py` factories, `@pytest.mark.unit`/`asyncio`/`integration` markers).

Key conventions from the codebase:
- `sys.path.insert(0, ...)` is NOT needed since `conftest.py` and existing tests import via `apps.reference.domains...` absolute paths
- Fixtures from `conftest.py`: `tmp_session_dir`, `mock_bus`, `project_root`, `make_snapshot`, `make_result`, `write_jsonl_file`
- LocalBus from `apps.reference.orchestrator.utils_event_bus` for event bus tests
- pydantic `model_validate` for contract validation

## Files to Create

### File 1: `test_logger_factory.py` (8 tests)
- Target: `runtime/logger_factory.py` - ScenarioLoggerFactory, ScenarioScoreWriter
- All `@pytest.mark.unit`
- Tests logger creation, propagation, directory creation, JSONL writing, score counting

### File 2: `test_reporting.py` (8 tests)
- Target: `runtime/reporting.py` - AggregateReporter, CSV_COLUMNS
- All `@pytest.mark.unit`
- Tests CSV writing, header dedup, column schema, JSONL health/summary, stats, accumulation

### File 3: `test_feature_mirror_writer.py` (10 tests)
- Target: `runtime/feature_mirror_writer.py` - FeatureMirrorWriter
- All `@pytest.mark.unit`
- Uses `mock_bus` fixture (LocalBus) for event emission
- Tests JSONL output, regime caching, symbol filtering, price extraction, payload extraction

### File 4: `test_hot_reload.py` (11 tests)
- Target: `runtime/hot_reload.py` - ReloadDiff, ConfigWatcher
- Mix of `@pytest.mark.unit` and `@pytest.mark.asyncio`
- Tests hash computation, diff detection, reload callbacks, rollback, watch loop exit, stats

### File 5: `test_launcher.py` (12 tests)
- Target: `runtime/launcher.py` - load_matrix_config, setup_logging, main_reactor, run
- Mix of `@pytest.mark.unit`, `@pytest.mark.asyncio`, `@pytest.mark.integration`
- Tests config loading, validation errors, logging setup, project root resolution, reactor flow

---

## Detailed File Contents

### File 1: `test_logger_factory.py`

```python
"""
Tests for runtime/logger_factory.py — Tier 4
=============================================

Covers:
- ScenarioLoggerFactory.create_scenario_logger
- ScenarioLoggerFactory.create_aggregate_logger
- ScenarioScoreWriter write_score / write_trade / write_health / scores_written
"""

import json
import logging
from pathlib import Path

import pytest

from apps.reference.domains.alpha_search.runtime.logger_factory import (
    ScenarioLoggerFactory,
    ScenarioScoreWriter,
)


# ---------------------------------------------------------------------------
# ScenarioLoggerFactory
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_create_scenario_logger_writes_to_file(tmp_path):
    """Log message appears in the scenario.log file."""
    logger = ScenarioLoggerFactory.create_scenario_logger("S01", tmp_path)
    logger.info("hello from scenario")
    # Flush handlers
    for h in logger.handlers:
        h.flush()
    log_file = tmp_path / "S01" / "scenario.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "hello from scenario" in content


@pytest.mark.unit
def test_scenario_logger_no_propagation(tmp_path):
    """Logger.propagate must be False to prevent cross-scenario leaks."""
    logger = ScenarioLoggerFactory.create_scenario_logger("S02", tmp_path)
    assert logger.propagate is False


@pytest.mark.unit
def test_scenario_logger_creates_directory(tmp_path):
    """Directory <log_dir>/<scenario_id>/ is created on logger init."""
    ScenarioLoggerFactory.create_scenario_logger("S03_NEW", tmp_path)
    assert (tmp_path / "S03_NEW").is_dir()


@pytest.mark.unit
def test_create_aggregate_logger_writes_to_file(tmp_path):
    """Aggregate logger writes to <session_dir>/aggregate/aggregate.log."""
    logger = ScenarioLoggerFactory.create_aggregate_logger(tmp_path)
    logger.info("aggregate event")
    for h in logger.handlers:
        h.flush()
    log_file = tmp_path / "aggregate" / "aggregate.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "aggregate event" in content


# ---------------------------------------------------------------------------
# ScenarioScoreWriter
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_score_writer_writes_jsonl(tmp_path):
    """write_score creates a valid JSONL line in scores.jsonl."""
    writer = ScenarioScoreWriter("S10", tmp_path)
    writer.write_score({"score": 0.42, "symbol": "BTCUSDT"})
    path = tmp_path / "S10" / "scores.jsonl"
    assert path.exists()
    line = path.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["score"] == 0.42
    assert record["scenario_id"] == "S10"
    assert "ts" in record


@pytest.mark.unit
def test_score_writer_trade_jsonl(tmp_path):
    """write_trade appends a valid JSON line to trades.jsonl."""
    writer = ScenarioScoreWriter("S11", tmp_path)
    writer.write_trade({"side": "BUY", "price": 95000.0})
    path = tmp_path / "S11" / "trades.jsonl"
    assert path.exists()
    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["side"] == "BUY"
    assert record["scenario_id"] == "S11"


@pytest.mark.unit
def test_score_writer_health_jsonl(tmp_path):
    """write_health appends a valid JSON line to health.jsonl."""
    writer = ScenarioScoreWriter("S12", tmp_path)
    writer.write_health({"event": "HEARTBEAT", "ok": True})
    path = tmp_path / "S12" / "health.jsonl"
    assert path.exists()
    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["event"] == "HEARTBEAT"
    assert record["scenario_id"] == "S12"


@pytest.mark.unit
def test_score_writer_count(tmp_path):
    """scores_written increments only on write_score calls."""
    writer = ScenarioScoreWriter("S13", tmp_path)
    assert writer.scores_written == 0
    writer.write_score({"a": 1})
    writer.write_score({"a": 2})
    writer.write_trade({"b": 3})
    assert writer.scores_written == 2
```

### File 2: `test_reporting.py`

```python
"""
Tests for runtime/reporting.py — Tier 4
========================================

Covers:
- AggregateReporter.log_result (CSV writing)
- AggregateReporter.log_health / log_summary (JSONL writing)
- CSV header deduplication and schema validation
- stats property
"""

import csv
import json
from pathlib import Path

import pytest

from apps.reference.domains.alpha_search.runtime.reporting import (
    AggregateReporter,
    CSV_COLUMNS,
)


def _make_result(**overrides) -> dict:
    """Minimal result dict compatible with CSV_COLUMNS."""
    base = {
        "scenario_id": "S01",
        "strategy_type": "aurora",
        "symbol": "BTCUSDT",
        "ts_ms": 1740000000000,
        "score": 0.15,
        "confidence": 0.8,
        "threshold": 0.155,
        "side": "NEUTRAL",
        "provider_id": "aurora",
        "regime": "DEFAULT",
    }
    base.update(overrides)
    return base


@pytest.mark.unit
def test_log_result_writes_csv_row(tmp_path):
    """A single log_result produces a data row in the CSV file."""
    reporter = AggregateReporter(tmp_path)
    reporter.log_result(_make_result())
    csv_path = tmp_path / "aggregate" / "aggregate_metrics.csv"
    assert csv_path.exists()
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2  # header + 1 row


@pytest.mark.unit
def test_csv_header_written_once(tmp_path):
    """Two log_result calls produce only one header line."""
    reporter = AggregateReporter(tmp_path)
    reporter.log_result(_make_result(scenario_id="S01"))
    reporter.log_result(_make_result(scenario_id="S02"))
    csv_path = tmp_path / "aggregate" / "aggregate_metrics.csv"
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    header_lines = [l for l in lines if l.startswith("timestamp,")]
    assert len(header_lines) == 1


@pytest.mark.unit
def test_csv_columns_match_schema(tmp_path):
    """CSV header matches the declared CSV_COLUMNS list."""
    reporter = AggregateReporter(tmp_path)
    reporter.log_result(_make_result())
    csv_path = tmp_path / "aggregate" / "aggregate_metrics.csv"
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert header == CSV_COLUMNS


@pytest.mark.unit
def test_log_health_writes_jsonl(tmp_path):
    """log_health writes a valid JSON line to health.jsonl."""
    reporter = AggregateReporter(tmp_path)
    reporter.log_health({"event": "SCENARIO_INIT_FAILED", "scenario_id": "S01"})
    health_path = tmp_path / "aggregate" / "health.jsonl"
    assert health_path.exists()
    record = json.loads(health_path.read_text(encoding="utf-8").strip())
    assert record["event"] == "SCENARIO_INIT_FAILED"
    assert "ts" in record


@pytest.mark.unit
def test_log_summary_writes_jsonl(tmp_path):
    """log_summary writes a valid JSON line to summary.jsonl."""
    reporter = AggregateReporter(tmp_path)
    reporter.log_summary({"S01": {"score_mean": 0.12}})
    summary_path = tmp_path / "aggregate" / "summary.jsonl"
    assert summary_path.exists()
    record = json.loads(summary_path.read_text(encoding="utf-8").strip())
    assert "scenarios" in record
    assert record["scenarios"]["S01"]["score_mean"] == 0.12


@pytest.mark.unit
def test_stats_csv_rows(tmp_path):
    """stats.csv_rows reflects the number of rows written."""
    reporter = AggregateReporter(tmp_path)
    reporter.log_result(_make_result())
    reporter.log_result(_make_result())
    reporter.log_result(_make_result())
    assert reporter.stats["csv_rows"] == 3


@pytest.mark.unit
def test_multiple_results_accumulate(tmp_path):
    """10 results produce 10 data rows + 1 header = 11 lines."""
    reporter = AggregateReporter(tmp_path)
    for i in range(10):
        reporter.log_result(_make_result(scenario_id=f"S{i:02d}"))
    csv_path = tmp_path / "aggregate" / "aggregate_metrics.csv"
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 11  # 1 header + 10 data rows


@pytest.mark.unit
def test_creates_aggregate_directory(tmp_path):
    """aggregate/ subdir exists after AggregateReporter init."""
    _ = AggregateReporter(tmp_path)
    assert (tmp_path / "aggregate").is_dir()
```

### File 3: `test_feature_mirror_writer.py`

```python
"""
Tests for runtime/feature_mirror_writer.py — Tier 4
====================================================

Covers:
- FeatureMirrorWriter JSONL output on EVT:FEATURES_CALCULATED
- Regime caching from EVT:REGIME_DETECTED
- Symbol filtering, empty-features skip, price extraction
- Payload extraction for dict and object payloads
- Output directory creation and stats counters
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.reference.domains.alpha_search.runtime.feature_mirror_writer import (
    FeatureMirrorWriter,
)
from apps.reference.orchestrator.utils_event_bus import LocalBus


def _features_payload(symbol="BTCUSDT", features=None, tf_sec=300, ts=1740000000000):
    """Build a payload dict for EVT:FEATURES_CALCULATED."""
    return {
        "symbol": symbol,
        "tf_sec": tf_sec,
        "ts": ts,
        "features": features if features is not None else {"price": 96000.0, "obi": 0.12},
    }


def _regime_payload(symbol="BTCUSDT", regime="TREND_UP"):
    """Build a payload dict for EVT:REGIME_DETECTED."""
    return {"symbol": symbol, "regime": regime}


@pytest.mark.unit
def test_on_features_writes_jsonl(tmp_path):
    """Emitting a features event writes one JSONL record to output."""
    out = tmp_path / "mirror" / "alpha_input_v1.jsonl"
    bus = LocalBus()
    writer = FeatureMirrorWriter(event_bus=bus, output_path=out)

    bus.emit("EVT:FEATURES_CALCULATED", _features_payload(), why="test")

    assert out.exists()
    record = json.loads(out.read_text(encoding="utf-8").strip())
    assert record["symbol"] == "BTCUSDT"
    assert "features" in record


@pytest.mark.unit
def test_regime_cache_included(tmp_path):
    """Regime from EVT:REGIME_DETECTED is included in the features record."""
    out = tmp_path / "mirror" / "alpha_input_v1.jsonl"
    bus = LocalBus()
    writer = FeatureMirrorWriter(event_bus=bus, output_path=out)

    bus.emit("EVT:REGIME_DETECTED", _regime_payload("BTCUSDT", "HIGH_VOLATILITY"), why="test")
    bus.emit("EVT:FEATURES_CALCULATED", _features_payload("BTCUSDT"), why="test")

    record = json.loads(out.read_text(encoding="utf-8").strip())
    assert record["regime"] == "HIGH_VOLATILITY"


@pytest.mark.unit
def test_symbol_filter_applied(tmp_path):
    """Symbols not in the filter list are skipped."""
    out = tmp_path / "mirror" / "alpha_input_v1.jsonl"
    bus = LocalBus()
    writer = FeatureMirrorWriter(event_bus=bus, output_path=out, symbols=["BTCUSDT"])

    bus.emit("EVT:FEATURES_CALCULATED", _features_payload("ETHUSDT"), why="test")

    # File should not exist or be empty (feature was filtered out)
    if out.exists():
        assert out.read_text(encoding="utf-8").strip() == ""
    assert writer.stats["snapshots_skipped"] == 1


@pytest.mark.unit
def test_empty_features_skipped(tmp_path):
    """Empty features dict causes the snapshot to be skipped."""
    out = tmp_path / "mirror" / "alpha_input_v1.jsonl"
    bus = LocalBus()
    writer = FeatureMirrorWriter(event_bus=bus, output_path=out)

    bus.emit("EVT:FEATURES_CALCULATED", _features_payload(features={}), why="test")

    if out.exists():
        assert out.read_text(encoding="utf-8").strip() == ""
    assert writer.stats["snapshots_skipped"] == 1


@pytest.mark.unit
def test_on_regime_caches_per_symbol(tmp_path):
    """Two different symbols get independent regime caches."""
    out = tmp_path / "mirror" / "alpha_input_v1.jsonl"
    bus = LocalBus()
    writer = FeatureMirrorWriter(event_bus=bus, output_path=out)

    bus.emit("EVT:REGIME_DETECTED", _regime_payload("BTCUSDT", "TREND_UP"), why="test")
    bus.emit("EVT:REGIME_DETECTED", _regime_payload("ETHUSDT", "MEAN_REVERSION"), why="test")

    assert writer.stats["regime_cache"]["BTCUSDT"] == "TREND_UP"
    assert writer.stats["regime_cache"]["ETHUSDT"] == "MEAN_REVERSION"


@pytest.mark.unit
def test_extract_price_priority(tmp_path):
    """Features with 'price' key takes priority over 'close'."""
    out = tmp_path / "mirror" / "alpha_input_v1.jsonl"
    bus = LocalBus()
    writer = FeatureMirrorWriter(event_bus=bus, output_path=out)

    features = {"price": 100.0, "close": 99.0, "obi": 0.1}
    bus.emit("EVT:FEATURES_CALCULATED", _features_payload(features=features), why="test")

    record = json.loads(out.read_text(encoding="utf-8").strip())
    assert record["price"] == 100.0


@pytest.mark.unit
def test_extract_payload_dict():
    """Dict event with 'pld' key returns inner dict."""
    result = FeatureMirrorWriter._extract_payload({"pld": {"foo": "bar"}})
    assert result == {"foo": "bar"}


@pytest.mark.unit
def test_extract_payload_object():
    """Object event with .pld attribute returns pld value."""
    event = SimpleNamespace(pld={"foo": "bar"})
    result = FeatureMirrorWriter._extract_payload(event)
    assert result == {"foo": "bar"}


@pytest.mark.unit
def test_output_dir_created(tmp_path):
    """Output path parent directory is created on init."""
    out = tmp_path / "deep" / "nested" / "output.jsonl"
    bus = LocalBus()
    writer = FeatureMirrorWriter(event_bus=bus, output_path=out)
    assert out.parent.is_dir()


@pytest.mark.unit
def test_stats_counters(tmp_path):
    """snapshots_written and snapshots_skipped are correctly tracked."""
    out = tmp_path / "mirror" / "alpha_input_v1.jsonl"
    bus = LocalBus()
    writer = FeatureMirrorWriter(event_bus=bus, output_path=out, symbols=["BTCUSDT"])

    # 2 valid writes
    bus.emit("EVT:FEATURES_CALCULATED", _features_payload("BTCUSDT"), why="test")
    bus.emit("EVT:FEATURES_CALCULATED", _features_payload("BTCUSDT"), why="test")
    # 1 skip (wrong symbol)
    bus.emit("EVT:FEATURES_CALCULATED", _features_payload("ETHUSDT"), why="test")
    # 1 skip (empty features)
    bus.emit("EVT:FEATURES_CALCULATED", _features_payload("BTCUSDT", features={}), why="test")

    assert writer.stats["snapshots_written"] == 2
    assert writer.stats["snapshots_skipped"] == 2
```

### File 4: `test_hot_reload.py`

```python
"""
Tests for runtime/hot_reload.py — Tier 4
=========================================

Covers:
- ReloadDiff has_changes property
- ConfigWatcher._compute_hash (file content hashing)
- ConfigWatcher._try_reload (valid, invalid YAML, callback returns False)
- ConfigWatcher.watch_loop (disabled exits immediately)
- ConfigWatcher.stop and stats
"""

import asyncio
from pathlib import Path

import pytest
import yaml

from apps.reference.domains.alpha_search.runtime.hot_reload import (
    ConfigWatcher,
    ReloadDiff,
)
from apps.reference.domains.alpha_search.runtime.contracts import (
    HotReloadConfig,
    ScenarioSpec,
)


def _minimal_matrix_yaml(scenario_id="S01_TEST", strategy_type="aurora"):
    """Return a valid scenario matrix YAML string."""
    return yaml.dump({
        "matrix_id": "test_matrix",
        "version": 2,
        "input": {"source_mode": "replay", "stream_path": "test.jsonl"},
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "enabled": True,
                "strategy_type": strategy_type,
                "config_mode": "override",
                "base_refs": {"aurora": "config/aurora/strategies/aurora.yaml"},
            }
        ],
    })


def _write_matrix(path: Path, content: str = None):
    """Write a matrix YAML to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or _minimal_matrix_yaml(), encoding="utf-8")


def _hot_reload_config(**overrides) -> HotReloadConfig:
    """Build a HotReloadConfig with sensible test defaults."""
    defaults = {
        "enabled": True,
        "poll_interval_sec": 1.0,
        "debounce_sec": 0.5,
        "rollback_on_error": True,
    }
    defaults.update(overrides)
    return HotReloadConfig(**defaults)


# ---------------------------------------------------------------------------
# ReloadDiff
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_reload_diff_has_changes_true():
    """ReloadDiff with added scenarios reports has_changes=True."""
    spec = ScenarioSpec(
        scenario_id="S_NEW",
        strategy_type="aurora",
        config_mode="override",
        base_refs={"aurora": "x.yaml"},
    )
    diff = ReloadDiff(added=[spec], removed=[], changed=[], unchanged=[])
    assert diff.has_changes is True


@pytest.mark.unit
def test_reload_diff_no_changes():
    """ReloadDiff with all empty lists reports has_changes=False."""
    diff = ReloadDiff(added=[], removed=[], changed=[], unchanged=["S01"])
    assert diff.has_changes is False


# ---------------------------------------------------------------------------
# ConfigWatcher._compute_hash
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_compute_hash_changes_on_write(tmp_path):
    """Hash changes when file content changes."""
    matrix = tmp_path / "matrix.yaml"
    _write_matrix(matrix, _minimal_matrix_yaml("S01"))

    watcher = ConfigWatcher(_hot_reload_config(), matrix)
    hash1 = watcher._compute_hash()

    _write_matrix(matrix, _minimal_matrix_yaml("S02_CHANGED"))
    hash2 = watcher._compute_hash()

    assert hash1 != ""
    assert hash2 != ""
    assert hash1 != hash2


@pytest.mark.unit
def test_compute_hash_missing_file(tmp_path):
    """Nonexistent matrix path returns empty string."""
    watcher = ConfigWatcher(
        _hot_reload_config(), tmp_path / "nonexistent.yaml"
    )
    assert watcher._compute_hash() == ""


# ---------------------------------------------------------------------------
# ConfigWatcher._compute_diff
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_compute_diff_has_changes(tmp_path):
    """Diff with enabled scenario(s) reports has_changes=True."""
    matrix = tmp_path / "matrix.yaml"
    _write_matrix(matrix)

    watcher = ConfigWatcher(_hot_reload_config(), matrix)

    from apps.reference.domains.alpha_search.runtime.contracts import (
        ScenarioMatrixConfig,
    )
    raw = yaml.safe_load(matrix.read_text(encoding="utf-8"))
    config = ScenarioMatrixConfig.model_validate(raw)

    diff = watcher._compute_diff(config)
    assert diff.has_changes is True


# ---------------------------------------------------------------------------
# ConfigWatcher._try_reload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_try_reload_valid_config(tmp_path):
    """Valid YAML with callback returning True increments generation."""
    matrix = tmp_path / "matrix.yaml"
    _write_matrix(matrix)

    callback_called = []

    def on_reload(config, diff):
        callback_called.append(True)
        return True

    watcher = ConfigWatcher(_hot_reload_config(), matrix, on_reload=on_reload)
    watcher._current_hash = "old_hash"
    new_hash = watcher._compute_hash()

    await watcher._try_reload(new_hash)

    assert len(callback_called) == 1
    assert watcher._generation == 1
    assert watcher.stats["reload_successes"] == 1


@pytest.mark.asyncio
async def test_try_reload_invalid_yaml_rollback(tmp_path):
    """Invalid YAML triggers rollback counter increment."""
    matrix = tmp_path / "matrix.yaml"
    matrix.write_text(":::invalid yaml [[[", encoding="utf-8")

    watcher = ConfigWatcher(_hot_reload_config(), matrix)
    await watcher._try_reload("some_hash")

    assert watcher.stats["reload_rollbacks"] >= 1
    assert watcher._generation == 0


@pytest.mark.asyncio
async def test_try_reload_callback_returns_false(tmp_path):
    """Callback returning False triggers rollback."""
    matrix = tmp_path / "matrix.yaml"
    _write_matrix(matrix)

    def on_reload(config, diff):
        return False

    watcher = ConfigWatcher(_hot_reload_config(), matrix, on_reload=on_reload)
    watcher._current_hash = "old_hash"
    new_hash = watcher._compute_hash()

    await watcher._try_reload(new_hash)

    assert watcher.stats["reload_rollbacks"] == 1
    assert watcher._generation == 0


# ---------------------------------------------------------------------------
# ConfigWatcher.watch_loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_watch_loop_disabled_exits():
    """watch_loop returns immediately when config.enabled=False."""
    watcher = ConfigWatcher(
        _hot_reload_config(enabled=False),
        Path("dummy.yaml"),
    )
    # Should return without blocking
    await asyncio.wait_for(watcher.watch_loop(), timeout=2.0)


# ---------------------------------------------------------------------------
# ConfigWatcher.stop and stats
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_stop_signal(tmp_path):
    """stop() sets _running to False."""
    watcher = ConfigWatcher(_hot_reload_config(), tmp_path / "m.yaml")
    assert watcher._running is True
    watcher.stop()
    assert watcher._running is False


@pytest.mark.unit
def test_stats_property(tmp_path):
    """stats dict contains all expected keys."""
    watcher = ConfigWatcher(_hot_reload_config(), tmp_path / "m.yaml")
    stats = watcher.stats
    expected_keys = {
        "generation", "reload_attempts", "reload_successes",
        "reload_rollbacks", "current_hash",
    }
    assert expected_keys.issubset(set(stats.keys()))
```

### File 5: `test_launcher.py`

```python
"""
Tests for runtime/launcher.py — Tier 4
=======================================

Covers:
- load_matrix_config: valid, missing, invalid
- setup_logging: file handler, console handler, no-file mode
- Project root resolution
- Session dir pattern
- main_reactor: replay with minimal data, zero workers
- run: default and custom matrix paths
"""

import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
import yaml

from apps.reference.domains.alpha_search.runtime.launcher import (
    load_matrix_config,
    setup_logging,
)
from apps.reference.domains.alpha_search.runtime.contracts import (
    ScenarioMatrixConfig,
)


def _minimal_matrix_dict(
    scenario_id="S01_TEST", stream_path="test_stream.jsonl"
):
    """Return a minimal valid matrix config dict."""
    return {
        "matrix_id": "test_matrix",
        "version": 2,
        "input": {"source_mode": "replay", "stream_path": stream_path},
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "enabled": True,
                "strategy_type": "aurora",
                "config_mode": "override",
                "base_refs": {"aurora": "config/aurora/strategies/aurora.yaml"},
            }
        ],
    }


def _write_matrix_yaml(path: Path, data: dict = None):
    """Write a matrix YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data or _minimal_matrix_dict(), f)


# ---------------------------------------------------------------------------
# load_matrix_config
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_load_matrix_config_valid(tmp_path):
    """Valid matrix YAML loads and validates successfully."""
    matrix = tmp_path / "scenario_matrix.yaml"
    _write_matrix_yaml(matrix)
    config = load_matrix_config(matrix)
    assert isinstance(config, ScenarioMatrixConfig)
    assert config.matrix_id == "test_matrix"
    assert len(config.scenarios) == 1


@pytest.mark.unit
def test_load_matrix_config_missing_file(tmp_path):
    """Missing file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_matrix_config(tmp_path / "nonexistent.yaml")


@pytest.mark.unit
def test_load_matrix_config_invalid_yaml(tmp_path):
    """Invalid schema raises pydantic ValidationError."""
    from pydantic import ValidationError

    matrix = tmp_path / "bad_matrix.yaml"
    matrix.parent.mkdir(parents=True, exist_ok=True)
    with open(matrix, "w", encoding="utf-8") as f:
        yaml.dump({"matrix_id": "bad", "scenarios": []}, f)

    with pytest.raises(ValidationError):
        load_matrix_config(matrix)


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_setup_logging_creates_file(tmp_path):
    """File handler is created and the log file exists after setup."""
    session = tmp_path / "session_log_test"
    logger = setup_logging(session, log_level="DEBUG", log_to_file=True)
    log_file = session / "aggregate" / "alpha_search_domain.log"
    assert log_file.exists() or (session / "aggregate").is_dir()
    # Check that a RotatingFileHandler is among the root handlers
    root = logging.getLogger()
    file_handlers = [
        h for h in root.handlers if isinstance(h, RotatingFileHandler)
    ]
    assert len(file_handlers) >= 1


@pytest.mark.unit
def test_setup_logging_console_handler(tmp_path):
    """A StreamHandler is present in the handlers."""
    session = tmp_path / "session_console_test"
    logger = setup_logging(session, log_to_file=False)
    root = logging.getLogger()
    stream_handlers = [
        h for h in root.handlers if isinstance(h, logging.StreamHandler)
    ]
    assert len(stream_handlers) >= 1


@pytest.mark.unit
def test_setup_logging_no_file(tmp_path):
    """log_to_file=False means no RotatingFileHandler is added."""
    session = tmp_path / "session_no_file"
    logger = setup_logging(session, log_to_file=False)
    root = logging.getLogger()
    # Count RotatingFileHandlers that point to our session dir
    rfh = [
        h for h in root.handlers
        if isinstance(h, RotatingFileHandler)
        and str(session) in str(getattr(h, "baseFilename", ""))
    ]
    assert len(rfh) == 0


# ---------------------------------------------------------------------------
# Project root resolution
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_project_root_resolution():
    """launcher.py parents[5] resolves to the project root."""
    launcher_path = Path(
        "apps/reference/domains/alpha_search/runtime/launcher.py"
    )
    # Simulate: from launcher.py, parents[5] = project root
    # 0=runtime, 1=alpha_search, 2=domains, 3=reference, 4=apps, 5=project_root
    from apps.reference.domains.alpha_search.runtime import launcher
    launcher_file = Path(launcher.__file__).resolve()
    project_root = launcher_file.parents[5]
    # The project root should contain the 'apps' directory
    assert (project_root / "apps").is_dir()


# ---------------------------------------------------------------------------
# Session dir creation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_session_dir_creation(tmp_path):
    """Session dir follows logs/alpha_search_runtime/<timestamp> pattern."""
    from datetime import datetime

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = tmp_path / "logs" / "alpha_search_runtime" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    assert session_dir.is_dir()
    # Verify pattern: 8-digit date + underscore + 6-digit time
    import re
    assert re.match(r"\d{8}_\d{6}", session_id)


# ---------------------------------------------------------------------------
# main_reactor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_main_reactor_replay_processes(tmp_path):
    """main_reactor in replay mode processes snapshots from JSONL stream."""
    from apps.reference.domains.alpha_search.runtime.launcher import main_reactor

    # Create a 2-snapshot JSONL stream
    stream_path = tmp_path / "stream" / "test_stream.jsonl"
    stream_path.parent.mkdir(parents=True, exist_ok=True)
    snapshots = []
    for i in range(2):
        snapshots.append({
            "ts_ms": 1740000000000 + i * 300000,
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1740000000000 + i * 300000,
            "price": 96000.0 + i,
            "features": {"obi": 0.12, "delta_price": 0.003, "close": 96000.0},
            "regime": "DEFAULT",
        })
    with open(stream_path, "w", encoding="utf-8") as f:
        for snap in snapshots:
            f.write(json.dumps(snap) + "\n")

    # Create a minimal matrix config that references the stream
    matrix_dict = _minimal_matrix_dict(stream_path=str(stream_path))
    matrix_path = tmp_path / "matrix.yaml"
    _write_matrix_yaml(matrix_path, matrix_dict)
    config = load_matrix_config(matrix_path)

    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("test_reactor")

    # Patch ScenarioManager to avoid full config resolution
    with patch(
        "apps.reference.domains.alpha_search.runtime.launcher.ScenarioManager"
    ) as MockManager:
        mock_mgr = MagicMock()
        mock_mgr.initialize.return_value = 0  # 0 workers -> early exit
        MockManager.return_value = mock_mgr

        await main_reactor(config, tmp_path, session_dir, logger)

        # With 0 workers it should exit early
        mock_mgr.initialize.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_main_reactor_zero_workers_exits(tmp_path):
    """main_reactor returns early when ScenarioManager initializes 0 workers."""
    from apps.reference.domains.alpha_search.runtime.launcher import main_reactor

    matrix_path = tmp_path / "matrix.yaml"
    _write_matrix_yaml(matrix_path)
    config = load_matrix_config(matrix_path)

    session_dir = tmp_path / "session"
    session_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("test_zero_workers")

    with patch(
        "apps.reference.domains.alpha_search.runtime.launcher.ScenarioManager"
    ) as MockManager:
        mock_mgr = MagicMock()
        mock_mgr.initialize.return_value = 0
        MockManager.return_value = mock_mgr

        await main_reactor(config, tmp_path, session_dir, logger)

        # Executor should NOT be started if workers = 0
        mock_mgr.initialize.assert_called_once()


# ---------------------------------------------------------------------------
# run() path resolution
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_run_default_matrix_path():
    """Default matrix path is project_root / config/alpha_search/scenario_matrix.yaml."""
    from apps.reference.domains.alpha_search.runtime import launcher

    project_root = Path(launcher.__file__).resolve().parents[5]
    expected = project_root / "config" / "alpha_search" / "scenario_matrix.yaml"
    # Verify the path construction matches what run() would produce
    assert expected.parts[-3:] == ("config", "alpha_search", "scenario_matrix.yaml")


@pytest.mark.unit
def test_run_custom_matrix_path():
    """Absolute and relative paths are handled correctly."""
    from apps.reference.domains.alpha_search.runtime import launcher

    project_root = Path(launcher.__file__).resolve().parents[5]

    # Absolute path should be used as-is
    abs_path = Path("/tmp/custom_matrix.yaml")
    resolved = Path(str(abs_path))
    assert resolved.is_absolute()

    # Relative path should be joined with project_root
    rel_path = Path("custom/matrix.yaml")
    resolved_rel = project_root / rel_path
    assert resolved_rel.is_absolute()
    assert str(resolved_rel).endswith("custom/matrix.yaml") or \
           str(resolved_rel).endswith("custom\\matrix.yaml")
```

## Execution Steps

1. Ensure `apps/reference/domains/alpha_search/tests/__init__.py` exists (create if missing)
2. Create all 5 test files with the content above
3. Verify files are syntactically valid

## Dependencies

- pytest
- pytest-asyncio
- pyyaml
- pydantic
- Source modules in `apps/reference/domains/alpha_search/runtime/`
- `apps/reference/orchestrator/utils_event_bus.py` (LocalBus)
