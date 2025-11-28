# apps/reference/domains/execution_position/simulated_adapter.py
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
    from apps.reference.domains.execution_position.infra.execution_adapter import AbstractExecutionAdapter
except ImportError:
    import sys
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent.parent.parent
    sys.path.insert(0, str(project_root / "vfoundation" / "vfoundation"))
    sys.path.insert(0, str(project_root / "apps"))
    from vfoundation.core.protocol import Message
    from apps.reference.domains.execution_position.infra.execution_adapter import (
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

    def __init__(self, fsm=None, config=None):
        super().__init__(fsm=fsm, config=config)
        # Internal store of orders and positions for simulated behavior
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._positions: Dict[str, Dict[str, Any]] = {}

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
        result = {
            "status": "ACCEPTED",
            "exchange_order_id": mock_order_id,
            # Preserve precision, return as string
            "filled_qty": str(Decimal(qty)),
            "message": "Order simulated successfully.",
            "timestamp": timestamp_ms,
        }

        # Track order in internal store for get_open_orders
        self._orders[mock_order_id] = {
            "symbol": symbol,
            "orderId": mock_order_id,
            "clientOrderId": dec_msg.pld.get("newClientOrderId"),
            "type": dec_msg.pld.get("order_type", "MARKET"),
            "reduceOnly": dec_msg.pld.get("reduceOnly", False),
            "closePosition": dec_msg.pld.get("closePosition", False),
            "origQty": qty,
            "executedQty": str(Decimal(qty)),
            "status": "ACCEPTED",
            "side": side,
        }

        return result

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
        res = {
            "status": "ACCEPTED",
            "exchange_order_id": order_id,
            "filled_qty": "0.0",  # No partial fills in simulation
            "message": "Cancel simulated successfully.",
            "timestamp": timestamp_ms,
        }

        # Remove order from internal store if present
        if order_id in self._orders:
            self._orders.pop(order_id, None)
        return res

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

    # ---- Async adapter compatibility: awaitable high-level methods used by ExecPosFSM
    async def place_market_entry(self, symbol: str, side: str, qty: str, new_client_order_id: str = None) -> Dict[str, Any]:
        # Delegate to synchronous place_order logic for simplicity
        # Build minimal dec_msg
        dec_msg = Message(op="DEC", verb="OPEN", src="sim", dst="execution_position", rid="sim", pld={
                          "symbol": symbol, "side": side, "qty": qty, "newClientOrderId": new_client_order_id})
        return self.place_order(dec_msg)

    async def place_stop_market_close_position(self, symbol: str, side: str, qty: str, new_client_order_id: str = None) -> Dict[str, Any]:
        # Simulate stop market close: create a cancelable reduce-only order
        dec_msg = Message(op="DEC", verb="PLACE_ORDER", src="sim", dst="execution_position", rid="sim", pld={
                          "symbol": symbol, "side": side, "qty": qty, "order_type": "STOP_MARKET", "newClientOrderId": new_client_order_id, "reduceOnly": True, "closePosition": True})
        return self.place_order(dec_msg)

    async def place_take_profit_market_close_position(self, symbol: str, side: str, price: str, new_client_order_id: str = None) -> Dict[str, Any]:
        dec_msg = Message(op="DEC", verb="PLACE_ORDER", src="sim", dst="execution_position", rid="sim", pld={
                          "symbol": symbol, "side": side, "qty": "0.0", "order_type": "TAKE_PROFIT_MARKET", "price": price, "newClientOrderId": new_client_order_id, "reduceOnly": True})
        return self.place_order(dec_msg)

    async def place_limit_reduce_only(self, symbol: str, side: str, price: str, qty: str, new_client_order_id: str = None) -> Dict[str, Any]:
        dec_msg = Message(op="DEC", verb="PLACE_ORDER", src="sim", dst="execution_position", rid="sim", pld={
                          "symbol": symbol, "side": side, "qty": qty, "order_type": "LIMIT", "price": price, "newClientOrderId": new_client_order_id, "reduceOnly": True})
        return self.place_order(dec_msg)

    async def place_market_reduce_only(self, symbol: str, side: str, qty: str, new_client_order_id: str = None) -> Dict[str, Any]:
        dec_msg = Message(op="DEC", verb="PLACE_ORDER", src="sim", dst="execution_position", rid="sim", pld={
                          "symbol": symbol, "side": side, "qty": qty, "order_type": "MARKET", "newClientOrderId": new_client_order_id, "reduceOnly": True})
        return self.place_order(dec_msg)

    async def cancel_order_async(self, symbol: str, order_id: str = None, client_order_id: str = None) -> Dict[str, Any]:
        # Support both signature styles: Cancel by order ID or client order ID
        # Accept None and return accepted
        dec_msg = Message(op="DEC", verb="CANCEL", src="sim", dst="execution_position", rid="sim", pld={
                          "symbol": symbol, "exchange_order_id": order_id, "client_order_id": client_order_id})
        return self.cancel_order_dec(dec_msg) if hasattr(self, 'cancel_order_dec') else {
            "status": "ACCEPTED",
            "exchange_order_id": order_id or client_order_id or "UNKNOWN",
            "filled_qty": "0.0",
            "message": "Cancel simulated successfully.",
            "timestamp": int(time.time() * 1000),
        }

    # Backwards-compatible cancellation accepting Message
    def cancel_order_dec(self, dec_msg: Message) -> Dict[str, Any]:
        return self.cancel_order(dec_msg)

    async def get_open_orders(self, symbol: str = None) -> list[Dict[str, Any]]:
        if symbol:
            return [v for v in self._orders.values() if v.get('symbol') == symbol]
        return list(self._orders.values())

    async def get_open_positions(self, symbol: str = None) -> list[Dict[str, Any]]:
        # Positions not simulated in depth; return list based on tracked positions
        if symbol:
            pos = self._positions.get(symbol)
            return [pos] if pos else []
        return list(self._positions.values())
