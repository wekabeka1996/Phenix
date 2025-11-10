"""
FSMP-P1-T02: Order Guardian Service
Dedicated service for TP/SL order cleanup with strict ownership tracking.

Responsibilities:
- Track order ownership (clientOrderId ↔ orderId mapping)
- Register entry and bracket orders with relationships
- Reconcile orphaned brackets on position close/flat transitions
- Handle -2011 (Unknown order) as success
- Rate limiting and safety guards
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from decimal import Decimal
import logging

from .order_ledger import OrderLedger, OrderRecord, OrderRole, OrderStatus

LOG = logging.getLogger(__name__)


@dataclass
class OrderMetadata:
    """Metadata for order registration"""
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    reduce_only: bool = False
    close_position: bool = False


class OrderGuardian:
    """
    Order Guardian: Manages TP/SL cleanup with strict ownership tracking.

    Ensures only our orders are cleaned up, handles race conditions,
    and provides audit trail for all cleanup operations.
    """

    def __init__(self, ledger: OrderLedger, adapter):
        self.ledger = ledger
        self.adapter = adapter

        # Rate limiting for cleanup operations
        self._last_cleanup_ts: Dict[str, float] = {}
        self._cleanup_cooldown_sec = 1.0  # Min time between cleanups per symbol

        # Metrics
        self._metrics = {
            "entries_registered": 0,
            "brackets_registered": 0,
            "reconciles_attempted": 0,
            "orphans_cancelled": 0,
            "cleanup_errors": 0,
            "race_condition_prevented": 0,
        }

    async def register_entry(self, response: Dict[str, Any], metadata: OrderMetadata) -> None:
        """
        Register entry order after successful placement.

        Args:
            response: Adapter response with orderId and clientOrderId
            metadata: Order metadata
        """
        try:
            order_id = str(response.get("orderId", ""))
            client_order_id = response.get("clientOrderId", "")

            if not order_id or not client_order_id:
                LOG.warning(
                    "[GUARD] register_entry: missing orderId or clientOrderId in response")
                return

            record = OrderRecord(
                order_id=order_id,
                client_order_id=client_order_id,
                symbol=metadata.symbol,
                side=metadata.side,
                order_type=metadata.order_type,
                status=OrderStatus.ACTIVE,  # Assume ACKed since we got response
                role=OrderRole.ENTRY
            )

            self.ledger.register_order(record)
            self._metrics["entries_registered"] += 1

            LOG.info("[GUARD] Entry registered", extra={
                "symbol": metadata.symbol,
                "role": "ENTRY",
                "orderId": order_id,
                "clientOrderId": client_order_id,
                "action": "register",
                "reason": "entry_placed"
            })

        except Exception as e:
            LOG.error(f"[GUARD] Failed to register entry: {e}")
            self._metrics["cleanup_errors"] += 1

    async def register_bracket(self, response: Dict[str, Any], role: str, entry_client_id: str) -> None:
        """
        Register bracket order (SL/TP) with link to parent entry.

        Args:
            response: Adapter response with orderId and clientOrderId
            role: "SL" or "TP"
            entry_client_id: Parent entry order's clientOrderId
        """
        try:
            order_id = str(response.get("orderId", ""))
            client_order_id = response.get("clientOrderId", "")

            if not order_id or not client_order_id:
                LOG.warning(
                    "[GUARD] register_bracket: missing orderId or clientOrderId in response")
                return

            # Get entry order to copy metadata
            entry_record = self.ledger.get_order_by_client_id(entry_client_id)
            if not entry_record:
                LOG.warning(
                    f"[GUARD] register_bracket: entry order {entry_client_id} not found in ledger")
                return

            record = OrderRecord(
                order_id=order_id,
                client_order_id=client_order_id,
                symbol=entry_record.symbol,
                side=response.get("side", entry_record.side),
                order_type=response.get("type", "STOP_MARKET"),
                status=OrderStatus.ACTIVE,
                role=OrderRole(role),
                entry_client_id=entry_client_id
            )

            self.ledger.register_order(record)
            self._metrics["brackets_registered"] += 1

            LOG.info("[GUARD] Bracket registered", extra={
                "symbol": entry_record.symbol,
                "role": role,
                "orderId": order_id,
                "clientOrderId": client_order_id,
                "entryClientId": entry_client_id,
                "action": "register",
                "reason": "bracket_placed"
            })

        except Exception as e:
            LOG.error(f"[GUARD] Failed to register bracket: {e}")
            self._metrics["cleanup_errors"] += 1

    async def reconcile_symbol(self, symbol: str) -> None:
        """
        Reconcile orders for symbol: cancel orphaned brackets if no position.

        Called on DEC:CLOSE execution and FLAT state transitions.

        Args:
            symbol: Trading symbol to reconcile
        """
        try:
            self._metrics["reconciles_attempted"] += 1

            # Rate limiting check
            now = time.time()
            last_cleanup = self._last_cleanup_ts.get(symbol, 0)
            if now - last_cleanup < self._cleanup_cooldown_sec:
                LOG.debug(
                    f"[GUARD] Skipping reconcile for {symbol} - rate limited")
                return

            self._last_cleanup_ts[symbol] = now

            # Check if position exists
            position_amt = await self._get_position_amount(symbol)
            has_position = abs(position_amt) >= 1e-10

            if has_position:
                LOG.debug(
                    f"[GUARD] Position exists for {symbol} ({position_amt}), skipping reconcile")
                return

            # No position - check for orphaned brackets
            orphaned_brackets = self.ledger.get_orphaned_brackets(symbol)
            if not orphaned_brackets:
                LOG.debug(f"[GUARD] No orphaned brackets for {symbol}")
                return

            LOG.info(
                f"[GUARD] Found {len(orphaned_brackets)} orphaned brackets for {symbol}, cancelling...")

            # Cancel orphaned brackets
            cancel_tasks = []
            for bracket in orphaned_brackets:
                if bracket.status in [OrderStatus.CANCELLED, OrderStatus.FILLED, OrderStatus.EXPIRED]:
                    continue  # Already terminal

                cancel_tasks.append(self._cancel_order_safe(bracket))

            if cancel_tasks:
                results = await asyncio.gather(*cancel_tasks, return_exceptions=True)

                cancelled_count = 0
                for bracket, result in zip(orphaned_brackets, results):
                    if isinstance(result, Exception):
                        LOG.warning(
                            f"[GUARD] Failed to cancel bracket {bracket.order_id}: {result}")
                        self._metrics["cleanup_errors"] += 1
                    else:
                        cancelled_count += 1
                        self._metrics["orphans_cancelled"] += 1

                        LOG.info("[GUARD] Orphan cancelled", extra={
                            "symbol": symbol,
                            "role": bracket.role.value,
                            "orderId": bracket.order_id,
                            "clientOrderId": bracket.client_order_id,
                            "entryClientId": bracket.entry_client_id,
                            "action": "cancel",
                            "reason": "orphaned_no_position"
                        })

                LOG.info(
                    f"[GUARD] Reconcile complete for {symbol}: cancelled {cancelled_count} orphans")

        except Exception as e:
            LOG.error(f"[GUARD] Reconcile failed for {symbol}: {e}")
            self._metrics["cleanup_errors"] += 1

    async def _get_position_amount(self, symbol: str) -> float:
        """Get current position amount for symbol"""
        try:
            positions = await self.adapter.get_open_positions()
            # Convert to dict if needed
            positions_list = [
                p.to_dict() if hasattr(p, 'to_dict') else (
                    p.__dict__ if not isinstance(p, dict) else p)
                for p in positions
            ]

            pos = next(
                (p for p in positions_list if p.get("symbol") == symbol), None
            )
            if pos:
                # Support both 'positionAmt' and 'position_amount'
                return float(pos.get("position_amount") or pos.get("positionAmt") or 0)
            return 0.0
        except Exception as e:
            LOG.warning(f"[GUARD] Failed to get position for {symbol}: {e}")
            return 0.0  # Assume no position on error

    async def _cancel_order_safe(self, order_record: OrderRecord) -> bool:
        """
        Cancel order with -2011 absorption and status update.

        Returns True if successfully cancelled or already terminal.
        """
        try:
            # Pre-check: get current order status
            try:
                order_info = await self.adapter.get_order(order_record.symbol, order_record.order_id)
                current_status = order_info.get("status", "").upper()

                # Already terminal?
                if current_status in ["CANCELED", "FILLED", "EXPIRED", "REJECTED"]:
                    LOG.debug(
                        f"[GUARD] Order {order_record.order_id} already {current_status}")
                    self.ledger.update_order_status(
                        order_record.order_id, OrderStatus(current_status))
                    return True

            except Exception as e:
                # Order might not exist (-2011 scenario)
                LOG.debug(
                    f"[GUARD] Pre-check failed for {order_record.order_id}: {e}")

            # Attempt cancellation
            cancel_result = await self.adapter.cancel_order(order_record.symbol, order_record.order_id)

            # Check response
            if cancel_result.get("status") == "CANCELED":
                self.ledger.update_order_status(
                    order_record.order_id, OrderStatus.CANCELLED)
                return True

            # Handle -2011 (Unknown order)
            error_code = cancel_result.get("code")
            if error_code == -2011 or "Unknown order" in cancel_result.get("msg", ""):
                LOG.debug(
                    f"[GUARD] -2011 absorbed for {order_record.order_id}")
                # Assume already cancelled/removed
                self.ledger.update_order_status(
                    order_record.order_id, OrderStatus.CANCELLED)
                return True

            # Other error
            LOG.warning(
                f"[GUARD] Cancel failed for {order_record.order_id}: {cancel_result}")
            return False

        except Exception as e:
            LOG.error(
                f"[GUARD] Exception cancelling {order_record.order_id}: {e}")
            return False

    def get_metrics(self) -> Dict[str, int]:
        """Get guardian metrics"""
        return self._metrics.copy()

    def reset_metrics(self) -> None:
        """Reset metrics counters"""
        for key in self._metrics:
            self._metrics[key] = 0
