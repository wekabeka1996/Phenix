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
from apps.reference.config_loader import ConfigLoader, AuroraConfig
from apps.reference.config_contract import ConfigContractError
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.retry_scheduler import RetryScheduler
# from apps.reference.domains.snapshot_scheduler.snapshot_scheduler import (
#     SnapshotScheduler,
# )

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
from apps.reference.domains.market_data.bar_aggregator import BarAggregator  # BAR-SSOT-002
# TASK32: Strategy plugin allowlist (no dynamic imports)
from apps.reference.domains.strategies.registry import StrategyPluginRegistry, StrategyRuntime
from apps.reference.domains.strategies.plugins.aurora_builtin import AuroraBuiltinPlugin
from apps.reference.domains.strategies.plugins.mean_reversion import MeanReversionPlugin
from vfoundation.core.protocol import truncate_why
from vfoundation.dr.wal_gc import WALGarbageCollector
from vfoundation.dr import wal
from apps.reference.telemetry.alerts import AlertManager
from vfoundation.core.fsm_emit_compat import emit_compat
from vfoundation.core import FSMCore
from vfoundation.core.protocol import Message
import json
import hashlib
import random
import logging
import sys
import time
import os
from datetime import datetime, timedelta
from pathlib import Path
import asyncio

# TASK-EXF-WIRE-STARTUP-09: Startup Guard Imports
from apps.reference.domains.exchange_filters.validator import validate_instruments_on_startup, FilterMismatchError
from apps.reference.adapters.binance_adapter import BinanceAdapter
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


