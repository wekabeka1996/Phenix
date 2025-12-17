#!/usr/bin/env python3
"""
Aurora Core Main Application

Demonstrates the complete Aurora Core FSM federation with all 5 domains:
- market_data: Receives market ticks from Binance WebSocket
- feature_engineering: Calculates trading features from market data
- risk_management: Assesses risk levels for positions
- position_tracking: Tracks portfolio state and P&L
- decision_making: Generates trade intents based on all inputs

Run with: python apps/reference/main.py
Set LOG_LEVEL environment variable to control logging:
- LOG_LEVEL=DEBUG - Show all messages including debug
- LOG_LEVEL=INFO (default) - Show info, warning, error messages
- LOG_LEVEL=WARNING - Show only warnings and errors
- LOG_LEVEL=ERROR - Show only errors
"""

from apps.reference.bootstrap.preflight import check_hybrid_coherence  # NEW IMPORT
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.fsm import ExecPosFSM
# from apps.reference.domains.snapshot_scheduler.snapshot_scheduler import (
#     SnapshotScheduler,
# )
from apps.reference.domains.account_observer.account_observer import AccountObserver
from apps.reference.domains.account_balance.account_connector import AccountConnector
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.domains.risk_management.risk_management import RiskManagement
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.domains.feature_engineering.feature_engineering import (
    FeatureEngineering,
)
# FSMP-ARCH-01: Import both MarketDataConnector and MarketDataProxy
# The actual class used is determined by feature flag at runtime
from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
from apps.reference.domains.market_data.proxy import MarketDataProxy
# NOTE: FeatureStore DISABLED — synchronous DB writes block tick processing
# from apps.reference.data.feature_store import FeatureStore
from vfoundation.core.protocol import truncate_why
from vfoundation.dr.wal_gc import WALGarbageCollector
from apps.reference.telemetry.alerts import AlertManager
from vfoundation.core.fsm_emit_compat import emit_compat
from vfoundation.core import FSMCore
from vfoundation.core.protocol import Message
import json
import logging
import sys
import time
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from logging.handlers import RotatingFileHandler
import asyncio
import threading
import concurrent.futures

# Add project root to path for imports
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))


