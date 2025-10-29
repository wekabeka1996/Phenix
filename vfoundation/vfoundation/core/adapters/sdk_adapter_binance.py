"""
Binance SDK adapter for paper/testnet mode (FSMP-P2-T01-SDK-BINDING-PAPER).

Thin wrapper over python-binance testnet client. NO LIVE TRADING.
"""
import logging
import time
from decimal import Decimal
from typing import Any, AsyncIterator, Dict, Optional

from vfoundation.core.adapters.execution_adapter import (
    ExecutionAdapter,
    ExecutionMode,
    OrderDTO,
)
from vfoundation.core.adapters.execution_exceptions import (
    ConfigurationError,
    InvalidModeError,
    SDKError,
)

logger = logging.getLogger(__name__)


class SdkAdapterBinance(ExecutionAdapter):
    """
    Real Binance SDK adapter (paper/testnet only).
    
    ENV Requirements (paper mode):
    - EXCHANGE_API_KEY: Binance testnet API key
    - EXCHANGE_API_SECRET: Binance testnet API secret
    - EXCHANGE_BASE_URL: https://testnet.binance.vision/api (default)
    - EXCHANGE_WS_URL: wss://testnet.binance.vision/ws (default)
    
    Security:
    - dry_run: No SDK initialization, all operations mocked
    - paper: SDK initialized with TESTNET endpoints only
    - live: BLOCKED (raises InvalidModeError)
    """
    
    def __init__(self, mode: ExecutionMode):
        super().__init__(mode)
        
        # Block live mode
        if mode == ExecutionMode.LIVE:
            raise InvalidModeError(
                operation="SdkAdapterBinance.__init__",
                mode="live",
                required_mode="paper"
            )
        
        # dry_run: no SDK initialization
        if mode == ExecutionMode.DRY_RUN:
            self._client: Optional[Any] = None
            logger.info("SdkAdapterBinance: dry_run mode, no SDK client")
            return
        
        # paper: require ENV and initialize testnet client
        from vfoundation.config import config
        
        if not config.exchange_api_key or not config.exchange_api_secret:
            raise ConfigurationError(["EXCHANGE_API_KEY", "EXCHANGE_API_SECRET"])
        
        # Validate testnet URL
        base_url = config.exchange_base_url or "https://testnet.binance.vision/api"
        if "testnet" not in base_url and "test" not in base_url:
            raise ConfigurationError(["EXCHANGE_BASE_URL (testnet required)"])
        
        try:
            # Import SDK lazily (optional dependency)
            from binance.client import Client
            
            self._client = Client(
                api_key=config.exchange_api_key,
                api_secret=config.exchange_api_secret,
                testnet=True
            )
            logger.info(f"SdkAdapterBinance: paper mode, testnet={base_url}")
        except ImportError:
            raise SDKError(
                operation="SdkAdapterBinance.__init__",
                sdk_code="IMPORT_ERROR",
                sdk_message="python-binance not installed. Run: pip install python-binance"
            )
        except Exception as e:
            raise SDKError(
                operation="SdkAdapterBinance.__init__",
                sdk_code="INIT_ERROR",
                sdk_message=str(e)[:80]
            )
    
    def _submit_impl(self, order: OrderDTO, client_order_id: str) -> Dict[str, Any]:
        """Submit order to Binance testnet."""
        if self.mode == ExecutionMode.DRY_RUN:
            # Mock response
            return {
                "event_type": "ORDER_PLACED",
                "client_order_id": client_order_id,
                "exchange_order_id": f"mock_{int(time.time()*1000)}",
                "symbol": order.symbol,
                "side": order.side,
                "status": "NEW",
                "filled_qty": "0",
                "remaining_qty": str(order.qty),
                "avg_fill_price": None,
                "reason": None
            }
        
        try:
            # Map to Binance API
            params = {
                "symbol": order.symbol,
                "side": order.side.upper(),
                "type": order.order_type.upper(),
                "quantity": float(order.qty),
                "newClientOrderId": client_order_id,
            }
            
            if order.order_type == "limit" and order.price:
                params["price"] = float(order.price)
                params["timeInForce"] = order.time_in_force or "GTC"
            
            if order.reduce_only:
                params["reduceOnly"] = "true"
            
            response = self._client.create_order(**params)  # type: ignore[union-attr]
            
            # Normalize response
            return {
                "event_type": "ORDER_PLACED",
                "client_order_id": response.get("clientOrderId", client_order_id),
                "exchange_order_id": str(response["orderId"]),
                "symbol": response["symbol"],
                "side": response["side"].lower(),
                "status": response["status"],
                "filled_qty": response.get("executedQty", "0"),
                "remaining_qty": str(
                    Decimal(response.get("origQty", "0")) - Decimal(response.get("executedQty", "0"))
                ),
                "avg_fill_price": response.get("avgPrice"),
                "reason": None
            }
        except Exception as e:
            # Map SDK errors to normalized codes
            error_str = str(e).lower()
            if "timeout" in error_str:
                code = "TIMEOUT"
            elif "rate" in error_str or "429" in error_str:
                code = "RATE_LIMIT"
            elif "insufficient" in error_str:
                code = "INSUFFICIENT_BALANCE"
            elif "invalid" in error_str:
                code = "INVALID_PARAMS"
            else:
                code = "UNKNOWN"
            
            raise SDKError(
                operation="submit",
                sdk_code=code,
                sdk_message=str(e)[:60]
            )
    
    def _cancel_impl(
        self,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cancel order on Binance testnet."""
        if self.mode == ExecutionMode.DRY_RUN:
            # Mock response
            return {
                "event_type": "CANCELLED",
                "client_order_id": client_order_id,
                "exchange_order_id": order_id,
                "reason": "User requested"
            }
        
        try:
            # Require symbol for Binance (not in ACL contract — workaround)
            # Real implementation should cache symbol by order_id
            params: Dict[str, Any] = {}
            
            if order_id:
                params["orderId"] = order_id
            if client_order_id:
                params["origClientOrderId"] = client_order_id
            
            # NOTE: Binance requires symbol — this is a mock limitation
            # Production should maintain order_id → symbol mapping
            response = self._client.cancel_order(symbol="BTCUSDT", **params)  # type: ignore[union-attr]
            
            return {
                "event_type": "CANCELLED",
                "client_order_id": response.get("clientOrderId", client_order_id),
                "exchange_order_id": str(response.get("orderId", order_id)),
                "reason": "User requested"
            }
        except Exception as e:
            raise SDKError(
                operation="cancel",
                sdk_code="CANCEL_FAILED",
                sdk_message=str(e)[:60]
            )
    
    def stream(self) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream order events from Binance WebSocket.
        
        NOTE: This is a placeholder. Real implementation requires
        python-binance WebSocket manager or binance-connector-python.
        """
        async def _stream() -> AsyncIterator[Dict[str, Any]]:
            if self.mode == ExecutionMode.DRY_RUN:
                # No events in dry_run
                if False:
                    yield {}
                return
            
            # paper: placeholder for WebSocket stream
            logger.warning("SdkAdapterBinance.stream: WebSocket not implemented, returning empty stream")
            if False:
                yield {}
        
        return _stream()
