"""Stateful smoothing for already-resolved regime multiplier factors.

The helper only transforms numeric multipliers on a per-symbol basis. It does
not resolve regime labels, load configuration, or emit diagnostics.
"""

from decimal import Decimal
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.reference.config_models import RegimeSmoothingConfig


class RegimeMultiplierSmoother:
    """Smooth per-symbol regime multipliers with EMA or linear ramp.

    The first observation for a symbol seeds the internal state and returns the
    raw factor unchanged. When config is missing or disabled, ``step`` acts as
    a passthrough and leaves any cached state untouched.
    """

    def __init__(self, config: Optional["RegimeSmoothingConfig"]) -> None:
        """Store the smoothing config and per-symbol transition state."""
        self.config = config
        self._last_smoothed: Dict[str, Decimal] = {}
        self._last_raw: Dict[str, Decimal] = {}
        self._bars_since_change: Dict[str, int] = {}
        self._ramp_start: Dict[str, Decimal] = {}

    def step(self, raw_factor: Decimal, symbol: str) -> Decimal:
        """Return the smoothed multiplier for one symbol update.

        A change in ``raw_factor`` resets the linear-ramp baseline to the last
        emitted smoothed value so the transition continues from the previous
        output instead of jumping to the new target immediately.
        """
        if self.config is None or not self.config.enabled:
            return raw_factor

        if symbol not in self._last_smoothed:
            # Seed the cache from the first observed factor instead of inventing
            # a synthetic baseline.
            self._last_smoothed[symbol] = raw_factor
            self._last_raw[symbol] = raw_factor
            self._bars_since_change[symbol] = 0
            self._ramp_start[symbol] = raw_factor
            return raw_factor

        prev_smoothed = self._last_smoothed[symbol]
        prev_raw = self._last_raw[symbol]

        if raw_factor != prev_raw:
            # Restart ramp bookkeeping whenever the target factor changes.
            self._bars_since_change[symbol] = 1
            self._last_raw[symbol] = raw_factor
            self._ramp_start[symbol] = prev_smoothed
        else:
            self._bars_since_change[symbol] += 1

        method = self.config.method

        if method == "ema":
            alpha = Decimal(str(self.config.ema_alpha))
            smoothed = alpha * raw_factor + \
                (Decimal("1.0") - alpha) * prev_smoothed
        elif method == "linear_ramp":
            ramp_bars = self.config.ramp_bars
            # Cap progress at 1.0 so the ramp lands on the target and stays
            # there on subsequent bars.
            bars = min(self._bars_since_change[symbol], ramp_bars)
            progress = Decimal(str(bars)) / Decimal(str(ramp_bars))
            ramp_base = self._ramp_start[symbol]
            smoothed = ramp_base + (raw_factor - ramp_base) * progress
        else:
            raise ValueError(f"Unknown regime smoothing method: {method!r}")

        self._last_smoothed[symbol] = smoothed
        return smoothed
