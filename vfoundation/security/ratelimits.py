from __future__ import annotations
from typing import Dict
import time


class RateLimiter:
    def __init__(self, per_s: int = 10) -> None:
        self.per_s = per_s
        self.bucket: Dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        q = self.bucket.setdefault(key, [])
        q[:] = [t for t in q if now - t < 1.0]
        if len(q) >= self.per_s:
            return False
        q.append(now)
        return True
