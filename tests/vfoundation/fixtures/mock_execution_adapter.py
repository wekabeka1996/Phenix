"""
MockExecutionAdapter — test fixture extracted from vfoundation.core.adapters.execution_adapter.

Use this in tests instead of importing from production code.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, Optional

from vfoundation.core.adapters.execution_adapter import (
    ExecutionAdapter,
    ExecutionMode,
    OrderDTO,
)

logger = logging.getLogger(__name__)


class MockExecutionAdapter(ExecutionAdapter):
    """
    Mock implementation for dry_run and paper modes.

    Simulates order lifecycle without real SDK calls.
    """

    def __init__(self, mode: Optional[ExecutionMode] = None) -> None:
        super().__init__(mode)
        self._next_exchange_order_id = 1
        self._orders: Dict[str, Dict[str, Any]] = {}

    def _submit_impl(self, order: OrderDTO, client_order_id: str) -> Dict[str, Any]:
        if self.mode == ExecutionMode.DRY_RUN:
            logger.info(f"DRY_RUN: Simulating submit {order.symbol} {order.side} {order.qty}")
            return {
                "event_type": "ORDER_PLACED",
                "client_order_id": client_order_id,
                "exchange_order_id": None,
                "symbol": order.symbol,
                "side": order.side,
                "order_type": order.order_type,
                "price": float(order.price) if order.price else None,
                "qty": float(order.qty),
                "qty_remain": float(order.qty),
                "status": "SIMULATED",
            }

        exchange_order_id = f"MOCK_{self._next_exchange_order_id}"
        self._next_exchange_order_id += 1

        order_state = {
            "client_order_id": client_order_id,
            "exchange_order_id": exchange_order_id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "price": order.price,
            "qty": order.qty,
            "qty_remain": order.qty,
            "status": "NEW",
        }
        self._orders[exchange_order_id] = order_state

        logger.info(f"PAPER: Order placed {exchange_order_id}")
        return {
            "event_type": "ORDER_PLACED",
            "client_order_id": client_order_id,
            "exchange_order_id": exchange_order_id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "price": float(order.price) if order.price else None,
            "qty": float(order.qty),
            "qty_remain": float(order.qty),
            "status": "NEW",
        }

    def _cancel_impl(
        self, order_id: Optional[str], client_order_id: Optional[str]
    ) -> Dict[str, Any]:
        if self.mode == ExecutionMode.DRY_RUN:
            logger.info(f"DRY_RUN: Simulating cancel {order_id or client_order_id}")
            return {
                "event_type": "CANCELLED",
                "client_order_id": client_order_id,
                "exchange_order_id": order_id,
                "reason": "USER_CANCEL",
                "status": "SIMULATED",
            }

        if order_id and order_id in self._orders:
            self._orders[order_id]["status"] = "CANCELLED"
            logger.info(f"PAPER: Order cancelled {order_id}")

        return {
            "event_type": "CANCELLED",
            "client_order_id": client_order_id,
            "exchange_order_id": order_id,
            "reason": "USER_CANCEL",
            "status": "CANCELLED",
        }

    async def stream(self) -> AsyncIterator[Dict[str, Any]]:
        logger.info("Mock stream: No events (use real adapter for streaming)")
        if False:  # pragma: no cover
            yield {}
