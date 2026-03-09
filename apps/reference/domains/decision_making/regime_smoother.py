from decimal import Decimal
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.reference.config_models import RegimeSmoothingConfig


class RegimeMultiplierSmoother:
    """
    Contract:
      Input: raw_factor (Decimal), symbol (str)
      Output: smoothed_factor (Decimal)
      State: per-symbol last_smoothed (Dict[str, Decimal])
      Invariant: when disabled → returns raw_factor unchanged
      Invariant: smoothed converges to raw within ceil(1/alpha) bars
      why format: "regime_smooth:ema α=0.3 prev=X raw=Y out=Z"
    """

    def __init__(self, config: Optional["RegimeSmoothingConfig"]) -> None:
        self.config = config
        self._last_smoothed: Dict[str, Decimal] = {}
        self._last_raw: Dict[str, Decimal] = {}
        self._bars_since_change: Dict[str, int] = {}
        self._ramp_start: Dict[str, Decimal] = {}

    def step(self, raw_factor: Decimal, symbol: str) -> Decimal:
        if self.config is None or not self.config.enabled:
            return raw_factor

        if symbol not in self._last_smoothed:
            self._last_smoothed[symbol] = raw_factor
            self._last_raw[symbol] = raw_factor
            self._bars_since_change[symbol] = 0
            self._ramp_start[symbol] = raw_factor
            return raw_factor

        prev_smoothed = self._last_smoothed[symbol]
        prev_raw = self._last_raw[symbol]

        if raw_factor != prev_raw:
            self._bars_since_change[symbol] = 1
            self._last_raw[symbol] = raw_factor
            self._ramp_start[symbol] = prev_smoothed
        else:
            self._bars_since_change[symbol] += 1

        method = self.config.method

        if method == "ema":
            alpha = Decimal(str(self.config.ema_alpha))
            smoothed = alpha * raw_factor + (Decimal("1.0") - alpha) * prev_smoothed
        elif method == "linear_ramp":
            ramp_bars = self.config.ramp_bars
            bars = min(self._bars_since_change[symbol], ramp_bars)
            progress = Decimal(str(bars)) / Decimal(str(ramp_bars))
            ramp_base = self._ramp_start[symbol]
            smoothed = ramp_base + (raw_factor - ramp_base) * progress
        else:
            raise ValueError(f"Unknown regime smoothing method: {method!r}")

        self._last_smoothed[symbol] = smoothed
        return smoothed
