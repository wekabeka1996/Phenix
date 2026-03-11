"""
Cross-Cutting: Concurrency Tests
==================================

Thread safety and deadlock detection tests.
5 tests marked @pytest.mark.slow.
"""

import threading
import time
import pytest
from unittest.mock import MagicMock

from apps.reference.domains.alpha_search.runtime.contracts import RuntimeConfig
from apps.reference.domains.alpha_search.runtime.executor import ScenarioExecutor
from apps.reference.domains.alpha_search.runtime.backpressure import BoundedIngestQueue


@pytest.mark.slow
class TestConcurrency:
    """Thread pool concurrency tests."""

    def test_thread_pool_10_scenarios_no_deadlock(self):
        """10 workers fan-out completes without deadlock."""
        cfg = RuntimeConfig(parallelism="thread_pool", max_workers=4, scenario_timeout_sec=5.0)
        executor = ScenarioExecutor(cfg)
        executor.start()

        workers = {}
        for i in range(10):
            w = MagicMock()
            w.process_snapshot.return_value = [{"score": 0.01 * i}]
            workers[f"S{i:02d}"] = w

        snapshot = MagicMock()

        for _ in range(5):
            results = executor.execute_all(workers, snapshot)
            assert len(results) == 10

        executor.shutdown()

    def test_thread_pool_20_scenarios_no_deadlock(self):
        """20 workers fan-out completes without deadlock."""
        cfg = RuntimeConfig(
            parallelism="thread_pool",
            max_workers=8,
            scenario_timeout_sec=5.0,
        )
        executor = ScenarioExecutor(cfg)
        executor.start()

        workers = {}
        for i in range(20):
            w = MagicMock()
            w.process_snapshot.return_value = [{"score": 0.005 * i}]
            workers[f"S{i:02d}"] = w

        snapshot = MagicMock()
        results = executor.execute_all(workers, snapshot)
        assert len(results) == 20
        executor.shutdown()

    def test_bounded_queue_concurrent_put_get(self):
        """Producer/consumer threads don't corrupt state."""
        q = BoundedIngestQueue(maxsize=500, policy="drop_oldest")
        errors = []
        put_count = 1000

        def producer():
            for _ in range(put_count):
                try:
                    q.put(MagicMock())
                except Exception as e:
                    errors.append(e)

        def consumer():
            for _ in range(put_count):
                try:
                    q.get()
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=producer),
            threading.Thread(target=producer),
            threading.Thread(target=consumer),
            threading.Thread(target=consumer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0

    def test_no_cross_worker_state_leak(self):
        """Workers with mutable state don't share between threads."""
        cfg = RuntimeConfig(parallelism="thread_pool", max_workers=4, scenario_timeout_sec=5.0)
        executor = ScenarioExecutor(cfg)
        executor.start()

        # Each worker tracks its own call count
        call_counts = {}

        def make_tracked_worker(sid):
            call_counts[sid] = 0
            w = MagicMock()

            def track_call(snap):
                call_counts[sid] += 1
                return [{"score": 0.1, "call_count": call_counts[sid]}]

            w.process_snapshot.side_effect = track_call
            return w

        workers = {f"S{i:02d}": make_tracked_worker(f"S{i:02d}") for i in range(5)}
        snapshot = MagicMock()

        for _ in range(3):
            executor.execute_all(workers, snapshot)

        # Each worker should have been called exactly 3 times
        for sid, count in call_counts.items():
            assert count == 3, f"{sid} was called {count} times, expected 3"

        executor.shutdown()

    def test_executor_shutdown_during_execution(self):
        """Shutdown while threads running doesn't hang."""
        cfg = RuntimeConfig(
            parallelism="thread_pool",
            max_workers=4,
            scenario_timeout_sec=5.0,
        )
        executor = ScenarioExecutor(cfg)
        executor.start()

        # Create slow workers
        workers = {}
        for i in range(4):
            w = MagicMock()

            def slow_process(snap, idx=i):
                time.sleep(0.5)
                return [{"score": 0.1}]

            w.process_snapshot.side_effect = slow_process
            workers[f"S{i:02d}"] = w

        snapshot = MagicMock()

        # Start execution in background
        result_holder = [None]

        def execute():
            result_holder[0] = executor.execute_all(workers, snapshot)

        t = threading.Thread(target=execute)
        t.start()

        time.sleep(0.1)  # Let execution start
        executor.shutdown()  # Should not hang

        t.join(timeout=10)
        assert not t.is_alive(), "Shutdown caused thread to hang"