def _run_async_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Run the shared asyncio loop in a dedicated thread."""
    asyncio.set_event_loop(loop)
    loop.run_forever()


# Import domain classes

# Import telemetry

# Import config loader


# =============================================================================
# RELIABLE RETRY SCHEDULER (D2 - Plan v1)
# =============================================================================

class RetryScheduler:
    """
    Reliable retry scheduler for EVT:INTENT_DEFERRED events.
    
    Features:
    - Stores deferred intents with retry_key for idempotency
    - Schedules re-emission of original_event after next_allowed_ts
    - Tracks attempt count and drops after max_attempts
    - Emits EVT:INTENT_DROPPED when giving up
    - Default restart behavior: drop all pending (fail-closed)
    
    Compliant with schemas/intent_deferred_v1.json and intent_dropped_v1.json.
    """
    
    def __init__(
        self, 
        fsm: FSMCore, 
        logger: logging.Logger | None = None,
        default_max_attempts: int = 5,
        min_retry_delay_ms: int = 500,
    ):
        self.fsm = fsm
        self.logger = logger or logging.getLogger("RetryScheduler")
        self.default_max_attempts = default_max_attempts
        self.min_retry_delay_ms = min_retry_delay_ms
        
        # Pending deferred intents: retry_key -> deferred payload dict
        self._pending: dict[str, dict[str, Any]] = {}
        
        # Active retry tasks: retry_key -> concurrent future (scheduled on bound loop)
        self._retry_tasks: dict[str, concurrent.futures.Future] = {}
        
        # Lock for thread-safety
        self._lock = threading.Lock()

        # Bound async loop for scheduling retries (must be running)
        self._loop: asyncio.AbstractEventLoop | None = None
        
        self.logger.info("RetryScheduler initialized (default_max_attempts=%d)", default_max_attempts)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Bind scheduler to a running asyncio loop (typically Aurora async loop thread).

        Safe to call multiple times; will schedule any already-pending intents.
        """
        self._loop = loop
        with self._lock:
            pending_keys = list(self._pending.keys())
        for retry_key in pending_keys:
            next_allowed_ts = int(self._pending.get(retry_key, {}).get("next_allowed_ts", 0))
            if next_allowed_ts > 0:
                self._schedule_retry(retry_key, next_allowed_ts)
    
    def register_deferred(self, deferred_payload: dict[str, Any]) -> bool:
        """
        Register a deferred intent for retry.
        
        Args:
            deferred_payload: Dict matching intent_deferred_v1.json schema
            
        Returns:
            True if registered, False if already exists or invalid
        """
        retry_key = deferred_payload.get("retry_key")
        if not retry_key:
            self.logger.warning("RetryScheduler: deferred_payload missing retry_key, ignoring")
            return False
        
        symbol = deferred_payload.get("symbol", "UNKNOWN")
        reason = deferred_payload.get("reason", "unknown")
        next_allowed_ts = deferred_payload.get("next_allowed_ts", 0)
        attempt = deferred_payload.get("attempt", 1)
        max_attempts = deferred_payload.get("max_attempts", self.default_max_attempts)
        original_event = deferred_payload.get("original_event")
        
        if not original_event:
            self.logger.warning("RetryScheduler: deferred_payload missing original_event for %s", retry_key)
            return False
        
        with self._lock:
            # Check if already pending with same key (idempotency)
            if retry_key in self._pending:
                existing = self._pending[retry_key]
                existing_attempt = existing.get("attempt", 1)
                if attempt <= existing_attempt:
                    self.logger.debug(
                        "RetryScheduler: %s already pending (attempt %d >= new %d), ignoring duplicate",
                        retry_key, existing_attempt, attempt
                    )
                    return False
            
            # Store pending
            self._pending[retry_key] = {
                "retry_key": retry_key,
                "symbol": symbol,
                "reason": reason,
                "next_allowed_ts": next_allowed_ts,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "original_event": original_event,
                "why_chain": deferred_payload.get("why_chain", []),
                "created_ts": deferred_payload.get("created_ts", int(time.time() * 1000)),
            }
            
            self.logger.info(
                "RetryScheduler: Registered %s (symbol=%s, reason=%s, attempt=%d/%d, next_ts=%d)",
                retry_key, symbol, reason, attempt, max_attempts, next_allowed_ts
            )
        
        # Schedule retry task
        self._schedule_retry(retry_key, next_allowed_ts)
        return True
    
    def _schedule_retry(self, retry_key: str, next_allowed_ts: int) -> None:
        """Schedule async task to retry after next_allowed_ts."""
        # Cancel existing task if any
        if retry_key in self._retry_tasks:
            old_future = self._retry_tasks.pop(retry_key)
            try:
                old_future.cancel()
            except Exception:
                pass
        
        async def _do_retry():
            # Calculate delay
            now_ms = int(time.time() * 1000)
            delay_ms = max(next_allowed_ts - now_ms, self.min_retry_delay_ms)
            delay_sec = delay_ms / 1000.0
            
            self.logger.debug("RetryScheduler: %s sleeping %.2fs before retry", retry_key, delay_sec)
            await asyncio.sleep(delay_sec)
            
            # Execute retry
            await self._execute_retry(retry_key)

        # Preferred: schedule onto a known running loop (AuroraAsyncLoop thread)
        if self._loop is not None and self._loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(_do_retry(), self._loop)
                self._retry_tasks[retry_key] = fut
                return
            except Exception as e:
                self.logger.error(
                    "RetryScheduler: Failed to schedule %s on bound loop: %r", retry_key, e
                )

        # Fallback: schedule onto current running loop (if any)
        try:
            loop = asyncio.get_running_loop()
            self._retry_tasks[retry_key] = loop.create_task(_do_retry())  # type: ignore[assignment]
            return
        except RuntimeError:
            pass

        # Fail-closed: keep pending but do not silently claim success
        self.logger.error(
            "RetryScheduler: No running asyncio loop bound; %s registered but retry NOT scheduled",
            retry_key,
        )
    
    async def _execute_retry(self, retry_key: str) -> None:
        """Execute retry for a pending deferred intent."""
        with self._lock:
            pending = self._pending.get(retry_key)
            if not pending:
                self.logger.debug("RetryScheduler: %s no longer pending, skip retry", retry_key)
                return
            
            attempt = pending.get("attempt", 1)
            max_attempts = pending.get("max_attempts", self.default_max_attempts)
            symbol = pending.get("symbol", "UNKNOWN")
            original_event = pending.get("original_event", {})
            why_chain = pending.get("why_chain", [])
            created_ts = pending.get("created_ts", 0)
        
        # Check if max attempts exceeded
        if attempt >= max_attempts:
            self._drop_intent(
                retry_key=retry_key,
                symbol=symbol,
                drop_reason="MAX_ATTEMPTS_EXCEEDED",
                original_reason=pending.get("reason", "unknown"),
                attempt=attempt,
                max_attempts=max_attempts,
                original_event=original_event,
                why_chain=why_chain + ["max_attempts_exceeded"],
                created_ts=created_ts,
            )
            return
        
        # Re-emit original event
        event_name = original_event.get("event_name", "")
        payload_min = original_event.get("payload_min", {})
        
        if not event_name or not payload_min:
            self.logger.error(
                "RetryScheduler: %s has invalid original_event, dropping",
                retry_key
            )
            self._drop_intent(
                retry_key=retry_key,
                symbol=symbol,
                drop_reason="STALE_INTENT",
                original_reason=pending.get("reason", "unknown"),
                attempt=attempt,
                max_attempts=max_attempts,
                original_event=original_event,
                why_chain=why_chain + ["invalid_original_event"],
                created_ts=created_ts,
            )
            return
        
        # Build re-emit message
        # Parse event_name: "EVT:MR_SIGNAL_PRODUCED" -> op="EVT", verb="MR_SIGNAL_PRODUCED"
        if ":" in event_name:
            op, verb = event_name.split(":", 1)
        else:
            op, verb = "EVT", event_name
        
        retry_msg = Message(
            op=op,
            verb=verb,
            src="retry_scheduler",
            dst="decision_making",
            rid=payload_min.get("rid", f"retry_{retry_key}_{attempt}"),
            pld=payload_min,
            why=f"retry_attempt_{attempt}_of_{max_attempts}",
        )
        
        self.logger.info(
            "RetryScheduler: Re-emitting %s for %s (attempt %d/%d)",
            event_name, symbol, attempt, max_attempts
        )
        
        # Remove from pending (will be re-added if deferred again)
        with self._lock:
            self._pending.pop(retry_key, None)
            self._retry_tasks.pop(retry_key, None)
        
        # Emit
        await emit_compat(self.fsm, retry_msg, logger=self.logger)
    
    def _drop_intent(
        self,
        retry_key: str,
        symbol: str,
        drop_reason: str,
        original_reason: str,
        attempt: int,
        max_attempts: int,
        original_event: dict,
        why_chain: list,
        created_ts: int,
    ) -> None:
        """Drop a deferred intent and emit EVT:INTENT_DROPPED."""
        dropped_ts = int(time.time() * 1000)
        
        drop_payload = {
            "retry_key": retry_key,
            "symbol": symbol,
            "drop_reason": drop_reason,
            "original_reason": original_reason,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "original_event": original_event,
            "why_chain": why_chain,
            "created_ts": created_ts,
            "dropped_ts": dropped_ts,
        }
        
        drop_msg = Message(
            op="EVT",
            verb="INTENT_DROPPED",
            src="retry_scheduler",
            dst="*",
            rid=f"drop_{retry_key}",
            pld=drop_payload,
            why=f"dropped_{drop_reason}",
        )
        
        self.logger.warning(
            "RetryScheduler: Dropping %s (reason=%s, attempts=%d/%d)",
            retry_key, drop_reason, attempt, max_attempts
        )
        
        # Remove from pending
        with self._lock:
            self._pending.pop(retry_key, None)
            self._retry_tasks.pop(retry_key, None)
        
        # Emit synchronously (called from async context, but emit_compat handles both)
        try:
            self.fsm.emit(drop_msg.op + ":" + drop_msg.verb, drop_msg.pld)
        except Exception as e:
            self.logger.error("RetryScheduler: Failed to emit INTENT_DROPPED: %s", e)
    
    def cancel_pending(self, retry_key: str) -> bool:
        """Cancel a pending deferred intent."""
        with self._lock:
            if retry_key not in self._pending:
                return False
            
            pending = self._pending.pop(retry_key)
            symbol = pending.get("symbol", "UNKNOWN")
        
        # Cancel task
        if retry_key in self._retry_tasks:
            task = self._retry_tasks.pop(retry_key)
            if not task.done():
                task.cancel()
        
        self.logger.info("RetryScheduler: Cancelled %s for %s", retry_key, symbol)
        return True
    
    def clear_all_pending(self, emit_dropped: bool = True, drop_reason: str = "RESTART_NO_PERSISTENCE") -> int:
        """
        Clear all pending deferred intents (fail-closed on restart).
        
        Args:
            emit_dropped: If True, emit EVT:INTENT_DROPPED for each
            drop_reason: Reason to use in dropped events
            
        Returns:
            Number of intents cleared
        """
        with self._lock:
            pending_copy = dict(self._pending)
            self._pending.clear()
            
            # Cancel all tasks
            for task in self._retry_tasks.values():
                if not task.done():
                    task.cancel()
            self._retry_tasks.clear()
        
        if not pending_copy:
            return 0
        
        self.logger.warning(
            "RetryScheduler: Clearing %d pending intents (reason=%s)",
            len(pending_copy), drop_reason
        )
        
        if emit_dropped:
            dropped_ts = int(time.time() * 1000)
            for retry_key, pending in pending_copy.items():
                drop_payload = {
                    "retry_key": retry_key,
                    "symbol": pending.get("symbol", "UNKNOWN"),
                    "drop_reason": drop_reason,
                    "original_reason": pending.get("reason", "unknown"),
                    "attempt": pending.get("attempt", 1),
                    "max_attempts": pending.get("max_attempts", self.default_max_attempts),
                    "original_event": pending.get("original_event", {}),
                    "why_chain": pending.get("why_chain", []) + [drop_reason.lower()],
                    "created_ts": pending.get("created_ts", 0),
                    "dropped_ts": dropped_ts,
                }
                try:
                    self.fsm.emit("EVT:INTENT_DROPPED", drop_payload)
                except Exception as e:
                    self.logger.error("RetryScheduler: Failed to emit INTENT_DROPPED for %s: %s", retry_key, e)
        
        return len(pending_copy)
    
    def get_pending_count(self) -> int:
        """Get count of pending deferred intents."""
        with self._lock:
            return len(self._pending)
    
    def get_pending_for_symbol(self, symbol: str) -> list[str]:
        """Get retry_keys for pending intents on a symbol."""
        with self._lock:
            return [k for k, v in self._pending.items() if v.get("symbol") == symbol]


