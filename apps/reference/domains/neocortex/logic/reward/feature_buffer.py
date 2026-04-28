"""
FeatureRingBuffer: Store recent feature snapshots for look-ahead reward settlement.

REGIME_PIVOT_PLAN Section 4.4 — Data Flow.

Maintains a per-symbol deque of (timestamp, latent_z, predicted_action, features_dict).
When the buffer reaches horizon_bars + 1 entries, the oldest entry (time t) pairs with
the newest entry (time t+H) to produce a settled episode for reward computation.
"""

from __future__ import annotations

# QUARANTINED: legacy_runtime
__quarantined__ = True

import logging
from collections import deque
from typing import Any, Dict, NamedTuple, Optional

import numpy as np

logger = logging.getLogger(__name__)


class BufferEntry(NamedTuple):
    """Single timestep stored in the ring buffer."""
    timestamp: float
    latent_z: np.ndarray
    predicted_action: int
    features: Dict[str, float]
    model_features: Optional[np.ndarray] = None


class SettledEpisode(NamedTuple):
    """A settled (t, t+H) pair ready for reward computation."""
    symbol: str
    timestamp_t: float
    latent_z_t: np.ndarray
    predicted_action: int
    features_t: Dict[str, float]
    model_features_t: Optional[np.ndarray]
    timestamp_t_plus_h: float
    features_t_plus_h: Dict[str, float]


class FeatureRingBuffer:
    """Per-symbol ring buffer for feature look-ahead settlement.

    For each symbol, stores the last (horizon_bars + 1) feature snapshots.
    When a new entry arrives and the buffer is full, the oldest entry is
    popped and paired with the newest to form a settled episode.

    Args:
        horizon_bars: Look-ahead horizon H (number of bars into the future).
    """

    def __init__(self, horizon_bars: int) -> None:
        if horizon_bars < 1:
            raise ValueError(f"horizon_bars must be >= 1, got {horizon_bars}")
        self.horizon_bars = horizon_bars
        self._required_len = horizon_bars + 1
        self._buffers: Dict[str, deque] = {}

    def push_and_settle(
        self,
        symbol: str,
        timestamp: float,
        latent_z: np.ndarray,
        predicted_action: int,
        features: Dict[str, float],
        model_features: Optional[np.ndarray] = None,
    ) -> Optional[SettledEpisode]:
        """Push a new observation and attempt to settle the oldest prediction.

        Args:
            symbol: Trading symbol (e.g. "BTCUSDT").
            timestamp: Wallclock or bar timestamp (epoch seconds or ms).
            latent_z: VAE-encoded latent vector for this timestep.
            predicted_action: PPO action index (0-4) predicted at this time.
            features: Raw feature dict from logs/features for this bar.
            model_features: Optional model-input feature vector for timestep t.

        Returns:
            SettledEpisode if enough bars have accumulated (len == horizon_bars + 1),
            otherwise None (still warming up).
        """
        if symbol not in self._buffers:
            self._buffers[symbol] = deque(maxlen=self._required_len)

        buf = self._buffers[symbol]
        entry = BufferEntry(
            timestamp=timestamp,
            latent_z=latent_z,
            predicted_action=predicted_action,
            features=features,
            model_features=(
                np.asarray(model_features, dtype=np.float32).reshape(-1).copy()
                if model_features is not None else None
            ),
        )

        # Append first, then check if buffer is full.
        # With maxlen = horizon_bars + 1, a full buffer means we have entries
        # spanning exactly horizon_bars intervals: buf[0]=time t, buf[-1]=time t+H.
        buf.append(entry)

        if len(buf) == self._required_len:
            oldest = buf[0]
            newest = buf[-1]

            return SettledEpisode(
                symbol=symbol,
                timestamp_t=oldest.timestamp,
                latent_z_t=oldest.latent_z,
                predicted_action=oldest.predicted_action,
                features_t=oldest.features,
                model_features_t=oldest.model_features,
                timestamp_t_plus_h=newest.timestamp,
                features_t_plus_h=newest.features,
            )

        return None

    def warmup_remaining(self, symbol: str) -> int:
        """Number of bars still needed before first settlement for a symbol."""
        buf = self._buffers.get(symbol)
        if buf is None:
            return self._required_len
        return max(0, self._required_len - len(buf))

    def reset(self, symbol: Optional[str] = None) -> None:
        """Clear buffer for a specific symbol or all symbols."""
        if symbol is not None:
            self._buffers.pop(symbol, None)
        else:
            self._buffers.clear()

    @property
    def symbols(self) -> list:
        """List of symbols with active buffers."""
        return list(self._buffers.keys())
