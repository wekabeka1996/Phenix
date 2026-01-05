"""π_bridge candidate acceptance rate limiter.

Implements StructuralPriorBridge.should_accept_candidate-style limiter abstraction.
We create a simple token bucket style gate keyed by (bridge_id or generic) that
limits accepted candidates per sliding window.

Logged events will be written by orchestrator integration into
logs/hybrid/pi_bridge_rate_limit.jsonl when a candidate is denied.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional
import time

@dataclass
class TokenBucket:
    capacity: int
    refill_time_s: float  # full refill interval
    tokens: float
    last_refill: float

    def refill(self, now: float) -> None:
        if now <= self.last_refill:
            return
        # Linear refill to capacity across refill_time_s
        delta = now - self.last_refill
        rate = self.capacity / self.refill_time_s
        self.tokens = min(self.capacity, self.tokens + delta * rate)
        self.last_refill = now

    def consume(self, now: float) -> bool:
        self.refill(now)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

class PiBridgeRateLimiter:
    """Manages token buckets per bridge label.

    If bridge_id is None we use a shared 'default' bucket.
    """
    def __init__(self, capacity: int = 5, refill_time_s: float = 60.0):
        self.capacity = capacity
        self.refill_time_s = refill_time_s
        self._buckets: Dict[str, TokenBucket] = {}

    def should_accept_candidate(self, bridge_id: Optional[str]) -> bool:
        now = time.time()
        key = bridge_id or 'default'
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self.capacity, self.refill_time_s, self.capacity, now)
            self._buckets[key] = bucket
        return bucket.consume(now)

    def snapshot(self) -> Dict[str, float]:
        return {k: v.tokens for k, v in self._buckets.items()}
