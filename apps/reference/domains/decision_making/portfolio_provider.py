from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from .contracts import PortfolioSnapshot


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


class PortfolioProvider:
    """Typed portfolio snapshot provider to prevent zero-overwrite bugs."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._latest: Optional[PortfolioSnapshot] = None
        self._last_nonzero: Optional[PortfolioSnapshot] = None

    @property
    def has_snapshot(self) -> bool:
        return self._latest is not None or self._last_nonzero is not None

    def ingest_snapshot(self, raw: Any) -> PortfolioSnapshot:
        snapshot = self._normalize_snapshot(raw)
        self._latest = snapshot
        if snapshot.equity_free_usdt > 0:
            self._last_nonzero = snapshot
        elif self._last_nonzero:
            self._logger.warning(
                "Portfolio snapshot has non-positive equity_free_usdt; retaining last non-zero snapshot",
                extra={
                    "equity_free_usdt": str(snapshot.equity_free_usdt),
                    "source": snapshot.source,
                },
            )
        return snapshot

    def get_snapshot(self, *, prefer_nonzero: bool = True) -> PortfolioSnapshot:
        if prefer_nonzero and self._last_nonzero:
            return self._last_nonzero
        if self._latest:
            return self._latest
        raise RuntimeError("Portfolio snapshot not available")

    def _normalize_snapshot(self, raw: Any) -> PortfolioSnapshot:
        if isinstance(raw, PortfolioSnapshot):
            return raw

        payload: dict[str, Any] = {}
        if hasattr(raw, "model_dump"):
            try:
                payload = raw.model_dump()
            except Exception:
                payload = {}
        if not payload and isinstance(raw, dict):
            payload = dict(raw)
        elif not payload and hasattr(raw, "__dict__"):
            payload = dict(vars(raw))

        def pick(keys: list[str], default: Optional[Any] = None) -> Any:
            for key in keys:
                if key in payload and payload[key] is not None:
                    return payload[key]
            return default

        equity_total = _to_decimal(
            pick(["equity_total_usdt", "equity_total", "equity"], "0"))
        equity_free = _to_decimal(
            pick(["equity_free_usdt", "equity_free"], "0"))
        equity_locked = pick(["equity_locked_usdt", "equity_locked"])
        positions_value = pick(["positions_value_usdt", "positions_value"])
        ts_val = pick(["timestamp", "ts"])
        if ts_val is None:
            ts = datetime.utcnow()
        else:
            try:
                ts = datetime.fromtimestamp(
                    float(ts_val)) if isinstance(ts_val, (int, float)) else datetime.fromisoformat(str(ts_val))
            except Exception:
                ts = datetime.utcnow()

        source = pick(["source"], None)

        return PortfolioSnapshot(
            equity_total=equity_total,
            equity_free=equity_free,
            equity_locked=equity_locked,
            positions_value=positions_value,
            timestamp=ts,
            source=source,
        )
