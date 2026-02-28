"""
Performance benchmark harness (Phase 12.3).

Runs a callable N times and records throughput, latency percentiles.
Supports configurable warm-up rounds, iterations, and SLO thresholds.

No hardcoded values — all parameters must be supplied.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""
    name: str
    iterations: int
    latencies_ms: List[float]
    warmup_rounds: int = 0

    @property
    def p50_ms(self) -> float:
        return self._percentile(50)

    @property
    def p95_ms(self) -> float:
        return self._percentile(95)

    @property
    def p99_ms(self) -> float:
        return self._percentile(99)

    @property
    def throughput_rps(self) -> float:
        """Requests per second."""
        total_s = sum(self.latencies_ms) / 1000.0
        if total_s <= 0:
            return 0.0
        return len(self.latencies_ms) / total_s

    def _percentile(self, pct: int) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lats = sorted(self.latencies_ms)
        idx = max(0, int(len(sorted_lats) * pct / 100) - 1)
        return sorted_lats[idx]

    def meets_slo(self, p95_slo_ms: float) -> bool:
        """True if p95 latency is within the given SLO."""
        return self.p95_ms <= p95_slo_ms


class PerfBenchmark:
    """
    Performance benchmark runner.

    Args:
        name: Benchmark name for reporting.
        warmup_rounds: Number of warm-up iterations (not counted in results).
        iterations: Number of measured iterations.
    """

    def __init__(
        self,
        name: str,
        warmup_rounds: int = 0,
        iterations: int = 100,
    ) -> None:
        self.name = name
        self.warmup_rounds = warmup_rounds
        self.iterations = iterations

    def run(self, func: Callable[[], Any]) -> BenchmarkResult:
        """
        Run the benchmark against func.

        Args:
            func: Zero-argument callable to benchmark.

        Returns:
            BenchmarkResult with latencies and derived statistics.
        """
        # Warm-up (not measured)
        for _ in range(self.warmup_rounds):
            func()

        latencies: List[float] = []
        for _ in range(self.iterations):
            start = time.perf_counter()
            func()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(elapsed_ms)

        return BenchmarkResult(
            name=self.name,
            iterations=self.iterations,
            latencies_ms=latencies,
            warmup_rounds=self.warmup_rounds,
        )


def benchmark_fsm_hot_path(
    fsm: Any,
    messages: List[Any],
    p95_threshold_ms: float = 50.0,
) -> BenchmarkResult:
    """Blueprint 12.3: Domain-specific FSM hot-path benchmark.

    Calls fsm.handle(msg) for each message and records latencies.
    """
    latencies: List[float] = []
    for msg in messages:
        start = time.perf_counter()
        fsm.handle(msg)
        latencies.append((time.perf_counter() - start) * 1000.0)
    return BenchmarkResult(
        name="fsm_hot_path",
        iterations=len(messages),
        latencies_ms=latencies,
    )


def benchmark_cb_health(
    adapter: Any,
    iterations: int = 100,
) -> BenchmarkResult:
    """Blueprint 12.3: Domain-specific circuit-breaker health benchmark.

    Calls adapter.health_check() repeatedly and records latencies.
    """
    bench = PerfBenchmark(name="cb_health", iterations=iterations)
    return bench.run(adapter.health_check)
