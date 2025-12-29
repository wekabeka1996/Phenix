"""
Symbol Executor V2 - Pure Execution Without Decision Logic
===========================================================

This executor is a "mechanical hand" - it executes orders but makes NO decisions
about TP/SL levels, timing, or quantities. All bracket logic lives in BracketService.

Key Changes from V1:
- REMOVED: _calculate_sl_price(), _calculate_tp_price()
- REMOVED: _place_brackets_close_position() - no auto-brackets after entry
- REMOVED: sl_pct, tp_rr parameters - no bracket math
- ADDED: execute_bracket() - executes a single bracket order from BracketPlan
- SIMPLIFIED: execute_entry() - places entry only, returns immediately after fill

Flow:
1. Runtime receives ENTRY_INTENT
2. ExecutorPool.execute_entry() places LIMIT/MARKET order
3. Runtime receives TRADE_EXECUTED
4. BracketService.evaluate() produces BracketPlan
5. Runtime calls ExecutorPool.execute_bracket() for each action
6. ExecutorPool routes to SymbolExecutorV2.execute_bracket()

Author: Copilot
Date: 2025-11-29
RID: EXECUTOR-POOL-PHASE4-BRACKETS-SINGLE-SOURCE
"""
from typing import Any, Dict, Optional, List, Tuple
import logging
import threading
import time
import asyncio
import httpx
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

logger = logging.getLogger(__name__)

# Enable nested event loops for running async from sync context
try:
    import nest_asyncio
    nest_asyncio.apply()
    _NEST_ASYNCIO_APPLIED = True
except ImportError:
    _NEST_ASYNCIO_APPLIED = False
    logger.debug("nest_asyncio not available")


def run_async_safe(coro) -> Any:
    """Run async coroutine from sync context safely."""
    return asyncio.run(coro)


class ExecutorState(Enum):
    """Simplified state machine - just entry flow."""
    IDLE = "IDLE"
    PLACING_ORDER = "PLACING_ORDER"
    WAITING_FILL = "WAITING_FILL"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass
class OrderResult:
    """Result of order execution."""
    success: bool
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    fill_price: Optional[str] = None
    fill_qty: Optional[str] = None
    error: Optional[str] = None
    latency_ms: float = 0.0