class AuroraBridge:
    """
    Bridge component that handles TRADE_INTENT_PROPOSED → CMD:OPEN conversion
    with portfolio freshness gate to prevent race conditions.
    """

    def __init__(self, fsm: FSMCore, config: dict[str, Any], logger: logging.Logger | None = None):
        self.fsm = fsm
        self.config = config
        self.logger = logger or logging.getLogger("AuroraBridge")

        # Portfolio freshness state
        self._last_portfolio: dict[str, Any] = {}
        self._last_portfolio_ts = 0

        # Deferred intents queue (key: idempotent_key or rid, value: intent Message)
        self._deferred: dict[str, Message] = {}
        self._deferred_tries: dict[str, int] = {}

        # QoS state for symbol cooldowns (from DecisionMaking deferrals)
        self._qos_next_allowed_ts_per_symbol: dict[str, int] = {}

        # Configuration
        position_tracking_config = config.get("position_tracking", {})
        self._ttl_sec = int(position_tracking_config.get(
            "positions_stale_ttl_sec", 5))
        self._retry_delay_sec = 0.5
        self._max_retries = 2
        
        # D2: Initialize reliable retry scheduler
        retry_config = config.get("bridge", {}).get("retry_scheduler", {})
        self._retry_scheduler = RetryScheduler(
            fsm=fsm,
            logger=self.logger,
            default_max_attempts=retry_config.get("max_attempts", 5),
            min_retry_delay_ms=retry_config.get("min_retry_delay_ms", 500),
        )

        # Register event listeners
        # Note: We register global handlers that properly handle async calls
        # instead of registering async methods directly (FSMCore calls listeners synchronously)
        self.fsm.listen("EVT:TRADE_INTENT_PROPOSED", on_trade_intent_proposed)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED",
                        on_portfolio_state_updated)
        self.fsm.listen("EVT:INTENT_DEFERRED", on_intent_deferred)
        
        self.logger.info(
            "AuroraBridge initialized (ttl_sec=%d, retry_scheduler_max_attempts=%d)",
            self._ttl_sec, self._retry_scheduler.default_max_attempts
        )
    
    @property
    def retry_scheduler(self) -> RetryScheduler:
        """Get the retry scheduler instance."""
        return self._retry_scheduler
    
    def clear_pending_on_restart(self) -> int:
        """
        D6: Clear all pending deferred intents on restart (fail-closed default).
        
        Emits EVT:INTENT_DROPPED with reason=RESTART_NO_PERSISTENCE for each.
        Call this during startup to ensure clean state.
        
        Returns:
            Number of intents dropped
        """
        return self._retry_scheduler.clear_all_pending(
            emit_dropped=True,
            drop_reason="RESTART_NO_PERSISTENCE"
        )

    def _is_portfolio_fresh(self) -> bool:
        """Check if portfolio data is fresh (within TTL)."""
        if not self._last_portfolio_ts:
            return False
        now_ms = int(time.time() * 1000)
        return (now_ms - self._last_portfolio_ts) <= self._ttl_sec * 1000

    def _is_qos_allowed(self, symbol: str) -> bool:
        """Check if QoS allows trading for the given symbol."""
        if not symbol:
            return True  # Allow if no symbol specified

        next_allowed_ts = self._qos_next_allowed_ts_per_symbol.get(symbol, 0)
        current_ts = int(time.time() * 1000)
        return current_ts >= next_allowed_ts

    async def on_portfolio_state_updated(self, event: Message) -> None:
        """Handle fresh portfolio updates and flush deferred intents."""
        self._last_portfolio = event.pld or {}
        self._last_portfolio_ts = int(
            self._last_portfolio.get("positions_last_ts_ms", 0)
        ) or int(time.time() * 1000)

        # Flush any deferred intents now that portfolio is fresh
        await self._flush_deferred_if_fresh()

    async def on_intent_deferred(self, event: Message) -> None:
        """Handle INTENT_DEFERRED events from DecisionMaking QoS."""
        symbol = event.pld.get("symbol")
        reason = event.pld.get("reason", "unknown")
        next_allowed_ts = event.pld.get("next_allowed_ts", 0)

        if not symbol:
            self.logger.warning(
                f"BRIDGE: INTENT_DEFERRED missing symbol: {event.pld}")
            return

        # Register QoS cooldown
        self._qos_next_allowed_ts_per_symbol[symbol] = next_allowed_ts

        # FIX: Ignore PORTFOLIO_STALE reason to prevent infinite loop
        # PORTFOLIO_STALE is handled by local retry task in on_trade_intent_proposed
        if reason == "PORTFOLIO_STALE":
            return

        self.logger.info(
            f"BRIDGE: QoS defer registered for {symbol} until {next_allowed_ts} (reason: {reason})")

        # Increment metrics (optional)
        try:
            from apps.reference.telemetry.metrics import inc_bridge_deferred
            inc_bridge_deferred(reason, symbol)
        except ImportError:
            pass  # Metrics unavailable

        # Schedule retry when QoS allows
        import asyncio

        async def _retry_after_qos():
            # Wait until QoS allows
            current_ts = int(time.time() * 1000)
            if next_allowed_ts > current_ts:
                delay_sec = (next_allowed_ts - current_ts) / 1000.0
                await asyncio.sleep(delay_sec)

            # Check if still blocked by QoS
            if not self._is_qos_allowed(symbol):
                self.logger.info(
                    f"BRIDGE: {symbol} still QoS blocked after defer wait")
                return

            # Re-emit the original signal to trigger new decision
            # This will cause DecisionMaking to re-evaluate with fresh data
            original_context = event.pld.get("original_context", {})
            if original_context:
                # Re-emit features to trigger new decision cycle
                features_msg = Message(
                    op="EVT",
                    verb="FEATURES_CALCULATED",
                    src="bridge",
                    dst="decision_making",
                    rid=event.rid,
                    pld=original_context.get("features", {}),
                    why="qos_defer_retry"
                )
                await emit_compat(self.fsm, features_msg, logger=self.logger)
                self.logger.info(
                    f"BRIDGE: Re-triggered decision cycle for {symbol} after QoS defer")
            else:
                self.logger.warning(
                    f"BRIDGE: No original context to retry {symbol} QoS defer")

        asyncio.create_task(_retry_after_qos())

    async def on_trade_intent_proposed(self, event: Message) -> None:
        """
        Handle trade intent with QoS and portfolio freshness gates.

        Checks QoS first, then portfolio freshness.
        If QoS blocks → defer intent
        If portfolio stale → defer intent
        If both OK → convert immediately to CMD:OPEN
        """
        symbol = event.pld.get("instrument") or event.pld.get("symbol") or ""

        # Check for forbidden LIMIT entry
        order_details = event.pld.get("order", {})
        if order_details.get("order_type") == "LIMIT":
            self.logger.error(
                "BRIDGE: LIMIT entry forbidden. Only MARKET entry allowed."
            )
            return

        # Check QoS first
        if not self._is_qos_allowed(symbol):
            # QoS blocked - defer the intent
            key = event.pld.get(
                "idempotent_key") or event.rid or str(time.time())
            self._deferred[key] = event
            self._deferred_tries[key] = self._deferred_tries.get(key, 0) + 1

            # Emit deferred event
            defer_evt = Message(
                op="EVT",
                verb="INTENT_DEFERRED",
                src="bridge",
                dst="*",
                rid=event.rid,
                pld={
                    "reason": "QOS_COOLDOWN",
                    "symbol": symbol,
                    "idempotent_key": event.pld.get("idempotent_key"),
                    "next_allowed_ts": self._qos_next_allowed_ts_per_symbol.get(symbol, 0),
                },
                why="bridge_qoS_blocked",
            )
            await emit_compat(self.fsm, defer_evt, logger=self.logger)

            self.logger.info(
                f"BRIDGE: Deferred TRADE_INTENT_PROPOSED rid={event.rid} for {symbol} "
                f"(QoS blocked, try #{self._deferred_tries[key]})"
            )

            # Schedule QoS retry
            import asyncio

            async def _retry_after_qos():
                await asyncio.sleep(1.0)  # Check every second
                if self._is_qos_allowed(symbol):
                    # QoS now allows - try to process
                    await self._flush_deferred_if_fresh()
                else:
                    # Still blocked - reschedule
                    asyncio.create_task(_retry_after_qos())

            asyncio.create_task(_retry_after_qos())
            return

        # QoS OK - check portfolio freshness
        if self._is_portfolio_fresh():
            self._dispatch_open(event)
            return

        # Portfolio stale - defer the intent
        key = event.pld.get("idempotent_key") or event.rid or str(time.time())
        self._deferred[key] = event
        self._deferred_tries[key] = self._deferred_tries.get(key, 0) + 1

        # Emit deferred event
        defer_evt = Message(
            op="EVT",
            verb="INTENT_DEFERRED",
            src="bridge",
            dst="*",
            rid=event.rid,
            pld={
                "reason": "PORTFOLIO_STALE",
                "symbol": symbol,
                "idempotent_key": event.pld.get("idempotent_key"),
            },
            why="bridge_waits_fresh_portfolio",
        )
        await emit_compat(self.fsm, defer_evt, logger=self.logger)

        self.logger.info(
            f"BRIDGE: Deferred TRADE_INTENT_PROPOSED rid={event.rid} for {symbol} "
            f"(portfolio stale, try #{self._deferred_tries[key]})"
        )

        # Schedule retry after delay
        import asyncio

        async def _retry_once():
            await asyncio.sleep(self._retry_delay_sec)
            # Check if we should drop due to timeout
            if self._deferred_tries.get(key, 0) >= self._max_retries:
                # Drop after max retries
                drop_evt = Message(
                    op="EVT",
                    verb="INTENT_DROPPED",
                    src="bridge",
                    dst="*",
                    rid=event.rid,
                    pld={
                        "reason": "STALE_PORTFOLIO_TIMEOUT",
                        "symbol": symbol,
                        "idempotent_key": event.pld.get("idempotent_key"),
                    },
                    why="bridge_drop_after_retries",
                )
                await emit_compat(self.fsm, drop_evt, logger=self.logger)
                self._deferred.pop(key, None)
                self._deferred_tries.pop(key, None)
                self.logger.info(
                    f"BRIDGE: Dropped deferred intent after {self._max_retries} retries: {key}"
                )
                return

            # Otherwise, try to flush if portfolio became fresh
            await self._flush_deferred_if_fresh()

        asyncio.create_task(_retry_once())

    async def _flush_deferred_if_fresh(self) -> None:
        """Flush deferred intents if portfolio is now fresh and QoS allows."""
        if not self._is_portfolio_fresh():
            return

        dropped_count = 0
        processed_count = 0

        for key, intent_msg in list(self._deferred.items()):
            symbol = intent_msg.pld.get(
                "instrument") or intent_msg.pld.get("symbol") or ""

            # Check QoS for this symbol
            if not self._is_qos_allowed(symbol):
                continue  # Still QoS blocked, keep deferred

            tries = self._deferred_tries.get(key, 0)
            if tries > self._max_retries:
                # Drop after max retries
                drop_evt = Message(
                    op="EVT",
                    verb="INTENT_DROPPED",
                    src="bridge",
                    dst="*",
                    rid=intent_msg.rid,
                    pld={
                        "reason": "STALE_PORTFOLIO_TIMEOUT",
                        "symbol": symbol,
                        "idempotent_key": intent_msg.pld.get("idempotent_key"),
                    },
                    why="bridge_drop_after_retries",
                )
                await emit_compat(self.fsm, drop_evt, logger=self.logger)
                self._deferred.pop(key, None)
                self._deferred_tries.pop(key, None)
                dropped_count += 1
                continue

            # Process the deferred intent
            self._dispatch_open(intent_msg)
            self._deferred.pop(key, None)
            self._deferred_tries.pop(key, None)
            processed_count += 1

            # Increment retry metric if this was retried
            if tries > 1:
                symbol = intent_msg.pld.get(
                    "instrument") or intent_msg.pld.get("symbol")
                try:
                    from apps.reference.telemetry.metrics import inc_bridge_retry
                    inc_bridge_retry(symbol)
                except ImportError:
                    pass  # Metrics unavailable

        if dropped_count > 0 or processed_count > 0:
            self.logger.info(
                f"BRIDGE: Flushed deferred intents - processed: {processed_count}, dropped: {dropped_count}"
            )

    def _dispatch_open(self, intent_msg: Message) -> None:
        """Convert TRADE_INTENT_PROPOSED to CMD:OPEN and dispatch."""
        self.logger.info(
            f"BRIDGE: Converting TRADE_INTENT_PROPOSED rid={intent_msg.rid} for {intent_msg.pld.get('instrument', 'unknown')} to CMD:OPEN"
        )

        # Extract order details from nested structure
        order_details = intent_msg.pld.get("order", {})
        # Accept multiple upstream shapes (legacy + MR handler)
        order_type_raw = order_details.get("order_type") or order_details.get("type")
        price_ref = (
            order_details.get("price_ref")
            or intent_msg.pld.get("price_ref")
            or intent_msg.pld.get("entry_price")
            or order_details.get("price")
            or intent_msg.pld.get("price")
        )

        command_payload = {
            # Pass through request ID for tracing
            "rid": intent_msg.pld.get("rid"),
            # Map 'instrument' to 'symbol'
            "symbol": intent_msg.pld.get("instrument"),
            "side": intent_msg.pld.get("side"),
            # Get qty from order.qty (as string)
            "qty": order_details.get("qty"),
            "price": order_details.get(
                "price"
            ),  # Get price from order.price (as string)
            "order_type": order_type_raw or "LIMIT",
            "tif": "GTC",  # Good-Till-Cancel
            "idempotent_key": intent_msg.pld.get(
                "idempotent_key"
            ),  # Pass through for deduplication
            "price_ref": price_ref,  # Pass current market price for min_notional/exposure checks
            # TP/SL Intent Data Propagation (PHASE A2 fix)
            "stop_price": intent_msg.pld.get("stop_price"),
            "target_price": intent_msg.pld.get("target_price"),
            "sl_pct": intent_msg.pld.get("sl_pct"),
        }

        # XAI instrumentation: exec_open_enter
        from vfoundation.core.why_codes import WhyCode, format_why_with_details
        exposure_reservation_state = "unknown"  # TODO: get actual reservation state
        self.logger.info(
            format_why_with_details(
                WhyCode.SUCCESS_ORDER_PLACED,  # closest match for execution entry
                f"rid={command_payload.get('rid')} symbol={command_payload.get('symbol')} side={command_payload.get('side')} qty={command_payload.get('qty')} clientOrderId={command_payload.get('idempotent_key')} exposure_reservation_state={exposure_reservation_state} why=exec_open_enter"
            )
        )

        self.logger.debug(
            f"BRIDGE: CMD:OPEN payload being sent: {command_payload}")

        # Preserve XAI chain: pass full WHY chain in data_ref.
        # SSOT: Message.data_ref must be list[str]; some upstreams still send pld["why"] as str.
        event_why_chain: list[str] = []
        pld_why = intent_msg.pld.get("why", [])
        if isinstance(intent_msg.data_ref, list) and intent_msg.data_ref:
            event_why_chain = [str(x) for x in intent_msg.data_ref if x is not None]
            # If upstream also provided a human WHY string (e.g., MR), preserve it as an additional ref.
            if isinstance(pld_why, str) and pld_why.strip() and pld_why.strip() not in event_why_chain:
                event_why_chain.append(pld_why.strip())
        else:
            if isinstance(pld_why, list):
                event_why_chain = [str(x) for x in pld_why if x is not None]
            elif isinstance(pld_why, str) and pld_why.strip():
                event_why_chain = [pld_why.strip()]

        # Pick a safe short WHY (<=80 chars). Prefer a known short code, else truncate.
        default_why = "exec_open_enter"
        bridge_why = default_why
        if isinstance(event_why_chain, list) and event_why_chain:
            candidate = str(event_why_chain[0])
            bridge_why = truncate_why(candidate) or default_why

        # Create Message for CMD:OPEN
        open_command = Message(
            op="CMD",
            verb="OPEN",
            src="decision_making",  # Source is decision_making
            dst="execution_position",
            parent_span_id=intent_msg.span_id,  # Link to parent event for tracing
            intent="COMMAND",  # v2.2: Classify as command
            why=bridge_why,  # Preserve first WHY for backward compatibility
            pld=command_payload,
            data_ref=event_why_chain,  # Full WHY chain (validated list[str])
        )

        self.logger.info(
            f"BRIDGE: Dispatched CMD:OPEN with rid={open_command.rid}, parent_span={intent_msg.span_id}"
        )

        # Handle the command directly with execution_position FSM
        if execution_position is not None:
            result = execution_position.handle(open_command)
            if result:
                self.logger.info(
                    f"BRIDGE: Execution FSM processed CMD:OPEN, result: {result.op}:{result.verb}"
                )
                # Emit the result synchronously via fsm.emit
                try:
                    event_name = f"{result.op}:{result.verb}"
                    self.fsm.emit(event_name, result.pld or {}, result.why or "bridge_result", result.data_ref)
                except Exception as e:
                    self.logger.error(f"BRIDGE: Error emitting result: {e}")
                
                if result.op == "ERR":
                    self.logger.error(
                        f"BRIDGE: Execution rejected - why={result.why}, pld={result.pld}"
                    )
        else:
            self.logger.error("BRIDGE: execution_position FSM not initialized")

    # ========== SYNCHRONOUS VERSIONS OF HANDLERS ==========
    
    def on_trade_intent_proposed_sync(self, event: Message) -> None:
        """
        Synchronous handler for trade intent.
        Checks QoS and portfolio freshness, dispatches CMD:OPEN if OK.
        If portfolio stale, defers intent for retry on next portfolio update.
        """
        symbol = event.pld.get("instrument") or event.pld.get("symbol") or ""
        rid = event.pld.get("rid", "unknown")
        
        # Check for forbidden LIMIT entry
        order_details = event.pld.get("order", {})
        if order_details.get("order_type") == "LIMIT":
            self.logger.error("BRIDGE: LIMIT entry forbidden. Only MARKET entry allowed.")
            return
        
        # Check QoS first
        if not self._is_qos_allowed(symbol):
            self.logger.info(f"BRIDGE: QoS blocked for {symbol}, skipping")
            return
        
        # Check portfolio freshness
        if not self._is_portfolio_fresh():
            # Defer intent for retry on next portfolio update (sync mode)
            idempotent_key = f"{symbol}_{rid}"
            if idempotent_key not in self._deferred:
                self._deferred[idempotent_key] = event
                self._deferred_tries[idempotent_key] = 0
                self.logger.info(f"BRIDGE: Portfolio stale for {symbol}, deferring intent (rid={rid})")
            else:
                self.logger.debug(f"BRIDGE: Intent already deferred for {symbol} (rid={rid})")
            return
        
        # Both OK - dispatch
        self._dispatch_open(event)
    
    def on_portfolio_state_updated_sync(self, event: Message) -> None:
        """Synchronous handler for portfolio updates. Flushes deferred intents."""
        self._last_portfolio = event.pld or {}
        self._last_portfolio_ts = int(
            self._last_portfolio.get("positions_last_ts_ms", 0)
        ) or int(time.time() * 1000)
        
        # Flush deferred intents now that portfolio is fresh
        if self._deferred:
            self.logger.info(f"BRIDGE: Portfolio updated, flushing {len(self._deferred)} deferred intents")
            to_remove = []
            for key, deferred_event in list(self._deferred.items()):
                self._deferred_tries[key] = self._deferred_tries.get(key, 0) + 1
                if self._deferred_tries[key] > self._max_retries:
                    self.logger.warning(f"BRIDGE: Deferred intent {key} exceeded max retries, dropping")
                    to_remove.append(key)
                    continue
                    
                symbol = deferred_event.pld.get("instrument") or deferred_event.pld.get("symbol") or ""
                if not self._is_qos_allowed(symbol):
                    self.logger.info(f"BRIDGE: Deferred intent {key} still QoS blocked, keeping")
                    continue
                
                # Dispatch and mark for removal
                self._dispatch_open(deferred_event)
                to_remove.append(key)
            
            # Clean up processed intents
            for key in to_remove:
                self._deferred.pop(key, None)
                self._deferred_tries.pop(key, None)
    
    def on_intent_deferred_sync(self, event: Message) -> None:
        """
        Synchronous handler for intent deferral.
        
        D2: Supports both legacy format and intent_deferred_v1.json compliant format.
        If payload has retry_key and original_event, uses RetryScheduler.
        Otherwise, falls back to legacy QoS cooldown registration.
        """
        pld = event.pld or {}
        symbol = pld.get("symbol")
        reason = pld.get("reason", "unknown")
        next_allowed_ts = pld.get("next_allowed_ts", 0)
        
        if not symbol:
            self.logger.warning(f"BRIDGE: INTENT_DEFERRED missing symbol: {pld}")
            return
        
        # Register QoS cooldown (always, for both legacy and v1)
        self._qos_next_allowed_ts_per_symbol[symbol] = next_allowed_ts
        
        # D2: Check if v1-compliant payload with retry_key and original_event
        retry_key = pld.get("retry_key")
        original_event = pld.get("original_event")
        
        if retry_key and original_event:
            # V1-compliant: use RetryScheduler for reliable retry
            deferred_payload = {
                "retry_key": retry_key,
                "symbol": symbol,
                "reason": reason,
                "next_allowed_ts": next_allowed_ts,
                "attempt": pld.get("attempt", 1),
                "max_attempts": pld.get("max_attempts", 5),
                "original_event": original_event,
                "why_chain": pld.get("why_chain", []),
                "created_ts": pld.get("created_ts", int(time.time() * 1000)),
            }
            registered = self._retry_scheduler.register_deferred(deferred_payload)
            if registered:
                self.logger.info(
                    f"BRIDGE: V1 deferred registered via RetryScheduler for {symbol} "
                    f"(retry_key={retry_key}, reason={reason})"
                )
            else:
                self.logger.debug(
                    f"BRIDGE: V1 deferred already pending or invalid for {symbol} (retry_key={retry_key})"
                )
        else:
            # Legacy format: just log QoS registration (no reliable retry)
            self.logger.info(
                f"BRIDGE: Legacy QoS defer registered for {symbol} until {next_allowed_ts} (reason={reason})"
            )


