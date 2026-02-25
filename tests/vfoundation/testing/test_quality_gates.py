"""
Phase 12.1-12.3 tests: chaos harness, DR timing verification, perf benchmark.

Note: vfoundation/testing/ package needs __init__.py.
"""
from __future__ import annotations

import time
from typing import List

import pytest

# ── chaos harness ──────────────────────────────────────────────────────────────
from vfoundation.testing.chaos import ChaosConfig, ChaosHarness


class TestChaosHarness:
    def test_no_chaos_by_default(self) -> None:
        """Default config should inject no errors or latency."""
        harness = ChaosHarness()
        func = lambda: 42
        wrapped = harness.wrap(func)
        assert wrapped() == 42
        assert harness.injected_errors == 0
        assert harness.injected_latency_total_ms == 0.0

    def test_error_rate_100_always_raises(self) -> None:
        """error_rate=1.0 should raise on every call."""
        harness = ChaosHarness(ChaosConfig(error_rate=1.0, seed=0))
        with pytest.raises(RuntimeError, match="chaos error"):
            harness.maybe_inject_error()
        assert harness.injected_errors == 1

    def test_error_rate_0_never_raises(self) -> None:
        """error_rate=0.0 must never raise regardless of seed."""
        harness = ChaosHarness(ChaosConfig(error_rate=0.0, seed=42))
        for _ in range(100):
            harness.maybe_inject_error()  # should not raise
        assert harness.injected_errors == 0

    def test_seed_reproducible(self) -> None:
        """Same seed should produce same error injection pattern."""
        errors_a: List[bool] = []
        errors_b: List[bool] = []
        for errors_list, seed in [(errors_a, 7), (errors_b, 7)]:
            harness = ChaosHarness(ChaosConfig(error_rate=0.5, seed=seed))
            for _ in range(20):
                try:
                    harness.maybe_inject_error()
                    errors_list.append(False)
                except RuntimeError:
                    errors_list.append(True)
        assert errors_a == errors_b, "same seed must produce identical injection pattern"

    def test_wrap_returns_correct_value(self) -> None:
        """Wrapped non-failing function should return its value."""
        harness = ChaosHarness(ChaosConfig(error_rate=0.0))
        result = harness.wrap(lambda: "hello")()
        assert result == "hello"

    def test_custom_error_type(self) -> None:
        """maybe_inject_error with custom error type should raise that type."""
        harness = ChaosHarness(ChaosConfig(error_rate=1.0, seed=0))
        with pytest.raises(ValueError):
            harness.maybe_inject_error(error_type=ValueError, message="custom")

    def test_latency_injected(self) -> None:
        """Configured latency should cause measurable delay."""
        harness = ChaosHarness(ChaosConfig(latency_ms=10.0))
        start = time.perf_counter()
        harness.maybe_inject_latency()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert elapsed_ms >= 8.0, f"expected >=8ms delay, got {elapsed_ms:.1f}ms"
        assert harness.injected_latency_total_ms >= 10.0

    def test_no_latency_by_default(self) -> None:
        """latency_ms=0 should not cause any delay."""
        harness = ChaosHarness()
        start = time.perf_counter()
        harness.maybe_inject_latency()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        assert elapsed_ms < 5.0, f"expected <5ms with no latency config, got {elapsed_ms:.1f}ms"


# ── DR timing verification ─────────────────────────────────────────────────────
from vfoundation.testing.dr_timing import DRTimingResult, DRTimingVerifier


class TestDRTimingVerifier:
    def test_wal_flush_within_slo(self) -> None:
        """WAL flush below SLO threshold should pass."""
        verifier = DRTimingVerifier(wal_flush_slo_ms=10.0)
        result = verifier.verify_wal_flush(elapsed_ms=5.0)
        assert result.passed is True, f"expected pass: {result.message}"

    def test_wal_flush_exceeds_slo(self) -> None:
        """WAL flush exceeding SLO should fail."""
        verifier = DRTimingVerifier(wal_flush_slo_ms=10.0)
        result = verifier.verify_wal_flush(elapsed_ms=15.0)
        assert result.passed is False, f"expected fail: {result.message}"

    def test_checkpoint_within_slo(self) -> None:
        """Checkpoint within SLO should pass."""
        verifier = DRTimingVerifier(checkpoint_slo_ms=100.0)
        result = verifier.verify_checkpoint(elapsed_ms=50.0)
        assert result.passed is True

    def test_recovery_slo(self) -> None:
        """Recovery time within SLO should pass."""
        verifier = DRTimingVerifier(recovery_slo_ms=5000.0)
        result = verifier.verify_recovery(elapsed_ms=3000.0)
        assert result.passed is True

    def test_all_passed_true_when_all_pass(self) -> None:
        """all_passed should be True when all measurements pass."""
        verifier = DRTimingVerifier(wal_flush_slo_ms=10.0, checkpoint_slo_ms=100.0)
        verifier.verify_wal_flush(1.0)
        verifier.verify_checkpoint(50.0)
        assert verifier.all_passed is True

    def test_all_passed_false_on_one_failure(self) -> None:
        """all_passed should be False if any measurement fails."""
        verifier = DRTimingVerifier(wal_flush_slo_ms=5.0)
        verifier.verify_wal_flush(10.0)  # fails
        assert verifier.all_passed is False


# ── perf benchmark harness ────────────────────────────────────────────────────
from vfoundation.testing.perf_benchmark import BenchmarkResult, PerfBenchmark


class TestPerfBenchmark:
    def test_runs_correct_iteration_count(self) -> None:
        """Benchmark should record exactly N latency measurements."""
        bench = PerfBenchmark(name="test", iterations=10)
        result = bench.run(lambda: None)
        assert len(result.latencies_ms) == 10

    def test_p95_within_reasonable_range(self) -> None:
        """p95 should be >= 0 for a fast no-op function."""
        bench = PerfBenchmark(name="test", iterations=100)
        result = bench.run(lambda: None)
        assert result.p95_ms >= 0

    def test_meets_slo_fast_function(self) -> None:
        """A fast no-op function should meet 100ms SLO."""
        bench = PerfBenchmark(name="noop", iterations=50)
        result = bench.run(lambda: None)
        assert result.meets_slo(p95_slo_ms=100.0), (
            f"expected no-op to meet 100ms SLO, p95={result.p95_ms:.2f}ms"
        )

    def test_throughput_rps_positive(self) -> None:
        """Throughput should be > 0 for any function."""
        bench = PerfBenchmark(name="noop", iterations=20)
        result = bench.run(lambda: None)
        assert result.throughput_rps > 0

    def test_warmup_rounds_not_counted(self) -> None:
        """Warm-up rounds should not add to latencies_ms."""
        bench = PerfBenchmark(name="warmup_test", warmup_rounds=5, iterations=10)
        result = bench.run(lambda: None)
        assert len(result.latencies_ms) == 10, (
            f"expected 10 measured iterations, got {len(result.latencies_ms)}"
        )
