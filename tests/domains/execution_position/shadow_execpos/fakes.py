import asyncio
from typing import Any, Dict, List, Optional

from apps.reference.domains.execution_position.shadow_execpos.types import ExecutionStatus


class FakeExecutionAdapter:
    """In-memory fake adapter for ExecPosRuntimeV2 smoke tests."""

    def __init__(self):
        self.placed_orders: List[Dict[str, Any]] = []
        self.cancelled_orders: List[Dict[str, Any]] = []
        self.open_positions: List[Dict[str, Any]] = []

    async def place_order(
        self,
        symbol: str,
        side: Optional[str],
        order_type: Optional[str],
        quantity: Optional[Any],
        price: Optional[Any] = None,
        client_order_id: Optional[str] = None,
        reduce_only: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        order_id = f"order_{len(self.placed_orders)+1}"
        entry = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
            "price": price,
            "client_order_id": client_order_id,
            "reduce_only": reduce_only,
            "extra": kwargs,
        }
        self.placed_orders.append(entry)
        return {
            "status": ExecutionStatus.SUBMITTED,
            "success": True,
            "order_id": order_id,
            "client_order_id": client_order_id,
            "error": None,
            "metadata": {},
        }

    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.cancelled_orders.append(
            {
                "symbol": symbol,
                "order_id": order_id,
                "client_order_id": client_order_id,
            }
        )
        return {
            "status": ExecutionStatus.SUCCESS,
            "success": True,
            "order_id": order_id,
            "client_order_id": client_order_id,
            "error": None,
            "metadata": {},
        }

    async def get_open_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if symbol:
            return [p for p in self.open_positions if p.get("symbol") == symbol]
        return list(self.open_positions)

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        if symbol:
            return [o for o in self.placed_orders if o.get("symbol") == symbol]
        return list(self.placed_orders)

    # Alias for create_order (used by ExecutionService)
    async def create_order(
        self,
        symbol: str = None,
        side: str = None,
        order_type: str = None,
        quantity: Any = None,
        price: Any = None,
        client_order_id: str = None,
        reduce_only: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Alias for place_order - ExecutionService uses create_order."""
        return await self.place_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            client_order_id=client_order_id,
            reduce_only=reduce_only,
            **kwargs,
        )

    # Synchronous helper for tests
    def place_position(self, symbol: str, qty: float, avg_price: float, side: str) -> None:
        self.open_positions.append(
            {"symbol": symbol, "positionAmt": qty,
                "entryPrice": avg_price, "side": side}
        )


async def run_runtime_event(runtime, event) -> None:
    """Helper to run runtime.handle inside tests."""
    await runtime.handle(event)
