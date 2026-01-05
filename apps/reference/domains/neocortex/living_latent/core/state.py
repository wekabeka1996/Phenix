# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""R2 Attractor online state tracking.

SPEC: docs/R2_online.md – maintains dwell, cooldown, churn counters.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import time

@dataclass
class AttractorState:
    current: str | None = None
    entered_ts: float | None = None
    last_switch_ts: float | None = None
    switch_count_hour: int = 0
    hour_bucket_start: float = field(default_factory=lambda: time.time())
    commits: int = 0
    rollbacks: int = 0

    def _maybe_roll_hour(self):
        now = time.time()
        if now - self.hour_bucket_start >= 3600:
            self.hour_bucket_start = now
            self.switch_count_hour = 0

    def switch_to(self, attr_id: str):
        self._maybe_roll_hour()
        self.current = attr_id
        ts = time.time()
        self.entered_ts = ts
        self.last_switch_ts = ts
        self.switch_count_hour += 1

    def can_switch(self, cfg) -> bool:
        self._maybe_roll_hour()
        cd = float(((cfg.get('r2') or {}).get('online') or {}).get('cooldown_s', 180) or 180)
        if self.last_switch_ts is None:
            return True
        return (time.time() - self.last_switch_ts) >= cd

    def dwell_seconds(self) -> float:
        if self.entered_ts is None:
            return 0.0
        return max(0.0, time.time() - self.entered_ts)