class AuroraBridge:
    """
    Bridge component that handles TRADE_INTENT_PROPOSED → CMD:OPEN conversion
    with portfolio freshness gate to prevent race conditions.
    """

    def __init__(self, fsm: FSMCore, config: AuroraConfig, logger: logging.Logger | None = None):
        self.fsm = fsm
        if isinstance(config, dict):
            raise TypeError("AuroraBridge requires AuroraConfig, got dict")
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

        # Configuration (strict object config)
        from apps.reference.domain_config import DomainConfigResolver
        resolver = DomainConfigResolver(config)
        self._ttl_sec = int(resolver.get_position_tracking().positions_stale_ttl_sec)

        # TASK47: DEV/SHADOW ONLY — disable portfolio stale TTL gate (never enable in live/prod).
        self._debug_disable_positions_stale_gate = bool(
            getattr(getattr(config.domains, "debug", None), "disable_positions_stale_gate", False)
        )
        if self._debug_disable_positions_stale_gate:
            self.logger.warning(
                "TASK47: DEBUG OVERRIDE ACTIVE: disable_positions_stale_gate=True (DEV/SHADOW ONLY)"
            )
            try:
                self.fsm.emit(
                    "EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE",
                    payload={
                        "flag": "disable_positions_stale_gate",
                        "why": "portfolio_stale_gate_disabled",
                    },
                    why="debug_override_active",
                )
            except Exception:
                pass
        
        # D2: Initialize reliable retry scheduler (strict object config)
        retry_config = config.bridge.retry_scheduler
        self._max_retries = int(retry_config.max_attempts)
        self._retry_delay_sec = int(retry_config.min_retry_delay_ms) / 1000.0
        self._retry_scheduler = RetryScheduler(
            fsm=fsm,
            logger=self.logger,
            default_max_attempts=int(retry_config.max_attempts),
            min_retry_delay_ms=int(retry_config.min_retry_delay_ms),
            backoff_factor=float(retry_config.backoff_factor),
            jitter_ms=int(retry_config.jitter_ms),
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

    # =========================================================================
    # TASK47c-C: Capacity Gate (L1)
    # =========================================================================
    
    def _check_capacity_gate(self, intent_msg: Message) -> tuple[bool, str, str]:
        """Check if intent passes capacity gate (max_notional by leverage).
        
        TASK47c-C: Capacity Gate L1 implementation.
        Formula: max_notional = equity_free_usdt * target_leverage * max_notional_utilization
        
        Args:
            intent_msg: TRADE_INTENT_PROPOSED message
            
        Returns:
            Tuple of (allowed: bool, reason: str, log_details: str)
            - allowed=True: proceed to dispatch
            - allowed=False: drop with reason
        """
        symbol = intent_msg.pld.get("instrument") or intent_msg.pld.get("symbol") or ""
        order_details = intent_msg.pld.get("order", {})
        
        # 1. Get notional from payload or calculate
        notional = intent_msg.pld.get("notional") or order_details.get("notional")
        
        if notional is None:
            # Calculate from qty * price_ref
            qty = order_details.get("qty")
            price_ref = (
                order_details.get("price_ref")
                or intent_msg.pld.get("price_ref")
                or intent_msg.pld.get("entry_price")
                or order_details.get("price")
                or intent_msg.pld.get("price")
            )
            
            if qty is None or price_ref is None:
                return (False, "missing_price_ref", f"symbol={symbol} qty={qty} price_ref={price_ref}")
            
            try:
                notional = abs(float(qty)) * float(price_ref)
            except (TypeError, ValueError) as e:
                return (False, "invalid_qty_price", f"symbol={symbol} qty={qty} price_ref={price_ref} error={e}")
        else:
            try:
                notional = float(notional)
            except (TypeError, ValueError) as e:
                return (False, "invalid_notional", f"symbol={symbol} notional={notional} error={e}")
        
        # 2. Get per-instrument execution config (TASK47c-A SSOT)
        instrument_specs = self.config.instruments.get(symbol) if self.config.instruments else None
        if instrument_specs is None:
            return (False, "missing_instrument_config", f"symbol={symbol} not in instruments")
        
        execution_config = getattr(instrument_specs, "execution", None)
        if execution_config is None:
            return (False, "missing_execution_config", f"symbol={symbol} has no execution config")
        
        try:
            target_leverage = float(execution_config.target_leverage)
            max_notional_utilization = float(execution_config.max_notional_utilization)
        except (TypeError, ValueError) as e:
            return (
                False,
                "invalid_execution_config",
                f"symbol={symbol} target_leverage={getattr(execution_config, 'target_leverage', None)} "
                f"max_notional_utilization={getattr(execution_config, 'max_notional_utilization', None)} error={e}",
            )
        
        # 3. Get equity_free_usdt from portfolio
        equity_free_usdt_raw = self._last_portfolio.get("equity_free_usdt", 0)
        try:
            equity_free_usdt = float(equity_free_usdt_raw)
        except (TypeError, ValueError) as e:
            return (
                False,
                "invalid_equity_data",
                f"symbol={symbol} equity_free_usdt={equity_free_usdt_raw} error={e}",
            )

        if equity_free_usdt <= 0:
            # Defensive: no equity data = fail-closed
            return (False, "missing_equity_data", f"symbol={symbol} equity_free_usdt={equity_free_usdt}")
        
        # 4. Calculate max_notional
        max_notional = equity_free_usdt * target_leverage * max_notional_utilization
        
        # 5. Compare
        log_details = (
            f"symbol={symbol} notional={notional:.2f} max_notional={max_notional:.2f} "
            f"equity={equity_free_usdt:.2f} leverage={target_leverage} utilization={max_notional_utilization}"
        )
        
        if notional > max_notional:
            return (False, "capacity_exceeded", log_details)
        
        return (True, "ok", log_details)

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

        order_details = event.pld.get("order", {})
        reduce_only = bool(
            order_details.get("reduce_only")
            or order_details.get("reduceOnly")
            or event.pld.get("reduce_only")
        )
        if reduce_only:
            # Reduce-only closes must bypass QoS/portfolio freshness gates.
            self._dispatch_close(event)
            return

        # Check for forbidden LIMIT entry
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

        # TASK47: DEV/SHADOW override — do NOT block on stale/missing portfolio.
        if getattr(self, "_debug_disable_positions_stale_gate", False):
            self.logger.warning(
                "BRIDGE: portfolio stale but override active; proceeding OPEN (why=portfolio_stale_gate_disabled)"
            )
            try:
                override_evt = Message(
                    op="EVT",
                    verb="CONFIG_DEBUG_OVERRIDE_ACTIVE",
                    src="bridge",
                    dst="*",
                    rid=event.rid,
                    pld={"flag": "disable_positions_stale_gate", "why": "portfolio_stale_gate_disabled"},
                    why="debug_override_active",
                )
                await emit_compat(self.fsm, override_evt, logger=self.logger)
            except Exception:
                pass
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
        if not self._is_portfolio_fresh() and not getattr(self, "_debug_disable_positions_stale_gate", False):
            return

        dropped_count = 0
        processed_count = 0

        for key, intent_msg in list(self._deferred.items()):
            symbol = intent_msg.pld.get(
                "instrument") or intent_msg.pld.get("symbol") or ""
            order_details = intent_msg.pld.get("order", {})
            reduce_only = bool(
                order_details.get("reduce_only")
                or order_details.get("reduceOnly")
                or intent_msg.pld.get("reduce_only")
            )
            if reduce_only:
                # Reduce-only closes bypass freshness/QoS gates; dispatch immediately.
                self._dispatch_close(intent_msg)
                self._deferred.pop(key, None)
                self._deferred_tries.pop(key, None)
                processed_count += 1
                continue

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
        order_details = intent_msg.pld.get("order", {})
        reduce_only = bool(
            order_details.get("reduce_only")
            or order_details.get("reduceOnly")
            or intent_msg.pld.get("reduce_only")
        )
        if reduce_only:
            self._dispatch_close(intent_msg)
            return

        symbol = intent_msg.pld.get("instrument") or intent_msg.pld.get("symbol") or ""
        
        # TASK47c-C: Capacity Gate - check before proceeding
        allowed, reason, log_details = self._check_capacity_gate(intent_msg)
        if not allowed:
            # Log structured capacity gate rejection
            self.logger.warning(f"CAPACITY_GATE_REJECT: {log_details}")
            
            # Emit INTENT_DROPPED
            drop_evt = Message(
                op="EVT",
                verb="INTENT_DROPPED",
                src="bridge",
                dst="*",
                rid=intent_msg.rid,
                pld={
                    "reason": reason,
                    "symbol": symbol,
                    "idempotent_key": intent_msg.pld.get("idempotent_key"),
                    "details": log_details[:80],  # Truncate to 80 chars
                },
                why=f"capacity_gate_{reason}"[:80],
            )

            # WAL: persist drop decision for post-mortem and DR traceability.
            # Best-effort: do not crash bridge on WAL issues.
            try:
                wal.append(drop_evt.model_dump())
            except Exception as wal_e:
                self.logger.warning(f"Failed to write INTENT_DROPPED to WAL: {wal_e}")
            try:
                self.fsm.emit("EVT:INTENT_DROPPED", drop_evt.pld, drop_evt.why)
            except Exception as e:
                self.logger.error(f"Failed to emit INTENT_DROPPED: {e}")
            return

        self.logger.info(
            f"BRIDGE: Converting TRADE_INTENT_PROPOSED rid={intent_msg.rid} for {intent_msg.pld.get('instrument', 'unknown')} to CMD:OPEN"
        )

        # Extract order details from nested structure
        # Accept multiple upstream shapes (legacy + MR handler)
        order_type_raw = order_details.get("order_type") or order_details.get("type")
        price_ref = (
            order_details.get("price_ref")
            or intent_msg.pld.get("price_ref")
            or intent_msg.pld.get("entry_price")
            or order_details.get("price")
            or intent_msg.pld.get("price")
        )

        # BUG FIX: MR Handler puts stop_price/target_price in price_ctx, not top-level
        # Extract from both locations for compatibility with all upstream sources
        price_ctx = intent_msg.pld.get("price_ctx") or {}
        
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
            # TP/SL Intent Data Propagation (PHASE A2 fix + price_ctx extraction)
            # Check top-level first, then price_ctx (MR Handler uses price_ctx)
            "stop_price": intent_msg.pld.get("stop_price") or price_ctx.get("stop_price"),
            "target_price": intent_msg.pld.get("target_price") or price_ctx.get("target_price"),
            "sl_pct": intent_msg.pld.get("sl_pct"),
        }

        # TASK40: Use the business rid (from payload) as the command rid to keep
        # OrderIndex correlation stable end-to-end (intent -> cmd -> entry).
        stable_rid = str(command_payload.get("rid") or intent_msg.rid)
        command_payload["rid"] = stable_rid

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
            rid=stable_rid,
            parent_span_id=intent_msg.span_id,  # Link to parent event for tracing
            intent="COMMAND",  # v2.2: Classify as command
            why=bridge_why,  # Preserve first WHY for backward compatibility
            pld=command_payload,
            data_ref=event_why_chain,  # Full WHY chain (validated list[str])
        )

        # WAL: persist CMD:OPEN emission so WAL contains non-account lifecycle evidence.
        # Best-effort: do not block or crash bridge on WAL issues.
        try:
            wal.append(open_command.model_dump())
        except Exception as wal_e:
            self.logger.warning(f"Failed to write CMD:OPEN to WAL: {wal_e}")

        self.logger.info(
            f"BRIDGE: Dispatched CMD:OPEN with rid={open_command.rid}, parent_span={intent_msg.span_id}"
        )

        # Handle the command directly with execution_position FSM
        if execution_position is not None:
            # TASK40: Mark "open intent in-flight" early (before the exchange ACK)
            # to stop order storms on repeated signals.
            try:
                if hasattr(self.fsm, "order_index") and self.fsm.order_index:  # type: ignore[attr-defined]
                    self.fsm.order_index.upsert_from_open(  # type: ignore[attr-defined]
                        rid=stable_rid,
                        idempotent_key=str(command_payload.get("idempotent_key") or stable_rid),
                        clientOrderId=None,
                        symbol=str(command_payload.get("symbol") or ""),
                        side=str(command_payload.get("side") or ""),
                        order_type="ENTRY_INTENT",
                    )
            except Exception:
                pass

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
                    # Unblock guard on immediate execution rejection.
                    try:
                        if hasattr(self.fsm, "order_index") and self.fsm.order_index:  # type: ignore[attr-defined]
                            ref = self.fsm.order_index.get(rid=stable_rid)  # type: ignore[attr-defined]
                            if ref is not None:
                                self.fsm.order_index.mark_terminal(ref)  # type: ignore[attr-defined]
                    except Exception:
                        pass
        else:
            self.logger.error("BRIDGE: execution_position FSM not initialized")

    def _dispatch_close(self, intent_msg: Message) -> None:
        """Convert reduce-only TRADE_INTENT_PROPOSED to CMD:CLOSE and dispatch."""
        symbol = intent_msg.pld.get("instrument") or intent_msg.pld.get("symbol")
        if not symbol:
            self.logger.error(
                "BRIDGE: reduce-only intent missing symbol/instrument; cannot dispatch CLOSE"
            )
            return

        self.logger.info(
            f"BRIDGE: Converting reduce-only TRADE_INTENT_PROPOSED rid={intent_msg.rid} for {symbol} to CMD:CLOSE"
        )

        # Preserve XAI chain: pass full WHY chain in data_ref.
        # SSOT: Message.data_ref must be list[str]; some upstreams still send pld["why"] as str.
        event_why_chain: list[str] = []
        pld_why = intent_msg.pld.get("why", [])
        if isinstance(intent_msg.data_ref, list) and intent_msg.data_ref:
            event_why_chain = [str(x) for x in intent_msg.data_ref if x is not None]
            if isinstance(pld_why, str) and pld_why.strip() and pld_why.strip() not in event_why_chain:
                event_why_chain.append(pld_why.strip())
        else:
            if isinstance(pld_why, list):
                event_why_chain = [str(x) for x in pld_why if x is not None]
            elif isinstance(pld_why, str) and pld_why.strip():
                event_why_chain = [pld_why.strip()]

        default_why = "exec_close_enter"
        bridge_why = default_why
        if isinstance(event_why_chain, list) and event_why_chain:
            candidate = str(event_why_chain[0])
            bridge_why = truncate_why(candidate) or default_why

        close_command = Message(
            op="CMD",
            verb="CLOSE",
            src="bridge",
            dst="execution_position",
            rid=intent_msg.rid,
            why=bridge_why,
            pld={
                "symbol": symbol,
                "reason": intent_msg.pld.get("reason") or "reduce_only_trade_intent",
                "idempotent_key": intent_msg.pld.get("idempotent_key"),
                "retry_key": intent_msg.pld.get("retry_key"),
            },
            data_ref=event_why_chain,
        )

        if execution_position is not None:
            result = execution_position.handle(close_command)
            if result:
                try:
                    event_name = f"{result.op}:{result.verb}"
                    self.fsm.emit(
                        event_name,
                        result.pld or {},
                        result.why or "bridge_result",
                        result.data_ref,
                    )
                except Exception as e:
                    self.logger.error(f"BRIDGE: Error emitting CLOSE result: {e}")
        else:
            self.logger.error("BRIDGE: execution_position FSM not initialized for CLOSE")

    # ========== SYNCHRONOUS VERSIONS OF HANDLERS ==========
    
    def on_trade_intent_proposed_sync(self, event: Message) -> None:
        """
        Synchronous handler for trade intent.
        Checks QoS and portfolio freshness, dispatches CMD:OPEN if OK.
        If portfolio stale, defers intent for retry on next portfolio update.
        """
        symbol = event.pld.get("instrument") or event.pld.get("symbol") or ""
        rid = event.pld.get("rid", "unknown")
        
        order_details = event.pld.get("order", {})
        reduce_only = bool(
            order_details.get("reduce_only")
            or order_details.get("reduceOnly")
            or event.pld.get("reduce_only")
        )
        if reduce_only:
            self._dispatch_close(event)
            return

        # Check for forbidden LIMIT entry
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
                "max_attempts": int(pld.get("max_attempts", self._retry_scheduler.default_max_attempts)),
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


