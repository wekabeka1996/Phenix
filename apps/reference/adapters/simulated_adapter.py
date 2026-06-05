# apps/reference/adapters/simulated_adapter.py
"""
Simulated Exchange Adapter (Refactored ADPT-FIX-01).

Implements AbstractExchangeAdapter for simulation and testing.
Strictly typed and consistent with BinanceAdapter.
"""

import logging
import time
import asyncio
from typing import Any, Dict, List, Optional
from decimal import Decimal

from .contract import (
    AbstractExchangeAdapter,
    ExchangeOrderParams,
    ExchangeOrderResponse,
    ExchangePosition,
)

logger = logging.getLogger(__name__)


class SimulatedAdapter(AbstractExchangeAdapter):
    """
    A simulated exchange adapter that mocks order placement and queries.
    Inherits from AbstractExchangeAdapter for strict contract compliance.
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._positions: List[ExchangePosition] = []
        self._orders: Dict[str, ExchangeOrderResponse] = {}
        self._latency_ms = self.config.get(
            "latency_ms", 10)  # Default 10ms latency
        logger.info(
            f"SimulatedAdapter initialized (latency={self._latency_ms}ms)")

    async def create_order(self, params: ExchangeOrderParams) -> ExchangeOrderResponse:
        """
        Simulate order creation with latency.
        """
        # ACK Latency
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000.0)

        symbol = params.symbol
        qty = params.quantity
        side = params.side
        price = params.price or "0.0"

        logger.info(
            f"[SIMULATED] create_order: {side} {qty} {symbol} @ {price} "
            f"(ClOrdID: {params.client_order_id})"
        )

        timestamp_ms = int(time.time() * 1000)
        order_id = f"sim_{timestamp_ms}_{params.client_order_id or 'noid'}"

        # Determine status
        # For simulation fidelity, we default to FILLED for market orders in simple mode,
        # but keep NEW for limits unless we implement a matching engine.
        # Given the "Optimistic Execution" audit finding, we should support explicit NEW state.
        # However, to preserve backward compatibility with the current training loop, we auto-fill by default
        # unless configured otherwise.

        # Optimistic default for now, but delayed by latency_ms above.
        status = "FILLED"

        response = ExchangeOrderResponse(
            order_id=order_id,
            client_order_id=params.client_order_id,
            symbol=symbol,
            side=side,
            quantity=str(qty),
            filled_qty=str(qty) if status == "FILLED" else "0.0",
            price=price,
            status=status,
            timestamp_ms=timestamp_ms,
        )

        self._orders[order_id] = response
        return response

    async def cancel_order(
        self, symbol: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None
    ) -> ExchangeOrderResponse:
        """
        Simulate order cancellation.
        """
        logger.info(
            f"[SIMULATED] cancel_order: {symbol} ID:{order_id} ClID:{client_order_id}")

        timestamp_ms = int(time.time() * 1000)

        # Echo back what we know
        return ExchangeOrderResponse(
            order_id=order_id or "unknown_sim_id",
            client_order_id=client_order_id,
            symbol=symbol,
            side="UNKNOWN",  # We don't track state deeply here yet
            quantity="0.0",
            filled_qty="0.0",
            price="0.0",
            status="CANCELED",
            timestamp_ms=timestamp_ms,
        )

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[ExchangeOrderResponse]:
        """
        Return empty list of open orders (or tracked ones if we implemented state).
        """
        return []

    async def get_open_orders_raw(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Return raw open-order payloads for simulation.
        """
        return []

    async def get_open_positions(self, symbol: Optional[str] = None) -> List[ExchangePosition]:
        """
        Return mocked open positions.
        """
        return self._positions

    async def get_mark_price(self, symbol: str, ttl_ms: int = 250) -> float:
        """
        Mock mark price.
        """
        return 50000.0  # Default mock price for everything

    async def get_last_price(self, symbol: str) -> float:
        """
        Mock last price.
        """
        return 50000.0

    async def get_account_balance(self) -> List[Dict[str, Any]]:
        """
        Mock balance.
        """
        return [
            {
                "asset": "USDT",
                "balance": "100000.0",
                "crossWalletBalance": "100000.0",
            }
        ]

    async def get_exchange_info(self, symbol: str) -> Dict[str, Any]:
        """
        Mock exchange info.
        """
        return {
            "symbol": symbol,
            "status": "TRADING",
            "filters": [],
        }

    async def quantize_quantity(self, symbol: str, qty: Any) -> str:
        """
        Mock quantization (identity).
        """
        return str(qty)

    async def aclose(self) -> None:
        """
        Cleanup.
        """
        pass
