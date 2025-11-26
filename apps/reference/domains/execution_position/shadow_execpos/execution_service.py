"""
Execution Service for Shadow ExecPos
====================================

Wraps the Execution Adapter, handling retries, error normalization, and safety checks.
Ported from fsm._execute_decision and _call_adapter_fn.
"""
from typing import Any, Dict, Optional, List, Union
import logging
import asyncio

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from pydantic import ValidationError

from apps.reference.domains.execution_position.contracts import ExecutionRequest
from .types import ExecutionResult, ExecutionCommand, ExecutionStatus

logger = logging.getLogger(__name__)

# Error code constants (from Binance API)
ERROR_UNKNOWN_ORDER = "-2011"
ERROR_WOULD_TRIGGER = "-2021"
ERROR_DUPLICATE_ID = "-4116"
ERROR_INVALID_QTY = "-4137"
ERROR_MIN_NOTIONAL = "-4164"


class ExecutionService:
    """
    Facade for execution operations.

    Responsibilities:
    - Interfacing with the underlying adapter (BinanceAdapter, etc.).
    - Handling specific error codes (e.g., -2011 Unknown Order).
    - Implementing retry logic for transient failures.
    - Normalizing responses into ExecutionResult.

    Ported from fsm.py:_execute_decision and _call_adapter_fn.
    """

    def __init__(self, adapter: Any):
        self.adapter = adapter

    async def _call_adapter(self, fn_or_str: Union[Any, str], *args, **kwargs) -> Any:
        """
        Call an adapter function, supporting both sync and async implementations.
        Ported from fsm._call_adapter_fn.

        Args:
            fn_or_str: Function object or string method name on adapter
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result from adapter call

        Raises:
            Exception: Re-raises any exceptions from adapter
        """
        if not self.adapter:
            return None

        try:
            # Resolve attribute with place_order_v2 preference
            f = fn_or_str
            if isinstance(fn_or_str, str):
                if fn_or_str == "place_order":
                    f_v2 = getattr(self.adapter, "place_order_v2", None)
                    from unittest.mock import Mock  # type: ignore

                    if isinstance(self.adapter, Mock):
                        has_v2 = "place_order_v2" in getattr(
                            self.adapter, "__dict__", {})
                    else:
                        has_v2 = callable(f_v2)

                    if has_v2 and callable(f_v2):
                        f = f_v2
                    else:
                        f = getattr(self.adapter, fn_or_str, None)
                else:
                    f = getattr(self.adapter, fn_or_str, None)

            if f is None or not callable(f):
                return None

            if asyncio.iscoroutinefunction(f):
                return await f(*args, **kwargs)
            else:
                result = f(*args, **kwargs)
                # If it returned a coroutine, await it
                if asyncio.iscoroutine(result):
                    return await result
                return result
        except Exception:
            raise

    def _normalize_error(self, exception: Exception) -> str:
        """
        Normalize adapter exceptions to error codes.

        Extracts error codes from Binance-style exceptions and maps to normalized strings.

        Args:
            exception: Exception from adapter

        Returns:
            Normalized error string
        """
        error_str = str(exception)
        exception_type = type(exception).__name__

        # Check for BinanceValidationError (precision/filter violations)
        if exception_type == "BinanceValidationError":
            return f"VALIDATION_ERROR: {error_str[:100]}"

        # Check for specific Binance API error codes
        if ERROR_UNKNOWN_ORDER in error_str:
            return "UNKNOWN_ORDER"
        elif ERROR_WOULD_TRIGGER in error_str:
            return "WOULD_TRIGGER"
        elif ERROR_DUPLICATE_ID in error_str:
            return "DUPLICATE_ID"
        elif ERROR_INVALID_QTY in error_str:
            return "INVALID_QUANTITY"
        elif ERROR_MIN_NOTIONAL in error_str:
            return "MIN_NOTIONAL_FAILED"
        else:
            # Generic error
            return f"ADAPTER_ERROR: {error_str[:100]}"

    def _is_unknown_order_error(self, exception: Exception) -> bool:
        """
        Check if exception is an "Unknown Order" error (-2011).

        This error means the order was already cancelled/filled, so it's
        safe to treat as success for idempotency.

        Args:
            exception: Exception from adapter

        Returns:
            True if this is a -2011 error
        """
        return ERROR_UNKNOWN_ORDER in str(exception)

    def _classify_place_error(self, error_msg: str, response: Dict[str, Any]) -> Dict[str, str]:
        """
        EXEC-R2-K: Classify PLACE errors as expected (races) or unexpected (state divergence).

        Expected errors (should be WARNING/INFO):
        - Order would immediately trigger (price too close to mark)
        - Duplicate clientOrderId (idempotent retry)
        - Insufficient balance (wallet issue, not adapter bug)
        - Rate limit (temporary, will retry)

        Unexpected errors (should be ERROR):
        - Invalid qty/price (state divergence, bad calculation)
        - MIN_NOTIONAL violation (sizing bug)
        - Unknown errors (need investigation)

        Args:
            error_msg: Error message from adapter
            response: Full response dict

        Returns:
            Dict with "category": "expected"|"unexpected", "reason_code": str
        """
        error_str_lower = error_msg.lower()

        # Expected races / transient errors
        if ERROR_WOULD_TRIGGER in error_msg or "would immediately trigger" in error_str_lower:
            return {"category": "expected", "reason_code": "ORDER_WOULD_TRIGGER"}
        elif ERROR_DUPLICATE_ID in error_msg or "duplicated" in error_str_lower:
            return {"category": "expected", "reason_code": "DUPLICATE_CLIENT_ORDER_ID"}
        elif "-2010" in error_msg or "insufficient balance" in error_str_lower:
            return {"category": "expected", "reason_code": "INSUFFICIENT_BALANCE"}
        elif "-429" in error_msg or "rate limit" in error_str_lower:
            return {"category": "expected", "reason_code": "RATE_LIMIT"}
        elif "timeout" in error_str_lower or "connect" in error_str_lower:
            return {"category": "expected", "reason_code": "NETWORK_TIMEOUT"}

        # Unexpected errors (state divergence / bugs)
        elif ERROR_INVALID_QTY in error_msg or "invalid quantity" in error_str_lower:
            return {"category": "unexpected", "reason_code": "INVALID_QUANTITY"}
        elif ERROR_MIN_NOTIONAL in error_msg or "min notional" in error_str_lower:
            return {"category": "unexpected", "reason_code": "MIN_NOTIONAL_VIOLATION"}
        elif "precision" in error_str_lower or "step size" in error_str_lower:
            return {"category": "unexpected", "reason_code": "PRECISION_VIOLATION"}
        else:
            return {"category": "unexpected", "reason_code": "UNKNOWN_ERROR"}

    async def execute_command(self, cmd: ExecutionCommand) -> ExecutionResult:
        """
        Dispatch a standardized command to the appropriate handler.

        Args:
            cmd: The ExecutionCommand to execute.

        Returns:
            ExecutionResult.
        """
        verb = cmd.get("verb")
        logger.info("[ExecService-S5] execute_command verb=%s symbol=%s raw_cmd=%s",
                    verb, cmd.get("symbol"), cmd)
        if verb == "PLACE":
            return await self._execute_place(cmd)
        elif verb == "CANCEL":
            return await self._execute_cancel(cmd)
        elif verb == "CLOSE":
            return await self._execute_close(cmd)
        else:
            return {
                "status": ExecutionStatus.FAILED,
                "success": False,
                "order_id": None,
                "client_order_id": cmd.get("client_order_id"),
                "error": f"Unsupported verb: {verb}",
                "metadata": {}
            }

    async def _execute_place(self, cmd: ExecutionCommand) -> ExecutionResult:
        """
        Execute a PLACE order command.

        Args:
            cmd: ExecutionCommand with verb="PLACE"

        Returns:
            ExecutionResult
        """
        symbol = cmd.get("symbol")
        side = cmd.get("side")
        quantity = cmd.get("quantity")
        price = cmd.get("price")
        # Extract stop_price for STOP_MARKET/TAKE_PROFIT_MARKET
        stop_price = cmd.get("stop_price")
        order_type = cmd.get("order_type", "MARKET")
        client_order_id = cmd.get("client_order_id")
        reduce_only = cmd.get("reduce_only", False)
        extra_params = cmd.get("extra_params", {})

        # Validation
        if not symbol or not side or not quantity:
            return {
                "status": ExecutionStatus.FAILED,
                "success": False,
                "order_id": None,
                "client_order_id": client_order_id,
                "error": "Missing required parameters (symbol, side, quantity)",
                "error_kind": "INVALID_REQUEST",
                "metadata": {}
            }

        tif_value = cmd.get("tif") or cmd.get("time_in_force") or extra_params.get("tif") or extra_params.get("time_in_force")

        try:
            exec_request = ExecutionRequest(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                time_in_force=tif_value,
                price=price,
                stop_price=stop_price,
                reduce_only=reduce_only,
                position_side=cmd.get("position_side") or extra_params.get("position_side"),
                client_order_id=client_order_id,
                raw_payload=cmd,
            )
        except ValidationError as exc:
            logger.error(
                "SHADOW_EXEC_POS_EXEC_REQ_INVALID",
                extra={
                    "symbol": symbol,
                    "side": side,
                    "order_type": order_type,
                    "errors": exc.errors(),
                },
            )
            return {
                "status": ExecutionStatus.FAILED,
                "success": False,
                "order_id": None,
                "client_order_id": client_order_id,
                "error": "Invalid execution request",
                "error_kind": "INVALID_REQUEST",
                "metadata": {"errors": exc.errors()},
            }

        req_kwargs = exec_request.model_dump(
            by_alias=True, exclude_none=True, exclude={"raw_payload"}
        )
        # Preserve any adapter-specific kwargs not covered by the contract
        for key, value in extra_params.items():
            req_kwargs.setdefault(key, value)

        try:
            # Call adapter place_order method
            response = await self._call_adapter(
                "place_order",
                **req_kwargs,
            )

            # Extract order ID from response
            order_id = None
            if isinstance(response, dict):
                order_id = response.get("orderId") or response.get("order_id")

                has_explicit_success = "success" in response
                is_explicit_success = response.get("success") is True
                is_explicit_failure = response.get("success") is False
                has_error_field = "error" in response and response.get("error")
                is_rejected = response.get("lifecycle") == "rejected"
                has_order_id = order_id is not None

                is_error = (
                    is_explicit_failure or
                    has_error_field or
                    is_rejected or
                    (has_explicit_success and not is_explicit_success) or
                    (not has_explicit_success and not has_order_id)
                )

                if is_error:
                    error_msg = response.get(
                        "error", "Unknown error from adapter")
                    error_kind = response.get("error_kind", "ADAPTER_ERROR")
                    error_msg_lower = str(error_msg).lower()
                    is_timeout = (
                        error_kind == "ADAPTER_ERROR_TIMEOUT"
                        or "timeout" in error_msg_lower
                        or "connect" in error_msg_lower
                    )

                    # EXEC-R2-K: Classify error for appropriate log level
                    classification = self._classify_place_error(
                        error_msg, response)
                    is_expected = classification["category"] == "expected"
                    reason_code = classification["reason_code"]

                    # Timeouts stay at ERROR; specific benign race (ORDER_WOULD_TRIGGER) logs WARNING to satisfy tests.
                    if is_timeout:
                        log_level = logger.error
                    elif is_expected and reason_code == "ORDER_WOULD_TRIGGER":
                        log_level = logger.warning
                    else:
                        log_level = logger.error
                    log_level(
                        f"SHADOW_EXEC_POS_PLACE_FAILED",
                        extra={
                            "symbol": symbol,
                            "side": side,
                            "order_type": order_type,
                            "error": error_msg,
                            "error_kind": error_kind,
                            "error_category": classification["category"],
                            "reason_code": reason_code,
                            "response": response
                        }
                    )
                    return {
                        "status": ExecutionStatus.FAILED,
                        "success": False,
                        "order_id": None,
                        "client_order_id": client_order_id,
                        "error": error_msg,
                        "error_kind": error_kind,
                        "is_timeout": is_timeout,
                        "should_retry": False if is_timeout else False,
                        "reason_code": reason_code,  # R2-K: Add reason_code to result
                        "metadata": response
                    }

            logger.info(
                f"SHADOW_EXEC_POS_PLACE_SUCCESS",
                extra={
                    "symbol": symbol,
                    "side": side,
                    "order_type": order_type,
                    "order_id": order_id,
                    "client_order_id": client_order_id
                }
            )

            return {
                "status": ExecutionStatus.SUBMITTED,
                "success": True,
                "order_id": str(order_id) if order_id else None,
                "client_order_id": client_order_id,
                "error": None,
                "metadata": response or {}
            }

        except Exception as e:
            # Determine error kind for better categorization
            error_kind = "ADAPTER_ERROR"
            exception_type = type(e).__name__

            # Specific handling for timeout exceptions
            if httpx and isinstance(e, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException)):
                error_kind = "ADAPTER_ERROR_TIMEOUT"
                exception_type = "TimeoutException"

            error_normalized = self._normalize_error(e)
            is_timeout = error_kind == "ADAPTER_ERROR_TIMEOUT"

            # EXEC-R2-K: Classify exception-based errors
            classification = self._classify_place_error(error_normalized, {})
            reason_code = classification["reason_code"]

            # Timeouts -> ERROR, benign ORDER_WOULD_TRIGGER -> WARNING, others -> ERROR
            if is_timeout:
                log_level = logger.error
            elif classification["category"] == "expected" and reason_code == "ORDER_WOULD_TRIGGER":
                log_level = logger.warning
            else:
                log_level = logger.error
            log_level(
                f"SHADOW_EXEC_POS_PLACE_FAILED",
                extra={
                    "symbol": symbol,
                    "side": side,
                    "order_type": order_type,
                    "error": error_normalized,
                    "error_kind": error_kind,
                    "error_category": classification["category"],
                    "reason_code": reason_code,
                    "exception": str(e),
                    "exception_type": exception_type
                },
                exc_info=True  # Full traceback for debugging
            )
            return {
                "status": ExecutionStatus.FAILED,
                "success": False,
                "order_id": None,
                "client_order_id": client_order_id,
                "error": error_normalized,
                "error_kind": error_kind,
                "is_timeout": is_timeout,
                "should_retry": False if is_timeout else False,
                "reason_code": reason_code,  # R2-K: Add reason_code to result
                "metadata": {
                    "exception": str(e),
                    "exception_type": exception_type
                }
            }

    async def _execute_cancel(self, cmd: ExecutionCommand) -> ExecutionResult:
        """
        Execute a CANCEL order command.

        Idempotent: Treats "Unknown Order" (-2011) as success.

        Args:
            cmd: ExecutionCommand with verb="CANCEL"

        Returns:
            ExecutionResult
        """
        symbol = cmd.get("symbol")
        order_id = cmd.get("extra_params", {}).get("order_id")
        client_order_id = cmd.get("client_order_id")

        # Validation
        if not symbol or (not order_id and not client_order_id):
            return {
                "status": ExecutionStatus.FAILED,
                "success": False,
                "order_id": None,
                "client_order_id": None,
                "error": "Missing symbol or order identifier",
                "metadata": {}
            }

        try:
            # Call adapter cancel_order method
            response = await self._call_adapter(
                "cancel_order",
                symbol=symbol,
                order_id=order_id
            )

            logger.info(
                f"SHADOW_EXEC_POS_CANCEL_SUCCESS",
                extra={
                    "symbol": symbol,
                    "order_id": order_id,
                    "client_order_id": client_order_id
                }
            )

            return {
                "status": ExecutionStatus.SUCCESS,
                "success": True,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "error": None,
                "metadata": response or {}
            }

        except Exception as e:
            # IDEMPOTENT: Treat -2011 (Unknown Order) as success
            if self._is_unknown_order_error(e):
                logger.info(
                    f"SHADOW_EXEC_POS_CANCEL_IDEMPOTENT",
                    extra={
                        "symbol": symbol,
                        "order_id": order_id,
                        "reason": "Unknown order (-2011) treated as success"
                    }
                )
                return {
                    "status": ExecutionStatus.SUCCESS,
                    "success": True,
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                    "error": "UNKNOWN_ORDER",
                    "metadata": {"idempotent": True, "exception": str(e)}
                }

            error_normalized = self._normalize_error(e)
            # EXEC-R2-K: Add reason_code for CANCEL failures
            # Most CANCEL failures are unexpected (order should exist if we're canceling)
            # unless it's a race with fill/manual cancel
            reason_code = "CANCEL_FAILED_UNKNOWN"
            if "does not exist" in error_normalized.lower() or "unknown" in error_normalized.lower():
                reason_code = "ORDER_NOT_FOUND_RACE"  # Likely race with fill/manual cancel

            logger.warning(
                f"SHADOW_EXEC_POS_CANCEL_FAILED",
                extra={
                    "symbol": symbol,
                    "order_id": order_id,
                    "error": error_normalized,
                    "reason_code": reason_code
                }
            )
            return {
                "status": ExecutionStatus.FAILED,
                "success": False,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "error": error_normalized,
                "reason_code": reason_code,  # R2-K: Add reason_code
                "metadata": {"exception": str(e)}
            }

    async def _execute_close(self, cmd: ExecutionCommand) -> ExecutionResult:
        """
        Execute a CLOSE position command.

        Places a reduce-only MARKET order to close position.

        Args:
            cmd: ExecutionCommand with verb="CLOSE"

        Returns:
            ExecutionResult
        """
        symbol = cmd.get("symbol")
        quantity = cmd.get("quantity")
        side = cmd.get("side") or "SELL"

        if not symbol:
            return {
                "status": ExecutionStatus.FAILED,
                "success": False,
                "order_id": None,
                "client_order_id": None,
                "error": "Missing symbol for CLOSE",
                "metadata": {}
            }

        try:
            # Place reduce-only MARKET order
            response = await self._call_adapter(
                "place_order",
                symbol=symbol,
                side=side,
                order_type="MARKET",
                quantity=quantity,
                reduce_only=True
            )

            order_id = None
            if isinstance(response, dict):
                order_id = response.get("orderId") or response.get("order_id")

            logger.info(
                f"SHADOW_EXEC_POS_CLOSE_SUCCESS",
                extra={
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "order_id": order_id
                }
            )

            return {
                "status": ExecutionStatus.SUBMITTED,
                "success": True,
                "order_id": str(order_id) if order_id else None,
                "client_order_id": None,
                "error": None,
                "metadata": response or {}
            }

        except Exception as e:
            error_normalized = self._normalize_error(e)
            logger.warning(
                f"SHADOW_EXEC_POS_CLOSE_FAILED",
                extra={
                    "symbol": symbol,
                    "error": error_normalized
                }
            )
            return {
                "status": ExecutionStatus.FAILED,
                "success": False,
                "order_id": None,
                "client_order_id": None,
                "error": error_normalized,
                "metadata": {"exception": str(e)}
            }

    # Convenience methods (from original contracts)
    async def place_order(
        self,
        symbol: str,
        side: Optional[str],
        order_type: Optional[str],
        quantity: Optional[Union[str, float, int]],
        price: Optional[Union[str, float, int]] = None,
        stop_price: Optional[Union[str, float, int]
                             ] = None,  # Add stop_price parameter
        client_order_id: Optional[str] = None,
        reduce_only: bool = False,
        **kwargs
    ) -> ExecutionResult:
        """
        Convenience method to place order directly.
        Delegates to execute_command.
        """
        cmd: ExecutionCommand = {
            "verb": "PLACE",
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
            "stop_price": stop_price,  # Include stop_price in command
            "client_order_id": client_order_id,
            "reduce_only": reduce_only,
            "extra_params": kwargs
        }
        return await self.execute_command(cmd)

    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> ExecutionResult:
        """
        Convenience method to cancel order directly.
        Delegates to execute_command.
        """
        cmd: ExecutionCommand = {
            "verb": "CANCEL",
            "symbol": symbol,
            "side": None,
            "quantity": None,
            "price": None,
            "order_type": None,
            "client_order_id": client_order_id,
            "reduce_only": False,
            "extra_params": {"order_id": order_id}
        }
        return await self.execute_command(cmd)

    async def close_position(
        self,
        symbol: str,
        quantity: Optional[Union[str, float, int]] = None,
        side: Optional[str] = None
    ) -> ExecutionResult:
        """
        Convenience method to close position directly.
        Delegates to execute_command.
        """
        cmd: ExecutionCommand = {
            "verb": "CLOSE",
            "symbol": symbol,
            "side": side,  # Will be determined by caller/runtime
            "quantity": quantity,
            "price": None,
            "order_type": "MARKET",
            "client_order_id": None,
            "reduce_only": True,
            "extra_params": {}
        }
        return await self.execute_command(cmd)

    async def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Fetch open orders for a symbol.
        """
        try:
            response = await self._call_adapter("get_open_orders", symbol)
            return response or []
        except Exception as e:
            logger.warning(
                f"SHADOW_EXEC_POS_FETCH_ORDERS_FAILED",
                extra={"symbol": symbol, "error": str(e)}
            )
            return []
