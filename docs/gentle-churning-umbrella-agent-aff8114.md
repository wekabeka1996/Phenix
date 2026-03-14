# Plan: Create Four Tier 3 Alpha Search Test Files

## Summary
Create 4 test files (50 total tests) for the alpha_search runtime tier 3 test plan, targeting `executor.py`, `backpressure.py`, `health.py`, and `ingest.py`.

## Source Files Reviewed
- `apps/reference/domains/alpha_search/runtime/executor.py` - ScenarioExecutor class
- `apps/reference/domains/alpha_search/runtime/backpressure.py` - BoundedIngestQueue class
- `apps/reference/domains/alpha_search/runtime/health.py` - HealthMonitor class
- `apps/reference/domains/alpha_search/runtime/ingest.py` - IngestGateway class
- `apps/reference/domains/alpha_search/runtime/contracts.py` - RuntimeConfig, AlphaInputV1
- `apps/reference/domains/alpha_search/tests/conftest.py` - Existing fixtures/patterns

## Key Observations from Source Code
1. **ScenarioExecutor**: Uses `worker.process_snapshot(snapshot)` interface. Thread pool fallback to sequential if `_pool` is None. Stats tracking for dispatches/timeouts/errors. TimeoutError (builtin) stored in results dict.
2. **BoundedIngestQueue**: Uses `collections.deque` with `threading.Lock`. drop_oldest uses `maxlen`, drop_newest/block use unbounded deque. Stats dict includes `utilization_pct`.
3. **HealthMonitor**: `CONSECUTIVE_FAILURE_THRESHOLD = 3`. Uses `time.time()` for heartbeats. `check_health` returns "unknown" for never-seen workers. Stats dict has keys: total_checks, total_degradations, currently_degraded, heartbeat_ages.
4. **IngestGateway**: Takes `Path` for stream_path. `iter_replay()` is sync iterator. `iter_live_tail()` is async iterator. `_parse_line` uses `AlphaInputV1.model_validate()`.

## Existing Patterns (from conftest.py and existing tests)
- `@pytest.mark.unit` decorator on all unit tests
- `make_snapshot()` helper in conftest for creating valid snapshot dicts
- `write_jsonl_file(path, records)` helper in conftest
- `runtime_config_sequential` and `runtime_config_parallel` fixtures available
- Import style: `from apps.reference.domains.alpha_search.runtime.contracts import ...`
- Tests use class groupings with `@pytest.mark.unit` on class

## Files to Create

### File 1: `apps/reference/domains/alpha_search/tests/test_executor.py` (16 tests)
- MockWorker helper (results, error, delay)
- Uses RuntimeConfig for sequential and thread_pool configs
- Uses MagicMock() for snapshot in most tests (executor just passes it through)
- Tests cover: sequential execution, parallel execution, error isolation, timeout handling, pool lifecycle, stats, fallback behavior

### File 2: `apps/reference/domains/alpha_search/tests/test_backpressure.py` (14 tests)
- Uses MagicMock() as queue items (queue is type-agnostic at runtime)
- Tests cover: FIFO ordering, drop_oldest policy, drop_newest policy, block policy, get_batch, stats/utilization, thread safety

### File 3: `apps/reference/domains/alpha_search/tests/test_health_monitor.py` (12 tests)
- Uses RuntimeConfig for config
- Uses `time.time()` manipulation via monkeypatch or time.sleep for stale checks
- Tests cover: heartbeat tracking, failure counting, degradation threshold, auto-recovery, check_health states, stats

### File 4: `apps/reference/domains/alpha_search/tests/test_ingest_gateway.py` (8 tests)
- Uses `tmp_path` fixture and `write_jsonl_file` from conftest
- Uses valid JSONL lines matching AlphaInputV1 schema
- Tests 1-6 sync (`@pytest.mark.unit`), tests 7-8 async (`@pytest.mark.asyncio`)
- Tests cover: valid replay, invalid JSON skip, schema validation skip, empty lines, missing file, stats, live tail follow, live tail wait

---

## Detailed File Contents

### File 1: test_executor.py