class SymbolExecutorV2:
    """
    Pure executor for a single trading symbol.

    NO bracket logic - just executes orders as instructed.
    BracketService is the single source of truth for TP/SL.
    """

    def __init__(
        self,
        symbol: str,
        adapter: Any,
        gatekeeper: Any,
        fill_timeout_sec: float = 60.0,
    ):
        """
        Initialize executor.

        NOTE: No sl_pct, tp_rr parameters - brackets are handled by BracketService.
        """
        self.symbol = symbol
        self.adapter = adapter
        self.gatekeeper = gatekeeper
        self.fill_timeout_sec = fill_timeout_sec

        # State
        self._lock = threading.RLock()
        self._state = ExecutorState.IDLE
        self._fill_event = threading.Event()
        self._current_order_id: Optional[str] = None

        # Metrics
        self._metrics = {
            "entries_started": 0,
            "entries_completed": 0,
            "entries_failed": 0,
            "brackets_executed": 0,
            "brackets_failed": 0,
            "fill_timeouts": 0,
            "avg_entry_latency_ms": 0.0,
        }
        self._entry_latencies: List[float] = []

        logger.info(
            f"[SymbolExecutorV2:{symbol}] Initialized (no bracket logic)")

    # ─────────────────────────────────────────────────────────────
    # Public API: Entry Orders
    # ─────────────────────────────────────────────────────────────

    def is_busy(self) -> bool:
        """Check if executor is processing an order."""
        with self._lock:
            return self._state not in (ExecutorState.IDLE, ExecutorState.COMPLETE, ExecutorState.FAILED)

    def get_state(self) -> str:
        """Get current state."""
        with self._lock:
            return self._state.value

    def execute_entry(
        self,
        side: str,
        quantity: str,
        price: Optional[str],
        client_order_id: str,
        order_type: str = "LIMIT",
    ) -> OrderResult:
        """
        Execute entry order only. NO automatic brackets.

        After this returns, Runtime should:
        1. Wait for TRADE_EXECUTED event
        2. Call BracketService.evaluate()
        3. Execute resulting BracketPlan via execute_bracket()

        Args:
            side: BUY or SELL
            quantity: Order quantity
            price: Limit price (None for MARKET)
            client_order_id: Unique ID
            order_type: LIMIT or MARKET

        Returns:
            OrderResult with success status
        """
        if self.is_busy():
            return OrderResult(
                success=False,
                error=f"Executor busy for {self.symbol}",
            )

        start_ts = time.time()

        with self._lock:
            self._state = ExecutorState.PLACING_ORDER
            self._fill_event.clear()
            self._metrics["entries_started"] += 1

        logger.info(
            f"[SymbolExecutorV2:{self.symbol}] ENTRY: {side} {quantity} @ {price or 'MARKET'}"
        )

        try:
            # Validate and round via gatekeeper
            rounded_qty, rounded_price, error = self._validate_and_round(
                quantity, price)
            if error:
                self._fail(error)
                return OrderResult(success=False, error=error)

            # Place order
            response = run_async_safe(self._place_order_async(
                side=side,
                quantity=rounded_qty,
                price=rounded_price,
                client_order_id=client_order_id,
                order_type=order_type,
            ))

            order_id = response.get("orderId") or response.get("order_id")
            status = response.get("status", "")

            with self._lock:
                self._current_order_id = order_id

            latency_ms = (time.time() - start_ts) * 1000

            # If already filled (MARKET order), return immediately
            if status == "FILLED":
                self._complete(latency_ms)
                return OrderResult(
                    success=True,
                    order_id=str(order_id),
                    client_order_id=client_order_id,
                    fill_price=str(response.get("avgPrice")
                                   or response.get("price") or price),
                    fill_qty=str(response.get("executedQty") or quantity),
                    latency_ms=latency_ms,
                )

            # For LIMIT orders, wait for fill with polling fallback
            with self._lock:
                self._state = ExecutorState.WAITING_FILL

            # Try WebSocket-based fill first (short timeout)
            filled = self._fill_event.wait(
                timeout=min(5.0, self.fill_timeout_sec))

            if not filled:
                # Fallback: Poll order status via REST API (for testnet where WebSocket may not work)
                logger.info(
                    f"[SymbolExecutorV2:{self.symbol}] No WebSocket fill, polling order status..."
                )
                poll_result = self._poll_order_status(
                    order_id=order_id,
                    timeout_sec=self.fill_timeout_sec - 5.0,
                    poll_interval_sec=1.0,
                )
                filled = poll_result is not None
                if poll_result:
                    # Extract fill data from poll result
                    poll_fill_price = poll_result.get("fill_price")
                    poll_fill_qty = poll_result.get("fill_qty")

            if not filled:
                self._metrics["fill_timeouts"] += 1
                self._fail("Fill timeout")
                return OrderResult(
                    success=False,
                    order_id=str(order_id),
                    client_order_id=client_order_id,
                    error="Fill timeout",
                )

            latency_ms = (time.time() - start_ts) * 1000
            self._complete(latency_ms)

            # Return fill data - prefer poll data over initial response
            final_fill_price = poll_fill_price if 'poll_fill_price' in dir() and poll_fill_price else (
                response.get("avgPrice") or response.get("price") or price
            )
            final_fill_qty = poll_fill_qty if 'poll_fill_qty' in dir() and poll_fill_qty else (
                response.get("executedQty") or quantity
            )

            return OrderResult(
                success=True,
                order_id=str(order_id),
                client_order_id=client_order_id,
                fill_price=str(final_fill_price) if final_fill_price else None,
                fill_qty=str(final_fill_qty) if final_fill_qty else None,
                latency_ms=latency_ms,
            )

        except Exception as e:
            logger.exception(
                f"[SymbolExecutorV2:{self.symbol}] Entry failed: {e}")
            self._fail(str(e))
            return OrderResult(success=False, error=str(e))

    def on_fill(self, fill_price: str, fill_qty: str, order_id: str) -> None:
        """
        Called when order fill event received via WebSocket.
        Thread-safe.
        """
        with self._lock:
            if self._state != ExecutorState.WAITING_FILL:
                return
            if self._current_order_id and str(self._current_order_id) != str(order_id):
                return

        logger.info(
            f"[SymbolExecutorV2:{self.symbol}] Fill: {fill_qty} @ {fill_price}")
        self._fill_event.set()

    def _poll_order_status(
        self,
        order_id: str,
        timeout_sec: float = 55.0,
        poll_interval_sec: float = 1.0,
    ) -> Optional[Dict[str, Any]]:
        """
        Poll order status via REST API until filled or timeout.

        Fallback for testnet where WebSocket USER_DATA_STREAM may not work.

        Returns:
            Dict with fill data if FILLED, None if timeout/error/cancelled
        """
        if not self.adapter:
            logger.warning(
                f"[SymbolExecutorV2:{self.symbol}] No adapter for polling")
            return None

        start_time = time.time()
        poll_count = 0

        while time.time() - start_time < timeout_sec:
            poll_count += 1
            try:
                # Query order status via REST API
                order_status = run_async_safe(
                    self.adapter.get_order(
                        symbol=self.symbol,
                        order_id=order_id,
                    )
                )

                status = order_status.get("status", "")

                if status == "FILLED":
                    fill_price = order_status.get(
                        "avgPrice") or order_status.get("price")
                    fill_qty = order_status.get(
                        "executedQty") or order_status.get("origQty")
                    logger.info(
                        f"[SymbolExecutorV2:{self.symbol}] Order {order_id} FILLED "
                        f"qty={fill_qty} @ {fill_price} (poll #{poll_count})"
                    )
                    return {
                        "status": "FILLED",
                        "fill_price": str(fill_price) if fill_price else None,
                        "fill_qty": str(fill_qty) if fill_qty else None,
                    }
                elif status in ("CANCELED", "EXPIRED", "REJECTED"):
                    logger.warning(
                        f"[SymbolExecutorV2:{self.symbol}] Order {order_id} {status} (poll #{poll_count})"
                    )
                    return None

                # Still pending, wait and retry
                logger.debug(
                    f"[SymbolExecutorV2:{self.symbol}] Order {order_id} status={status} (poll #{poll_count})"
                )

            except Exception as e:
                logger.warning(
                    f"[SymbolExecutorV2:{self.symbol}] Poll error: {e} (poll #{poll_count})"
                )

            time.sleep(poll_interval_sec)

        logger.warning(
            f"[SymbolExecutorV2:{self.symbol}] Poll timeout after {poll_count} attempts"
        )
        return None

    # ─────────────────────────────────────────────────────────────
    # Public API: Bracket Orders (from BracketPlan)
    # ─────────────────────────────────────────────────────────────

    def execute_bracket(
        self,
        action_type: str,  # "PLACE_SL", "PLACE_TP", "CANCEL"
        side: str,  # Exit side: SELL for LONG, BUY for SHORT
        stop_price: Optional[str] = None,
        order_id: Optional[str] = None,  # For CANCEL
        client_order_id: Optional[str] = None,
    ) -> OrderResult:
        """
        Execute a single bracket action from BracketPlan.

        This is a "dumb" executor - it does exactly what BracketService says.
        No calculation, no decision, just execution.

        Args:
            action_type: PLACE_SL, PLACE_TP, or CANCEL
            side: Exit side for bracket (SELL for LONG position, BUY for SHORT)
            stop_price: Stop price for SL/TP
            order_id: Order ID to cancel (for CANCEL action)
            client_order_id: Client order ID

        Returns:
            OrderResult with execution status
        """
        start_ts = time.time()

        logger.info(
            f"[SymbolExecutorV2:{self.symbol}] BRACKET: {action_type} "
            f"side={side} stop_price={stop_price} order_id={order_id}"
        )

        try:
            if action_type == "CANCEL":
                if not order_id:
                    return OrderResult(success=False, error="CANCEL requires order_id")

                response = run_async_safe(self._cancel_order_async(order_id))
                latency_ms = (time.time() - start_ts) * 1000

                self._metrics["brackets_executed"] += 1
                return OrderResult(
                    success=True,
                    order_id=order_id,
                    latency_ms=latency_ms,
                )

            elif action_type in ("PLACE_SL", "PLACE_TP"):
                if not stop_price:
                    return OrderResult(success=False, error=f"{action_type} requires stop_price")

                # FIX-PRECISION: Normalize stop_price using gatekeeper's tick_size
                normalized_stop_price = self._normalize_stop_price(stop_price)
                if normalized_stop_price is None:
                    return OrderResult(success=False, error="Failed to normalize stop_price")

                order_type = "STOP_MARKET" if action_type == "PLACE_SL" else "TAKE_PROFIT_MARKET"

                response = run_async_safe(self._place_bracket_async(
                    side=side,
                    order_type=order_type,
                    stop_price=normalized_stop_price,
                    client_order_id=client_order_id,
                ))

                latency_ms = (time.time() - start_ts) * 1000
                new_order_id = response.get(
                    "orderId") or response.get("order_id")

                self._metrics["brackets_executed"] += 1
                return OrderResult(
                    success=True,
                    order_id=str(new_order_id) if new_order_id else None,
                    client_order_id=client_order_id,
                    latency_ms=latency_ms,
                )

            else:
                return OrderResult(success=False, error=f"Unknown action_type: {action_type}")

        except Exception as e:
            logger.error(
                f"[SymbolExecutorV2:{self.symbol}] Bracket failed: {e}")
            self._metrics["brackets_failed"] += 1
            return OrderResult(success=False, error=str(e))

    # ─────────────────────────────────────────────────────────────
    # Metrics
    # ─────────────────────────────────────────────────────────────

    def get_metrics(self) -> Dict[str, Any]:
        """Get executor metrics."""
        with self._lock:
            return {
                "symbol": self.symbol,
                "state": self._state.value,
                "is_busy": self.is_busy(),
                **self._metrics,
            }

    # ─────────────────────────────────────────────────────────────
    # Internal: Validation
    # ─────────────────────────────────────────────────────────────

    def _validate_and_round(
        self, quantity: str, price: Optional[str]
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Validate and round quantity/price using gatekeeper."""
        if self.gatekeeper is None:
            return quantity, price, None

        try:
            decision = self.gatekeeper.validate_order(
                symbol=self.symbol,
                qty=quantity,
                price=price,
            )

            if not decision["allowed"]:
                return None, None, f"Gatekeeper rejected: {decision['reason']}"

            rounded_qty = decision["modified_params"].get("quantity", quantity)
            rounded_price = decision["modified_params"].get("price", price)

            return str(rounded_qty), str(rounded_price) if rounded_price else None, None

        except Exception as e:
            logger.warning(
                f"[SymbolExecutorV2:{self.symbol}] Gatekeeper error: {e}")
            return quantity, price, None

    def _normalize_stop_price(self, stop_price: str) -> Optional[str]:
        """
        Normalize stop_price to tick_size precision.

        FIX-PRECISION: BracketService may send high-precision Decimal like
        134.9165999999999877445588936 but Binance requires tick_size alignment.
        """
        try:
            price_dec = Decimal(str(stop_price))

            if self.gatekeeper is None:
                # Fallback: truncate to 8 decimals
                result = price_dec.quantize(Decimal("0.00000001"))
                logger.debug(
                    f"[SymbolExecutorV2:{self.symbol}] stop_price normalized (fallback): "
                    f"{stop_price} → {result}"
                )
                return str(result)

            # Get tick_size from gatekeeper
            specs = self.gatekeeper._get_instrument_specs(self.symbol)
            tick_size = specs.get("tick_size", Decimal("0.01"))

            # Round DOWN to nearest tick_size (same as gatekeeper._round_to_step)
            if tick_size > 0:
                from decimal import ROUND_DOWN
                steps = (
                    price_dec / tick_size).to_integral_value(rounding=ROUND_DOWN)
                result = steps * tick_size
            else:
                result = price_dec.quantize(Decimal("0.00000001"))

            logger.debug(
                f"[SymbolExecutorV2:{self.symbol}] stop_price normalized: "
                f"{stop_price} → {result} (tick_size={tick_size})"
            )
            return str(result)

        except Exception as e:
            logger.error(
                f"[SymbolExecutorV2:{self.symbol}] Failed to normalize stop_price: {e}")
            # Fail-closed: return None to prevent precision error
            return None

    # ─────────────────────────────────────────────────────────────
    # Internal: Async Operations
    # ─────────────────────────────────────────────────────────────

    def _create_session(self) -> httpx.AsyncClient:
        """Create fresh httpx session with adapter config."""
        api_key = getattr(self.adapter, 'api_key', None)
        base_url = getattr(self.adapter, 'base_url', None)
        timeout_val = getattr(self.adapter, '_timeout', None)

        headers = {
            "X-MBX-APIKEY": api_key} if api_key and isinstance(api_key, str) else {}

        if not isinstance(timeout_val, httpx.Timeout):
            timeout_val = httpx.Timeout(30.0)

        kwargs = {
            "timeout": timeout_val,
            "headers": headers,
            "limits": httpx.Limits(max_connections=10),
        }

        if base_url and isinstance(base_url, str):
            kwargs["base_url"] = base_url

        return httpx.AsyncClient(**kwargs)

    async def _signed_request(
        self,
        session: httpx.AsyncClient,
        method: str,
        path: str,
        params: dict,
    ) -> Dict[str, Any]:
        """Make signed request."""
        base_url = getattr(self.adapter, 'base_url', '')
        url = f"{base_url}{path}"

        if hasattr(self.adapter, '_sign_build'):
            _, final_params = self.adapter._sign_build(dict(params))
        else:
            final_params = params

        response = await session.request(method.upper(), url, params=final_params)

        if response.status_code >= 400:
            raise Exception(
                f"API Error {response.status_code}: {response.text}")

        return response.json()

    async def _place_order_async(
        self,
        side: str,
        quantity: str,
        price: Optional[str],
        client_order_id: str,
        order_type: str,
    ) -> Dict[str, Any]:
        """Place entry order (LIMIT or MARKET)."""
        session = self._create_session()

        try:
            order_params = {
                "symbol": self.symbol,
                "side": side.upper(),
                "type": order_type.upper(),
                "quantity": quantity,
                "newClientOrderId": client_order_id,
            }

            if order_type.upper() == "LIMIT":
                order_params["price"] = price
                order_params["timeInForce"] = "GTC"

            response = await self._signed_request(
                session=session,
                method="POST",
                path="/fapi/v1/order",
                params=order_params,
            )

            return response

        finally:
            try:
                await session.aclose()
            except Exception:
                pass

    async def _place_bracket_async(
        self,
        side: str,
        order_type: str,
        stop_price: str,
        client_order_id: Optional[str],
    ) -> Dict[str, Any]:
        """Place bracket order with closePosition=true."""
        session = self._create_session()

        try:
            order_params = {
                "symbol": self.symbol,
                "side": side.upper(),
                "type": order_type,
                "closePosition": "true",  # Key: closes ENTIRE position
                "stopPrice": stop_price,
            }

            if client_order_id:
                order_params["newClientOrderId"] = client_order_id

            response = await self._signed_request(
                session=session,
                method="POST",
                path="/fapi/v1/order",
                params=order_params,
            )

            return response

        finally:
            try:
                await session.aclose()
            except Exception:
                pass

    async def _cancel_order_async(self, order_id: str) -> Dict[str, Any]:
        """Cancel order by ID."""
        session = self._create_session()

        try:
            cancel_params = {
                "symbol": self.symbol,
                "orderId": order_id,
            }

            response = await self._signed_request(
                session=session,
                method="DELETE",
                path="/fapi/v1/order",
                params=cancel_params,
            )

            return response

        finally:
            try:
                await session.aclose()
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────
    # Internal: State Management
    # ─────────────────────────────────────────────────────────────

    def _complete(self, latency_ms: float) -> None:
        """Mark execution complete."""
        with self._lock:
            self._state = ExecutorState.COMPLETE
            self._current_order_id = None
            self._metrics["entries_completed"] += 1

            self._entry_latencies.append(latency_ms)
            if len(self._entry_latencies) > 100:
                self._entry_latencies = self._entry_latencies[-100:]
            self._metrics["avg_entry_latency_ms"] = sum(
                self._entry_latencies) / len(self._entry_latencies)

    def _fail(self, error: str) -> None:
        """Mark execution failed."""
        with self._lock:
            self._state = ExecutorState.FAILED
            self._current_order_id = None
            self._metrics["entries_failed"] += 1

        logger.error(f"[SymbolExecutorV2:{self.symbol}] Failed: {error}")