def _perform_alert_checks(alert_manager: AlertManager, wal_dir: Path, config: AuroraConfig) -> None:
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

# NOTE: This module is imported by some tests via importlib. Without a guard,
# the module-level logging setup below adds duplicate handlers, causing double
# (or N×) log lines in `logs/*.log` during a single pytest run.
_AURORA_LOGGING_TAG = "_aurora_main_logging_configured"
_aurora_logging_already_configured = any(
    getattr(h, _AURORA_LOGGING_TAG, False) for h in root_logger.handlers
)

# Configure handlers only once per process.
if not _aurora_logging_already_configured:

    def _tag(handler: logging.Handler) -> logging.Handler:
        setattr(handler, _AURORA_LOGGING_TAG, True)
        return handler

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))
    console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    console_handler.stream.reconfigure(encoding="utf-8")  # type: ignore
    root_logger.addHandler(_tag(console_handler))

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
    root_logger.addHandler(_tag(file_handler))

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
    root_logger.addHandler(_tag(fe_handler))

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
    root_logger.addHandler(_tag(rm_handler))

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
    root_logger.addHandler(_tag(dm_handler))

    # Execution Position domain logs
    ep_log_file = logs_dir / "domain_execution_position.log"
    ep_handler = RotatingFileHandler(
        ep_log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    ep_handler.setLevel(logging.DEBUG)
    ep_handler.setFormatter(file_formatter)
    ep_handler.addFilter(
        lambda record: record.name.startswith(
            "apps.reference.domains.execution_position")
    )
    domain_handlers["execution_position"] = ep_handler
    root_logger.addHandler(_tag(ep_handler))

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
    root_logger.addHandler(_tag(rd_handler))

    # Mean Reversion strategy logs (separate file, strategy-level telemetry)
    mr_log_file = logs_dir / "domain_mean_reversion.log"
    mr_handler = RotatingFileHandler(
        mr_log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    mr_handler.setLevel(logging.DEBUG)
    mr_handler.setFormatter(file_formatter)
    mr_handler.addFilter(lambda record: record.name.startswith("domain_mean_reversion"))
    domain_handlers["mean_reversion"] = mr_handler
    root_logger.addHandler(_tag(mr_handler))

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
    root_logger.addHandler(_tag(chain_handler))

LOG = logging.getLogger("AuroraCore")


def _init_order_index(fsm: FSMCore, config: Any) -> None:
    """App-level wiring for order correlation index used by WS client.

    Kept here (composition root) to avoid coupling vfoundation.core to app domains.
    """
    from apps.reference.domains.execution_position.order_index import OrderIndex

    ttl_sec: int | None = None

    # Prefer strict, typed config (YAML -> resolvers -> Pydantic)
    try:
        ttl_raw = config.domains.execution_position.order_index.ttl_sec
        ttl_sec = int(ttl_raw)
    except Exception:
        pass

    # Fallback to dict-style config (legacy bootstrap paths)
    if ttl_sec is None and isinstance(config, dict):
        domains = config.get("domains")
        execpos = domains.get("execution_position") if isinstance(domains, dict) else None
        oi_cfg = execpos.get("order_index") if isinstance(execpos, dict) else None
        if isinstance(oi_cfg, dict) and "ttl_sec" in oi_cfg:
            ttl_sec = int(oi_cfg["ttl_sec"])

    if ttl_sec is None:
        raise ValueError(
            "OrderIndex wiring fail-closed: missing required config path "
            "domains.execution_position.order_index.ttl_sec"
        )
    if ttl_sec <= 0:
        raise ValueError(
            "OrderIndex wiring fail-closed: invalid domains.execution_position.order_index.ttl_sec "
            f"(must be int > 0, got {ttl_sec})"
        )

    fsm.order_index = OrderIndex(ttl_sec=ttl_sec)  # type: ignore[attr-defined]
    LOG.info(f"✅ OrderIndex wired into FSMCore (ttl_sec={ttl_sec})")


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
    _init_order_index(fsm, config)

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
    # account_observer = AccountObserver(fsm, config_dict) (Deleted: TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)
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
    # fsm.register_domain("account_observer", account_observer) (Deleted: TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01)
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

    # TASK-EXF-WIRE-STARTUP-09: Validate Instruments vs Exchange
    if config.system.validate_instruments_on_startup:
        async def _startup_validation():
            LOG.info("🛡️ STARTUP GUARD: Validating exchange filters...")
            
            # Use testnet if executing in testnet (Hybrid or Pure Testnet)
            is_testnet = (
                config.trading_mode == "testnet" or 
                config.trading_mode == "hybrid_live_data_testnet_exec"
            )
            
            # Force-disable warn_only in LIVE/PRODUCTION to ensure safety
            # If we are in live/production, we MUST crash on filter mismatch.
            warn_only = config.system.warn_only_filters
            if config.trading_mode in ("live", "production") and warn_only:
                LOG.warning("⚠️ SECURITY: warn_only_filters=True ignored in LIVE/PROD mode. Enforcing FAIL-CLOSED.")
                warn_only = False

            api_cfg = config.binance_api.testnet if is_testnet else config.binance_api.live
            
            # Create temporary adapter for validation
            adapter = BinanceAdapter(
                api_key=api_cfg.api_key or "",
                api_secret=api_cfg.api_secret or "",
                testnet=is_testnet,
                logger=LOG
            )
            
            # Convert Pydantic models back to raw dicts for validator consumption
            instruments_raw = {
                k: v.model_dump() for k, v in config.instruments.items()
            }
            
            try:
                await validate_instruments_on_startup(
                    adapter=adapter,
                    instruments_config={"instruments": instruments_raw},
                    mode="testnet" if is_testnet else "live",
                    warn_only=warn_only
                )
            except FilterMismatchError as e:
                LOG.critical(f"🛑 STARTUP BLOCKED: Exchange Filter Mismatch!\n{e}")
                sys.exit(1)
            except Exception as e:
                LOG.critical(f"🛑 STARTUP BLOCKED: Validation error: {e}")
                sys.exit(1)
            finally:
                # Cleanup adapter resources if possible
                if hasattr(adapter, "close"):
                    await adapter.close()

        # Run validation in temporary loop
        try:
            asyncio.run(_startup_validation())
        except SystemExit:
            raise
        except Exception as e:
            LOG.critical(f"Async loop error during filter validation: {e}")
            sys.exit(1)

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

    # Initialize Alert Manager
    alert_manager = AlertManager(config=config, logger=LOG)
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
    is_coherent, reasons = check_hybrid_coherence(config)
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
    _init_order_index(fsm, config)
    
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
    bridge = AuroraBridge(fsm=fsm, config=config, logger=LOG)

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
    account_balance = AccountConnector(fsm=fsm, config=config)

    # Account Observer (observes trades and sends portfolio updates)
    # FSMP-P3-T01: AccountObserver removed (Legacy Spot code).
    # risk_portfolio_source logic preserved if needed for other components but observer init removed.
    
    # account_observer = AccountObserver(
    #     fsm=fsm, config=config, environment=risk_portfolio_source)

    # FSMP-ARCH-01: Market Data Connector with Multiprocessing Feature Flag
    if config.trading.market_data is None:
        raise ConfigContractError(
            path="trading.market_data",
            why="Missing required config (market_data).",
        )
    use_multiprocessing = bool(config.trading.market_data.use_multiprocessing)
    
    if use_multiprocessing:
        LOG.info("🚀 Using MarketDataProxy (multiprocessing mode)")
        market_data = MarketDataProxy(fsm=fsm, config=config)
    else:
        LOG.info("📊 Using MarketDataConnector (legacy single-process mode)")
        market_data = MarketDataConnector(fsm=fsm, config=config)

    # Feature Engineering (calculates trading features)
    feature_engineering = FeatureEngineering(
        fsm=fsm, config=config)

    # ==========================================
    # BAR-SSOT-002: BarAggregator as passive observer
    # ==========================================
    bar_aggregator = None
    bar_config = getattr(config.trading.market_data, 'bar_aggregator', None)
    
    if bar_config is None:
        # CLOSEOUT-BASELINE-001: Explicit why for missing config
        LOG.info(
            "ℹ️ BarAggregator disabled",
            extra={"why": "bar_agg_disabled_missing_config", "reason": "config.trading.market_data.bar_aggregator not defined"}
        )
    elif not bar_config.enabled:
        # CLOSEOUT-BASELINE-001: Explicit why for disabled flag
        LOG.info(
            "ℹ️ BarAggregator disabled",
            extra={"why": "bar_agg_disabled_config", "reason": "bar_aggregator.enabled=false"}
        )
    else:
        # Enabled: validate timeframes and wire
        timeframes = bar_config.timeframes_sec
        if not timeframes:
            LOG.warning(
                "⚠️ BarAggregator enabled but timeframes_sec empty, using defaults [60, 300]",
                extra={"why": "bar_agg_timeframes_default"}
            )
            timeframes = [60, 300]
        bar_aggregator = BarAggregator(timeframes_sec=timeframes, emit_fn=fsm.emit)
        fsm.listen("EVT:MARKET_TICK_RECEIVED", bar_aggregator.on_market_tick)
        LOG.info(
            f"✅ BarAggregator enabled",
            extra={"why": "bar_agg_enabled", "timeframes_sec": timeframes}
        )

    # Risk Management (assesses position risk)
    # Task 18: Pass AuroraConfig object directly (Resolves domain_configuration internally via DomainConfigResolver)
    risk_management = RiskManagement(fsm=fsm, config=config)

    # Position Tracking (tracks portfolio state)
    position_tracking = PositionTracking(fsm=fsm, config=config)

    # Execution Position (handles order execution on testnet)
    global execution_position
    execution_position = ExecPosFSM(config=config, fsm=fsm)
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
            # Ensure the loop thread actually entered run_forever() before binding.
            for _ in range(100):
                if guardian_loop.is_running():
                    break
                time.sleep(0.01)
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

    # TASK32: Strategy plugins (allowlist registry) wired in composition root
    strategy_plugins = StrategyPluginRegistry()
    strategy_plugins.register(AuroraBuiltinPlugin())
    strategy_plugins.register(MeanReversionPlugin())
    StrategyRuntime(fsm=fsm, config=config, registry=strategy_plugins).start()
    
    # RegimeDetector: Analyzes market features to detect trading regimes (TREND_UP, TREND_DOWN, etc.)
    # Emits EVT:REGIME_DETECTED which decision_making uses for regime-aware sizing
    regime_detector = RegimeDetector(config=config, fsm=fsm)
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

    LOG.info("Starting account observer - SKIPPED (Deleted)")
    # account_observer.start()

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
                    _perform_alert_checks(
                        alert_manager, wal_dir, config)
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
            # "account_observer", (Deleted)
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

        LOG.info("All components stopped or shutdown attempted. Exiting.")
        print("Aurora Core shutdown complete.")


if __name__ == "__main__":
    main()