```python
"""
Unit tests for ScenarioExecutor.

Tests apps/reference/domains/alpha_search/runtime/executor.py:
  ScenarioExecutor: parallel/sequential fan-out, timeout handling,
  error isolation, pool lifecycle, stats tracking.

16 tests, all marked @pytest.mark.unit.
"""

import time
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.alpha_search.runtime.contracts import RuntimeConfig
from apps.reference.domains.alpha_search.runtime.executor import ScenarioExecutor


# ---------------------------------------------------------------------------
# Mock worker
# ---------------------------------------------------------------------------

class MockWorker:
    """Lightweight mock that implements process_snapshot interface."""

    def __init__(self, results=None, error=None, delay=0):
        self.results = results or [{"score": 0.1}]
        self.error = error
        self.delay = delay

    def process_snapshot(self, snapshot):
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.results


def _seq_config(**overrides) -> RuntimeConfig:
    """RuntimeConfig for sequential execution."""
    kw = dict(parallelism="sequential", max_workers=1, scenario_timeout_sec=5.0)
    kw.update(overrides)
    return RuntimeConfig(**kw)


def _par_config(**overrides) -> RuntimeConfig:
    """RuntimeConfig for thread_pool execution."""
    kw = dict(parallelism="thread_pool", max_workers=4, scenario_timeout_sec=5.0)
    kw.update(overrides)
    return RuntimeConfig(**kw)


# ==========================================================================
# Tests
# ==========================================================================

@pytest.mark.unit
class TestScenarioExecutor:

    # -- Sequential -----------------------------------------------------------

    def test_sequential_execution_all_workers(self):
        """All 3 sequential workers return results successfully."""
        executor = ScenarioExecutor(_seq_config())
        workers = {
            "S01": MockWorker(results=[{"score": 0.1}]),
            "S02": MockWorker(results=[{"score": 0.2}]),
            "S03": MockWorker(results=[{"score": 0.3}]),
        }
        snap = MagicMock()
        results = executor.execute_all(workers, snap)

        assert len(results) == 3
        for sid in ("S01", "S02", "S03"):
            assert isinstance(results[sid], list)
        assert results["S01"][0]["score"] == 0.1

    def test_sequential_worker_error_isolated(self):
        """One worker raises, others succeed -- error isolated per worker."""
        executor = ScenarioExecutor(_seq_config())
        workers = {
            "S01": MockWorker(results=[{"score": 0.1}]),
            "S02": MockWorker(error=ValueError("boom")),
            "S03": MockWorker(results=[{"score": 0.3}]),
        }
        snap = MagicMock()
        results = executor.execute_all(workers, snap)

        assert len(results) == 3
        assert isinstance(results["S01"], list)
        assert isinstance(results["S02"], Exception)
        assert isinstance(results["S03"], list)

    def test_sequential_timeout_warning(self, caplog):
        """Slow worker exceeding timeout gets logged but result still returned."""
        cfg = _seq_config(scenario_timeout_sec=0.05)
        executor = ScenarioExecutor(cfg)
        workers = {"S01": MockWorker(delay=0.1)}
        snap = MagicMock()

        import logging
        with caplog.at_level(logging.WARNING):
            results = executor.execute_all(workers, snap)

        # Result still returned despite exceeding timeout (sequential just warns)
        assert isinstance(results["S01"], list)
        assert "exceeded timeout" in caplog.text

    # -- Parallel -------------------------------------------------------------

    def test_parallel_execution_all_workers(self):
        """Thread pool mode: 3 workers all return results."""
        executor = ScenarioExecutor(_par_config())
        executor.start()
        try:
            workers = {
                "S01": MockWorker(results=[{"score": 0.1}]),
                "S02": MockWorker(results=[{"score": 0.2}]),
                "S03": MockWorker(results=[{"score": 0.3}]),
            }
            snap = MagicMock()
            results = executor.execute_all(workers, snap)

            assert len(results) == 3
            for sid in ("S01", "S02", "S03"):
                assert isinstance(results[sid], list)
        finally:
            executor.shutdown()

    def test_parallel_worker_error_isolated(self):
        """Thread pool: 1 raises, 2 succeed -- errors isolated."""
        executor = ScenarioExecutor(_par_config())
        executor.start()
        try:
            workers = {
                "S01": MockWorker(results=[{"score": 0.1}]),
                "S02": MockWorker(error=RuntimeError("fail")),
                "S03": MockWorker(results=[{"score": 0.3}]),
            }
            snap = MagicMock()
            results = executor.execute_all(workers, snap)

            assert isinstance(results["S01"], list)
            assert isinstance(results["S02"], Exception)
            assert isinstance(results["S03"], list)
        finally:
            executor.shutdown()

    def test_parallel_timeout_returns_timeout_error(self):
        """Worker exceeding timeout produces TimeoutError in results."""
        cfg = _par_config(scenario_timeout_sec=0.1)
        executor = ScenarioExecutor(cfg)
        executor.start()
        try:
            workers = {"S01": MockWorker(delay=5.0)}
            snap = MagicMock()
            results = executor.execute_all(workers, snap)

            assert isinstance(results["S01"], TimeoutError)
        finally:
            executor.shutdown()

    def test_parallel_fallback_to_sequential(self):
        """thread_pool mode without start() falls back to sequential execution."""
        executor = ScenarioExecutor(_par_config())
        # Deliberately NOT calling start()
        workers = {
            "S01": MockWorker(results=[{"score": 0.1}]),
            "S02": MockWorker(results=[{"score": 0.2}]),
        }
        snap = MagicMock()
        results = executor.execute_all(workers, snap)

        # Should still work via sequential fallback
        assert len(results) == 2
        assert isinstance(results["S01"], list)

    # -- Lifecycle ------------------------------------------------------------

    def test_start_creates_pool(self):
        """After start(), _pool is not None for thread_pool mode."""
        executor = ScenarioExecutor(_par_config())
        assert executor._pool is None
        executor.start()
        assert executor._pool is not None
        executor.shutdown()

    def test_start_sequential_no_pool(self):
        """Sequential mode start() does not create a pool."""
        executor = ScenarioExecutor(_seq_config())
        executor.start()
        assert executor._pool is None

    def test_shutdown_pool(self):
        """After shutdown, pool is no longer usable."""
        executor = ScenarioExecutor(_par_config())
        executor.start()
        pool_ref = executor._pool
        executor.shutdown()
        # ThreadPoolExecutor._shutdown is True after shutdown()
        assert pool_ref._shutdown is True

    # -- Stats ----------------------------------------------------------------

    def test_stats_counters(self):
        """Stats reflect dispatches, timeouts, errors correctly."""
        executor = ScenarioExecutor(_seq_config())
        workers_ok = {"S01": MockWorker()}
        workers_err = {"S01": MockWorker(error=ValueError("e"))}
        snap = MagicMock()

        executor.execute_all(workers_ok, snap)
        executor.execute_all(workers_err, snap)

        st = executor.stats
        assert st["total_dispatches"] == 2
        assert st["total_errors"] == 1

    def test_execute_all_increments_counter(self):
        """Each execute_all call increments _total_dispatches."""
        executor = ScenarioExecutor(_seq_config())
        snap = MagicMock()
        workers = {"S01": MockWorker()}

        for _ in range(5):
            executor.execute_all(workers, snap)

        assert executor.stats["total_dispatches"] == 5

    def test_parallel_respects_max_workers(self):
        """Pool._max_workers matches config max_workers."""
        cfg = _par_config(max_workers=7)
        executor = ScenarioExecutor(cfg)
        executor.start()
        assert executor._pool._max_workers == 7
        executor.shutdown()

    def test_parallel_mixed_results(self):
        """Mixed success/error results associated correctly by scenario_id."""
        executor = ScenarioExecutor(_par_config())
        executor.start()
        try:
            workers = {
                "S01": MockWorker(results=[{"score": 0.5}]),
                "S02": MockWorker(error=ValueError("bad")),
                "S03": MockWorker(results=[{"score": 0.9}]),
                "S04": MockWorker(error=TypeError("type")),
            }
            snap = MagicMock()
            results = executor.execute_all(workers, snap)

            assert isinstance(results["S01"], list)
            assert isinstance(results["S02"], ValueError)
            assert isinstance(results["S03"], list)
            assert isinstance(results["S04"], TypeError)
        finally:
            executor.shutdown()

    def test_sequential_large_batch(self):
        """20 mock workers all succeed in sequential mode."""
        executor = ScenarioExecutor(_seq_config())
        workers = {f"S{i:02d}": MockWorker(results=[{"score": i * 0.01}]) for i in range(20)}
        snap = MagicMock()
        results = executor.execute_all(workers, snap)

        assert len(results) == 20
        assert all(isinstance(v, list) for v in results.values())

    def test_shutdown_idempotent(self):
        """Double shutdown does not crash."""
        executor = ScenarioExecutor(_par_config())
        executor.start()
        executor.shutdown()
        executor.shutdown()  # Should not raise
```

