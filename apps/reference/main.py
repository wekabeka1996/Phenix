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

from apps.reference.bootstrap.preflight import check_hybrid_coherence, HybridIncoherenceError  # NEW IMPORT
from apps.reference.config_loader import ConfigLoader
# Legacy ExecPosFSM import removed - use build_execution_runtime factory instead
from apps.reference.domains.execution_position.infra.runtime_factory import build_execution_runtime
# from apps.reference.domains.snapshot_scheduler.snapshot_scheduler import (
#     SnapshotScheduler,
# )
from apps.reference.domains.account_observer.account_observer import AccountObserver
from apps.reference.domains.account_balance.account_connector import AccountConnector
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.domains.risk_management.risk_management import RiskManagement
from apps.reference.domains.feature_engineering.feature_engineering import (
    FeatureEngineering,
)
from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
from apps.reference.data.feature_store import FeatureStore
from apps.reference.domains.execution_position.contracts import (
    TradeIntentPayload,
    OpenCommandPayload,
    resolve_order_defaults,
)
from vfoundation.dr import wal
from vfoundation.core.protocol import truncate_why
from vfoundation.dr.wal_gc import WALGarbageCollector
from apps.reference.telemetry.alerts import AlertManager
from vfoundation.core.fsm_emit_compat import emit_compat
from vfoundation.core import FSMCore
from vfoundation.core.protocol import Message
from apps.reference.utils import get_domain_mode_from_mapping
from tools.config_validator_v2 import (
    format_validation_summary,
    validate_config_v2,
)
import json
import logging
import sys
import time
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from logging.handlers import RotatingFileHandler
import asyncio
import threading
from vfoundation.obs import debug_api
from pydantic import ValidationError

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
            "positions_stale_ttl_sec", 35))  # Must be > portfolio update interval (~30s)
        self._retry_delay_sec = 0.5
        self._max_retries = 2

        # Register event listeners
        # Note: We register global handlers that properly handle async calls
        # instead of registering async methods directly (FSMCore calls listeners synchronously)
        self.fsm.listen("EVT:TRADE_INTENT_PROPOSED", on_trade_intent_proposed)
        self.fsm.listen("EVT:PORTFOLIO_STATE_UPDATED",
                        on_portfolio_state_updated)
        self.fsm.listen("EVT:INTENT_DEFERRED", on_intent_deferred)

    def _build_trade_intent_model(self, intent_msg: Message) -> TradeIntentPayload | None:
        """Normalize raw intent payload into TradeIntentPayload."""
        payload = intent_msg.pld or {}
        order = payload.get("order") or {}
        metadata = payload.get("metadata") or payload.get("meta") or {}

        mapped_payload = {
            "symbol": payload.get("symbol") or payload.get("instrument"),
            "side": payload.get("side"),
            "quantity": payload.get("quantity") or order.get("qty"),
            "price": payload.get("price") or order.get("price"),
            "price_ref": payload.get("price_ref") or order.get("price_ref"),
            "order_type": payload.get("order_type") or order.get("order_type") or order.get("type"),
            "time_in_force": payload.get("time_in_force") or payload.get("tif") or order.get("time_in_force") or order.get("tif"),
            "rid": payload.get("rid") or intent_msg.rid,
            "strategy_id": payload.get("strategy_id") or metadata.get("strategy_id"),
            "idempotent_key": payload.get("idempotent_key") or metadata.get("idempotent_key") or metadata.get("idempotency_key"),
            "metadata": metadata,
            "why": payload.get("why"),
        }

        try:
            return TradeIntentPayload(**mapped_payload)
        except ValidationError as exc:
            self.logger.error(
                "BRIDGE: Invalid TRADE_INTENT_PROPOSED payload",
                extra={"rid": intent_msg.rid, "errors": exc.errors()},
            )
            return None

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
        # Use current time if positions_last_ts_ms is missing/zero (no open positions)
        positions_ts = self._last_portfolio.get("positions_last_ts_ms", 0)
        self._last_portfolio_ts = int(
            positions_ts) if positions_ts else int(time.time() * 1000)

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
        try:
            self.logger.info(f"BRIDGE: on_trade_intent_proposed called for rid={event.rid}")
            intent_model = self._build_trade_intent_model(event)
            if intent_model is None:
                return

            symbol = intent_model.symbol or ""

            # Resolve order type from config (entry_orders.order_type) with fallback to price-based detection
            entry_orders_cfg = self.config.get("entry_orders", {})
            config_order_type = entry_orders_cfg.get(
                "order_type")  # LIMIT or MARKET from config
            config_tif = entry_orders_cfg.get("time_in_force", "GTC")

            # If config specifies order type, use it; otherwise fall back to price-based detection
            if config_order_type:
                resolved_order_type = config_order_type.upper()
                resolved_tif = config_tif if resolved_order_type == "LIMIT" else None
                self.logger.info(
                    f"BRIDGE: Using order_type from config: {resolved_order_type} (tif={resolved_tif})")
            else:
                resolved_order_type, resolved_tif = resolve_order_defaults(
                    intent_model.price, intent_model.order_type, intent_model.time_in_force
                )

            # For LIMIT orders, ensure price is provided
            if resolved_order_type == "LIMIT" and not intent_model.price:
                self.logger.error(
                    f"BRIDGE: LIMIT order requested but no price provided for {symbol}. "
                    f"Intent had price={intent_model.price}"
                )
                return

            # Check QoS first
            if not self._is_qos_allowed(symbol):
                # QoS blocked - defer the intent
                key = intent_model.idempotent_key or event.rid or str(time.time())
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
                        "idempotent_key": intent_model.idempotent_key,
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
                self._dispatch_open(event, intent_model=intent_model)
                return

            # Portfolio stale - defer the intent
            key = intent_model.idempotent_key or event.rid or str(time.time())
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
                    "idempotent_key": intent_model.idempotent_key,
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
        except Exception as e:
            self.logger.error(f"BRIDGE: Exception in on_trade_intent_proposed for rid={event.rid}: {e}", exc_info=True)

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

    def _dispatch_open(self, intent_msg: Message, intent_model: TradeIntentPayload | None = None) -> None:
        """Convert TRADE_INTENT_PROPOSED to CMD:OPEN and dispatch."""
        self.logger.info(f"BRIDGE: _dispatch_open called for rid={intent_msg.rid}")
        trade_intent = intent_model or self._build_trade_intent_model(
            intent_msg)
        if trade_intent is None:
            return

        raw_symbol = trade_intent.symbol or "unknown"
        self.logger.info(
            f"BRIDGE: Converting TRADE_INTENT_PROPOSED rid={intent_msg.rid} for {raw_symbol} to CMD:OPEN"
        )

        if raw_symbol == "unknown":
            self.logger.error(
                f"BRIDGE: CRITICAL - Missing symbol in TRADE_INTENT_PROPOSED payload, rid={intent_msg.rid}. "
                f"Available keys: {list(intent_msg.pld.keys())}"
            )

        resolved_order_type, resolved_tif = resolve_order_defaults(
            trade_intent.price, trade_intent.order_type, trade_intent.time_in_force
        )
        try:
            open_cmd = OpenCommandPayload(
                rid=trade_intent.rid or intent_msg.pld.get("rid"),
                symbol=trade_intent.symbol,
                side=trade_intent.side,
                quantity=trade_intent.quantity,
                price=trade_intent.price,
                price_ref=trade_intent.price_ref,
                order_type=resolved_order_type,
                time_in_force=resolved_tif,
                idempotent_key=trade_intent.idempotent_key,
                strategy_id=trade_intent.strategy_id,
                client_order_id=intent_msg.pld.get("client_order_id"),
                why=trade_intent.why if isinstance(
                    trade_intent.why, str) else None,
            )
        except ValidationError as exc:
            self.logger.error(
                "BRIDGE: Failed to build OpenCommandPayload",
                extra={"rid": intent_msg.rid, "errors": exc.errors()},
            )
            return

        command_payload = open_cmd.model_dump(by_alias=True, exclude_none=True)

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

        # Preserve XAI chain: pass full WHY chain in data_ref
        event_why_chain = intent_msg.pld.get("why", [])
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
            why=bridge_why,  # Preserve first WHY for backward compatibility
            pld=command_payload,
            data_ref=event_why_chain or [],  # Full WHY chain
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
                # Emit the result for downstream listeners
                import asyncio
                asyncio.create_task(emit_compat(
                    self.fsm, result, logger=self.logger))
                if result.op == "ERR":
                    self.logger.error(
                        f"BRIDGE: Execution rejected - why={result.why}, pld={result.pld}"
                    )
        else:
            self.logger.error("BRIDGE: execution_position FSM not initialized")


