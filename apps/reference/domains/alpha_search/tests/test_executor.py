"""
T3: Scenario Executor Tests
============================

Tests for apps/reference/domains/alpha_search/runtime/executor.py
16 tests covering sequential/parallel execution, timeouts, error isolation.
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from apps.reference.domains.alpha_search.runtime.contracts import RuntimeConfig
from apps.reference.domains.alpha_search.runtime.executor import ScenarioExecutor


def _make_executor(parallelism="sequential", max_workers=4, timeout=5.0):
    """Create executor with given config."""
    cfg = RuntimeConfig(
        parallelism=parallelism,
        max_workers=max_workers,
        scenario_timeout_sec=timeout,
    )
    return ScenarioExecutor(cfg)


def _make_mock_workers(count, return_val=None, side_effect=None):
    """Create N mock workers."""
    workers = {}
    for i in range(count):
        w = MagicMock()
        if side_effect:
            w.process_snapshot.side_effect = side_effect
        else:
            w.process_snapshot.return_value = return_val or [{"score": 0.1 * i}]
        workers[f"S{i:02d}"] = w
    return workers


@pytest.mark.unit
class TestSequentialExecution:
    """Tests for sequential execution mode."""

    def test_all_workers_called(self):
        """All workers called and results returned."""
        executor = _make_executor(parallelism="sequential")
        executor.start()

        workers = _make_mock_workers(3)
        snapshot = MagicMock()

        results = executor.execute_all(workers, snapshot)
        assert len(results) == 3
        for w in workers.values():
            w.process_snapshot.assert_called_once_with(snapshot)

        executor.shutdown()

    def test_worker_error_isolated(self):
        """One error doesn't crash others."""
        executor = _make_executor(parallelism="sequential")
        executor.start()

        w_good = MagicMock()
        w_good.process_snapshot.return_value = [{"score": 0.5}]
        w_bad = MagicMock()
        w_bad.process_snapshot.side_effect = ValueError("boom")
        workers = {"S_GOOD": w_good, "S_BAD": w_bad}

        snapshot = MagicMock()
        results = executor.execute_all(workers, snapshot)

        assert isinstance(results["S_GOOD"], list)
        assert isinstance(results["S_BAD"], Exception)
        executor.shutdown()

    def test_timeout_warning(self):
        """Slow worker is logged (but not killed in sequential mode)."""
        executor = _make_executor(parallelism="sequential", timeout=0.5)
        executor.start()

        w_slow = MagicMock()
        def slow_process(snap):
            time.sleep(0.6)
            return [{"score": 0.1}]
        w_slow.process_snapshot.side_effect = slow_process
        workers = {"S_SLOW": w_slow}

        snapshot = MagicMock()
        results = executor.execute_all(workers, snapshot)
        # Should still return results (sequential doesn't kill)
        assert isinstance(results["S_SLOW"], list)
        executor.shutdown()

    def test_large_batch(self):
        """20 workers processed without error."""
        executor = _make_executor(parallelism="sequential")
        executor.start()

        workers = _make_mock_workers(20)
        snapshot = MagicMock()

        results = executor.execute_all(workers, snapshot)
        assert len(results) == 20
        executor.shutdown()