### File 2: test_backpressure.py

```python
"""
Unit tests for BoundedIngestQueue.

Tests apps/reference/domains/alpha_search/runtime/backpressure.py:
  BoundedIngestQueue: FIFO ordering, overflow policies (drop_oldest,
  drop_newest, block), get_batch, stats, thread safety.

14 tests, all marked @pytest.mark.unit.
"""

import threading
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.alpha_search.runtime.backpressure import BoundedIngestQueue


# ==========================================================================
# Tests
# ==========================================================================

@pytest.mark.unit
class TestBoundedIngestQueue:

    def test_put_get_fifo(self):
        """Items dequeued in FIFO order: put A, B, C -> get A, B, C."""
        q = BoundedIngestQueue(maxsize=10, policy="drop_oldest")
        items = ["A", "B", "C"]
        for item in items:
            q.put(item)

        assert q.get() == "A"
        assert q.get() == "B"
        assert q.get() == "C"

    def test_drop_oldest_policy(self):
        """drop_oldest with maxsize=3: put 5 items -> only last 3 remain."""
        q = BoundedIngestQueue(maxsize=3, policy="drop_oldest")
        for i in range(5):
            q.put(f"item_{i}")

        assert q.size == 3
        assert q.get() == "item_2"
        assert q.get() == "item_3"
        assert q.get() == "item_4"

    def test_drop_oldest_stats(self):
        """drop_oldest: stats.total_dropped incremented when items evicted."""
        q = BoundedIngestQueue(maxsize=2, policy="drop_oldest")
        for i in range(5):
            q.put(f"item_{i}")

        st = q.stats
        assert st["total_dropped"] == 3
        assert st["total_put"] == 5

    def test_drop_newest_policy(self):
        """drop_newest with maxsize=3: 4th item rejected, first 3 remain."""
        q = BoundedIngestQueue(maxsize=3, policy="drop_newest")
        for i in range(4):
            q.put(f"item_{i}")

        assert q.size == 3
        assert q.get() == "item_0"
        assert q.get() == "item_1"
        assert q.get() == "item_2"

    def test_drop_newest_returns_false(self):
        """drop_newest put() returns False when full."""
        q = BoundedIngestQueue(maxsize=2, policy="drop_newest")
        assert q.put("a") is True
        assert q.put("b") is True
        assert q.put("c") is False

    def test_block_policy_no_limit(self):
        """block policy accepts all items (no upper bound)."""
        q = BoundedIngestQueue(maxsize=10, policy="block")
        for i in range(10000):
            assert q.put(f"item_{i}") is True
        assert q.size == 10000

    def test_get_empty_returns_none(self):
        """get() on empty queue returns None."""
        q = BoundedIngestQueue(maxsize=10, policy="drop_oldest")
        assert q.get() is None

    def test_get_batch_up_to_max(self):
        """get_batch(3) with 5 items returns 3, leaving 2."""
        q = BoundedIngestQueue(maxsize=10, policy="drop_oldest")
        for i in range(5):
            q.put(f"item_{i}")

        batch = q.get_batch(max_items=3)
        assert len(batch) == 3
        assert batch == ["item_0", "item_1", "item_2"]
        assert q.size == 2

    def test_get_batch_empty(self):
        """get_batch on empty queue returns empty list."""
        q = BoundedIngestQueue(maxsize=10, policy="drop_oldest")
        assert q.get_batch(max_items=5) == []

    def test_size_property(self):
        """size reflects current queue length."""
        q = BoundedIngestQueue(maxsize=100, policy="drop_oldest")
        assert q.size == 0
        q.put("a")
        q.put("b")
        assert q.size == 2
        q.get()
        assert q.size == 1

    def test_stats_counters(self):
        """total_put, total_get, total_dropped correct after operations."""
        q = BoundedIngestQueue(maxsize=2, policy="drop_oldest")
        q.put("a")
        q.put("b")
        q.put("c")  # drops "a"
        q.get()      # gets "b"

        st = q.stats
        assert st["total_put"] == 3
        assert st["total_get"] == 1
        assert st["total_dropped"] == 1

    def test_utilization_pct(self):
        """50 items in maxsize=100 -> utilization_pct == 50.0."""
        q = BoundedIngestQueue(maxsize=100, policy="drop_oldest")
        for i in range(50):
            q.put(f"item_{i}")

        assert q.stats["utilization_pct"] == 50.0

    def test_thread_safety(self):
        """4 producers + 2 consumers: no crash and counts consistent."""
        q = BoundedIngestQueue(maxsize=5000, policy="drop_oldest")
        items_per_producer = 500
        errors = []

        def producer(pid):
            try:
                for i in range(items_per_producer):
                    q.put(f"p{pid}_{i}")
            except Exception as e:
                errors.append(e)

        consumed = []
        consumed_lock = threading.Lock()

        def consumer():
            try:
                for _ in range(400):
                    item = q.get()
                    if item is not None:
                        with consumed_lock:
                            consumed.append(item)
            except Exception as e:
                errors.append(e)

        threads = []
        for pid in range(4):
            threads.append(threading.Thread(target=producer, args=(pid,)))
        for _ in range(2):
            threads.append(threading.Thread(target=consumer))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Thread errors: {errors}"
        # Total put should be 4 * 500 = 2000
        assert q.stats["total_put"] == 4 * items_per_producer

    def test_maxsize_drop_oldest_never_exceeds(self):
        """After many puts, size never exceeds maxsize for drop_oldest."""
        q = BoundedIngestQueue(maxsize=10, policy="drop_oldest")
        for i in range(100):
            q.put(f"item_{i}")
            assert q.size <= 10
```