# Global bridge instance for backward compatibility
_bridge_instance: AuroraBridge | None = None


def on_trade_intent_proposed(event: Message) -> None:
    """Global handler for TRADE_INTENT_PROPOSED events - delegates to bridge."""
    try:
        LOG.info(f"GLOBAL: on_trade_intent_proposed called for rid={event.rid}")
        global _bridge_instance, guardian_loop
        if _bridge_instance is not None:
            LOG.info(f"GLOBAL: _bridge_instance exists, guardian_loop={guardian_loop is not None}")
            if guardian_loop is not None:
                LOG.info(f"GLOBAL: guardian_loop.is_running()={guardian_loop.is_running()}")
            # Run async method in sync context
            import asyncio
            if guardian_loop is not None and guardian_loop.is_running():
                LOG.info(f"GLOBAL: Using run_coroutine_threadsafe for rid={event.rid}")
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        _bridge_instance.on_trade_intent_proposed(event),
                        guardian_loop
                    )
                    LOG.info(f"GLOBAL: run_coroutine_threadsafe returned future={future}, done={future.done()} for rid={event.rid}")
                    # Add callback to handle completion
                    def on_future_done(fut):
                        try:
                            result = fut.result()
                            LOG.info(f"GLOBAL: Future completed successfully for rid={event.rid}, result={result}")
                        except Exception as e:
                            LOG.error(f"GLOBAL: Future failed for rid={event.rid}: {e}", exc_info=True)
                    future.add_done_callback(on_future_done)
                except Exception as e:
                    LOG.error(f"GLOBAL: run_coroutine_threadsafe failed for rid={event.rid}: {e}", exc_info=True)
            else:
                LOG.warning(f"GLOBAL: No guardian_loop or not running, trying fallback for rid={event.rid}")
                # Fallback (should not happen in normal operation)
                try:
                    loop = asyncio.get_running_loop()
                    LOG.info(f"GLOBAL: Using create_task in running loop for rid={event.rid}")
                    loop.create_task(_bridge_instance.on_trade_intent_proposed(event))
                except RuntimeError:
                    LOG.warning(f"GLOBAL: No running loop, using asyncio.run for rid={event.rid}")
                    # No running loop, create new one
                    asyncio.run(_bridge_instance.on_trade_intent_proposed(event))
        else:
            LOG.error(
                "BRIDGE: No bridge instance available for on_trade_intent_proposed")
    except Exception as e:
        LOG.error(f"GLOBAL: Exception in on_trade_intent_proposed for rid={event.rid}: {e}", exc_info=True)


