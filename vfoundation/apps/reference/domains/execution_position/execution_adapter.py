# apps/reference/domains/execution_position/execution_adapter.py
"""
Abstract Execution Adapter Interface (Part EXECUTE-T04-A).

Defines the contract between execution_position FSM and trading venue executors.
This abstraction enables:
- Pluggable execution backends (Binance, simulation, other exchanges)
- Clean separation: FSM logic vs. venue-specific API calls
- Testability: Mock adapters for unit tests
- Future flexibility: Easy integration of new execution venues

Architecture:
    execution_position FSM → DEC:OPEN/ADJUST/CANCEL
        ↓
    AbstractExecutionAdapter (this interface)
        ↓
    Concrete implementations:
        - BinanceExecutionAdapter (real exchange)
        - SimulatedExecutionAdapter (backtesting/shadow mode)
        - PaperTradingAdapter (paper trading)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from vfoundation.core.protocol import Message


class AbstractExecutionAdapter(ABC):
    """
    Abstract interface for an execution adapter.
    
    Defines the contract for how the Execution FSM interacts with a trading
    venue (real or simulated). Any concrete execution adapter must implement
    these three core methods.
    
    Design Philosophy:
    - FSM emits DECISION messages (DEC:OPEN, DEC:ADJUST, DEC:CANCEL)
    - Adapter translates FSM decisions into venue-specific API calls
    - Adapter returns standardized response format
    - FSM remains agnostic to execution venue details
    
    Example Usage:
        >>> adapter = BinanceExecutionAdapter(config, api_credentials)
        >>> dec_open = Message(op="DEC", verb="OPEN", pld={"symbol": "ETHUSDT", ...})
        >>> result = adapter.place_order(dec_open)
        >>> if result['status'] == 'ACCEPTED':
        ...     # FSM transitions to PENDING state
    """

    @abstractmethod
    def place_order(self, dec_msg: Message) -> Dict[str, Any]:
        """
        Places an order on the exchange based on a DECISION message.
        
        This method is called when the FSM emits:
        - DEC:OPEN (new position)
        - DEC:ADJUST (modify existing order/position)
        
        Args:
            dec_msg: The DEC:OPEN or DEC:ADJUST message from the FSM.
                Expected payload fields:
                - symbol: str (e.g., "ETHUSDT")
                - side: str ("buy" or "sell")
                - qty: str (Decimal as string for precision)
                - price: str (limit price, Decimal as string)
                - order_type: str ("LIMIT", "MARKET", etc.)
                - tif: str ("GTC", "IOC", "FOK")
                Additional fields may vary by venue.
        
        Returns:
            A dictionary with order confirmation details from the exchange.
            Standard fields:
            - status: str ("ACCEPTED", "REJECTED", "ERROR")
            - exchange_order_id: str (venue's order ID, if accepted)
            - filled_qty: str (immediately filled quantity, if any)
            - message: str (error message if rejected)
            - timestamp: int (order placement timestamp, ms)
            
            Example success response:
                {
                    'status': 'ACCEPTED',
                    'exchange_order_id': '12345678',
                    'filled_qty': '0.0',
                    'message': 'Order placed successfully',
                    'timestamp': 1234567890123
                }
            
            Example rejection response:
                {
                    'status': 'REJECTED',
                    'exchange_order_id': None,
                    'filled_qty': '0.0',
                    'message': 'Insufficient funds',
                    'timestamp': 1234567890123
                }
        
        Raises:
            May raise venue-specific exceptions if critical error occurs.
            Adapter should catch and convert to ERROR status where possible.
        """
        pass

    @abstractmethod
    def cancel_order(self, dec_msg: Message) -> Dict[str, Any]:
        """
        Cancels an existing order on the exchange.
        
        This method is called when the FSM emits:
        - DEC:CANCEL (cancel pending order)
        
        Args:
            dec_msg: The DEC:CANCEL message from the FSM.
                Expected payload fields:
                - exchange_order_id: str (venue's order ID to cancel)
                - symbol: str (for validation)
        
        Returns:
            A dictionary with cancellation confirmation.
            Standard fields:
            - status: str ("CANCELLED", "NOT_FOUND", "ERROR")
            - exchange_order_id: str (echoed back)
            - message: str (confirmation or error message)
            - timestamp: int (cancellation timestamp, ms)
            
            Example success response:
                {
                    'status': 'CANCELLED',
                    'exchange_order_id': '12345678',
                    'message': 'Order cancelled successfully',
                    'timestamp': 1234567890123
                }
            
            Example not found response:
                {
                    'status': 'NOT_FOUND',
                    'exchange_order_id': '12345678',
                    'message': 'Order not found or already filled',
                    'timestamp': 1234567890123
                }
        
        Raises:
            May raise venue-specific exceptions if critical error occurs.
        """
        pass

    @abstractmethod
    def get_status(self) -> str:
        """
        Returns the current status of the adapter connection.
        
        This method allows the FSM to check adapter health before attempting
        order placement. Can be used for:
        - Circuit breaker: Halt trading if adapter disconnected
        - Health checks: Periodic connection validation
        - Graceful degradation: Fall back to shadow mode on error
        
        Returns:
            A string representing the adapter's connection state:
            - 'CONNECTED': Adapter ready to execute orders
            - 'DISCONNECTED': Connection lost, retrying
            - 'ERROR': Critical error, adapter non-functional
            - 'DEGRADED': Partial functionality (e.g., read-only)
            
        Example:
            >>> adapter.get_status()
            'CONNECTED'
        
        Note:
            Implementations should cache status checks to avoid excessive
            API calls. Recommended check frequency: once per second.
        """
        pass


# Type aliases for clarity
OrderResult = Dict[str, Any]
CancelResult = Dict[str, Any]
AdapterStatus = str
