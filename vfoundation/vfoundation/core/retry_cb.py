from __future__ import annotations
import random
import time
import threading
from typing import Optional

from ..config import config


class RetryPolicy:
    def __init__(self, retries: int = 3, base_ms: int = 20, max_ms: int = 2000) -> None:
        self.retries = retries
        self.base_ms = base_ms
        self.max_ms = max_ms

    def backoff_ms(self, attempt: int) -> int:
        # exponential backoff with jitter
        return min(self.max_ms, int((2**attempt) * self.base_ms + random.randint(0, 10)))


class CircuitBreaker:
    def __init__(
        self, threshold: Optional[int] = None, cool_down_s: Optional[float] = None
    ) -> None:
        self.threshold = threshold if threshold is not None else config.cb_threshold
        self.cool_down_s = cool_down_s if cool_down_s is not None else config.cb_cooldown_sec
        self.failures = 0
        self.state = "CLOSED"
        self.open_ts: float = 0.0
        self._lock = threading.Lock()

    def on_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.state = "CLOSED"

    def on_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= self.threshold:
                self.state = "OPEN"
                self.open_ts = time.time()

    def allow(self) -> bool:
        with self._lock:
            if self.state == "CLOSED":
                return True
            elif self.state == "HALF_OPEN":
                # Allow first request through in half-open state
                return True
            elif self.state == "OPEN":
                # Check if cool-down period has passed
                if time.time() - self.open_ts > self.cool_down_s:
                    # Transition to half-open for probing
                    self.state = "HALF_OPEN"
                    return True
                return False
            return True  # Default fallback
