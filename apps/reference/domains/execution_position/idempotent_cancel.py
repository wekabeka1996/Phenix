"""
PHASE 4: Idempotent Order Cancellations
Implements robust cancellation with pre-checks, -2011 absorption, and deterministic clientOrderId.
"""

import asyncio
import hashlib
import time
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple, Callable, Awaitable
from dataclasses import dataclass
from dataclasses import asdict, is_dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Binance order statuses"""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class ClientOrderIdConfig:
    """Configuration for deterministic clientOrderId generation"""
    prefix: str = "AUR"  # Aurora prefix
    use_timestamp: bool = True
    counter_enabled: bool = True


@dataclass
class IdempotentCancelResult:
    """Result of idempotent cancellation attempt"""
    success: bool
    reason: str
    # NEW, PARTIALLY_FILLED, FILLED, etc.
    order_status_before: Optional[str] = None
    order_status_after: Optional[str] = None
    already_canceled: bool = False  # True if was already CANCELED/FILLED/EXPIRED
    # Binance error code (e.g., -2011 = Unknown order)
    error_code: Optional[int] = None
    is_idempotent_success: bool = False  # True if -2011 or already terminal state


class IdempotentCancelHelper:
    """
    Helper for idempotent order cancellations with -2011 absorption.

    Strategy:
    1. Pre-cancel getOrder check: If already CANCELED/FILLED/EXPIRED → success (no cancel needed)
    2. Cancel order via API
    3. -2011 handling: Treat "Unknown order" as success (order missing = already gone)
    4. Log all outcomes for audit trail
    """

    def __init__(self, config: Optional[ClientOrderIdConfig] = None, logger_inst: Optional[logging.Logger] = None):
        self.config = config or ClientOrderIdConfig()
        self.logger = logger_inst or logger
        self._counter = 0

    @staticmethod
    def generate_deterministic_clientOrderId(
        symbol: str,
        side: str,
        notional_usdt: Decimal,
        session_prefix: str = "AUR",
        use_timestamp: bool = True,
        counter: int = 0
    ) -> str:
        """
        Generate deterministic clientOrderId for idempotency.

        Format: AUR-{symbol}-{side}-{notional}-{timestamp_or_counter}

        Example:
          AUR-BTCUSDT-BUY-1000-1730944323456
          AUR-ETHUSDT-SELL-500-0

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            side: BUY or SELL
            notional_usdt: Order notional in USD
            session_prefix: Custom prefix (default: AUR)
            use_timestamp: If True, use millisecond timestamp; else use counter
            counter: Counter value (used if use_timestamp=False)

        Returns:
            Deterministic clientOrderId string (max 36 chars)
        """
        # Hash notional to get compact representation (avoid precision issues)
        notional_hash = hashlib.md5(
            str(notional_usdt).encode()).hexdigest()[:6]

        if use_timestamp:
            # Last 6 digits of ms timestamp
            time_component = int(time.time() * 1000) % 1_000_000
        else:
            time_component = counter % 1_000_000

        # Format: AUR-SYMBOL-SIDE-NOTIONAL_HASH-TIME_COMPONENT
        client_order_id = f"{session_prefix}-{symbol}-{side}-{notional_hash}-{time_component}"

        # Binance limit: max 36 chars
        if len(client_order_id) > 36:
            # Truncate symbol if needed
            max_symbol_len = 36 - \
                len(f"{session_prefix}---{notional_hash}-{time_component}")
            symbol_trunc = symbol[:max_symbol_len]
            client_order_id = f"{session_prefix}-{symbol_trunc}-{side}-{notional_hash}-{time_component}"

        return client_order_id

    async def get_order_before_cancel(
        self,
        symbol: str,
        order_id: str,
        get_order_func
    ) -> Optional[Dict[str, Any]]:
        """
        Pre-cancel check: Get order status before attempting cancellation.

        Args:
            symbol: Trading symbol
            order_id: Binance orderId to check
            get_order_func: Async function to call (e.g., self.get_order from adapter)

        Returns:
            Order dict or None if not found
        """
        try:
            order = await get_order_func(symbol, order_id)
            return self._normalize_response(order)
        except Exception as e:
            # Binance returns both -2011 (Unknown order) and -2013 (Order does not exist)
            # for already-gone orders. Treat this as idempotent success upstream.
            code = getattr(e, "code", None)
            msg = (getattr(e, "msg", None) or str(e) or "").strip()
            if code in (-2011, -2013) or "Unknown order" in msg or "Order does not exist" in msg:
                self.logger.warning(
                    f"IDEMPOTENT_CANCEL: getOrder pre-check indicates NOT_FOUND: {e}"
                )
                return {"status": "NOT_FOUND", "code": code, "msg": msg}

            self.logger.warning(f"IDEMPOTENT_CANCEL: getOrder pre-check failed: {e}")
            return None

    @staticmethod
    def _normalize_response(resp: Any) -> Dict[str, Any]:
        if resp is None:
            return {}
        if isinstance(resp, dict):
            return resp
        if hasattr(resp, "to_dict") and callable(getattr(resp, "to_dict")):
            try:
                maybe = resp.to_dict()
                if isinstance(maybe, dict):
                    return maybe
            except Exception:
                pass
        if is_dataclass(resp):
            try:
                data = asdict(resp)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        if hasattr(resp, "__dict__"):
            try:
                return dict(vars(resp))
            except Exception:
                pass
        return {"raw": str(resp)}

    async def cancel_order_idempotent(
        self,
        symbol: str,
        order_id: str,
        cancel_func: Callable[[str, str], Awaitable[Any]],
        get_order_func: Callable[[str, str], Awaitable[Any]],
        max_retries: int = 2
    ) -> IdempotentCancelResult:
        """
        Cancel order with idempotent semantics and -2011 absorption.

        Algorithm:
        1. Pre-check: getOrder to see if already terminal
           → If CANCELED/FILLED/EXPIRED: return success (no cancel needed)
        2. Cancel via API
        3. If success: return success
        4. If -2011 (Unknown order): treat as idempotent success (order missing = already gone)
        5. If other error: return failure

        Args:
            symbol: Trading symbol
            order_id: Binance orderId to cancel
            cancel_func: Async function to cancel (e.g., self._cancel_binance_order_async)
            get_order_func: Async function to get order (e.g., self.get_order)
            max_retries: Max retry attempts for transient errors

        Returns:
            IdempotentCancelResult with success flag and details
        """
        # Step 1: Pre-cancel check
        pre_check_order = await self.get_order_before_cancel(symbol, order_id, get_order_func)

        if pre_check_order:
            status = str(pre_check_order.get("status") or "").upper()
            if status in ["CANCELED", "FILLED", "EXPIRED", "REJECTED", "NOT_FOUND"]:
                # Already terminal - cancel not needed
                self.logger.info(
                    f"IDEMPOTENT_CANCEL: Order {order_id} already {status} (pre-check), "
                    f"treating as success"
                )
                return IdempotentCancelResult(
                    success=True,
                    reason=(
                        f"PRE_CHECK_TERMINAL_{status}"
                        if status != "NOT_FOUND"
                        else "PRE_CHECK_NOT_FOUND"
                    ),
                    order_status_before=status,
                    order_status_after=status,
                    already_canceled=(status in {"CANCELED", "NOT_FOUND"}),
                    is_idempotent_success=True
                )

            if status in ["NEW", "PARTIALLY_FILLED", "ACCEPTED", "PARTIAL_FILL"]:
                # Can proceed with cancel
                self.logger.debug(
                    f"IDEMPOTENT_CANCEL: Pre-check OK, order {order_id} is {status}, proceeding")

        # Step 2: Attempt cancel
        for attempt in range(max_retries):
            try:
                result = self._normalize_response(await cancel_func(symbol, order_id))

                # Check Binance response
                status = str(result.get("status") or "").upper()
                if status in ("CANCELED", "CANCELLED"):
                    self.logger.info(
                        f"IDEMPOTENT_CANCEL: Successfully canceled order {order_id} "
                        f"(attempt {attempt + 1})"
                    )
                    return IdempotentCancelResult(
                        success=True,
                        reason="CANCEL_SUCCESS",
                        order_status_before=pre_check_order.get(
                            "status") if pre_check_order else None,
                        order_status_after=status,
                        is_idempotent_success=True
                    )

                # Check for Binance error codes
                error_code = result.get("code")
                error_msg = result["msg"] if "msg" in result else ""

                # -2011: Unknown order (order missing = already gone or never existed)
                if error_code in (-2011, -2013) or "Unknown order" in error_msg or "Order does not exist" in error_msg:
                    absorbed_code = error_code if error_code in (-2011, -2013) else -2011
                    self.logger.warning(
                        f"IDEMPOTENT_CANCEL: Got {absorbed_code} (order missing) for {order_id}, "
                        f"treating as idempotent success"
                    )
                    return IdempotentCancelResult(
                        success=True,
                        reason=f"IDEMPOTENT_{absorbed_code}_ABSORBED",
                        order_status_before=pre_check_order.get(
                            "status") if pre_check_order else None,
                        order_status_after="UNKNOWN",
                        error_code=absorbed_code,
                        is_idempotent_success=True
                    )

                # Other Binance errors
                if error_code:
                    self.logger.error(
                        f"IDEMPOTENT_CANCEL: Binance error code {error_code}: {error_msg}"
                    )
                    return IdempotentCancelResult(
                        success=False,
                        reason=f"BINANCE_ERROR_{error_code}",
                        error_code=error_code,
                        order_status_before=pre_check_order.get(
                            "status") if pre_check_order else None,
                        is_idempotent_success=False
                    )

                # Unknown response format
                return IdempotentCancelResult(
                    success=False,
                    reason=f"UNKNOWN_RESPONSE: {result}",
                    order_status_before=pre_check_order.get(
                        "status") if pre_check_order else None,
                    is_idempotent_success=False
                )

            except Exception as e:
                self.logger.warning(
                    f"IDEMPOTENT_CANCEL: Exception on attempt {attempt + 1}: {e}"
                )
                if attempt == max_retries - 1:
                    return IdempotentCancelResult(
                        success=False,
                        reason=f"EXCEPTION_AFTER_{max_retries}_RETRIES: {str(e)}",
                        order_status_before=pre_check_order.get(
                            "status") if pre_check_order else None,
                        is_idempotent_success=False
                    )
                # Retry on transient errors
                await self._backoff_wait(attempt)

        # Should not reach here
        return IdempotentCancelResult(
            success=False,
            reason="UNEXPECTED_RETRY_EXHAUSTION",
            order_status_before=pre_check_order.get(
                "status") if pre_check_order else None,
            is_idempotent_success=False
        )

    @staticmethod
    async def _backoff_wait(attempt: int) -> None:
        """Exponential backoff before retry"""
        wait_ms = min(100 * (2 ** attempt),
                      1000)  # 100ms, 200ms, 400ms, capped at 1s
        await asyncio.sleep(wait_ms / 1000)

    def log_cancel_result(self, result: IdempotentCancelResult, order_id: str) -> None:
        """Log cancellation result for audit trail"""
        status_str = "SUCCESS" if result.success else "FAILED"
        level = logging.INFO if result.success else logging.WARNING

        self.logger.log(
            level,
            f"IDEMPOTENT_CANCEL_AUDIT: order_id={order_id} status={status_str} "
            f"reason={result.reason} before={result.order_status_before} "
            f"after={result.order_status_after} error_code={result.error_code} "
            f"idempotent_success={result.is_idempotent_success}"
        )
