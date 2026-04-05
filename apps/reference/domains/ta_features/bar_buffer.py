"""
TA Features — Rolling OHLCV Bar Buffer.

Maintains a fixed-size deque of OHLCV bar data per (symbol, tf_sec).
Used by TAFeaturesEngine to feed the math calculators.
"""

from collections import deque
from decimal import Decimal
from typing import Deque, List


class BarBuffer:
    """
    Fixed-size rolling buffer of OHLCV bars (oldest → newest).

    Args:
        maxlen: Maximum bars stored. Oldest bars are silently evicted
                once the buffer is full (deque semantics).
    """

    def __init__(self, maxlen: int = 50) -> None:
        self._maxlen = maxlen
        self._opens:      Deque[Decimal] = deque(maxlen=maxlen)
        self._highs:      Deque[Decimal] = deque(maxlen=maxlen)
        self._lows:       Deque[Decimal] = deque(maxlen=maxlen)
        self._closes:     Deque[Decimal] = deque(maxlen=maxlen)
        self._volumes:    Deque[Decimal] = deque(maxlen=maxlen)
        self._timestamps: Deque[int] = deque(maxlen=maxlen)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def push(
        self,
        open_:  Decimal,
        high:   Decimal,
        low:    Decimal,
        close:  Decimal,
        volume: Decimal,
        ts_ms:  int,
    ) -> None:
        """Append one OHLCV bar to the buffer."""
        self._opens.append(open_)
        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)
        self._volumes.append(volume)
        self._timestamps.append(ts_ms)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._closes)

    def enough(self, min_bars: int) -> bool:
        """True when the buffer holds at least `min_bars` entries."""
        return len(self._closes) >= min_bars

    @property
    def opens(self) -> List[Decimal]:
        return list(self._opens)

    @property
    def highs(self) -> List[Decimal]:
        return list(self._highs)

    @property
    def lows(self) -> List[Decimal]:
        return list(self._lows)

    @property
    def closes(self) -> List[Decimal]:
        return list(self._closes)

    @property
    def volumes(self) -> List[Decimal]:
        return list(self._volumes)

    @property
    def last_ts_ms(self) -> int:
        """Timestamp of the most recent bar, or 0 if empty."""
        return self._timestamps[-1] if self._timestamps else 0