### File 3: test_health_monitor.py

```python
"""
Unit tests for HealthMonitor.

Tests apps/reference/domains/alpha_search/runtime/health.py:
  HealthMonitor: heartbeat tracking, consecutive failure counting,
  degradation threshold, auto-recovery, check_health states, stats.

12 tests, all marked @pytest.mark.unit.
"""

import time
from unittest.mock import patch

import pytest

from apps.reference.domains.alpha_search.runtime.contracts import RuntimeConfig
from apps.reference.domains.alpha_search.runtime.health import HealthMonitor


def _health_config(**overrides) -> RuntimeConfig:
    """RuntimeConfig with health-relevant defaults."""
    kw = dict(health_heartbeat_sec=30.0, memory_budget_mb_per_scenario=50)
    kw.update(overrides)
    return RuntimeConfig(**kw)


# ==========================================================================
# Tests
# ==========================================================================

@pytest.mark.unit
class TestHealthMonitor:

    def test_record_success_updates_heartbeat(self):
        """record_success sets a heartbeat timestamp."""
        hm = HealthMonitor(_health_config())
        hm.record_success("S01")
        assert "S01" in hm._last_heartbeat
        assert hm._last_heartbeat["S01"] > 0

    def test_record_success_resets_failures(self):
        """After 2 failures + 1 success, consecutive failure counter = 0."""
        hm = HealthMonitor(_health_config())
        hm.record_failure("S01")
        hm.record_failure("S01")
        assert hm._consecutive_failures["S01"] == 2
        hm.record_success("S01")
        assert hm._consecutive_failures["S01"] == 0

    def test_record_success_recovers_degraded(self):
        """Degraded scenario + success -> recovered (no longer degraded)."""
        hm = HealthMonitor(_health_config())
        # Push to degraded
        for _ in range(3):
            hm.record_failure("S01")
        assert hm.is_degraded("S01")

        hm.record_success("S01")
        assert not hm.is_degraded("S01")

    def test_record_failure_increments(self):
        """Single failure increments counter to 1."""
        hm = HealthMonitor(_health_config())
        hm.record_failure("S01")
        assert hm._consecutive_failures["S01"] == 1

    def test_degradation_after_3_failures(self):
        """3 consecutive failures -> scenario becomes degraded."""
        hm = HealthMonitor(_health_config())
        for _ in range(3):
            hm.record_failure("S01")
        assert hm.is_degraded("S01")
        assert "S01" in hm.degraded_scenarios

    def test_no_degradation_below_threshold(self):
        """2 failures -> scenario NOT degraded."""
        hm = HealthMonitor(_health_config())
        hm.record_failure("S01")
        hm.record_failure("S01")
        assert not hm.is_degraded("S01")

    def test_is_degraded_true_false(self):
        """is_degraded returns True for degraded, False for healthy."""
        hm = HealthMonitor(_health_config())
        assert not hm.is_degraded("S01")  # never seen = not degraded

        for _ in range(3):
            hm.record_failure("S01")
        assert hm.is_degraded("S01")

        hm.record_success("S02")
        assert not hm.is_degraded("S02")

    def test_check_health_healthy(self):
        """Recent heartbeat -> status 'healthy'."""
        hm = HealthMonitor(_health_config(health_heartbeat_sec=30.0))
        hm.record_success("S01")  # sets heartbeat to now

        statuses = hm.check_health(["S01"])
        assert statuses["S01"] == "healthy"

    def test_check_health_stale(self):
        """Old heartbeat (> 3x heartbeat_sec) -> status 'stale'."""
        hm = HealthMonitor(_health_config(health_heartbeat_sec=10.0))
        # Set heartbeat far in the past
        hm._last_heartbeat["S01"] = time.time() - 100

        statuses = hm.check_health(["S01"])
        assert statuses["S01"] == "stale"

    def test_check_health_degraded(self):
        """Degraded scenario -> status 'degraded' (takes priority over stale)."""
        hm = HealthMonitor(_health_config())
        for _ in range(3):
            hm.record_failure("S01")

        statuses = hm.check_health(["S01"])
        assert statuses["S01"] == "degraded"

    def test_check_health_unknown(self):
        """No heartbeat ever recorded -> status 'unknown'."""
        hm = HealthMonitor(_health_config())
        statuses = hm.check_health(["S01"])
        assert statuses["S01"] == "unknown"

    def test_stats_property(self):
        """Stats dict contains all expected keys."""
        hm = HealthMonitor(_health_config())
        hm.record_success("S01")
        hm.record_failure("S02")

        st = hm.stats
        assert "total_checks" in st
        assert "total_degradations" in st
        assert "currently_degraded" in st
        assert "heartbeat_ages" in st
        assert isinstance(st["currently_degraded"], list)
        assert isinstance(st["heartbeat_ages"], dict)
```