# Global bridge instance for backward compatibility
_bridge_instance: AuroraBridge | None = None


def on_trade_intent_proposed(event: Message) -> None:
    """Global handler for TRADE_INTENT_PROPOSED events - delegates to bridge."""
    global _bridge_instance
    LOG.info(f"BRIDGE_HANDLER: on_trade_intent_proposed called for {event.pld.get('instrument', 'unknown')}")
    if _bridge_instance is not None:
        try:
            # Call synchronous method directly
            _bridge_instance.on_trade_intent_proposed_sync(event)
            LOG.info("BRIDGE_HANDLER: Task completed")
        except Exception as e:
            LOG.error(f"BRIDGE_HANDLER: Error: {e}")
            import traceback
            LOG.error(traceback.format_exc())
    else:
        LOG.error(
            "BRIDGE: No bridge instance available for on_trade_intent_proposed")


def on_portfolio_state_updated(event: Message) -> None:
    """Global handler for PORTFOLIO_STATE_UPDATED events - delegates to bridge."""
    global _bridge_instance
    if _bridge_instance is not None:
        try:
            # Call synchronous method directly
            _bridge_instance.on_portfolio_state_updated_sync(event)
        except Exception as e:
            LOG.error(f"BRIDGE: Error in on_portfolio_state_updated: {e}")
    else:
        LOG.error(
            "BRIDGE: No bridge instance available for on_portfolio_state_updated")