def on_portfolio_state_updated(event: Message) -> None:
    """Global handler for PORTFOLIO_STATE_UPDATED events - delegates to bridge."""
    global _bridge_instance, guardian_loop
    if _bridge_instance is not None:
        # Run async method in sync context
        import asyncio
        if guardian_loop is not None and guardian_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _bridge_instance.on_portfolio_state_updated(event),
                guardian_loop
            )
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    _bridge_instance.on_portfolio_state_updated(event))
            except RuntimeError:
                # No running loop, create new one
                asyncio.run(_bridge_instance.on_portfolio_state_updated(event))
    else:
        LOG.error(
            "BRIDGE: No bridge instance available for on_portfolio_state_updated")


def on_intent_deferred(event: Message) -> None:
    """Global handler for INTENT_DEFERRED events - delegates to bridge."""
    global _bridge_instance, guardian_loop
    if _bridge_instance is not None:
        # Run async method in sync context
        import asyncio
        if guardian_loop is not None and guardian_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _bridge_instance.on_intent_deferred(event),
                guardian_loop
            )
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_bridge_instance.on_intent_deferred(event))
            except RuntimeError:
                # No running loop, create new one
                asyncio.run(_bridge_instance.on_intent_deferred(event))
    else:
        LOG.error("BRIDGE: No bridge instance available for on_intent_deferred")


