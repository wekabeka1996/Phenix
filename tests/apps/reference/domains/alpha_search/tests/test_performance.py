"""
Cross-Cutting: Performance Tests
==================================

Performance benchmarks and regression detection.
4 tests marked @pytest.mark.slow.
"""

import json
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from apps.reference.domains.alpha_search.runtime.contracts import RuntimeConfig
from apps.reference.domains.alpha_search.runtime.executor import ScenarioExecutor
from apps.reference.domains.alpha_search.runtime.ingest import IngestGateway
from tests.apps.reference.domains.alpha_search.snapshot_factory import make_snapshot


@pytest.mark.slow
class TestPerformance:
    """Performance benchmarks for critical operations."""

    def test_single_snapshot_10_scenarios_under_100ms(self):
        """p95 < 100ms per snapshot with 10 scenarios."""
        cfg = RuntimeConfig(
            parallelism="thread_pool",
            max_workers=4,
            scenario_timeout_sec=5.0,
        )
        executor = ScenarioExecutor(cfg)
        executor.start()

        # Create 10 mock workers with realistic processing time
        workers = {}
        for i in range(10):
            w = MagicMock()
            w.process_snapshot.return_value = [
                {"score": 0.01 * i, "scenario_id": f"S{i:02d}"}]
            workers[f"S{i:02d}"] = w

        snapshot = MagicMock()

        # Warmup
        executor.execute_all(workers, snapshot)

        # Benchmark
        latencies = []
        for _ in range(20):
            start = time.monotonic()
            executor.execute_all(workers, snapshot)
            latencies.append((time.monotonic() - start) * 1000)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]

        executor.shutdown()
        assert p95 < 100, f"p95 latency {p95:.1f}ms exceeds 100ms"

    def test_single_snapshot_20_scenarios_under_200ms(self):
        """p95 < 200ms per snapshot with 20 scenarios."""
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

        # Warmup
        executor.execute_all(workers, snapshot)

        latencies = []
        for _ in range(20):
            start = time.monotonic()
            executor.execute_all(workers, snapshot)
            latencies.append((time.monotonic() - start) * 1000)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]

        executor.shutdown()
        assert p95 < 200, f"p95 latency {p95:.1f}ms exceeds 200ms"

    def test_ingest_1000_lines_replay(self, tmp_path):
        """1000 lines parsed in < 2s."""
        path = tmp_path / "big_stream.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for i in range(1000):
                snapshot = make_snapshot(
                    ts_ms=1740000000000 + i, price=96000.0 + i * 0.1)
                f.write(json.dumps(snapshot) + "\n")

        gateway = IngestGateway(stream_path=path, mode="replay")

        start = time.monotonic()
        count = sum(1 for _ in gateway.iter_replay())
        elapsed = time.monotonic() - start

        assert count == 1000
        assert elapsed < 2.0, f"Ingesting 1000 lines took {elapsed:.2f}s (limit 2s)"

    def test_memory_10_scenarios_under_500mb(self):
        """RSS stays reasonable for 10 scenarios (mock workers)."""
        import os

        try:
            import psutil
            process = psutil.Process(os.getpid())
            rss_before = process.memory_info().rss / (1024 * 1024)
        except ImportError:
            pytest.skip("psutil not installed")

        cfg = RuntimeConfig(
            parallelism="thread_pool",
            max_workers=4,
            scenario_timeout_sec=5.0,
        )
        executor = ScenarioExecutor(cfg)
        executor.start()

        workers = {}
        for i in range(10):
            w = MagicMock()
            w.process_snapshot.return_value = [
                {"score": 0.01 * i, "big_data": "x" * 1000}
            ]
            workers[f"S{i:02d}"] = w

        snapshot = MagicMock()

        # Process many snapshots to accumulate memory
        for _ in range(100):
            executor.execute_all(workers, snapshot)

        executor.shutdown()

        rss_after = process.memory_info().rss / (1024 * 1024)
        delta_mb = rss_after - rss_before

        # Memory growth should be reasonable
        assert delta_mb < 500, f"Memory grew by {delta_mb:.0f}MB (limit 500MB)"
