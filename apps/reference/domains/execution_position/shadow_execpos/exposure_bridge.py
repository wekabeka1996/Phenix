"""
Exposure Bridge for ExecPos V2 Runtime
=======================================

Emits exposure update events to notify other domains (portfolio, risk)
about changes in execution position exposure.

Responsibilities:
- Emit EVT:EXEC_POS_EXPOSURE_UPDATED events on position changes
- Fail-closed: event emission failures are logged but never crash the runtime
"""
from __future__ import annotations
import time
import logging
from typing import Any, Callable, Dict, Optional
from decimal import Decimal, InvalidOperation

from apps.reference.domains.execution_position.contracts import (
    EVT_EXEC_POS_EXPOSURE_UPDATED,
    POSITION_ZERO_TOLERANCE
)

logger = logging.getLogger(__name__)


class ExposureBridge:
    """
    Exposure bridge for emitting position exposure updates.

    Uses dependency injection for the event emission function to enable testing
    and avoid tight coupling to specific event bus implementations.
    """

    def __init__(self, emit_fn: Callable[[str, Dict[str, Any]], None]):
        """
        Initialize exposure bridge with dependency injection.

        Args:
            emit_fn: Function to emit messages (accepts event_kind and payload)
        """
        self.emit_fn = emit_fn
        self._metrics = {
            "exposures_emitted": 0,
            "emit_errors": 0,
        }

    def emit_exposure_update(self, position_state: Dict[str, Any]) -> bool:
        """
        Emit EXEC_POS_EXPOSURE_UPDATED event for position state change.

        Args:
            position_state: Current position state with symbol, size, direction, etc.

        Returns:
            True if emission succeeded, False if failed (failure is logged, never raises)
        """
        try:
            # Create Message compatible event
            # Note: We'll use a simple dict that can be converted to Message by the runtime
            event = {
                "kind": EVT_EXEC_POS_EXPOSURE_UPDATED,
                "payload": {
                    "symbol": position_state.get("symbol"),
                    "net_position_size": str(position_state.get("position_size") or position_state.get("qty", 0)),
                    "direction": self._normalize_direction(position_state),
                    "exposure_usdt": str(self._calculate_exposure_usdt(position_state)),
                    "leverage": position_state.get("leverage", 1),
                    "realized_pnl": str(position_state.get("realized_pnl", 0)),
                    "unrealized_pnl": str(position_state.get("unrealized_pnl", 0)),
                    "update_time": time.time(),
                },
                "source": "execution_position_v2",
            }

            # Emit event (fail-closed)
            # Call emit_fn with event_kind and payload separately
            self.emit_fn(event["kind"], event["payload"])
            self._metrics["exposures_emitted"] += 1
            logger.debug(
                f"Exposure: emitted update for {event['payload']['symbol']} "
                f"({event['payload']['direction']}, size={event['payload']['net_position_size']})"
            )
            return True

        except Exception as e:
            self._metrics["emit_errors"] += 1
            logger.error(
                f"Exposure emission failed: {e}",
                exc_info=False,
                extra={"symbol": position_state.get("symbol"), "error": str(e)}
            )
            return False

    def _normalize_direction(self, position_state: Dict[str, Any]) -> str:
        """
        Normalize position direction to LONG/SHORT/FLAT.

        Args:
            position_state: Position state dict

        Returns:
            Direction string: LONG, SHORT, or FLAT
        """
        # Check explicit direction field
        direction = position_state.get("direction") or position_state.get("side")
        if direction:
            direction_upper = str(direction).upper()
            if direction_upper in ("LONG", "SHORT", "FLAT"):
                return direction_upper

        # Infer from position size
        try:
            size = float(position_state.get("position_size") or position_state.get("qty", 0))
            if abs(size) < POSITION_ZERO_TOLERANCE:
                return "FLAT"
            return "LONG" if size > 0 else "SHORT"
        except (ValueError, TypeError):
            return "FLAT"

    def _calculate_exposure_usdt(self, position_state: Dict[str, Any]) -> Decimal:
        """
        Calculate exposure in USDT (position_size * entry_price).

        Args:
            position_state: Position state dict

        Returns:
            Exposure in USDT as Decimal
        """
        try:
            size = Decimal(str(position_state.get("position_size") or position_state.get("qty", 0)))
            entry_price = Decimal(str(position_state.get("entry_price") or position_state.get("avg_price", 0)))
            return abs(size * entry_price)
        except (ValueError, TypeError, InvalidOperation):
            return Decimal("0")

    def get_metrics(self) -> Dict[str, int]:
        """Get exposure bridge metrics."""
        return dict(self._metrics)