@pytest.mark.unit
class TestParallelExecution:
    """Tests for thread_pool parallel execution."""

    def test_all_workers_called(self):
        """Thread pool fans out and collects results."""
        executor = _make_executor(parallelism="thread_pool", max_workers=4)
        executor.start()

        workers = _make_mock_workers(5)
        snapshot = MagicMock()

        results = executor.execute_all(workers, snapshot)
        assert len(results) == 5

        executor.shutdown()

    def test_worker_error_isolated(self):
        """Exception contained per worker in parallel mode."""
        executor = _make_executor(parallelism="thread_pool", max_workers=4)
        executor.start()

        w_good = MagicMock()
        w_good.process_snapshot.return_value = [{"score": 0.5}]
        w_bad = MagicMock()
        w_bad.process_snapshot.side_effect = ValueError("parallel boom")
        workers = {"S_GOOD": w_good, "S_BAD": w_bad}

        snapshot = MagicMock()
        results = executor.execute_all(workers, snapshot)

        assert isinstance(results["S_GOOD"], list)
        assert isinstance(results["S_BAD"], Exception)
        executor.shutdown()

    def test_timeout_returns_timeout_error(self):
        """TimeoutError in results dict for slow worker."""
        executor = _make_executor(parallelism="thread_pool", max_workers=2, timeout=0.5)
        executor.start()

        w_slow = MagicMock()
        def slow_process(snap):
            time.sleep(2.0)  # Much longer than timeout
            return [{"score": 0.1}]
        w_slow.process_snapshot.side_effect = slow_process
        workers = {"S_SLOW": w_slow}

        snapshot = MagicMock()
        results = executor.execute_all(workers, snapshot)

        assert isinstance(results["S_SLOW"], TimeoutError)
        executor.shutdown()

    def test_fallback_to_sequential(self):
        """No pool -> sequential fallback."""
        executor = _make_executor(parallelism="thread_pool")
        # Don't call start() -> no pool

        workers = _make_mock_workers(2)
        snapshot = MagicMock()

        results = executor.execute_all(workers, snapshot)
        assert len(results) == 2  # Still works via fallback
        executor.shutdown()

    def test_mixed_success_failure(self):
        """Some succeed, some fail, all returned."""
        executor = _make_executor(parallelism="thread_pool", max_workers=4)
        executor.start()

        workers = {}
        for i in range(5):
            w = MagicMock()
            if i % 2 == 0:
                w.process_snapshot.return_value = [{"score": 0.1}]
            else:
                w.process_snapshot.side_effect = RuntimeError(f"err_{i}")
            workers[f"S{i:02d}"] = w

        snapshot = MagicMock()
        results = executor.execute_all(workers, snapshot)

        assert len(results) == 5
        assert isinstance(results["S00"], list)
        assert isinstance(results["S01"], Exception)
        executor.shutdown()

    def test_respects_max_workers(self):
        """Pool created with correct max_workers."""
        executor = _make_executor(parallelism="thread_pool", max_workers=7)
        executor.start()
        assert executor._pool._max_workers == 7
        executor.shutdown()


@pytest.mark.unit
class TestExecutorLifecycle:
    """Tests for start/shutdown/stats."""

    def test_start_creates_pool(self):
        """ThreadPoolExecutor created for thread_pool mode."""
        executor = _make_executor(parallelism="thread_pool")
        assert executor._pool is None
        executor.start()
        assert executor._pool is not None
        executor.shutdown()

    def test_start_sequential_no_pool(self):
        """No pool created for sequential mode."""
        executor = _make_executor(parallelism="sequential")
        executor.start()
        assert executor._pool is None

    def test_shutdown_idempotent(self):
        """Double shutdown doesn't crash."""
        executor = _make_executor(parallelism="thread_pool")
        executor.start()
        executor.shutdown()
        executor.shutdown()  # Should not raise

    def test_stats_counters(self):
        """total_dispatches, total_timeouts, total_errors correct."""
        executor = _make_executor(parallelism="sequential")
        executor.start()

        w_good = MagicMock()
        w_good.process_snapshot.return_value = [{"score": 0.1}]
        w_bad = MagicMock()
        w_bad.process_snapshot.side_effect = RuntimeError("err")

        snapshot = MagicMock()

        executor.execute_all({"G": w_good}, snapshot)
        executor.execute_all({"B": w_bad}, snapshot)

        stats = executor.stats
        assert stats["total_dispatches"] == 2
        assert stats["total_errors"] == 1
        assert stats["parallelism"] == "sequential"
        executor.shutdown()

    def test_execute_all_increments_dispatch_counter(self):
        """Counter incremented per call."""
        executor = _make_executor(parallelism="sequential")
        executor.start()

        workers = _make_mock_workers(1)
        snapshot = MagicMock()

        for _ in range(5):
            executor.execute_all(workers, snapshot)

        assert executor._total_dispatches == 5
        executor.shutdown()