# Local FSMCore mock has been removed. The real FSMCore from vfoundation is now used.


# JSON Formatter for structured logging
class JSONFormatter(logging.Formatter):
    """JSON formatter for structured event chain logging."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "function": record.funcName,
            "line": record.lineno,
        }

        extra_fields: dict[str, Any] = {}
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in {
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
                }:
                    extra_fields[key] = value

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

    # Check risk gate (placeholder - would need actual risk metrics)
        # This would typically come from risk_management domain
        # alert_manager.check_risk_gate(current_risk_percent)

    LOG.debug(f"Alert checks completed: {alert_stats}")


def _resolve_execpos_runtime_mode(config: Any) -> str:
    """Extract execution_position.runtime_mode (defaults to v2)."""
    try:
        cfg_dict = config.to_dict() if hasattr(config, "to_dict") else config
        if isinstance(cfg_dict, dict):
            exec_cfg = cfg_dict.get("execution_position", cfg_dict)
        else:
            exec_cfg = {}
        if isinstance(exec_cfg, dict):
            runtime_mode = exec_cfg.get("runtime_mode", "v2")
        else:
            runtime_mode = getattr(exec_cfg, "runtime_mode", "v2")
    except Exception:
        runtime_mode = "v2"

    if runtime_mode is None:
        return "v2"
    try:
        return str(runtime_mode).lower()
    except Exception:
        return "v2"


def _wire_guardian_loop_for_execpos(
    execution_position: Any,
    guardian_loop: asyncio.AbstractEventLoop,
    logger: logging.Logger | None = None,
) -> bool:
    """
    Wire Guardian loop for runtimes that support it (legacy ExecPosFSM).

    Returns:
        True if set_async_loop was invoked; False otherwise.
    """
    log = logger or LOG
    runtime_name = type(
        execution_position).__name__ if execution_position is not None else "None"

    if execution_position is None:
        log.warning(
            "ExecutionPosition runtime is None; skipping Guardian loop wiring")
        return False

    set_loop = getattr(execution_position, "set_async_loop", None)
    if callable(set_loop):
        set_loop(guardian_loop)
        log.info(
            "ExecutionPosition runtime %s: Guardian loop wired via set_async_loop",
            runtime_name,
        )
        return True

    log.warning(
        "ExecutionPosition runtime %s has no set_async_loop; "
        "WS event handlers will fail to schedule coroutines!",
        runtime_name,
    )
    return False


# Global FSM instance
fsm: FSMCore | None = None
# Created via build_execution_runtime factory
execution_position: Any | None = None
# Global async loop for background tasks
guardian_loop: asyncio.AbstractEventLoop | None = None

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

# Market Data domain logs (separate file for high-frequency data)
md_log_file = logs_dir / "domain_market_data.log"
md_handler = RotatingFileHandler(
    md_log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
md_handler.setLevel(logging.DEBUG)
md_handler.setFormatter(file_formatter)
md_handler.addFilter(
    lambda record: record.name.startswith(
        "apps.reference.domains.market_data")
)
domain_handlers["market_data"] = md_handler
root_logger.addHandler(md_handler)

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
            trade_formatted_logger = logging.getLogger(
                "aurora.trade_formatted")
            trade_formatted_logger.info(trade_info)


def initialize_domains(config) -> FSMCore:
    """Initialize all application domains and wire them up."""
    global fsm, execution_position

    LOG.info("Initializing Aurora Core domains...")

    # 1. Create the central FSMCore instance
    fsm = FSMCore()

    # 2. Initialize EXECUTION POSITION FSM FIRST (before market_data triggers trade intents)
    # This ensures execution_position is ready when on_trade_intent_proposed is called
    # Use factory to build runtime based on config (legacy vs v2)
    runtime_mode = _resolve_execpos_runtime_mode(config)
    runtime_target = "ExecPosFSM (legacy)" if runtime_mode == "legacy" else "V2RuntimeFacade"
    LOG.info("ExecutionPosition runtime_mode='%s' -> using %s",
             runtime_mode, runtime_target)
    execution_position = build_execution_runtime(
        config=config,
        fsm=fsm
    )
    LOG.info(
        f"✅ Execution position runtime initialized first: {type(execution_position).__name__}")

    # 3. Initialize other domains
    # Note: This replay() function is legacy code, may need full config refactoring
    market_data = MarketDataConnector(fsm, config_dict)  # Pass full config
    feature_engineering = FeatureEngineering(
        fsm, config_dict.get("trading", {}))
    risk_management = RiskManagement(fsm, config_dict.get("system", {}))
    position_tracking = PositionTracking(fsm, config_dict.get("system", {}))
    decision_making = DecisionMaking(fsm, config_dict.get("trading", {}))
    account_balance = AccountConnector(fsm, config_dict)
    account_observer = AccountObserver(fsm, config_dict)
    # snapshot_scheduler = SnapshotScheduler(fsm, config_dict)  # Moved to main()

    try:
        position_tracking.register_snapshot_fetcher(
            lambda symbol, reason, rid: account_balance.force_snapshot_refresh(
                symbol=symbol,
                reason=reason,
                rid=rid,
            )
        )
    except Exception as e:
        LOG.warning(
            f"Failed to register snapshot fetcher in initialize_domains: {e}")

    # 4. Register domains in the FSM core for inter-domain communication if needed
    fsm.register_domain("market_data", market_data)
    fsm.register_domain("feature_engineering", feature_engineering)
    fsm.register_domain("risk_management", risk_management)
    fsm.register_domain("position_tracking", position_tracking)
    fsm.register_domain("decision_making", decision_making)
    fsm.register_domain("account_balance", account_balance)
    fsm.register_domain("account_observer", account_observer)
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

    validation_result = validate_config_v2(project_root / "config")
    summary = format_validation_summary(validation_result)
    LOG.info("Config v2 validation summary:\n%s", summary)
    if validation_result.get("status") != "ok":
        LOG.critical("Config v2 validation failed; aborting startup.")
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

    def _multi_tf_rollup_worker(feature_store: FeatureStore, symbols: list[str], interval_sec: int) -> None:
        """Background worker for multi-timeframe feature aggregation.

        Args:
            feature_store: FeatureStore instance
            symbols: list of symbols to roll up (from config)
            interval_sec: sleep interval between rollups
        """
        while not hasattr(_multi_tf_rollup_worker, '_stop') or not _multi_tf_rollup_worker._stop:
            try:
                # Get symbols that have recent features (last 24h)
                end_time = datetime.now()
                start_time = end_time - timedelta(hours=24)

                # Aggregate configured symbols
                symbols_to_rollup = symbols or []

                for symbol in symbols_to_rollup:
                    try:
                        # Rollup to higher timeframes
                        feature_store.aggregate_all_timeframes(
                            symbol=symbol,
                            start_time=start_time,
                            end_time=end_time
                        )
                        LOG.debug(f"Completed multi-TF rollup for {symbol}")
                    except Exception as e:
                        LOG.warning(
                            f"Error in multi-TF rollup for {symbol}: {e}")

            except Exception as e:
                LOG.error(f"Error in multi-TF rollup worker: {e}")

            time_module.sleep(interval_sec)

    # Start multi-TF rollup thread (every 15 minutes)
    def start_multi_tf_rollup(feature_store: FeatureStore, symbols: list[str]) -> Thread:
        thread = Thread(
            target=_multi_tf_rollup_worker,
            args=(feature_store, symbols, 900),  # 15 minutes
            daemon=True,
            name="Multi-TF-Rollup"
        )
        thread.start()
        return thread

    # multi_tf_thread will be initialized later after feature_store is created
    multi_tf_thread = None

    # Initialize Alert Manager
    alert_manager = AlertManager(config=config.to_dict(), logger=LOG)
    LOG.info("✅ Alert Manager initialized")

    # FSMP-P3-T01: Pre-flight check for hybrid coherence
    try:
        is_coherent, reasons = check_hybrid_coherence(config.to_dict())
        LOG.info("HYBRID: OK (live data, testnet exec)")
    except HybridIncoherenceError as e:
        LOG.critical(f"🚨 CRITICAL: {e}")
        # Hard fail - exit the application
        sys.exit(1)

    # Step 2: Initialize FSM Core
    LOG.info("Initializing FSM Core...")
    global fsm
    fsm = FSMCore()

    # Step 2: Create event listeners
    LOG.info("Setting up event listeners...")
    # Initialize AuroraBridge (handles TRADE_INTENT_PROPOSED → CMD:OPEN with freshness gate)
    bridge = AuroraBridge(fsm=fsm, config=config.to_dict(), logger=LOG)

    # Set global bridge instance for backward compatibility
    global _bridge_instance
    _bridge_instance = bridge

    # Add debug listener for all events (optional, can be removed for production)
    debug_events = [
        "EVT:MARKET_TICK_RECEIVED",
        "EVT:FEATURES_CALCULATED",
        "EVT:RISK_ASSESSMENT_COMPLETED",
        "EVT:PORTFOLIO_STATE_UPDATED",
        "EVT:TRADE_INTENT_PROPOSED",
    ]
    for event_name in debug_events:
        fsm.listen(event_name, debug_event_listener)

    # Step 3: Initialize all domain components
    LOG.info("Initializing domain components...")

    # Account Connector (source of account balance and positions)
    account_balance = AccountConnector(fsm=fsm, config=config.to_dict())

    # Account Observer (observes trades and sends portfolio updates)
    # FSMP-P3-T01: Use resolved risk_portfolio_source for AccountObserver environment
    risk_portfolio_source = config.get("_resolved", {}).get(
        "risk_portfolio_source", "testnet")  # Default to testnet for safety
    # Set _resolved for preflight checks
    if not hasattr(config, '_resolved'):
        config._resolved = {}
    config._resolved["risk_portfolio_source"] = risk_portfolio_source
    account_observer = AccountObserver(
        fsm=fsm, config=config.to_dict(), environment=risk_portfolio_source)

    # Market Data Connector (source of market ticks)
    # Pass full config object to access trading section attributes
    market_data = MarketDataConnector(fsm=fsm, config=config)

    # PERFORMANCE FIX: FeatureStore DISABLED
    # - 20GB bloated database was slowing down the system
    # - Nobody reads from it (only writes)
    # - Aggregations blocked event loop for 5-17 seconds
    # To re-enable: uncomment below and delete data/features.db first
    #
    # def _init_feature_store(path: Path) -> FeatureStore:
    #     return FeatureStore(
    #         db_path=str(path),
    #         retention_days=90,
    #     )
    # configured_path = os.environ.get("FEATURE_STORE_DB_PATH")
    # feature_store_path = Path(configured_path) if configured_path else project_root / "data" / "features.db"
    # feature_store = _init_feature_store(feature_store_path)
    feature_store = None  # DISABLED
    LOG.info("⚠️ Feature Store DISABLED for performance (was 20GB bloated)")

    # PERFORMANCE FIX: Multi-TF rollup DISABLED (depends on feature_store)
    # multi_tf_thread = start_multi_tf_rollup(feature_store, symbols_cfg)
    multi_tf_thread = None

    # Feature Engineering (calculates trading features)
    # feature_store=None will skip DB writes
    feature_engineering = FeatureEngineering(
        fsm=fsm, config=config.to_dict(), feature_store=feature_store)

    # Risk Management (assesses position risk)
    # Extract domain-specific config with correct mode overrides
    try:
        risk_domain_mode = config.get_domain_mode("risk_management")
    except AttributeError:
        risk_domain_mode = get_domain_mode_from_mapping(
            config, "risk_management")
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

    try:
        position_tracking.register_snapshot_fetcher(
            lambda symbol, reason, rid: account_balance.force_snapshot_refresh(
                symbol=symbol,
                reason=reason,
                rid=rid,
            )
        )
    except Exception as e:
        LOG.warning(f"Failed to register snapshot fetcher: {e}")

    try:
        debug_api.register_resync_handler(
            lambda reason, symbol=None: position_tracking.force_full_resync(
                reason=reason,
                symbol=symbol,
            )
        )
    except Exception as e:
        LOG.warning(f"Failed to register debug resync handler: {e}")

    # Execution Position (handles order execution on testnet)
    global execution_position
    # Use factory to build runtime based on config (legacy vs v2)
    runtime_mode = _resolve_execpos_runtime_mode(config)
    runtime_target = "ExecPosFSM (legacy)" if runtime_mode == "legacy" else "V2RuntimeFacade"
    LOG.info("ExecutionPosition runtime_mode='%s' -> using %s",
             runtime_mode, runtime_target)
    execution_position = build_execution_runtime(
        config=config,
        fsm=fsm
    )
    LOG.info(
        f"✅ Execution position runtime initialized: {type(execution_position).__name__}")

    try:
        debug_api.register_agg_oco_state_provider(
            lambda symbol=None, side=None: execution_position.get_agg_oco_state_snapshot(
                symbol=symbol,
                side=side,
                as_dict=True,
            )
        )
    except Exception as exc:
        LOG.warning(f"Failed to register agg_oco_state provider: {exc}")

    # ==========================================
    # DR: DISASTER RECOVERY STATE RESTORATION
    # ==========================================
    LOG.info("--- Starting Disaster Recovery Check ---")

    # Initialize components needed for DR (execution_position initialized above)
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
                snapshot_wrapper = json.load(f)
            # If snapshot is wrapped with integrity, verify and extract
            try:
                if isinstance(snapshot_wrapper, dict) and "integrity_hash" in snapshot_wrapper and "data" in snapshot_wrapper:
                    wrapper_data = snapshot_wrapper["data"]
                    expected_hash = snapshot_wrapper.get("integrity_hash")
                    # Compute hash of data for verification
                    import hashlib
                    import json as _json
                    actual_hash = hashlib.sha256(_json.dumps(
                        wrapper_data, sort_keys=True).encode("utf-8")).hexdigest()
                    if expected_hash and expected_hash != actual_hash:
                        raise ValueError(
                            "Snapshot integrity verification failed")
                    snapshot_data = wrapper_data
                else:
                    snapshot_data = snapshot_wrapper
            except Exception as e:
                LOG.error(
                    f"Snapshot integrity check failed for {latest_snapshot_path.name}: {e}")
                snapshot_data = None

            # Restore state from snapshot
            if snapshot_data and position_tracking.load_snapshot(snapshot_data):
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
    global guardian_loop
    guardian_loop_thread: Optional[threading.Thread] = None

    LOG.info("--- Starting Order/Position Synchronization ---")
    guardian_loop = asyncio.new_event_loop()
    guardian_loop_thread = threading.Thread(
        target=_run_async_loop,
        args=(guardian_loop,),
        name="AuroraAsyncLoop",
        daemon=True,
    )
    runtime_name = type(
        execution_position).__name__ if execution_position is not None else "None"
    _wire_guardian_loop_for_execpos(
        execution_position=execution_position,
        guardian_loop=guardian_loop,
        logger=LOG,
    )
    guardian_loop_thread.start()

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
                "ExecutionPosition runtime %s has no sync_open_orders_and_positions(); skipping initial sync (expected for V2)",
                runtime_name,
            )

        guardian_start_fn = getattr(
            execution_position,
            "start_order_guardian",
            None,
        )
        if callable(guardian_start_fn):
            LOG.info("Starting OrderGuardian...")
            guardian_start_future = asyncio.run_coroutine_threadsafe(
                guardian_start_fn(),
                guardian_loop,
            )
            guardian_start_future.result()
            LOG.info("✅ OrderGuardian started")
        else:
            LOG.info(
                "ExecutionPosition runtime %s has no start_order_guardian(); skipping Guardian startup (expected for V2)",
                runtime_name,
            )

        LOG.info("✅ Order/Position synchronization complete")
    except Exception as e:
        LOG.error(
            f"❌ Error during order/position sync or OrderGuardian startup: {e}")
        import traceback
        LOG.debug(traceback.format_exc())
    else:
        LOG.debug("OrderGuardian background loop thread running")
    LOG.info("--- Order/Position Synchronization Finished ---")
    LOG.info("--- Order/Position Synchronization Finished ---")

    # Decision Making (generates trade intents) - execution_position initialized above
    decision_making = DecisionMaking(fsm=fsm, config=config.to_dict())

    # Register all domains in FSM core for cross-domain access
    fsm.register_domain('account_balance', account_balance)
    fsm.register_domain('account_observer', account_observer)
    fsm.register_domain('market_data', market_data)
    fsm.register_domain('feature_engineering', feature_engineering)
    fsm.register_domain('risk_management', risk_management)
    fsm.register_domain('position_tracking', position_tracking)
    fsm.register_domain('decision_making', decision_making)
    fsm.register_domain('execution_position', execution_position)

    # Initialize Snapshot Scheduler (DR - Phase L4)
    LOG.info("Initializing snapshot scheduler (DR)...")
    # Snapshot scheduler configuration (overridable via config.wave_0.snapshot)
    # DISABLED: Snapshot scheduler creates unnecessary load during testing
    # Default values (testing defaults): 30s interval
    snapshot_enabled_default = False  # DISABLED for performance
    snapshot_interval_default = 30
    snapshot_dir_default = "ops/snapshots"
    snapshot_domains_default = ["position_tracking"]

    try:
        wave0_cfg = config.to_dict().get("wave_0", {})
    except Exception:
        wave0_cfg = {}

    snapshot_cfg = (wave0_cfg.get("snapshot") if isinstance(
        wave0_cfg, dict) else None) or {}
    snapshot_enabled = snapshot_cfg.get("enabled", snapshot_enabled_default)
    snapshot_interval = snapshot_cfg.get(
        "interval_sec", snapshot_interval_default)
    snapshot_dir_val = snapshot_cfg.get("snapshot_dir", snapshot_dir_default)
    snapshot_domains = snapshot_cfg.get("domains", snapshot_domains_default)

    snapshot_scheduler_config = {
        "interval_sec": snapshot_interval,
        "snapshot_dir": snapshot_dir_val,
        "domains": snapshot_domains,
    }
    if snapshot_enabled:
        try:
            from apps.reference.domains.snapshot_scheduler.snapshot_scheduler import SnapshotScheduler

            snapshot_scheduler = SnapshotScheduler(
                fsm=fsm, config=snapshot_scheduler_config)
            # Register and start
            # fsm.register_domain('snapshot_scheduler', snapshot_scheduler)
            snapshot_scheduler.start()
            LOG.info(
                f"✅ Snapshot scheduler enabled (interval={snapshot_interval}s)")
        except Exception as e:
            LOG.error(f"Failed to initialize snapshot_scheduler: {e}")
            snapshot_scheduler = None
    else:
        snapshot_scheduler = None
    # fsm.register_domain('snapshot_scheduler', snapshot_scheduler)

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

    LOG.info("Starting execution position adapter (WebSocket USER_DATA_STREAM)...")
    if hasattr(execution_position, 'adapter') and execution_position.adapter:
        if hasattr(execution_position.adapter, 'start'):
            # Run async start() in event loop (asyncio imported globally at top)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule in existing loop
                    asyncio.ensure_future(execution_position.adapter.start())
                else:
                    loop.run_until_complete(execution_position.adapter.start())
            except RuntimeError:
                # No event loop, create new one
                asyncio.run(execution_position.adapter.start())
            LOG.info("✅ Execution position WebSocket USER_DATA_STREAM started")
        else:
            LOG.info("⚠️ Adapter has no start() method (shadow mode?)")
    else:
        LOG.info("⚠️ No adapter available for execution position")

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

        # Stop async resources in execution_position adapter (http client cleanup)
        if 'execution_position' in locals() and execution_position is not None:
            try:
                adapter = getattr(execution_position, 'adapter', None)
                if adapter is not None and hasattr(adapter, 'stop_async'):
                    # Run async cleanup
                    try:
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(adapter.stop_async())
                        loop.close()
                        LOG.info(
                            "Execution position adapter HTTP client closed.")
                    except Exception as async_e:
                        LOG.warning(f"Error during async cleanup: {async_e}")
            except Exception as e:
                LOG.debug(f"Could not cleanup execution adapter: {e}")

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

        # Optimize Feature Store before shutdown
        try:
            if 'feature_store' in locals():
                feature_store.optimize()
                LOG.info("Feature Store optimized.")
        except Exception as e:
            LOG.error(f"Error optimizing Feature Store: {e}")

        LOG.info("All components stopped or shutdown attempted. Exiting.")
        print("Aurora Core shutdown complete.")


if __name__ == "__main__":
    main()
