"""
Abstract Exchange Adapter Base Class

Defines the interface that all exchange adapters (Binance, Kraken, etc.)
must implement. This allows vfoundation core to work with any exchange adapter
without knowing its specific implementation details.

Core Principles:
- Framework-agnostic: only abstract methods and protocol definitions
- Exchange-specific adapters implement these methods
- Used by FSM domains for place/cancel/query orders
- No external imports (only typing, abc, dataclasses)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ExchangeOrderParams:
    """Exchange-agnostic order parameters"""
    symbol: str
    side: str  # BUY or SELL
    order_type: str  # MARKET, LIMIT, STOP_MARKET, TAKE_PROFIT_MARKET
    quantity: str
    price: Optional[str] = None
    time_in_force: str = "GTC"
    reduce_only: bool = False
    close_position: bool = False
    client_order_id: Optional[str] = None
    position_side: Optional[str] = None  # LONG/SHORT for HEDGE mode
    stop_price: Optional[str] = None  # for stop/TP orders
    working_type: Optional[str] = None  # MARK_PRICE or CONTRACT_PRICE


@dataclass
class ExchangeOrderResponse:
    """Normalized exchange order response"""
    order_id: str
    client_order_id: Optional[str]
    symbol: str
    side: str
    quantity: str
    filled_qty: str
    price: Optional[str]
    status: str  # ACCEPTED, REJECTED, FILLED, PARTIAL_FILL, CANCELED
    timestamp_ms: int
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for compatibility."""
        return {
            "orderId": self.order_id,
            "clientOrderId": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "origQty": self.quantity,
            "executedQty": self.filled_qty,
            "price": self.price,
            "status": self.status,
            "time": self.timestamp_ms,
            "reason": self.reason,
        }


@dataclass
class ExchangePosition:
    """Normalized exchange position data"""
    symbol: str
    position_side: str  # BOTH for ONE_WAY, LONG/SHORT for HEDGE
    side: str  # LONG or SHORT (computed for convenience)
    position_amount: str  # string for precision
    entry_price: str
    mark_price: str
    unrealized_profit: str
    leverage: int
    margin_type: str  # CROSS or ISOLATED
    isolated_margin: float
    update_time_ms: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for compatibility."""
        return {
            "symbol": self.symbol,
            "positionSide": self.position_side,
            "side": self.side,
            "positionAmt": self.position_amount,
            "position_amount": self.position_amount,  # Alternative key
            "entryPrice": self.entry_price,
            "markPrice": self.mark_price,
            "unRealizedProfit": self.unrealized_profit,
            "leverage": self.leverage,
            "marginType": self.margin_type,
            "isolatedMargin": self.isolated_margin,
            "updateTime": self.update_time_ms,
        }


class AbstractExchangeAdapter(ABC):
    """
    Base interface for exchange adapters.

    All exchange-specific adapters (BinanceAdapter, KrakenAdapter, etc.)
    must inherit from this class and implement all abstract methods.

    vfoundation domains use these adapters through this interface,
    ensuring loose coupling from specific exchange implementations.
    """

    @abstractmethod
    async def create_order(self, params: ExchangeOrderParams) -> ExchangeOrderResponse:
        """
        Create an order on the exchange.

        Args:
            params: Exchange-agnostic order parameters

        Returns:
            Normalized order response

        Raises:
            Must document exchange-specific errors (e.g., InsufficientBalance, InvalidOrder)
        """
        pass

    @abstractmethod
    async def cancel_order(
        self, symbol: str, order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> ExchangeOrderResponse:
        """
        Cancel an open order.

        Args:
            symbol: Trading pair
            order_id: Exchange order ID
            client_order_id: Client-side order ID for idempotency

        Returns:
            Normalized cancelled order response
        """
        pass

    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[ExchangeOrderResponse]:
        """
        Retrieve open orders (optionally filtered by symbol).

        Args:
            symbol: Optional symbol filter

        Returns:
            List of open orders
        """
        pass

    @abstractmethod
    async def get_open_positions(self, symbol: Optional[str] = None) -> List[ExchangePosition]:
        """
        Retrieve open positions (optionally filtered by symbol).
        Only returns non-zero positions.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of open positions
        """
        pass

    @abstractmethod
    async def get_mark_price(self, symbol: str, ttl_ms: int = 250) -> float:
        """
        Get mark price for a symbol with optional TTL cache.

        Args:
            symbol: Trading pair
            ttl_ms: Cache time-to-live in milliseconds

        Returns:
            Mark price as float
        """
        pass

    @abstractmethod
    async def get_last_price(self, symbol: str) -> float:
        """
        Get last traded price for a symbol.

        Args:
            symbol: Trading pair

        Returns:
            Last price as float
        """
        pass

    @abstractmethod
    async def get_account_balance(self) -> List[Dict[str, Any]]:
        """
        Get account balance information.

        Returns:
            List of asset balances with amounts
        """
        pass

    @abstractmethod
    async def get_exchange_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get exchange information for a symbol (filters, precision, etc.).

        Args:
            symbol: Trading pair

        Returns:
            Exchange info dict with filters and constraints
        """
        pass

    @abstractmethod
    async def quantize_quantity(self, symbol: str, qty: Any) -> str:
        """
        Quantize quantity to symbol's LOT_SIZE/step and validate MIN_NOTIONAL.

        Args:
            symbol: Trading pair
            qty: Quantity to quantize

        Returns:
            Quantized quantity as string
        """
        pass

    @abstractmethod
    async def aclose(self) -> None:
        """
        Close/cleanup adapter resources (session, connections, etc.).
        Safe to call multiple times.
        """
        pass