def on_intent_deferred(event: Message) -> None:
    """Global handler for INTENT_DEFERRED events - delegates to bridge."""
    global _bridge_instance
    if _bridge_instance is not None:
        try:
            # Call synchronous method directly
            _bridge_instance.on_intent_deferred_sync(event)
        except Exception as e:
            LOG.error(f"BRIDGE: Error in on_intent_deferred: {e}")
    else:
        LOG.error("BRIDGE: No bridge instance available for on_intent_deferred")
# Local FSMCore mock has been removed. The real FSMCore from vfoundation is now used.


# JSON Formatter for structured logging
class JSONFormatter(logging.Formatter):
    """JSON formatter for structured event chain logging."""

    def format(self, record):
        # Extract extra fields from record
        extra_fields = {}
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                    "message",
                ]:
                    extra_fields[key] = value

        # Create structured log entry
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields
        log_entry.update(extra_fields)

        return json.dumps(log_entry, default=str, ensure_ascii=False)


# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()


def _perform_alert_checks(alert_manager: AlertManager, wal_dir: Path, config: dict) -> None:
    """Perform periodic system health checks and raise alerts if needed."""
    # Check WAL size
    try:
        wal_files = list(wal_dir.glob("*.wal"))
        total_wal_size_mb = sum(
            f.stat().st_size for f in wal_files) / (1024 * 1024)
        alert_manager.check_wal_size(total_wal_size_mb)
    except Exception as e:
        LOG.error(f"Error checking WAL size: {e}")

    # Check circuit breaker status (placeholder - would need actual CB state)
    # For now, just check if we have any active alerts as proxy
    alert_stats = alert_manager.get_alert_stats()
    if alert_stats["active_alerts"] > 5:
        # Assume CB active if many alerts
        alert_manager.check_circuit_breaker(True, 300)
    
    # Check entropy spike (NEW)
    # Note: entropy_monitor is initialized in initialize_domains()
    # This function is called from guardian_loop which runs after domains are initialized
    try:
        # Use globals().get() to safely access entropy_monitor
        em = globals().get('entropy_monitor')
        if em is not None:
            spike_detected, reason = em.detect_spike()
            if spike_detected:
                alert_manager.trigger_alert(
                    severity="CRITICAL",
                    message=f"System anomaly detected: {reason}",
                    context=em.get_metrics()
                )
                LOG.critical(f"🚨 ENTROPY SPIKE: {reason}")
    except Exception as e:
        LOG.error(f"Error checking entropy: {e}")

    # Check risk gate (placeholder - would need actual risk metrics)
    # This would typically come from risk_management domain
    # alert_manager.check_risk_gate(current_risk_percent)

    LOG.debug(f"Alert checks completed: {alert_stats}")


# Global FSM instance
fsm: FSMCore | None = None
execution_position: ExecPosFSM | None = None

# Create logs directory if it doesn't exist
logs_dir = project_root / "logs"
logs_dir.mkdir(exist_ok=True)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, log_level, logging.INFO))

# Create console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(getattr(logging, log_level, logging.INFO))
console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(message)s")
console_handler.setFormatter(console_formatter)
console_handler.stream.reconfigure(encoding="utf-8")  # type: ignore
root_logger.addHandler(console_handler)

# File handler for detailed logs
log_file = logs_dir / "aurora_core.log"
file_handler = RotatingFileHandler(
    log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)  # Log everything to the file
