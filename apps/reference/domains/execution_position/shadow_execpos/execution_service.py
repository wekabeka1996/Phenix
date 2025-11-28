"""
Execution Service for Shadow ExecPos
====================================

Wraps the Execution Adapter, handling retries, error normalization, and safety checks.
Ported from fsm._execute_decision and _call_adapter_fn.
"""
from typing import Any, Dict, Optional, List, Union
import logging
import asyncio
import os
import yaml

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

try:
    import httpcore
except ImportError:
    httpcore = None  # type: ignore

from pydantic import ValidationError

from vfoundation.core.adapters.base import ExchangeOrderParams
from apps.reference.domains.execution_position.contracts import ExecutionRequest
from .types import ExecutionResult, ExecutionCommand, ExecutionStatus

logger = logging.getLogger(__name__)

# Timeout exception types for classification
TIMEOUT_EXCEPTION_NAMES = frozenset({
    "ReadTimeout", "ConnectTimeout", "WriteTimeout",
    "PoolTimeout", "TimeoutException"
})

# Network exception types for classification
NETWORK_EXCEPTION_NAMES = frozenset({
    "ConnectError", "RemoteProtocolError", "NetworkError",
    "ConnectionError", "OSError"
})


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
        self.ERROR_CODES = self._load_error_config()

    def _load_error_config(self) -> Dict[str, str]:
        """Load adapter error codes from YAML config."""
        default_codes = {
            "unknown_order": "-2011",
            "would_trigger": "-2021",
            "duplicate_id": "-4116",
            "invalid_qty": "-4137",
            "min_notional": "-4164",
            "insufficient_balance": "-2010",
            "rate_limit": "-429"
        }

        try:
            # Locate config file relative to this file
            # Path: apps/reference/domains/execution_position/config/adapter_errors.yaml
            # Current file: apps/reference/domains/execution_position/shadow_execpos/execution_service.py
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config", "adapter_errors.yaml")

            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    data = yaml.safe_load(f)
                    if data and "binance" in data:
                        return data["binance"]

            logger.warning(f"Adapter error config not found at {config_path}, using defaults")
            return default_codes

        except Exception as e:
            logger.error(f"Failed to load adapter error config: {e}", exc_info=True)
            return default_codes

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
            # Resolve attribute
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

    def _classify_exception(self, exception: Exception) -> Dict[str, Any]:
        """
        Centralized exception classification logic.

        Returns:
            Dict containing:
            - error_kind: str (ADAPTER_ERROR, ADAPTER_ERROR_TIMEOUT, ADAPTER_ERROR_NETWORK)
            - is_timeout: bool
            - is_network: bool
            - normalized_error: str
        """
        exception_type = type(exception).__name__
        error_str = str(exception)

        # 1. Check for Timeout
        is_timeout = exception_type in TIMEOUT_EXCEPTION_NAMES
        if httpx and isinstance(exception, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException)):
            is_timeout = True
        if httpcore and isinstance(exception, (httpcore.ReadTimeout, httpcore.ConnectTimeout)):
            is_timeout = True

        # Fallback: Check string name explicitly if isinstance fails (e.g. mocking issues)
        if not is_timeout and exception_type in ("ReadTimeout", "ConnectTimeout", "TimeoutException"):
            is_timeout = True

        if is_timeout:
            return {
                "error_kind": "ADAPTER_ERROR_TIMEOUT",
                "is_timeout": True,
                "is_network": False,
                "normalized_error": f"TIMEOUT: {error_str[:80]}"
            }

        # 2. Check for Network Error
        is_network = exception_type in NETWORK_EXCEPTION_NAMES
        if httpx and isinstance(exception, httpx.ConnectError):
            is_network = True
        if httpcore and isinstance(exception, httpcore.ConnectError):
            is_network = True

        if is_network:
            return {
                "error_kind": "ADAPTER_ERROR_NETWORK",
                "is_timeout": False,
                "is_network": True,
                "normalized_error": f"NETWORK_ERROR: {error_str[:80]}"
            }

        # 3. Check for Validation Error
        if exception_type == "BinanceValidationError":
            return {
                "error_kind": "ADAPTER_ERROR",
                "is_timeout": False,
                "is_network": False,
                "normalized_error": f"VALIDATION_ERROR: {error_str[:100]}"
            }

        # 4. Check for Specific API Errors (using loaded config)
        if self.ERROR_CODES["unknown_order"] in error_str:
            norm_err = "UNKNOWN_ORDER"
        elif self.ERROR_CODES["would_trigger"] in error_str:
            norm_err = "WOULD_TRIGGER"
        elif self.ERROR_CODES["duplicate_id"] in error_str:
            norm_err = "DUPLICATE_ID"
        elif self.ERROR_CODES["invalid_qty"] in error_str:
            norm_err = "INVALID_QUANTITY"
        elif self.ERROR_CODES["min_notional"] in error_str:
            norm_err = "MIN_NOTIONAL_FAILED"
        else:
            norm_err = f"ADAPTER_ERROR: {error_str[:100]}"

        return {
            "error_kind": "ADAPTER_ERROR",
            "is_timeout": False,
            "is_network": False,
            "normalized_error": norm_err
        }

    def _normalize_error(self, exception: Exception) -> str:
        """
        Normalize adapter exceptions to error codes.
        Delegates to _classify_exception.
        """
        return self._classify_exception(exception)["normalized_error"]

    def _is_unknown_order_error(self, exception: Exception) -> bool:
        """
        Check if exception is an "Unknown Order" error.
        """
        return self.ERROR_CODES["unknown_order"] in str(exception)

    def _classify_place_error(self, error_msg: str, response: Dict[str, Any]) -> Dict[str, str]:
        """
        EXEC-R2-K: Classify PLACE errors as expected (races) or unexpected (state divergence).
        """
        error_str_lower = error_msg.lower()

        # Expected races / transient errors
        if self.ERROR_CODES["would_trigger"] in error_msg or "would immediately trigger" in error_str_lower:
            return {"category": "expected", "reason_code": "ORDER_WOULD_TRIGGER"}
        elif self.ERROR_CODES["duplicate_id"] in error_msg or "duplicated" in error_str_lower:
            return {"category": "expected", "reason_code": "DUPLICATE_CLIENT_ORDER_ID"}
        elif self.ERROR_CODES["insufficient_balance"] in error_msg or "insufficient balance" in error_str_lower:
            return {"category": "expected", "reason_code": "INSUFFICIENT_BALANCE"}
        elif self.ERROR_CODES["rate_limit"] in error_msg or "rate limit" in error_str_lower:
            return {"category": "expected", "reason_code": "RATE_LIMIT"}
        elif "timeout" in error_str_lower or "connect" in error_str_lower:
            return {"category": "expected", "reason_code": "NETWORK_TIMEOUT"}

        # Unexpected errors (state divergence / bugs)
        elif self.ERROR_CODES["invalid_qty"] in error_msg or "invalid quantity" in error_str_lower:
            return {"category": "unexpected", "reason_code": "INVALID_QUANTITY"}
        elif self.ERROR_CODES["min_notional"] in error_msg or "min notional" in error_str_lower:
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

        tif_value = cmd.get("tif") or cmd.get("time_in_force") or extra_params.get(
            "tif") or extra_params.get("time_in_force")

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
                position_side=cmd.get(
                    "position_side") or extra_params.get("position_side"),
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
            # Construct ExchangeOrderParams
            # Note: We convert values to strings as expected by ExchangeOrderParams
            params = ExchangeOrderParams(
                symbol=str(req_kwargs.get("symbol")),
                side=str(req_kwargs.get("side")),
                order_type=str(req_kwargs.get("order_type", "MARKET")),
                quantity=str(req_kwargs.get("quantity")),
                price=str(req_kwargs.get("price")) if req_kwargs.get("price") is not None else None,
                time_in_force=str(req_kwargs.get("time_in_force", "GTC")),
                reduce_only=bool(req_kwargs.get("reduce_only", False)),
                close_position=bool(req_kwargs.get("close_position", False)),
                client_order_id=str(req_kwargs.get("client_order_id")) if req_kwargs.get("client_order_id") else None,
                position_side=str(req_kwargs.get("position_side")) if req_kwargs.get("position_side") else None,
                stop_price=str(req_kwargs.get("stop_price")) if req_kwargs.get("stop_price") is not None else None,
                working_type=str(req_kwargs.get("working_type")) if req_kwargs.get("working_type") else None,
            )

            # Call adapter create_order method
            # Note: create_order returns ExchangeOrderResponse object, we need to convert it to dict or use it directly
            response_obj = await self._call_adapter(
                "create_order",
                params=params,
            )

            # Convert ExchangeOrderResponse to dict if needed
            response = response_obj.to_dict() if hasattr(response_obj, "to_dict") else response_obj

            # Handle missing adapter method or None response
            if response is None:
                return {
                    "status": ExecutionStatus.FAILED,
                    "success": False,
                    "order_id": None,
                    "client_order_id": client_order_id,
                    "error": "Adapter returned None (method missing?)",
                    "error_kind": "ADAPTER_ERROR",
                    "metadata": {}
                }

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
                        "should_retry": False,  # Currently no retry logic
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
            # Use centralized classification
            classification = self._classify_exception(e)
            error_kind = classification["error_kind"]
            error_normalized = classification["normalized_error"]
            is_timeout = classification["is_timeout"]
            is_network = classification["is_network"]
            exception_type = type(e).__name__

            # EXEC-R2-K: Classify exception-based errors
            place_classification = self._classify_place_error(error_normalized, {})
            reason_code = place_classification["reason_code"]

            # Timeouts/Network -> ERROR, benign ORDER_WOULD_TRIGGER -> WARNING, others -> ERROR
            if is_timeout or is_network:
                log_level = logger.error
            elif place_classification["category"] == "expected" and reason_code == "ORDER_WOULD_TRIGGER":
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
                    "error_category": place_classification["category"],
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
                "is_network": is_network,
                "should_retry": False,  # Currently no retry logic
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

            # Handle structured timeout response from adapter
            if isinstance(response, dict) and response.get("error_kind") == "ADAPTER_ERROR_TIMEOUT":
                logger.warning(
                    "SHADOW_EXEC_POS_CANCEL_TIMEOUT",
                    extra={
                        "symbol": symbol,
                        "order_id": order_id,
                        "error_kind": "ADAPTER_ERROR_TIMEOUT",
                    }
                )
                return {
                    "status": ExecutionStatus.FAILED,
                    "success": False,
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                    "error": response.get("error", "Timeout"),
                    "error_kind": "ADAPTER_ERROR_TIMEOUT",
                    "is_timeout": True,
                    "metadata": response,
                }

            # Handle structured error response (non-timeout)
            if isinstance(response, dict) and response.get("success") is False:
                error_msg = response.get("error", "Unknown error from adapter")
                error_kind = response.get("error_kind", "ADAPTER_ERROR")
                logger.warning(
                    "SHADOW_EXEC_POS_CANCEL_FAILED",
                    extra={
                        "symbol": symbol,
                        "order_id": order_id,
                        "error": error_msg,
                        "error_kind": error_kind,
                    }
                )
                return {
                    "status": ExecutionStatus.FAILED,
                    "success": False,
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                    "error": error_msg,
                    "error_kind": error_kind,
                    "metadata": response,
                }

            logger.info(
                "SHADOW_EXEC_POS_CANCEL_SUCCESS",
                extra={
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

            # Use centralized classification
            classification = self._classify_exception(e)
            error_kind = classification["error_kind"]
            error_normalized = classification["normalized_error"]
            is_timeout = classification["is_timeout"]

            if is_timeout:
                logger.warning(
                    f"SHADOW_EXEC_POS_CANCEL_TIMEOUT_EXCEPTION",
                    extra={
                        "symbol": symbol,
                        "order_id": order_id,
                        "error": str(e)
                    }
                )
                return {
                    "status": ExecutionStatus.FAILED,
                    "success": False,
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                    "error": str(e),
                    "error_kind": "ADAPTER_ERROR_TIMEOUT",
                    "is_timeout": True,
                    "metadata": {"exception": str(e)}
                }

            # EXEC-R2-K: Add reason_code for CANCEL failures
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
            # Place reduce-only MARKET order via create_order
            params = ExchangeOrderParams(
                symbol=str(symbol),
                side=str(side),
                order_type="MARKET",
                quantity=str(quantity),
                reduce_only=True,
                time_in_force="GTC"
            )

            response_obj = await self._call_adapter(
                "create_order",
                params=params
            )

            response = response_obj.to_dict() if hasattr(response_obj, "to_dict") else response_obj

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
