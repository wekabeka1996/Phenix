# SPDX-License-Identifier: MIT
"""
LLA R2 Policy Engine
Manages online switching between R0 and R1 with anti-thrash protection.
"""

import time
from typing import Dict, Any


# R2 policy parameters
PARAMS = {
    "interval_s": 30,
    "cooldown_s": 45,
    "min_dwell_s": 90,
    "max_switches_per_hour": 6
}


class R2Policy:
    """R2 switching policy with anti-thrash protection."""

    def __init__(self, now_fn=time.time):
        self.now = now_fn
        self.last_switch = 0.0
        self.switches: list[float] = []

    def maybe_switch(self, metrics: Dict[str, Any]) -> bool:
        """
        Decide whether to switch R2 state based on metrics and policy.

        Args:
            metrics: Dict with:
                - last_two_windows_ok: bool (both windows in [7,13] and duty < 0.30)
                - reason: 'metric'|'schedule'|'manual'

        Returns:
            True if switch should occur, False otherwise
        """
        now = self.now()

        # Clean old switches (older than 1 hour)
        self.switches = [t for t in self.switches if now - t < 3600]

        # Check maximum switches per hour
        if len(self.switches) >= PARAMS["max_switches_per_hour"]:
            return False

        # Check minimum dwell time
        if (now - self.last_switch) < PARAMS["min_dwell_s"]:
            return False

        # Check cooldown period
        if (now - self.last_switch) < PARAMS["cooldown_s"]:
            return False

        # Anti-thrash: don't switch if last two windows are stable
        if metrics.get("last_two_windows_ok", False):
            return False

        # Perform switch
        self.switches.append(now)
        self.last_switch = now
        return True