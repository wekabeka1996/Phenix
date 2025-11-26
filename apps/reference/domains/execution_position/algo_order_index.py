"""
AlgoOrderIndex — State Management for Binance Algo Orders (Phase 1)
===================================================================

Manages the lifecycle and state of Algo Orders (STOP, TAKE_PROFIT, TRAILING_STOP)
placed via the Algo Service endpoint (/fapi/v1/algoOrder).

Responsibilities:
- Store AlgoOrderState indexed by client_algo_order_id and algo_order_id.
- Process ALGO_UPDATE events from User Data Stream.
- Provide lookup for BracketService integration.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional, List, Any

LOG = logging.getLogger(__name__)


@dataclass
class AlgoOrderState:
    """Internal representation of an Algo Order's lifecycle."""
    algo_order_id: str          # Binance-assigned ID
    client_algo_order_id: str   # Our ID
    symbol: str
    side: str                   # BUY/SELL
    algo_type: str              # STOP_MARKET, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET
    status: str                 # NEW, WORKING, FILLED, CANCELED, REJECTED
    quantity: Decimal
    trigger_price: Optional[Decimal] = None  # stopPrice or activationPrice
    callback_rate: Optional[Decimal] = None  # For TRAILING_STOP
    position_id: Optional[str] = None
    reduce_only: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Last known execution details
    last_executed_qty: Decimal = Decimal("0")
    cumulative_filled_qty: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")


@dataclass
class AlgoOrderUpdate:
    """DTO for ALGO_UPDATE event payload."""
    algo_order_id: str
    client_algo_order_id: str
    symbol: str
    side: str
    algo_type: str
    status: str
    last_executed_qty: Decimal
    cumulative_filled_qty: Decimal
    transaction_time: int
    trigger_price: Optional[Decimal] = None


class AlgoOrderIndex:
    """
    In-memory index for Algo Orders.
    """

    def __init__(self):
        # Primary index: client_algo_order_id -> AlgoOrderState
        self._by_client_id: Dict[str, AlgoOrderState] = {}
        # Secondary index: algo_order_id -> AlgoOrderState
        self._by_algo_id: Dict[str, AlgoOrderState] = {}

    def register_new_algo_order(
        self,
        client_algo_order_id: str,
        algo_order_id: str,
        symbol: str,
        side: str,
        algo_type: str,
        quantity: Decimal,
        reduce_only: bool = True,
        trigger_price: Optional[Decimal] = None
    ) -> str:
        """
        Register a newly placed Algo Order.

        Args:
            client_algo_order_id: Client-assigned ID
            algo_order_id: Binance-assigned ID
            symbol: Trading symbol
            side: BUY/SELL
            algo_type: STOP_MARKET, TAKE_PROFIT_MARKET, etc.
            quantity: Order quantity
            reduce_only: Whether order is reduce-only
            trigger_price: Stop/Trigger price

        Returns:
            algo_order_id (str)
        """
        if not client_algo_order_id:
            LOG.warning(
                f"Registering algo order without client_id: {algo_order_id}")
            client_algo_order_id = f"UNKNOWN_{algo_order_id}"

        state = AlgoOrderState(
            algo_order_id=algo_order_id,
            client_algo_order_id=client_algo_order_id,
            symbol=symbol,
            side=side,
            algo_type=algo_type,
            status="NEW",
            quantity=quantity,
            trigger_price=trigger_price,
            reduce_only=reduce_only,
        )

        self._update_indexes(state)
        LOG.info(
            f"Registered new Algo Order: {client_algo_order_id} (ID: {algo_order_id})")
        return algo_order_id

    def update_from_event(self, update: AlgoOrderUpdate) -> Optional[AlgoOrderState]:
        """
        Update state from ALGO_UPDATE event.
        """
        state = self.get_by_client_id(
            update.client_algo_order_id) or self.get_by_algo_id(update.algo_order_id)

        if not state:
            # If not found, create a new entry (rehydration from stream)
            state = AlgoOrderState(
                algo_order_id=update.algo_order_id,
                client_algo_order_id=update.client_algo_order_id,
                symbol=update.symbol,
                side=update.side,
                algo_type=update.algo_type,
                status=update.status,
                # Unknown initial qty if missed registration
                quantity=Decimal("0"),
                trigger_price=update.trigger_price
            )
            LOG.info(
                f"Discovered Algo Order from stream: {update.client_algo_order_id}")

        # Update fields
        state.status = update.status
        state.last_executed_qty = update.last_executed_qty
        state.cumulative_filled_qty = update.cumulative_filled_qty
        state.updated_at = time.time()

        self._update_indexes(state)
        return state

    def get_by_client_id(self, client_id: str) -> Optional[AlgoOrderState]:
        return self._by_client_id.get(client_id)

    def get_by_algo_id(self, algo_id: str) -> Optional[AlgoOrderState]:
        return self._by_algo_id.get(algo_id)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[AlgoOrderState]:
        """Return all active (working/new) algo orders."""
        active_statuses = {"NEW", "WORKING", "PARTIALLY_FILLED"}
        orders = [
            s for s in self._by_client_id.values()
            if s.status in active_statuses
        ]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def _update_indexes(self, state: AlgoOrderState):
        self._by_client_id[state.client_algo_order_id] = state
        self._by_algo_id[state.algo_order_id] = state