file_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
file_handler.setFormatter(file_formatter)
root_logger.addHandler(file_handler)

# Domain-specific log handlers
domain_handlers = {}

# Feature Engineering domain logs
fe_log_file = logs_dir / "domain_feature_engineering.log"
fe_handler = RotatingFileHandler(
    fe_log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
fe_handler.setLevel(logging.DEBUG)
fe_handler.setFormatter(file_formatter)
fe_handler.addFilter(
    lambda record: record.name.startswith(
        "apps.reference.domains.feature_engineering")
)
domain_handlers["feature_engineering"] = fe_handler
root_logger.addHandler(fe_handler)

# Risk Management domain logs
rm_log_file = logs_dir / "domain_risk_management.log"
rm_handler = RotatingFileHandler(
    rm_log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
rm_handler.setLevel(logging.DEBUG)
rm_handler.setFormatter(file_formatter)
rm_handler.addFilter(
    lambda record: record.name.startswith(
        "apps.reference.domains.risk_management")
)
domain_handlers["risk_management"] = rm_handler
root_logger.addHandler(rm_handler)

# Decision Making domain logs
dm_log_file = logs_dir / "domain_decision_making.log"
dm_handler = RotatingFileHandler(
    dm_log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
dm_handler.setLevel(logging.DEBUG)
dm_handler.setFormatter(file_formatter)
dm_handler.addFilter(
    lambda record: record.name.startswith(
        "apps.reference.domains.decision_making")
)
domain_handlers["decision_making"] = dm_handler
root_logger.addHandler(dm_handler)

# Execution Management domain logs
em_log_file = logs_dir / "domain_execution_management.log"
em_handler = RotatingFileHandler(
    em_log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
em_handler.setLevel(logging.DEBUG)
em_handler.setFormatter(file_formatter)
em_handler.addFilter(
    lambda record: record.name.startswith(
        "apps.reference.domains.execution_position")
)
domain_handlers["execution_management"] = em_handler
root_logger.addHandler(em_handler)

# Regime Detector domain logs
rd_log_file = logs_dir / "domain_regime_detector.log"
rd_handler = RotatingFileHandler(
    rd_log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
rd_handler.setLevel(logging.DEBUG)
rd_handler.setFormatter(file_formatter)
rd_handler.addFilter(
    lambda record: record.name.startswith(
        "apps.reference.domains.regime_detector")
)
domain_handlers["regime_detector"] = rd_handler
root_logger.addHandler(rd_handler)

# Event Chain structured logs (JSON format)
chain_log_file = logs_dir / "event_chain.log"
chain_handler = RotatingFileHandler(
    chain_log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
chain_handler.setLevel(logging.INFO)
json_formatter = JSONFormatter()
chain_handler.setFormatter(json_formatter)
chain_handler.addFilter(
    lambda record: hasattr(record, "rid") or record.name == "event_chain"
)
domain_handlers["event_chain"] = chain_handler
root_logger.addHandler(chain_handler)

LOG = logging.getLogger("AuroraCore")


def debug_event_listener(event: Any) -> None:
    """
    Debug listener to see all events flowing through the system.
    """
    print(f"📡 EVENT: {event.op}:{event.verb} from {event.src} - {event.why}")
    if hasattr(event, "pld") and event.pld:
        # Only show key fields for market data to avoid spam
        if event.verb == "MARKET_TICK_RECEIVED":
            pld = event.pld
            print(
                f"   📊 {pld.get('symbol')} bid={pld.get('bid')} ask={pld.get('ask')}"
            )
        elif event.verb in [
            "FEATURES_CALCULATED",
            "RISK_ASSESSMENT_COMPLETED",
            "PORTFOLIO_STATE_UPDATED",
        ]:
            print(f"   📊 {event.verb} for {event.pld.get('symbol', 'unknown')}")
        elif event.verb == "TRADE_INTENT_PROPOSED":
            order_details = event.pld.get("order", {})
            quantity = order_details.get("qty", "None")
            order_details.get("price", "None")
            trade_info = f"   🎯 TRADE INTENT: {event.pld.get('side')} {quantity} {event.pld.get('instrument')}"
            print(trade_info)

            # Log formatted trade info to formatted log file (exactly as shown in console)
            # Note: Structured logging handled by AuroraLogAdapter in execution_position/fsm.py
            trade_formatted_logger = logging.getLogger(
                "aurora.trade_formatted")
            trade_formatted_logger.info(trade_info)


def initialize_domains(config: dict[str, Any]) -> FSMCore:
    """Initialize all application domains and wire them up."""
    global fsm, execution_position

    LOG.info("Initializing Aurora Core domains...")

    # 1. Create the central FSMCore instance
    fsm = FSMCore()

    # 2. Initialize EXECUTION POSITION FSM FIRST (before market_data triggers trade intents)
    # This ensures execution_position is ready when on_trade_intent_proposed is called
    config_dict = config
    execution_position = ExecPosFSM(config=config_dict, fsm=fsm)
    LOG.info("✅ Execution position FSM initialized first")

    # 3. Initialize other domains
    # Note: This replay() function is legacy code, may need full config refactoring
    market_data = MarketDataConnector(fsm, config_dict)  # Pass full config
    feature_engineering = FeatureEngineering(
        fsm, config_dict.get("trading", {}))
    risk_management = RiskManagement(fsm, config_dict.get("system", {}))
    position_tracking = PositionTracking(fsm, config_dict.get("system", {}))
    # NOTE: Legacy unused initialization (line 1718 is the actual one used)
    decision_making = DecisionMaking(fsm, config_dict.get("trading", {}))
    account_balance = AccountConnector(fsm, config_dict)
    account_observer = AccountObserver(fsm, config_dict)
    # RegimeDetector: Analyzes market features to detect trading regimes
    # Emits EVT:REGIME_DETECTED for decision_making to use
    regime_detector = RegimeDetector(config_dict, fsm)
    # snapshot_scheduler = SnapshotScheduler(fsm, config_dict)  # Moved to main()

    # 4. Register domains in the FSM core for inter-domain communication if needed
    fsm.register_domain("market_data", market_data)
    fsm.register_domain("feature_engineering", feature_engineering)
    fsm.register_domain("risk_management", risk_management)
    fsm.register_domain("position_tracking", position_tracking)
    fsm.register_domain("decision_making", decision_making)
    fsm.register_domain("account_balance", account_balance)
    fsm.register_domain("account_observer", account_observer)
    fsm.register_domain("regime_detector", regime_detector)
    # fsm.register_domain("snapshot_scheduler", snapshot_scheduler)  # Moved to main()
    fsm.register_domain("execution_position", execution_position)

    LOG.info("All domains initialized and registered.")
    return fsm


def main() -> None:
    """Main application entry point."""
    LOG.info("Starting Aurora Core...")

    # Step 1: Load configuration
    LOG.info("Loading configuration...")
    # ConfigLoader accepts config_dir parameter (path to aurora configs)
    config_loader = ConfigLoader(config_dir=project_root / "config" / "aurora")
    config = config_loader.load_config()
    LOG.info("Configuration loaded successfully")

    # Initialize WAL Garbage Collector
    wal_dir = project_root / "ops" / "wal"
    wal_gc = WALGarbageCollector(
        wal_dir=wal_dir,
        retention_days=7,
        max_file_size_mb=100,
        logger=LOG
    )
    wal_gc_thread = wal_gc.start_background_gc(
        interval_sec=3600)  # Run every hour
    LOG.info("✅ WAL Garbage Collector initialized")

    # Initialize Multi-TF Feature Aggregation Scheduler
    from threading import Thread
    import time as time_module

    # NOTE: Multi-TF rollup DISABLED — FeatureStore removed for max tick throughput
    # def _multi_tf_rollup_worker(...) — REMOVED
    # def start_multi_tf_rollup(...) — REMOVED

    # Initialize Alert Manager
    alert_manager = AlertManager(config=config.to_dict(), logger=LOG)
    LOG.info("✅ Alert Manager initialized")

    # Initialize EntropyMonitor for system anomaly detection
    from vfoundation.obs.entropy_monitor import EntropyMonitor
    entropy_monitor = EntropyMonitor(
        window_sec=60,  # 1-minute sliding window
        volume_threshold=100,  # Alert if >100 events/min
        error_rate_threshold=0.5  # Alert if >50% errors
    )
    LOG.info("✅ EntropyMonitor initialized")

    # FSMP-P3-T01: Pre-flight check for hybrid coherence
    is_coherent, reasons = check_hybrid_coherence(config.to_dict())
    if not is_coherent:
        LOG.critical(
            f"🚨 CRITICAL: Hybrid mode is incoherent. Trading will be deferred. Reasons: {'; '.join(reasons)}"
        )
        # In a real scenario, this would trigger a system-wide deferral or shutdown.
        # For now, we just log and continue, assuming downstream components will handle deferral.
        # TODO: Implement a global deferral mechanism or graceful shutdown here.

    # Step 2: Initialize FSM Core
    LOG.info("Initializing FSM Core...")
    global fsm
    fsm = FSMCore()
    
    # Wrap FSMCore.emit to track events with EntropyMonitor
    original_emit = fsm.emit
    def emit_with_monitoring(event_name: str, payload: dict, why: str, data_ref=None):
        """Emit with entropy monitoring"""
        # Track event for anomaly detection
        from vfoundation.core.protocol import Message
        tracking_msg = Message(
            op=event_name.split(":")[0] if ":" in event_name else "EVT",
            verb=event_name.split(":")[1] if ":" in event_name else event_name,
            src="fsm_core",
            dst="any",
            pld=payload,
            why=why
        )
        entropy_monitor.track_event(tracking_msg)
        
        # Call original emit
        return original_emit(event_name, payload, why, data_ref)
    
    fsm.emit = emit_with_monitoring
    LOG.info("✅ FSMCore initialized with EntropyMonitor tracking")

    # Step 2: Create event listeners
    LOG.info("Setting up event listeners...")
    # Initialize AuroraBridge (handles TRADE_INTENT_PROPOSED → CMD:OPEN with freshness gate)
    bridge = AuroraBridge(fsm=fsm, config=config.to_dict(), logger=LOG)

    # D6: Fail-closed restart behavior - clear any pending deferred intents
    # This ensures clean state after restart/crash, emitting EVT:INTENT_DROPPED for each
    dropped_count = bridge.clear_pending_on_restart()
    if dropped_count > 0:
        LOG.warning(f"🗑️ D6: Cleared {dropped_count} pending deferred intents on restart (fail-closed)")
    else:
        LOG.info("✅ D6: No pending deferred intents on restart (clean state)")

    # Set global bridge instance for backward compatibility
    global _bridge_instance
    _bridge_instance = bridge

    # P2 FIX: Gate debug listener with environment variable to avoid hot-path prints in production
    # Set AURORA_DEBUG_EVENTS=1 to enable debug event logging
    if os.environ.get("AURORA_DEBUG_EVENTS", "0") == "1":
        debug_events = [
            "EVT:MARKET_TICK_RECEIVED",
            "EVT:FEATURES_CALCULATED",
            "EVT:RISK_ASSESSMENT_COMPLETED",
            "EVT:PORTFOLIO_STATE_UPDATED",
            "EVT:TRADE_INTENT_PROPOSED",
        ]
        for event_name in debug_events:
            fsm.listen(event_name, debug_event_listener)
        LOG.info("🐛 Debug event listener ENABLED (AURORA_DEBUG_EVENTS=1)")
    else:
        LOG.debug("Debug event listener DISABLED (set AURORA_DEBUG_EVENTS=1 to enable)")

    # Step 3: Initialize all domain components
    LOG.info("Initializing domain components...")

    # Account Connector (source of account balance and positions)
    account_balance = AccountConnector(fsm=fsm, config=config.to_dict())

    # Account Observer (observes trades and sends portfolio updates)
    # FSMP-P3-T01: Use resolved risk_portfolio_source for AccountObserver environment
    risk_portfolio_source = config.get("_resolved", {}).get(
        "risk_portfolio_source", "testnet")  # Default to testnet for safety
    account_observer = AccountObserver(
        fsm=fsm, config=config.to_dict(), environment=risk_portfolio_source)

    # FSMP-ARCH-01: Market Data Connector with Multiprocessing Feature Flag
    # Feature flag: trading.market_data.use_multiprocessing (default: False for safety)
    market_data_cfg = config.to_dict().get("trading", {}).get("market_data", {})
    use_multiprocessing = market_data_cfg.get("use_multiprocessing", False)
    
    if use_multiprocessing:
        LOG.info("🚀 Using MarketDataProxy (multiprocessing mode)")
        market_data = MarketDataProxy(fsm=fsm, config=config)
    else:
        LOG.info("📊 Using MarketDataConnector (legacy single-process mode)")
        market_data = MarketDataConnector(fsm=fsm, config=config)

    # Feature Store (stores historical features for backtesting)
    # NOTE: FeatureStore DISABLED — synchronous DB writes block tick processing!
    # All feature_store code removed for maximum tick throughput.
    LOG.info("⚡ Feature Store DISABLED — no DB writes, maximum tick throughput")

    # Feature Engineering (calculates trading features) — NO feature_store
    feature_engineering = FeatureEngineering(
        fsm=fsm, config=config.to_dict(), feature_store=None)

    # Risk Management (assesses position risk)
    # Extract domain-specific config with correct mode overrides
    risk_domain_mode = config.to_dict().get("trading", {}).get(
        "domain_configuration", {}).get("risk_management", {}).get("trading_mode", "live")
    risk_config = config.to_dict()

    # Always apply mode-specific overrides for risk domain (even if same as global mode)
    from copy import deepcopy
    risk_config = deepcopy(risk_config)
    trading = risk_config.get("trading", {})
    risk = trading.get("risk", {})
    if isinstance(risk, dict):
        risk_mode_overrides = risk.get(risk_domain_mode, {})
        if isinstance(risk_mode_overrides, dict) and risk_mode_overrides:
            if "trading_allowed_thresholds" not in risk:
                risk["trading_allowed_thresholds"] = {}
            thresholds = risk["trading_allowed_thresholds"]
            for key, value in risk_mode_overrides.items():
                old_val = thresholds.get(key)
                thresholds[key] = value
                LOG.info(
                    f"[domain-config] Risk override for mode '{risk_domain_mode}': {key} {old_val} → {value}")

    risk_management = RiskManagement(fsm=fsm, config=risk_config)

    # Position Tracking (tracks portfolio state)
    position_tracking = PositionTracking(fsm=fsm, config=config.to_dict())

    # Execution Position (handles order execution on testnet)
    global execution_position
    execution_position = ExecPosFSM(config=config.to_dict(), fsm=fsm)
    LOG.info("✅ Execution position FSM initialized")

    # ==========================================
    # DR: DISASTER RECOVERY STATE RESTORATION
    # ==========================================
    LOG.info("--- Starting Disaster Recovery Check ---")

    # Initialize components needed for DR (execution_position already initialized in initialize_domains)
    from apps.reference.dr_loader import find_latest_snapshot, replay_wal_after
    import json

    snapshot_dir_path = str(project_root / "ops" / "snapshots")
    wal_dir_path = str(project_root / "ops" / "wal")

    latest_snapshot_path = find_latest_snapshot(snapshot_dir_path)

    if latest_snapshot_path:
        try:
            LOG.info(f"Found latest snapshot: {latest_snapshot_path.name}")

            # Load snapshot data
            with open(latest_snapshot_path, "r", encoding="utf-8") as f:
                snapshot_data = json.load(f)

            # Restore state from snapshot
            if position_tracking.load_snapshot(snapshot_data):
                LOG.info("✅ Successfully loaded state from snapshot")
                LOG.info(
                    f"   Snapshot timestamp: {snapshot_data.get('timestamp_utc', 'unknown')}"
                )
                LOG.info(
                    f"   Positions restored: {snapshot_data.get('metadata', {}).get('positions_count', 0)}"
                )

                # Replay WAL entries after snapshot
                snapshot_ts = snapshot_data.get("timestamp_utc")
                if snapshot_ts:
                    LOG.info("Replaying WAL entries after snapshot...")
                    replayed_count = replay_wal_after(
                        wal_dir_path, snapshot_ts, position_tracking
                    )
                    LOG.info(f"✅ Replayed {replayed_count} events from WAL")

                # ==========================================
                # FSM HYDRATION FROM SNAPSHOT
                # ==========================================
                LOG.info("Hydrating FSMs from restored positions...")
                restored_positions = position_tracking.get_positions()
                hydrated_count = 0
                for symbol, position_data in restored_positions.items():
                    # Reformat data for hydrate method
                    hydrate_data = {
                        "symbol": symbol,
                        "qty": position_data["quantity"],
                        "entry_price": position_data["avg_price"],
                        "side": "BUY" if position_data["quantity"] > 0 else "SELL",
                    }
                    execution_position.hydrate(hydrate_data)
                    hydrated_count += 1
                LOG.info(f"✅ Hydrated {hydrated_count} FSMs.")
                # ==========================================

            else:
                LOG.warning(
                    f"⚠️ Failed to restore state from snapshot: {latest_snapshot_path.name}"
                )
                LOG.info("Starting with empty state.")

        except Exception as e:
            LOG.error(
                f"Error during disaster recovery: {e}. Starting with empty state."
            )
            import traceback

            LOG.debug(traceback.format_exc())
    else:
        LOG.warning("No snapshot found. Starting with a clean state.")

    LOG.info("--- Disaster Recovery Check Finished ---")

    # ==========================================
    # SYNC OPEN ORDERS AND POSITIONS WITH BINANCE
    # ==========================================
    guardian_loop: Optional[asyncio.AbstractEventLoop] = None
    guardian_loop_thread: Optional[threading.Thread] = None

    LOG.info("--- Starting Order/Position Synchronization ---")
    guardian_loop = asyncio.new_event_loop()
    guardian_loop_thread = threading.Thread(
        target=_run_async_loop,
        args=(guardian_loop,),
        name="AuroraAsyncLoop",
        daemon=True,
    )
    execution_position.set_async_loop(guardian_loop)
    guardian_loop_thread.start()

    # Bind Bridge RetryScheduler to the running Aurora async loop (loop-safe scheduling).
    try:
        if _bridge_instance is not None and guardian_loop is not None:
            _bridge_instance.retry_scheduler.bind_loop(guardian_loop)
            LOG.info("✅ Bound RetryScheduler to AuroraAsyncLoop")
    except Exception as e:
        LOG.warning(f"Failed to bind RetryScheduler to AuroraAsyncLoop: {e}")

    try:
        sync_fn = getattr(
            execution_position,
            "sync_open_orders_and_positions",
            None,
        )
        if callable(sync_fn):
            sync_future = asyncio.run_coroutine_threadsafe(
                sync_fn(),
                guardian_loop,
            )
            sync_future.result()
        else:
            LOG.info(
                "ExecutionPosition has no sync_open_orders_and_positions(); skipping initial sync"
            )

        LOG.info("Starting OrderGuardian...")
        guardian_start_future = asyncio.run_coroutine_threadsafe(
            execution_position.start_order_guardian(),
            guardian_loop,
        )
        guardian_start_future.result()

        LOG.info("✅ Order/Position synchronization complete")
        LOG.info("✅ OrderGuardian started")
    except Exception as e:
        LOG.error(
            f"❌ Error during order/position sync or OrderGuardian startup: {e}")
        import traceback
        LOG.debug(traceback.format_exc())
    else:
        LOG.debug("OrderGuardian background loop thread running")
    LOG.info("--- Order/Position Synchronization Finished ---")
    LOG.info("--- Order/Position Synchronization Finished ---")

    # Decision Making (generates trade intents) - execution_position already initialized in initialize_domains()
    # CFG-DOMAINS-STEP-02-FIX: Pass AuroraConfig (not dict) to DecisionMaking
    decision_making = DecisionMaking(fsm=fsm, config=config)
    
    # RegimeDetector: Analyzes market features to detect trading regimes (TREND_UP, TREND_DOWN, etc.)
    # Emits EVT:REGIME_DETECTED which decision_making uses for regime-aware sizing
    regime_detector = RegimeDetector(config=config.to_dict(), fsm=fsm)
    LOG.info("✅ RegimeDetector initialized and subscribed to EVT:FEATURES_CALCULATED")


    # P2 CLEANUP: register_domain calls are now done in initialize_domains()
    # These commented lines preserved for historical reference only:
    # Domain registration moved to initialize_domains() at lines 906-916

    # Initialize Snapshot Scheduler (DR - Phase L4)
    LOG.info("Initializing snapshot scheduler (DR)...")
    snapshot_scheduler_config = {
        "interval_sec": 30,  # 30 seconds for testing (production: 300)
        "snapshot_dir": "ops/snapshots",
        "domains": ["position_tracking"],  # Start with position_tracking only
    }
    # snapshot_scheduler = SnapshotScheduler(
    #     fsm=fsm, config=snapshot_scheduler_config)
    snapshot_scheduler = None  # Temporarily disabled

    # Step 4: Start all components
    LOG.info("Starting account connector...")
    account_balance.start()

    LOG.info("Starting account observer...")
    account_observer.start()

    LOG.info("Starting market data connector...")
    # MarketDataConnector requires async loop - use guardian_loop
    if guardian_loop is not None and guardian_loop.is_running():
        try:
            market_data_future = asyncio.run_coroutine_threadsafe(
                market_data.start_async(),
                guardian_loop,
            )
            market_data_future.result(timeout=10)  # Wait up to 10s for startup
            LOG.info("✅ MarketDataConnector started via async loop")
        except Exception as e:
            LOG.error(f"Failed to start MarketDataConnector: {e}")
    else:
        LOG.warning(
            "⚠️ No async loop available for MarketDataConnector - market data will not be available")

    LOG.info("Starting feature engineering...")
    feature_engineering.start()

    LOG.info("Starting risk management...")
    risk_management.start()

    LOG.info("Starting position tracking...")
    position_tracking.start()

    LOG.info("Starting decision making...")
    decision_making.start()

    LOG.info("Starting regime detector...")
    try:
        if hasattr(regime_detector, "start"):
            regime_detector.start()
            LOG.info("✅ RegimeDetector started")
        else:
            LOG.info("ℹ️ RegimeDetector has no start() method (purely reactive)")
    except Exception as e:
        LOG.error(f"Failed to start RegimeDetector: {e}")

    LOG.info("Starting snapshot scheduler (DR)...")
    # snapshot_scheduler.start()
    LOG.info("Snapshot scheduler temporarily disabled")

    # Step 5: Keep the application running
    LOG.info("Aurora Core is running... Press Ctrl+C to stop.")
    print("\n" + "=" * 60)
    print("🌟 AURORA CORE IS ACTIVE 🌟")
    print("Waiting for market data and trade signals...")
    print("Press Ctrl+C to stop the application.")
    print("=" * 60 + "\n")

    # Alert monitoring state
    last_alert_check = time.time()
    alert_check_interval = 60  # Check every 60 seconds

    try:
        while True:
            current_time = time.time()

            # Periodic alert checks
            if current_time - last_alert_check >= alert_check_interval:
                try:
                    from typing import cast
                    config_dict_arg = cast(dict[Any, Any], config.to_dict(
                    ) if hasattr(config, 'to_dict') else config)
                    _perform_alert_checks(
                        alert_manager, wal_dir, config_dict_arg)
                except Exception as e:
                    LOG.error(f"Error during alert checks: {e}")
                last_alert_check = current_time

            time.sleep(1)
    except KeyboardInterrupt:
        LOG.info("Shutting down Aurora Core...")
        print("\nShutting down Aurora Core...")

        LOG.info("Shutdown signal received. Stopping all components...")

        if guardian_loop is not None:
            try:
                if guardian_loop.is_running():
                    guardian_loop.call_soon_threadsafe(guardian_loop.stop)
                if guardian_loop_thread is not None:
                    guardian_loop_thread.join(timeout=5)
            except Exception as loop_exc:
                LOG.error(f"Error stopping guardian asyncio loop: {loop_exc}")
            finally:
                try:
                    guardian_loop.close()
                except Exception:
                    pass

        # Helper to stop components safely if they exist
        for name in [
            "account_balance",
            "account_observer",
            "market_data",
            "feature_engineering",
            "risk_management",
            "position_tracking",
            "decision_making",
            "snapshot_scheduler",
            "execution_position",
        ]:
            try:
                comp = locals().get(name)
                if comp is not None and hasattr(comp, "stop"):
                    comp.stop()
                    LOG.info(f"{name} stopped.")
            except Exception as e:
                LOG.error(f"Error stopping {name}: {e}")

        # Stop WAL GC
        try:
            wal_gc.stop()
            wal_gc_thread.join(timeout=5)
            LOG.info("WAL GC stopped.")
        except Exception as e:
            LOG.error(f"Error stopping WAL GC: {e}")

        # NOTE: FeatureStore DISABLED — no cleanup needed

        LOG.info("All components stopped or shutdown attempted. Exiting.")
        print("Aurora Core shutdown complete.")


if __name__ == "__main__":
    main()
