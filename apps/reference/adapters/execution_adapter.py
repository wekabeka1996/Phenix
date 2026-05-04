"""
Abstract base class for execution adapters.
"""

import abc
from typing import List, Dict, Any, Optional


class AbstractExecutionAdapter(abc.ABC):
    """Abstract base class for execution adapters."""

    def __init__(self, fsm, config):
        self.fsm = fsm
        self.config = config

    @abc.abstractmethod
    async def place_order(self, msg):
        """Place an order."""
        raise NotImplementedError

    @abc.abstractmethod
    async def cancel_order(self, msg):
        """Cancel an order."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_status(self) -> str:
        """Get the status of the adapter."""
        raise NotImplementedError

    @abc.abstractmethod
    async def get_open_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get open positions from the exchange."""
        raise NotImplementedError

    @abc.abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get open orders from the exchange."""
        raise NotImplementedError
