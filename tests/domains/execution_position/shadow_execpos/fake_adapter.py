"""
Fake Adapter for Shadow ExecPos Testing
=======================================

Simulates exchange adapter behavior for offline testing.
"""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import asyncio

@dataclass
class FakeAdapterCall:
    """Record of an adapter call."""
    verb: str  # "place", "cancel", "close", "get_open_orders"
    symbol: str
    kwargs: Dict[str, Any] = field(default_factory=dict)

class FakeRecordingAdapter:
    """
    Test adapter that records all calls and simulates responses.

    Useful for verifying ExecutionService behavior without real exchange.
    """

    def __init__(self):
        self.calls: List[FakeAdapterCall] = []
        self._order_counter = 1000
        self._error_codes: Dict[str, int] = {}  # order_id -> error_code for simulation

    def set_error_for_order(self, order_id: str, error_code: int):
        """Configure adapter to raise error for specific order."""
        self._error_codes[order_id] = error_code

    async def create_order(self, params=None, **kwargs):
        """Alias for place_order to support ExecutionService."""
        if params:
            return await self.place_order(
                symbol=params.symbol,
                side=params.side,
                order_type=params.order_type,
                quantity=params.quantity,
                price=params.price,
                client_order_id=params.client_order_id,
                reduce_only=params.reduce_only,
                tif=params.time_in_force,
                **kwargs
            )
        return await self.place_order(**kwargs)

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Any,
        price: Optional[Any] = None,
        client_order_id: Optional[str] = None,
        reduce_only: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """Simulate place_order call."""
        self.calls.append(FakeAdapterCall(
            verb="place",
            symbol=symbol,
            kwargs={
                "side": side,
                "order_type": order_type,
                "quantity": str(quantity) if quantity is not None else None,
                "price": str(price) if price else None,
                "client_order_id": client_order_id,
                "reduce_only": reduce_only,
                **kwargs
            }
        ))

        # Simulate successful placement
        order_id = f"ORDER_{self._order_counter}"
        self._order_counter += 1

        await asyncio.sleep(0)  # Yield control

        return {
            "orderId": order_id,
            "symbol": symbol,
            "status": "NEW",
            "side": side,
            "type": order_type
        }

    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Simulate cancel_order call."""
        self.calls.append(FakeAdapterCall(
            verb="cancel",
            symbol=symbol,
            kwargs={"order_id": order_id, **kwargs}
        ))

        # Check if we should simulate an error
        if order_id and order_id in self._error_codes:
            error_code = self._error_codes[order_id]
            raise Exception(f"APIError: code={error_code}, msg=Simulated error")

        await asyncio.sleep(0)

        return {
            "orderId": order_id,
            "status": "CANCELED"
        }

    async def get_open_orders(self, symbol: str, **kwargs) -> List[Dict[str, Any]]:
        """Simulate get_open_orders call."""
        self.calls.append(FakeAdapterCall(
            verb="get_open_orders",
            symbol=symbol,
            kwargs=kwargs
        ))

        await asyncio.sleep(0)

        # Return empty list by default
        return []

    def reset(self):
        """Clear call history."""
        self.calls = []
        self._order_counter = 1000
        self._error_codes = {}
