# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""R1 Metrics Context (ring buffers).

SPEC: R1.METRICS — provides low-latency sampling windows for evaluator.

Design:
- Each metric keeps a deque[(ts, value)] with pruning on insert (lazy O(1) amortized).
- Public record_* methods insert (ts,value) (ts default = time.time()).
- Public sample_* methods return list[float] of values where now-ts <= duration_s.
- Latency p95 treated as already aggregated scalar (still time-series to allow window mean / last).

Thread model: main loop single-threaded; no locks required.

Fallback semantics: if window empty, returns []. Evaluator will then compute 0 deltas.

"""
from __future__ import annotations
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Tuple, List

_MAX_SECONDS_RETENTION = 3600  # hard cap for pruning (1h)

@dataclass
class _Series:
    data: Deque[Tuple[float, float]] = field(default_factory=deque)

    def append(self, value: float, ts: float | None = None):
        ts = time.time() if ts is None else ts
        self.data.append((ts, float(value)))
        # Lazy prune (drop older than retention threshold)
        cutoff = ts - _MAX_SECONDS_RETENTION
        while self.data and self.data[0][0] < cutoff:
            self.data.popleft()

    def sample(self, duration_s: float) -> List[float]:
        now = time.time()
        cutoff = now - duration_s
        # Walk from right (newest) backwards until older than cutoff
        out = []
        for ts, v in reversed(self.data):
            if ts < cutoff:
                break
            out.append(v)
        return list(reversed(out))  # chronological order

@dataclass
class MetricsContext:
    efe: _Series = field(default_factory=_Series)
    emp: _Series = field(default_factory=_Series)
    homeo: _Series = field(default_factory=_Series)
    surprisal: _Series = field(default_factory=_Series)
    latency_p95: _Series = field(default_factory=_Series)

    # Record APIs
    def record_efe(self, x: float, ts: float | None = None):
        self.efe.append(x, ts)
    def record_emp(self, x: float, ts: float | None = None):
        self.emp.append(x, ts)
    def record_homeo(self, x: float, ts: float | None = None):
        self.homeo.append(x, ts)
    def record_surprisal(self, x: float, ts: float | None = None):
        self.surprisal.append(x, ts)
    def record_latency_p95(self, x: float, ts: float | None = None):
        self.latency_p95.append(x, ts)

    # Sample APIs
    def sample_efe(self, duration_s: float):
        return self.efe.sample(duration_s)
    def sample_empowerment(self, duration_s: float):
        return self.emp.sample(duration_s)
    def sample_homeostasis(self, duration_s: float):
        return self.homeo.sample(duration_s)
    def sample_surprisal(self, duration_s: float):
        return self.surprisal.sample(duration_s)
    def sample_latency_p95(self, duration_s: float):
        vals = self.latency_p95.sample(duration_s)
        return vals[-1] if vals else 0.0

    # Minimal interface for rollback guard (homeostasis)
    def get_homeostasis(self) -> float | None:
        vals = self.homeo.sample(60.0)
        return sum(vals)/len(vals) if vals else None

__all__ = ["MetricsContext"]
