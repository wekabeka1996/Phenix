# vfoundation/apps/reference/domains/execution_position/exposure_guard.py
"""
Portfolio Exposure Guard for execution_position domain.

Blocks new position openings when total exposure exceeds configured fraction of equity_free_usdt.
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExposureState:
    """Internal state for exposure tracking."""

    equity_free_usdt: Decimal = Decimal("0")
    open_positions_usd: Decimal = Decimal("0")
    pending_open_usd: Decimal = Decimal("0")
    reservations: Dict[str, Decimal] = field(default_factory=dict)  # key -> notional_usd
    reservations_ts: Dict[str, float] = field(default_factory=dict)  # key -> epoch_s


def _d(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """
    Safe Decimal parsing function.

    Converts value to Decimal safely, returning default on failure.
    """
    try:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        return default


class ExposureGuard:
    """
    Guards against excessive portfolio exposure by blocking new positions.

    Tracks current positions and pending orders to ensure total notional exposure
    doesn't exceed max_portfolio_fraction of equity_free_usdt.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize ExposureGuard with configuration.

        Args:
            config: Execution config dict with exposure settings
        """
        exposure_config = config.get("exposure", {})
        self.max_portfolio_fraction = _d(exposure_config.get("max_portfolio_fraction", 0.20))
        self.count_pending_orders = exposure_config.get("count_pending_orders", True)
        self.exclude_reduce_only = exposure_config.get("exclude_reduce_only", True)
        self.ttl_sec = int(exposure_config.get("pending_reservation_ttl_sec", 90))  # 90s default

        # State
        self.state = ExposureState()

        logger.info(
            f"ExposureGuard initialized: max_fraction={self.max_portfolio_fraction}, "
            f"count_pending={self.count_pending_orders}, exclude_reduce_only={self.exclude_reduce_only}, "
            f"ttl_sec={self.ttl_sec}"
        )

    def on_portfolio_update(self, payload: Dict[str, Any]) -> None:
        """
        Update equity and positions from portfolio state.

        Args:
            payload: Portfolio state payload from EVT:PORTFOLIO_STATE_UPDATED
        """
        # Update equity
        equity_str = payload.get("equity_free_usdt")
        if equity_str is not None:
            self.state.equity_free_usdt = _d(equity_str)

        # Recalculate positions notional
        positions = payload.get("positions", [])
        self.state.open_positions_usd = Decimal("0")

        for pos in positions:
            qty_str = pos.get("net_position", "0")
            price_str = pos.get("avg_entry_price", "0")

            qty = _d(qty_str)
            price = _d(price_str)

            if abs(qty) > Decimal("1e-9") and price > 0:
                notional = abs(qty) * price
                self.state.open_positions_usd += notional

        logger.debug(
            f"Portfolio updated: equity={self.state.equity_free_usdt}, "
            f"positions_notional={self.state.open_positions_usd}, pending_count={len(self.state.reservations)}"
        )

    def can_open(self, new_notional_usd: Decimal) -> tuple[bool, Dict[str, Any]]:
        """
        Check if new position can be opened without exceeding exposure limit.

        Args:
            new_notional_usd: Notional value of new position in USD

        Returns:
            (allowed: bool, data: dict with exposure details)
        """
        # Calculate current total exposure
        current_exposure = self.state.open_positions_usd

        # Add pending exposure if configured
        if self.count_pending_orders:
            current_exposure += self.state.pending_open_usd

        # Calculate exposure after adding new position
        new_total_exposure = current_exposure + new_notional_usd

        # Calculate limit
        limit_usd = self.state.equity_free_usdt * self.max_portfolio_fraction

        # Check if within limit
        allowed = new_total_exposure <= limit_usd

        data = {
            "equity_usd": str(self.state.equity_free_usdt),
            "limit_usd": str(limit_usd),
            "positions_usd": str(self.state.open_positions_usd),
            "pending_usd": str(self.state.pending_open_usd) if self.count_pending_orders else "0",
            "new_usd": str(new_notional_usd),
            "exposure_will_be_usd": str(new_total_exposure),
        }

        logger.debug(
            f"Exposure check: allowed={allowed}, current={current_exposure}, "
            f"new_total={new_total_exposure}, limit={limit_usd}"
        )

        return allowed, data

    def reserve(self, key: str, notional_usd: Decimal, reduce_only: bool = False) -> None:
        """
        Reserve exposure for pending order.

        Args:
            key: Unique key for the reservation (idempotent_key or rid)
            notional_usd: Notional value to reserve
            reduce_only: Whether this is a reduce-only order
        """
        if not self.count_pending_orders:
            return

        if self.exclude_reduce_only and reduce_only:
            logger.debug(f"Skipping reserve for reduce-only order: {key}")
            return

        now = time.time()
        self.state.reservations[key] = notional_usd
        self.state.reservations_ts[key] = now
        self.state.pending_open_usd += notional_usd
        logger.debug(f"Reserved exposure: key={key}, notional={notional_usd}, ts={now}")

    def release(self, key: str) -> None:
        """
        Release reserved exposure.

        Args:
            key: Reservation key to release
        """
        val = self.state.reservations.pop(key, None)
        self.state.reservations_ts.pop(key, None)
        if val is not None and self.count_pending_orders:
            self.state.pending_open_usd = max(Decimal("0"), self.state.pending_open_usd - val)
            logger.debug(f"Released exposure: key={key}, notional={val}")
        else:
            logger.warning(f"Attempted to release non-existent reservation: {key}")

    def expire_stale(self) -> List[str]:
        """
        Clean up expired reservations based on TTL.

        Returns:
            List of expired keys that were cleaned up
        """
        if self.ttl_sec <= 0:
            return []

        now = time.time()
        expired = []
        for k, ts in list(self.state.reservations_ts.items()):
            if now - ts >= self.ttl_sec:
                self.release(k)
                expired.append(k)
                logger.info(f"Expired stale reservation: key={k}, age={now - ts:.1f}s")

        if expired:
            logger.info(f"Expired {len(expired)} stale reservations")

        return expired

    def metrics_snapshot(self) -> Dict[str, str]:
        """
        Get current metrics snapshot for telemetry.

        Returns:
            Dict with string values for exposure metrics
        """
        current_exposure = self.state.open_positions_usd + (
            self.state.pending_open_usd if self.count_pending_orders else Decimal("0")
        )
        limit_usd = self.state.equity_free_usdt * self.max_portfolio_fraction

        return {
            "pending_usd": str(self.state.pending_open_usd),
            "open_positions_usd": str(self.state.open_positions_usd),
            "equity_usd": str(self.state.equity_free_usdt),
            "limit_usd": str(limit_usd),
            "current_exposure_usd": str(current_exposure),
            "reservations": str(len(self.state.reservations)),
        }

    def get_exposure_summary(self) -> Dict[str, Any]:
        """
        Get current exposure summary.

        Returns:
            Dict with exposure details
        """
        current_total = self.state.open_positions_usd + (
            self.state.pending_open_usd if self.count_pending_orders else Decimal("0")
        )
        limit_usd = self.state.equity_free_usdt * self.max_portfolio_fraction

        return {
            "equity_usd": str(self.state.equity_free_usdt),
            "limit_usd": str(limit_usd),
            "positions_usd": str(self.state.open_positions_usd),
            "pending_usd": str(self.state.pending_open_usd),
            "current_exposure_usd": str(current_total),
            "utilization_pct": float((current_total / limit_usd * 100) if limit_usd > 0 else 0),
            "pending_orders_count": len(self.state.reservations),
        }
