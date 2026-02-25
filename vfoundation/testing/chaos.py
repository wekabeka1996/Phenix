"""
Chaos test harness (Phase 12.1).

Provides helpers to inject faults (random errors, latency spikes, resource exhaustion)
in a controlled, reproducible manner for resilience testing.

All parameters are configurable — no hardcoded constants.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, TypeVar

T = TypeVar("T")


@dataclass
class ChaosConfig:
    """Configuration for a chaos injection scenario."""
    error_rate: float = 0.0          # 0.0–1.0 probability of injecting error
    latency_ms: float = 0.0          # extra latency per call (ms)
    latency_jitter_ms: float = 0.0   # jitter added to latency_ms
    seed: Optional[int] = None       # RNG seed for reproducibility


class ChaosHarness:
    """
    Chaos injection harness for resilience tests.

    Wraps callables to inject configurable faults.
    Thread-safe: each harness has its own RNG instance.
    """

    def __init__(self, config: Optional[ChaosConfig] = None) -> None:
        self.config = config or ChaosConfig()
        self._rng = random.Random(self.config.seed)
        self._injected_errors: int = 0
        self._injected_latency_total_ms: float = 0.0

    def maybe_inject_error(self, error_type: type = RuntimeError, message: str = "chaos error") -> None:
        """Raise error_type if random sample is within error_rate threshold."""
        if self.config.error_rate > 0 and self._rng.random() < self.config.error_rate:
            self._injected_errors += 1
            raise error_type(message)

    def maybe_inject_latency(self) -> None:
        """Sleep for latency_ms + jitter if configured."""
        if self.config.latency_ms > 0:
            jitter = self._rng.uniform(0, self.config.latency_jitter_ms)
            delay_ms = self.config.latency_ms + jitter
            self._injected_latency_total_ms += delay_ms
            time.sleep(delay_ms / 1000.0)

    def wrap(self, func: Callable[..., T]) -> Callable[..., T]:
        """Return a wrapped version of func that injects chaos on each call."""
        def _wrapped(*args: Any, **kwargs: Any) -> T:
            self.maybe_inject_latency()
            self.maybe_inject_error()
            return func(*args, **kwargs)
        return _wrapped

    @property
    def injected_errors(self) -> int:
        return self._injected_errors

    @property
    def injected_latency_total_ms(self) -> float:
        return self._injected_latency_total_ms