### File 4: test_ingest_gateway.py

```python
"""
Unit tests for IngestGateway.

Tests apps/reference/domains/alpha_search/runtime/ingest.py:
  IngestGateway: replay mode (sync iterator), live_tail mode (async),
  JSON/schema validation, stats tracking.

8 tests (6 sync unit, 2 async).
"""

import asyncio
import json
from pathlib import Path

import pytest

from apps.reference.domains.alpha_search.runtime.ingest import IngestGateway
from apps.reference.domains.alpha_search.tests.conftest import make_snapshot, write_jsonl_file


def _valid_line(**overrides) -> dict:
    """A dict that validates as AlphaInputV1."""
    return make_snapshot(**overrides)


# ==========================================================================
# Sync replay tests
# ==========================================================================

@pytest.mark.unit
class TestIngestReplay:

    def test_replay_valid_jsonl(self, tmp_path):
        """3 valid JSONL lines -> 3 AlphaInputV1 snapshots yielded."""
        records = [_valid_line(price=96000.0 + i) for i in range(3)]
        path = write_jsonl_file(tmp_path / "stream.jsonl", records)

        gw = IngestGateway(stream_path=path, mode="replay")
        snapshots = list(gw.iter_replay())

        assert len(snapshots) == 3
        assert snapshots[0].price == 96000.0
        assert snapshots[2].price == 96002.0

    def test_replay_skips_invalid_json(self, tmp_path):
        """Invalid JSON line is skipped, counter incremented."""
        path = tmp_path / "stream.jsonl"
        lines = [
            json.dumps(_valid_line()),
            "not valid json {{{{",
            json.dumps(_valid_line(price=97000.0)),
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        gw = IngestGateway(stream_path=path, mode="replay")
        snapshots = list(gw.iter_replay())

        assert len(snapshots) == 2
        assert gw.stats["snapshots_rejected"] == 1

    def test_replay_skips_invalid_schema(self, tmp_path):
        """Valid JSON but missing required fields -> skipped."""
        path = tmp_path / "stream.jsonl"
        lines = [
            json.dumps(_valid_line()),
            json.dumps({"foo": "bar"}),  # missing required fields
            json.dumps(_valid_line(price=98000.0)),
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        gw = IngestGateway(stream_path=path, mode="replay")
        snapshots = list(gw.iter_replay())

        assert len(snapshots) == 2
        assert gw.stats["snapshots_rejected"] == 1

    def test_replay_empty_lines_skipped(self, tmp_path):
        """Blank lines are silently ignored."""
        path = tmp_path / "stream.jsonl"
        content = (
            json.dumps(_valid_line()) + "\n"
            + "\n"
            + "   \n"
            + json.dumps(_valid_line(price=99000.0)) + "\n"
        )
        path.write_text(content, encoding="utf-8")

        gw = IngestGateway(stream_path=path, mode="replay")
        snapshots = list(gw.iter_replay())

        assert len(snapshots) == 2

    def test_replay_missing_file(self, tmp_path):
        """Non-existent file -> 0 snapshots, no crash."""
        gw = IngestGateway(
            stream_path=tmp_path / "does_not_exist.jsonl",
            mode="replay",
        )
        snapshots = list(gw.iter_replay())
        assert len(snapshots) == 0

    def test_replay_stats(self, tmp_path):
        """After replay, stats show correct counts."""
        records = [_valid_line(price=96000.0 + i) for i in range(3)]
        path = tmp_path / "stream.jsonl"
        lines = [json.dumps(r) for r in records] + ["bad json"]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        gw = IngestGateway(stream_path=path, mode="replay")
        list(gw.iter_replay())

        st = gw.stats
        assert st["snapshots_read"] == 3
        assert st["snapshots_rejected"] == 1
        assert st["lines_read"] == 4
        assert st["eof_reached"] is True


# ==========================================================================
# Async live tail tests
# ==========================================================================

@pytest.mark.asyncio
class TestIngestLiveTail:

    async def test_live_tail_follows_growing_file(self, tmp_path):
        """Write initial lines, tail them, write more, get more."""
        path = tmp_path / "stream.jsonl"

        # Write initial content
        initial = [_valid_line(price=96000.0 + i) for i in range(2)]
        write_jsonl_file(path, initial)

        gw = IngestGateway(stream_path=path, mode="live_tail", poll_interval_sec=0.05)
        collected = []

        async def consume():
            async for snap in gw.iter_live_tail():
                collected.append(snap)
                if len(collected) >= 4:
                    break

        async def produce():
            await asyncio.sleep(0.15)
            # Append more lines
            with open(path, "a", encoding="utf-8") as f:
                for i in range(2, 4):
                    f.write(json.dumps(_valid_line(price=96000.0 + i)) + "\n")

        try:
            await asyncio.wait_for(
                asyncio.gather(consume(), produce()),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            pass  # Acceptable if we collected enough

        assert len(collected) >= 3  # Should get at least initial + some appended

    async def test_live_tail_waits_on_no_data(self, tmp_path):
        """Empty file: tail returns nothing within short wait period."""
        path = tmp_path / "stream.jsonl"
        path.write_text("", encoding="utf-8")

        gw = IngestGateway(stream_path=path, mode="live_tail", poll_interval_sec=0.05)
        collected = []

        async def consume():
            async for snap in gw.iter_live_tail():
                collected.append(snap)

        try:
            await asyncio.wait_for(consume(), timeout=0.2)
        except asyncio.TimeoutError:
            pass

        assert len(collected) == 0
```

## Execution Steps

1. Create `apps/reference/domains/alpha_search/tests/test_executor.py` with 16 tests
2. Create `apps/reference/domains/alpha_search/tests/test_backpressure.py` with 14 tests
3. Create `apps/reference/domains/alpha_search/tests/test_health_monitor.py` with 12 tests
4. Create `apps/reference/domains/alpha_search/tests/test_ingest_gateway.py` with 8 tests

Total: 50 tests across 4 files.
