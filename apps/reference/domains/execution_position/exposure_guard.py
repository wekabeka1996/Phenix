"""
EXP-FIX: Exposure Guard with Portfolio Notional Hard Gate.

Implements fail-closed behavior when portfolio positions are stale/unknown,
and post-fill hold mechanism to prevent race conditions.
"""

from __future__ import annotations

import time
import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from vfoundation.obs.order_logger import order_logger


@dataclass
class ExposureState:
    """Data class for exposure state management."""

    reservations: Dict[str, Decimal]  # key -> notional_usd
    reservations_ts: Dict[str, float]  # key -> timestamp
    pending_exposure: Dict[str, Dict[str, Any]]  # key -> {notional, ts, reduce_only}
    postfill_reservations: Dict[
        str, Dict[str, Any]
    ]  # key -> {'notional': Decimal, 'exp_ts': float}


class ExposureGuard:
    """
    Exposure Guard with hard portfolio notional gate.

    Features:
    - Fail-closed when positions are stale/unknown
    - Post-fill hold to prevent FILL→portfolio race conditions
    - Shadow notional validation for safety
    """

    def __init__(self, config: Dict[str, Any], fsm: Optional[Any] = None):
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.fsm = fsm  # Store FSM reference for event emission

        # Configuration
        exposure_config = (
            config.get("trading", {}).get("execution", {}).get("exposure", {})
        )
        self.max_portfolio_fraction = Decimal(
            str(exposure_config.get("max_portfolio_fraction", "0.20"))
        )
        self.pending_ttl_sec = exposure_config.get("pending_ttl_sec", 90)
        self.post_fill_hold_ttl_sec = exposure_config.get("post_fill_hold_ttl_sec", 5)
        self.positions_stale_ttl_sec = exposure_config.get("positions_stale_ttl_sec", 5)

        # State
        self.state = ExposureState(
            reservations={},
            reservations_ts={},
            pending_exposure={},
            postfill_reservations={},
        )

        # Metrics
        self.metrics = {
            "exposure_fail_closed_total": {},
            "postfill_hold_active": 0,
            "postfill_hold_expired_total": 0,
            "exposure_mismatch_total": 0,
        }

    def can_open(
        self, symbol: str, notional_usd: Decimal, portfolio_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check if opening a position is allowed based on exposure limits.

        EXP-FIX: Fail-closed if positions are stale/unknown.

        Args:
            symbol: Trading symbol
            notional_usd: Position notional value in USD
            portfolio_state: Latest portfolio state from EVT:PORTFOLIO_STATE_UPDATED

        Returns:
            Dict with 'allowed': bool and 'reason' if rejected
        """
        now_ms = int(time.time() * 1000)

        # Extract portfolio data
        try:
            equity_free_usdt_str = portfolio_state.get("equity_free_usdt", "0")
            open_positions_usd_str = portfolio_state.get("open_positions_usd", "0")
            positions_last_ts_ms = portfolio_state.get("positions_last_ts_ms", 0)

            equity_free_usdt = (
                Decimal(str(equity_free_usdt_str))
                if equity_free_usdt_str
                else Decimal("0")
            )
            open_positions_usd = (
                Decimal(str(open_positions_usd_str))
                if open_positions_usd_str
                else Decimal("0")
            )
        except (ValueError, TypeError, AttributeError) as e:
            self.logger.error(f"EXPOSURE_DATA_ERROR: Invalid portfolio data - {e}")
            return {"allowed": False, "reason": "PORTFOLIO_DATA_INVALID"}

        # EXP-FIX: Fail-closed if positions are stale or unknown
        if open_positions_usd is None or positions_last_ts_ms == 0:
            reason = "PORTFOLIO_UNKNOWN"
            self._increment_metric("exposure_fail_closed_total", reason)
            self.logger.warning(
                f"EXPOSURE_FAIL_CLOSED: {reason} - no position data available"
            )
            # Emit event for bridge to monitor
            if self.fsm:
                from vfoundation.core.protocol import Message

                self.fsm.emit(
                    Message(
                        op="EVT",
                        verb="EXPOSURE_FAIL_CLOSED",
                        src="execution_position",
                        dst="*",
                        pld={"reason": reason},
                        why="exposure_fail_closed",
                    )
                )
            return {"allowed": False, "reason": reason}

        stale_sec = (now_ms - positions_last_ts_ms) / 1000.0
        if stale_sec > self.positions_stale_ttl_sec:
            reason = "PORTFOLIO_STALE"
            self._increment_metric("exposure_fail_closed_total", reason)
            self.logger.warning(
                f"EXPOSURE_FAIL_CLOSED: {reason} - stale {stale_sec:.1f}s > {self.positions_stale_ttl_sec}s"
            )
            # Emit event for bridge to monitor
            if self.fsm:
                from vfoundation.core.protocol import Message

                self.fsm.emit(
                    Message(
                        op="EVT",
                        verb="EXPOSURE_FAIL_CLOSED",
                        src="execution_position",
                        dst="*",
                        pld={"reason": reason, "stale_sec": stale_sec},
                        why="exposure_fail_closed",
                    )
                )
            return {"allowed": False, "reason": reason, "stale_sec": stale_sec}

        # Calculate current exposure
        current_pending = sum(self.state.reservations.values())
        current_postfill = sum(
            item["notional"]
            for item in self.state.postfill_reservations.values()
            if time.time() < item["exp_ts"]
        )
        total_exposure = open_positions_usd + current_pending + current_postfill

        # Calculate limit
        portfolio_limit = equity_free_usdt * self.max_portfolio_fraction
        new_total_exposure = total_exposure + notional_usd

        # Log exposure breakdown
        utilization_pct = (
            (new_total_exposure / equity_free_usdt * 100) if equity_free_usdt > 0 else 0
        )
        self.logger.info(
            f"EXPOSURE_BREAKDOWN: eq={equity_free_usdt:.2f}, pos={open_positions_usd:.2f}, "
            f"pend={current_pending:.2f}, postfill={current_postfill:.2f}, "
            f"new_total={new_total_exposure:.2f}, lim={portfolio_limit:.2f}, util={utilization_pct:.1f}%"
        )

        # Check limit
        if new_total_exposure > portfolio_limit:
            reason = "EXPOSURE_LIMIT_EXCEEDED"
            self.logger.warning(
                f"EXPOSURE_REJECT: {reason} - would exceed {portfolio_limit:.2f} USD limit"
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": f"exposure_check_{symbol}_{now_ms}",
                "event_type": "ORDER_REJECTED",
                "symbol": symbol,
                "side": "NONE",
                "quantity": float(notional_usd),
                "nrr_code": "NRR-011",
                "why": f"Exposure limit exceeded: {new_total_exposure:.2f} > {portfolio_limit:.2f}",
                "source_fsm": "ExposureGuard",
                "metadata": {"exposure_check": True, "portfolio_limit": float(portfolio_limit), "new_total": float(new_total_exposure)}
            })

            return {"allowed": False, "reason": reason}

        return {"allowed": True}

    def reserve(
        self, key: str, notional_usd: Decimal, reduce_only: bool = False
    ) -> None:
        """
        Reserve exposure for a pending order.

        Args:
            key: Reservation key (idempotent_key or rid)
            notional_usd: Notional value to reserve
            reduce_only: Whether this is a reduce-only order
        """
        now = time.time()
        self.state.reservations[key] = notional_usd
        self.state.reservations_ts[key] = now

        # Store in pending_exposure for legacy compatibility
        self.state.pending_exposure[key] = {
            "notional": notional_usd,
            "ts": now,
            "reduce_only": reduce_only,
        }

        self.logger.debug(f"EXPOSURE_RESERVE: key={key}, usd={notional_usd}")

        # Log to OrderLoggerV1
        order_logger.write({
            "rid": f"reserve_{key}",
            "event_type": "ORDER_INTENT",
            "symbol": "",  # Will be filled by caller context
            "side": "NONE",
            "quantity": float(notional_usd),
            "source_fsm": "ExposureGuard",
            "reservation_id": key,
            "metadata": {"reservation_created": True, "reduce_only": reduce_only}
        })

    def release(self, key: str) -> None:
        """
        Release exposure reservation.

        Args:
            key: Reservation key to release
        """
        if key in self.state.reservations:
            released_usd = self.state.reservations.pop(key)
            self.state.reservations_ts.pop(key, None)
            self.state.pending_exposure.pop(key, None)
            self.logger.debug(f"EXPOSURE_RELEASE: key={key}, usd={released_usd}")

    def on_fill(self, key: str, notional_usd: Decimal) -> None:
        """
        Handle order fill - move to post-fill hold instead of immediate release.

        EXP-FIX: Prevents race condition where FILL is processed before portfolio update.

        Args:
            key: Reservation key
            notional_usd: Filled notional value
        """
        if key in self.state.reservations:
            # Move to post-fill hold instead of releasing
            expiration_ts = time.time() + self.post_fill_hold_ttl_sec
            self.state.postfill_reservations[key] = {
                "notional": notional_usd,
                "exp_ts": expiration_ts,
            }
            self.state.reservations.pop(key, None)
            self.state.reservations_ts.pop(key, None)
            self.state.pending_exposure.pop(key, None)

            self.metrics["postfill_hold_active"] = len(self.state.postfill_reservations)
            self.logger.debug(
                f"POSTFILL_HOLD: key={key}, usd={notional_usd}, expires={expiration_ts}"
            )

    def expire_stale(self) -> List[str]:
        """
        Clean up stale reservations and expired post-fill holds.

        Returns:
            List of expired reservation keys
        """
        now = time.time()
        expired = []

        # Clean up stale reservations
        stale_reservations = [
            key
            for key, ts in self.state.reservations_ts.items()
            if now - ts > self.pending_ttl_sec
        ]
        for key in stale_reservations:
            expired.append(key)
            self.state.reservations.pop(key, None)
            self.state.reservations_ts.pop(key, None)
            self.state.pending_exposure.pop(key, None)

        # Clean up expired post-fill holds
        expired_postfill = [
            key
            for key, item in self.state.postfill_reservations.items()
            if now >= item["exp_ts"]
        ]
        for key in expired_postfill:
            self.state.postfill_reservations.pop(key, None)
            self.metrics["postfill_hold_expired_total"] += 1
            expired.append(key)  # Add to expired list

        self.metrics["postfill_hold_active"] = len(self.state.postfill_reservations)

        if expired:
            self.logger.info(
                f"EXPOSURE_CLEANUP: expired {len(expired)} reservations, {len(expired_postfill)} postfill holds"
            )

        return expired

    def get_exposure_summary(self) -> Dict[str, Any]:
        """Get current exposure summary for metrics."""
        total_pending = sum(self.state.reservations.values())
        total_postfill = len(self.state.postfill_reservations)

        return {
            "reservations_count": len(self.state.reservations),
            "reservations_usd": float(total_pending),
            "postfill_hold_count": total_postfill,
            "pending_ttl_sec": self.pending_ttl_sec,
            "postfill_hold_ttl_sec": self.post_fill_hold_ttl_sec,
        }

    def _increment_metric(self, metric_name: str, label: str) -> None:
        """Increment a labeled metric counter."""
        if metric_name not in self.metrics:
            self.metrics[metric_name] = {}
        if label not in self.metrics[metric_name]:
            self.metrics[metric_name][label] = 0
        self.metrics[metric_name][label] += 1
