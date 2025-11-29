# apps/reference/adapters/simulated_adapter.py
"""
Simulated Execution Adapter (Part EXECUTE-T04-B).

A mock execution adapter that simulates order placement without real API calls.
Used for:
- Shadow mode testing (validate FSM logic without real execution)
- Development and debugging (no API credentials needed)
- Integration tests (fast, deterministic responses)
- Backtesting preparation (baseline for trade simulation)

This adapter always returns successful responses, enabling full FSM flow
validation without exchange connectivity.
"""

import logging
import time
from decimal import Decimal
from typing import Dict, Any

# Handle both package import and standalone execution
try:
    from vfoundation.core.protocol import Message
    from .execution_adapter import AbstractExecutionAdapter
except ImportError:
    import sys
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent.parent.parent
    sys.path.insert(0, str(project_root / "vfoundation" / "vfoundation"))
    sys.path.insert(0, str(project_root / "apps"))
    from vfoundation.core.protocol import Message
    from apps.reference.adapters.execution_adapter import (
        AbstractExecutionAdapter,
    )

logger = logging.getLogger(__name__)


class SimulatedExecutionAdapter(AbstractExecutionAdapter):
    """
    A simulated execution adapter that logs order requests and returns
    mock successful responses without connecting to any real exchange.

    Design:
    - Always returns 'ACCEPTED' status (no real validation)
    - Generates mock exchange_order_id using timestamp
    - Preserves qty for fill simulation
    - Logs all operations for observability
    - Returns 'CONNECTED' status (no real connection)

    Use Cases:
    - Shadow mode: Run FSM without real orders
    - Integration tests: Fast, deterministic behavior
    - Development: No API credentials needed
    - TDD: Validate FSM logic before exchange integration

    Example:
        >>> adapter = SimulatedExecutionAdapter()
        >>> dec_open = Message(op="DEC", verb="OPEN",
        ...                    pld={"symbol": "ETHUSDT", "qty": "0.5"})
        >>> result = adapter.place_order(dec_open)
        >>> assert result['status'] == 'ACCEPTED'
        >>> assert 'sim_' in result['exchange_order_id']
    """

    def place_order(self, dec_msg: Message) -> Dict[str, Any]:
        """
        Simulate order placement.

        Args:
            dec_msg: DEC:OPEN or DEC:ADJUST message with order details
                Expected payload: {symbol, side, qty, price, order_type, tif}

        Returns:
            Standardized response:
            {
                'status': 'ACCEPTED' (always successful in simulation),
                'exchange_order_id': 'sim_<timestamp_ms>' (mock ID),
                'filled_qty': '<qty>' (echoes input qty as string),
                'message': 'Order simulated successfully.',
                'timestamp': <current_time_ms>
            }

        Notes:
            - No validation of payload fields (always succeeds)
            - No real API call (instant response)
            - Deterministic behavior (useful for tests)
        """
        symbol = dec_msg.pld.get("symbol", "UNKNOWN")
        qty = dec_msg.pld.get("qty", "0.0")
        side = dec_msg.pld.get("side", "UNKNOWN")
        price = dec_msg.pld.get("price", "0.0")

        logger.info(
            f"[SIMULATED] Placing order: {side.upper()} {qty} {symbol} @ {price}. "
            f"Simulating immediate acceptance."
        )

        # Generate mock exchange order ID using timestamp for uniqueness
        timestamp_ms = int(time.time() * 1000)
        mock_order_id = f"sim_{timestamp_ms}"

        # Return standardized success response
        return {
            "status": "ACCEPTED",
            "exchange_order_id": mock_order_id,
            "filled_qty": str(Decimal(qty)),  # Preserve precision, return as string
            "message": "Order simulated successfully.",
            "timestamp": timestamp_ms,
        }

    def cancel_order(self, dec_msg: Message) -> Dict[str, Any]:
        """
        Simulate order cancellation.

        Args:
            dec_msg: DEC:CANCEL message with exchange_order_id to cancel
                Expected payload: {exchange_order_id}

        Returns:
            Standardized response:
            {
                'status': 'ACCEPTED' (always successful),
                'exchange_order_id': '<original_order_id>' (echoed),
                'filled_qty': '0.0' (no fills in simulation),
                'message': 'Cancel simulated successfully.',
                'timestamp': <current_time_ms>
            }

        Notes:
            - No validation if order exists (always succeeds)
            - No state tracking (stateless adapter)
        """
        order_id = dec_msg.pld.get("exchange_order_id", "UNKNOWN")

        logger.info(
            f"[SIMULATED] Cancelling order {order_id}. "
            f"Simulating immediate cancellation."
        )

        timestamp_ms = int(time.time() * 1000)

        # Return standardized cancel success response
        return {
            "status": "ACCEPTED",
            "exchange_order_id": order_id,
            "filled_qty": "0.0",  # No partial fills in simulation
            "message": "Cancel simulated successfully.",
            "timestamp": timestamp_ms,
        }

    def get_status(self) -> str:
        """
        Simulate connection status check.

        Returns:
            'CONNECTED' (always, no real connection to check)

        Notes:
            - Used by FSM for circuit breaker logic
            - In simulation, always returns healthy status
            - Real adapters would check actual connection health
        """
        return "CONNECTED"

    async def get_open_positions(
        self, symbol: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Simulate getting open positions.

        Returns:
            Empty list (stateless simulation does not track positions).
        """
        return []

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """
        Simulate getting open orders.

        Returns:
            Empty list (stateless simulation does not track orders).
        """
        return []
