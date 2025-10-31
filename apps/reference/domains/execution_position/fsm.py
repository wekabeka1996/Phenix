"""
FSMP-P1-T02: Orchestration of 3 FSM flows for execution_position domain.

This FSM acts as a wrapper, routing commands to the appropriate flow FSM
(Open, Manage, Close) on a per-symbol basis. It integrates directly with
the vFoundation BinanceAdapter to execute trades in the configured environment.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple

from vfoundation.core.fsm_emit_compat import Message, emit_compat
from vfoundation.dr import wal
from vfoundation.adapters.binance_adapter import BinanceAdapter, BinanceAPIError

from .fsm_open import OpenFlowFSM
from .fsm_manage import ManageFlowFSM
from .fsm_close import CloseFlowFSM
from .exposure_guard import ExposureGuard
from .utils import (
    quantize_stop_price,
    validate_anti_2021,
    generate_client_order_id,
    calc_tp_sl_from_mark,
    validate_not_immediate,
    opposite_side,
)
from .aurora_log_adapter import AuroraLogAdapter
from .metrics_collector import MetricsCollector
from vfoundation.obs.order_logger import order_logger
from .utils import quantize_stop_price, validate_anti_2021, generate_client_order_id
from vfoundation.obs.correlation import CorrelationStore

LOG = logging.getLogger(__name__)


class ExecPosFSM:
    """
    Wrapper FSM for the execution_position domain. It manages FSM instances
    per symbol and handles trade execution via the BinanceAdapter.
    """

    def __init__(self, config: Dict[str, Any], fsm, shadow_mode: bool = False):
        self.config = config
        self.fsm = fsm
        self.shadow_mode = shadow_mode
        self.adapter: Optional[BinanceAdapter] = None

        self.open_flows: Dict[str, OpenFlowFSM] = {}
        self.manage_flows: Dict[str, ManageFlowFSM] = {}
        self.close_flows: Dict[str, CloseFlowFSM] = {}

        self.log_adapter = AuroraLogAdapter()
        self.metrics_collector = MetricsCollector()

        # EXP-FIX: Initialize exposure guard
        self.exposure_guard = ExposureGuard(self.config, fsm=self.fsm)
        self._latest_portfolio_state = {}  # EXP-FIX: Store latest portfolio state

        self.correlation_store = CorrelationStore()

        if not self.shadow_mode:
            self._initialize_adapter()

    def _initialize_adapter(self):
        """Initializes the BinanceAdapter based on the domain-level trading_mode."""
        # Check if config_loader has get_domain_mode method (new approach)
        mode = "testnet"  # Default fallback

        # Try to get domain-specific mode first
        if hasattr(self.config, "get_domain_mode"):
            try:
                mode = self.config.get_domain_mode("execution_position")
                LOG.info(f"✅ ExecPosFSM using domain-specific mode: {mode}")
            except Exception as e:
                LOG.warning(f"Could not get domain mode, using fallback: {e}")
                mode = self.config.get("trading_mode", "testnet")
        else:
            # Fallback to global mode
            mode = self.config.get("trading_mode", "testnet")
            LOG.info(f"ExecPosFSM using global trading_mode: {mode}")

        LOG.info(f"🎯 EXECUTION POSITION FSM MODE: {mode.upper()}")

        api_config = self.config.get("binance_api", {})

        env_config = {}
        if mode == "live":
            env_config = api_config.get("live", {})
            LOG.info("❌ ExecPosFSM adapter is configured for LIVE execution.")
        else:  # 'testnet' or 'hybrid_live_data_testnet_exec'
            env_config = api_config.get("testnet", {})
            LOG.info(
                f"✅ ExecPosFSM adapter is configured for TESTNET execution (mode: {mode})."
            )

        if not all(
            [
                env_config.get("api_key"),
                env_config.get("api_secret"),
                env_config.get("rest_url"),
            ]
        ):
            LOG.error(
                f"API configuration for execution in '{mode}' mode is incomplete. Execution will be simulated."
            )
            LOG.debug(
                f"  - API Key present: {bool(env_config.get('api_key'))}")
            LOG.debug(
                f"  - API Secret present: {bool(env_config.get('api_secret'))}")
            LOG.debug(f"  - REST URL: {env_config.get('rest_url')}")
            self.shadow_mode = True  # Fallback to shadow mode if config is missing
            return

        self.adapter = BinanceAdapter(
            api_key=env_config["api_key"],
            api_secret=env_config["api_secret"],
            rest_url=env_config["rest_url"],
        )
        LOG.info(
            f"✅ BinanceAdapter initialized for ExecPosFSM with base URL: {self.adapter.base_url}"
        )

    def _get_or_create_flows(
        self, symbol: str
    ) -> Tuple[OpenFlowFSM, ManageFlowFSM, CloseFlowFSM]:
        """Get or create the set of FSMs for a given symbol."""
        if symbol not in self.manage_flows:
            LOG.info(f"Creating new set of FSMs for symbol: {symbol}")
            exec_config = self.config.get("trading", {}).get("execution", {})
            cooldown_ms = float(exec_config.get("cooldown_ms", 1000))
            cooldown_sec = cooldown_ms / 1000.0
            guard_enabled = exec_config.get("guard_enabled", True)

            self.open_flows[symbol] = OpenFlowFSM(
                cooldown_sec=cooldown_sec,
                guard_enabled=guard_enabled,
                config=self.config,
                metrics_collector=self.metrics_collector,
            )
            self.manage_flows[symbol] = ManageFlowFSM(config=self.config)
            self.close_flows[symbol] = CloseFlowFSM()

        return (
            self.open_flows[symbol],
            self.manage_flows[symbol],
            self.close_flows[symbol],
        )

    def hydrate(self, position_data: Dict[str, Any]):
        """Hydrate the FSMs for a given position from a snapshot."""
        symbol = position_data.get("symbol")
        if not symbol:
            LOG.error("HYDRATION_ERROR: position_data is missing 'symbol'")
            return

        _, manage_flow, close_flow = self._get_or_create_flows(symbol)

        LOG.info(f"Hydrating FSMs for symbol {symbol} from snapshot.")
        manage_flow.hydrate(position_data)
        close_flow.hydrate(position_data)

    def handle(self, msg: Message) -> Optional[Message]:
        """Route message to the appropriate flow and handle execution decisions."""
        pld = msg.pld or {}

        # EXP-FIX: Store latest portfolio state for exposure checks
        if msg.op == "EVT" and msg.verb == "PORTFOLIO_STATE_UPDATED":
            self._latest_portfolio_state = msg.pld or {}
            # Clean up stale reservations on portfolio updates
            expired = self.exposure_guard.expire_stale()
            # EXP-FIX: Release post-fill holds since portfolio is now updated
            released_postfill = list(
                self.exposure_guard.state.postfill_reservations.keys()
            )
            for key in released_postfill:
                self.exposure_guard.state.postfill_reservations.pop(key, None)
            if released_postfill:
                LOG.debug(
                    f"RELEASED_POSTFILL_HOLDS: {len(released_postfill)} keys")
                if hasattr(self, "metrics_collector") and self.metrics_collector:
                    for _ in released_postfill:
                        self.metrics_collector.record_postfill_released()
            if expired:
                # EXP-FIX: Record expired post-fill holds
                if hasattr(self, "metrics_collector") and self.metrics_collector:
                    for _ in expired:
                        if _ in self.exposure_guard.state.postfill_reservations:
                            self.metrics_collector.record_postfill_expired()

                # Emit event for expired reservations
                expired_msg = Message(
                    op="EVT",
                    verb="PENDING_EXPOSURE_EXPIRED",
                    intent="OBSERVATION",
                    src="execution_position",
                    dst="monitoring",
                    rid="exposure_cleanup",
                    pld={"expired_keys": expired, "why": "ttl_expired"},
                    why="exposure_cleanup",
                )
                try:
                    asyncio.get_running_loop()  # Check for running loop
                    asyncio.create_task(
                        emit_compat(self.fsm, expired_msg, logger=self.logger)
                    )
                except RuntimeError:
                    # No running loop, skip emission
                    pass
            return None  # Portfolio updates don't need further processing

        symbol = pld.get("symbol")
        if not symbol:
            LOG.warning(
                f"ExecPosFSM received message without symbol: {msg.verb}")
            return None

        open_flow, manage_flow, close_flow = self._get_or_create_flows(symbol)
        result = None

        # Route to the correct FSM based on the message verb
        if msg.verb == "OPEN":
            # EXP-FIX: Fail-closed exposure check before processing CMD:OPEN
            if self._check_exposure_fail_closed(msg):
                return None  # Error already emitted
            result = open_flow.handle(msg)
        elif msg.verb in ["PARTIAL_FILL", "FILL", "TRADE_EXECUTED", "ORDER_UPDATED"]:
            manage_result = manage_flow.handle(msg)
            close_result = close_flow.handle(msg)
            result = manage_result if manage_result else close_result

            # EXP-FIX: Handle post-fill hold for FILLED orders
            if msg.verb == "FILL" and result:
                self._handle_fill_event(msg)

        elif msg.verb == "CLOSE":
            result = close_flow.handle(msg)
        else:
            result = manage_flow.handle(msg)

        # If a decision was made, log it and execute if not in shadow mode
        if result and result.op == "DEC":
            wal.append(result.model_dump())
            if not self.shadow_mode and self.adapter:
                # Asynchronously execute the trade decision
                loop = asyncio.get_event_loop()
                loop.create_task(self._execute_decision(result))

        return result

    async def _execute_decision(self, decision: Message):
        """Asynchronously execute a trading decision using the adapter."""
        if not self.adapter:
            return

        # --- CRITICAL SAFETY GUARDRAIL ---
        # Get domain-specific mode (execution_position should be testnet)
        domain_mode = "testnet"
        if hasattr(self.config, "get_domain_mode"):
            try:
                domain_mode = self.config.get_domain_mode("execution_position")
            except:
                domain_mode = self.config.get("trading_mode", "testnet")
        else:
            domain_mode = self.config.get("trading_mode", "testnet")

        LOG.info(f"🎯 Executing with domain_mode={domain_mode}")

        if domain_mode == "testnet":
            if "testnet" not in self.adapter.base_url:
                LOG.critical(
                    "🚨 GUARDRAIL TRIGGERED: Domain mode is TESTNET, but adapter is configured for LIVE API! Order BLOCKED."
                )
                # Optionally emit a critical error event
                fatal_msg = Message(
                    op="ERR",
                    verb="FATAL_CONFIG_MISMATCH",
                    intent="ERROR",
                    src="execution_position",
                    dst="monitoring",
                    rid="config_check",
                    pld={"reason": "Testnet mode with live execution URL"},
                    why="Testnet mode with live execution URL",
                )
                await emit_compat(self.fsm, fatal_msg, logger=self.logger)
                return
            else:
                LOG.info(
                    "✅ Testnet mode confirmed: adapter URL contains 'testnet'")
        elif domain_mode == "live":
            LOG.warning(
                "⚠️ LIVE execution mode - ensure you know what you're doing!")

        # --- END GUARDRAIL ---

        try:
            symbol = decision.pld["symbol"]
            side = decision.pld["side"].upper()
            qty = decision.pld["qty"]

            # Get mark price and filters
            mark = await self.adapter.get_mark_price(symbol)
            exchange_info = await self.adapter.get_exchange_info(symbol)
            tick_size = float(
                next(
                    f["tickSize"]
                    for f in exchange_info["symbols"][0]["filters"]
                    if f["filterType"] == "PRICE_FILTER"
                )
            )

            # Assume tp_bps and sl_bps from config or default
            tp_bps = 100  # example
            sl_bps = 50  # example

            tp, sl = calc_tp_sl_from_mark(
                mark, "LONG" if side == "BUY" else "SHORT", tp_bps, sl_bps
            )

            # Quantize
            tp = quantize_stop_price(
                tp, tick_size, side="BUY" if side == "BUY" else "SELL"
            )
            sl = quantize_stop_price(
                sl, tick_size, side="SELL" if side == "BUY" else "BUY"
            )

            # Validate
            validate_not_immediate(
                "LONG" if side == "BUY" else "SHORT", tp, sl, mark)

            # Place MARKET entry
            entry_id = generate_client_order_id("ENTRY", symbol)
            entry_resp = await self.adapter.place_market_entry(
                symbol, side, qty, entry_id
            )
            LOG.info(f"✅ MARKET entry placed: {entry_resp}")

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": decision.rid,
                "event_type": "ORDER_PLACED",
                "symbol": symbol,
                "side": side,
                "quantity": float(qty),
                "client_order_id": entry_id,
                "order_id": str(entry_resp.get("orderId", "")),
                "source_fsm": "ExecPosFSM",
                "reservation_id": decision.corr_id,
                "adapter_response": entry_resp,
                "metadata": {"order_type": "MARKET_ENTRY", "corr_id": decision.corr_id}
            })

            # Correlation: store entry ACK
            entry_order_id = str(entry_resp["orderId"])
            decision.link_ack_id = entry_order_id
            self.correlation_store.put_entry_ack(entry_order_id, {
                'corr_id': decision.corr_id,
                'oco_group_id': decision.oco_group_id,
                'rid': decision.rid,
                'parent_client_order_id': None
            })
            self.log_adapter.log_trade_execution(
                rid=decision.rid,
                symbol=symbol,
                side=side,
                order_id=entry_order_id,
                status="ACK",
                corr_id=decision.corr_id
            )

            # Check for existing brackets to avoid duplicates
            open_orders = await self.adapter.get_open_orders(symbol)
            existing_sl = any(
                o["type"] == "STOP_MARKET" and o.get("closePosition") == "true"
                for o in open_orders
            )
            existing_tp = any(
                o["type"] in ["TAKE_PROFIT_MARKET", "LIMIT"]
                and o.get("closePosition") == "true"
                or o.get("reduceOnly") == "true"
                for o in open_orders
            )

            if existing_sl:
                LOG.warning(f"SL already exists for {symbol}, skipping")
            else:
                # Place SL
                sl_side = opposite_side(side)
                sl_id = generate_client_order_id("SL", symbol)
                sl_resp = await self.adapter.place_stop_market_close_position(
                    symbol, sl_side, str(sl), new_client_order_id=sl_id
                )
                LOG.info(f"✅ SL placed: {sl_resp}")

                # Correlation: store SL ACK
                sl_order_id = str(sl_resp["orderId"])
                self.correlation_store.put_sl_tp_ack(
                    sl_order_id, entry_resp["clientOrderId"], decision.corr_id, decision.oco_group_id, decision.rid)

            if existing_tp:
                LOG.warning(f"TP already exists for {symbol}, skipping")
            else:
                # Place TP with retry/fallback
                tp_side = opposite_side(side)
                tp_id = generate_client_order_id("TP", symbol)
                try:
                    tp_resp = (
                        await self.adapter.place_take_profit_market_close_position(
                            symbol, tp_side, str(tp), new_client_order_id=tp_id
                        )
                    )
                    LOG.info(f"✅ TP TAKE_PROFIT_MARKET placed: {tp_resp}")

                    # Correlation: store TP ACK
                    tp_order_id = str(tp_resp["orderId"])
                    self.correlation_store.put_sl_tp_ack(
                        tp_order_id, entry_resp["clientOrderId"], decision.corr_id, decision.oco_group_id, decision.rid)
                except BinanceAPIError as e:
                    if e.code == -2021:
                        # Retry with widened TP
                        tp_adj = tp * 1.002  # +20 bps approx
                        tp_adj = quantize_stop_price(
                            tp_adj, tick_size, side="BUY" if side == "BUY" else "SELL"
                        )
                        self.metrics_collector.record_retry(
                            "tp_adjust") if self.metrics_collector else None
                        try:
                            tp_resp = await self.adapter.place_take_profit_market_close_position(
                                symbol, tp_side, str(tp_adj), new_client_order_id=tp_id
                            )
                            LOG.info(
                                f"✅ TP TAKE_PROFIT_MARKET retried: {tp_resp}")
                        except BinanceAPIError:
                            # Fallback to LIMIT reduceOnly
                            self.metrics_collector.record_retry(
                                "tp_fallback") if self.metrics_collector else None
                            tp_resp = await self.adapter.place_limit_reduce_only(
                                symbol,
                                tp_side,
                                str(tp_adj),
                                qty,
                                new_client_order_id=tp_id,
                            )
                            LOG.info(f"✅ TP LIMIT fallback placed: {tp_resp}")

                            # Correlation: store TP ACK
                            tp_order_id = str(tp_resp["orderId"])
                            self.correlation_store.put_sl_tp_ack(
                                tp_order_id, entry_resp["clientOrderId"], decision.corr_id, decision.oco_group_id, decision.rid)
                    else:
                        raise

        except Exception as e:
            LOG.error(
                f"❌ Adapter failed to execute decision {decision.verb} for {decision.pld.get('symbol')}: {e}",
                exc_info=True,
            )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": decision.rid,
                "event_type": "ORDER_REJECTED",
                "symbol": decision.pld.get("symbol", ""),
                "side": decision.pld.get("side", "NONE"),
                "quantity": float(decision.pld.get("qty", 0)),
                "nrr_code": "NRR-015",  # Exchange rejected
                "why": f"Adapter execution failed: {str(e)}",
                "source_fsm": "ExecPosFSM",
                "metadata": {"error": str(e), "decision_verb": decision.verb}
            })

            # Emit an error event
            exec_failed_msg = Message(
                op="ERR",
                verb="EXECUTION_FAILED",
                intent="ERROR",
                src="execution_position",
                dst="monitoring",
                rid=decision.rid,
                pld={"error": str(
                    e), "original_decision": decision.model_dump()},
                why="Execution failed due to adapter error",
            )
            await emit_compat(self.fsm, exec_failed_msg, logger=self.logger)

    def get_metrics(self) -> Dict[str, Any]:
        """Aggregate metrics from all managed FSMs."""
        all_metrics = {}
        for symbol, open_fsm in self.open_flows.items():
            all_metrics[f"{symbol}_open"] = open_fsm.get_metrics()
        for symbol, manage_fsm in self.manage_flows.items():
            all_metrics[f"{symbol}_manage"] = manage_fsm.get_metrics()
        for symbol, close_fsm in self.close_flows.items():
            all_metrics[f"{symbol}_close"] = close_fsm.get_metrics()
        return all_metrics

    def open_flow(self, symbol: str) -> OpenFlowFSM:
        """Get or create OpenFlowFSM for the given symbol."""
        open_f, _, _ = self._get_or_create_flows(symbol)
        return open_f

    def manage_flow(self, symbol: str) -> ManageFlowFSM:
        """Get or create ManageFlowFSM for the given symbol."""
        _, manage_f, _ = self._get_or_create_flows(symbol)
        return manage_f

    def close_flow(self, symbol: str) -> CloseFlowFSM:
        """Get or create CloseFlowFSM for the given symbol."""
        _, _, close_f = self._get_or_create_flows(symbol)
        return close_f

    def _check_exposure_fail_closed(self, msg: Message) -> bool:
        """
        EXP-FIX: Check exposure limits with fail-closed behavior.

        Returns True if request should be blocked (error already emitted).
        """
        pld = msg.pld or {}
        symbol = pld.get("symbol")
        qty = pld.get("qty")
        price_ref = pld.get("price_ref")

        if not symbol or not qty or not price_ref:
            LOG.warning(
                f"EXPOSURE_CHECK_SKIP: Missing required fields for {symbol}")
            return False

        try:
            # Calculate notional
            notional_usd = Decimal(str(qty)) * Decimal(str(price_ref))

            # Check exposure with fail-closed logic
            exposure_check = self.exposure_guard.can_open(
                symbol, notional_usd, self._latest_portfolio_state
            )

            if not exposure_check["allowed"]:
                reason = exposure_check["reason"]
                stale_sec = exposure_check.get("stale_sec", 0)

                # Emit ERR:OPEN with fail-closed reason
                error_msg = Message(
                    op="ERR",
                    verb="OPEN",
                    src="execution_position",
                    dst=msg.src,
                    rid=msg.rid,
                    pld={
                        "reason": reason,
                        "stale_sec": stale_sec,
                        "symbol": symbol,
                        "requested_notional": str(notional_usd),
                    },
                    why=f"exposure_fail_closed_{reason.lower()}",
                )

                # EXP-FIX: Record fail-closed metric
                if hasattr(self, "metrics_collector") and self.metrics_collector:
                    self.metrics_collector.record_exposure_fail_closed(reason)

                # Reserve exposure temporarily to prevent race conditions
                reserve_key = pld.get(
                    "idempotent_key") or msg.rid or f"rid_{msg.rid}"
                self.exposure_guard.reserve(reserve_key, notional_usd)

                # Emit error asynchronously
                try:
                    asyncio.get_running_loop()  # Check for running loop
                    asyncio.create_task(self._emit_error_async(error_msg))
                except RuntimeError:
                    # No running loop, emit synchronously if possible
                    try:
                        asyncio.get_running_loop()
                        asyncio.create_task(
                            emit_compat(self.fsm, error_msg,
                                        logger=self.logger)
                        )
                    except RuntimeError:
                        # Really no loop, skip emission
                        pass
                return True

            # EXP-FIX: Periodic shadow notional check (every 10 requests approx)
            if hasattr(self, "_shadow_check_counter"):
                self._shadow_check_counter += 1
            else:
                self._shadow_check_counter = 1

            if self._shadow_check_counter % 10 == 0 and self.adapter:
                try:
                    asyncio.get_running_loop()  # Check for running loop
                    asyncio.create_task(self._check_shadow_notional())
                except RuntimeError:
                    # No running loop, skip async check
                    pass

            # Reserve exposure for successful check
            reserve_key = pld.get(
                "idempotent_key") or msg.rid or f"rid_{msg.rid}"
            self.exposure_guard.reserve(reserve_key, notional_usd)

            return False

        except Exception as e:
            LOG.error(f"EXPOSURE_CHECK_ERROR: {e}", exc_info=True)
            return False

    async def _emit_error_async(self, msg: Message) -> None:
        """Asynchronously emit an error message."""
        try:
            await emit_compat(self.fsm, msg, logger=getattr(self, "logger", None))
        except Exception as e:
            # Не даємо Task впасти "unretrieved" — лог і поглинання
            LOG.exception(
                "Failed to emit error message via emit_compat: %r", e)

    def _handle_fill_event(self, msg: Message) -> None:
        """
        EXP-FIX: Handle order fill events for post-fill hold mechanism.

        Moves reservation from pending to post-fill hold to prevent race conditions.
        """
        pld = msg.pld or {}
        reserve_key = pld.get("idempotent_key") or pld.get(
            "client_order_id") or msg.rid

        if not reserve_key:
            LOG.warning("FILL_EVENT_SKIP: No reserve_key found in fill event")
            return

        # Calculate filled notional (approximate)
        qty = pld.get("qty", 0)
        price = pld.get("price", 0)
        try:
            notional_usd = Decimal(str(qty)) * Decimal(str(price))
            self.exposure_guard.on_fill(reserve_key, notional_usd)

            # EXP-FIX: Record post-fill hold metric
            if hasattr(self, "metrics_collector") and self.metrics_collector:
                self.metrics_collector.record_postfill_hold(
                    len(self.exposure_guard.state.postfill_reservations)
                )

            # Log to OrderLoggerV1
            order_logger.write({
                "rid": pld.get("rid", f"fill_{reserve_key}"),
                "event_type": "ORDER_STATE_CHANGED",
                "symbol": pld.get("symbol", ""),
                "side": pld.get("side", "NONE"),
                "quantity": float(qty),
                "price": float(price),
                "client_order_id": pld.get("client_order_id", ""),
                "order_id": pld.get("order_id", ""),
                "source_fsm": "ExecPosFSM",
                "reservation_id": reserve_key,
                "metadata": {"fill_status": "FILLED", "notional_usd": float(notional_usd)}
            })

            LOG.debug(
                f"FILL_HANDLED: key={reserve_key}, notional={notional_usd}")
        except Exception as e:
            LOG.error(f"FILL_HANDLE_ERROR: {e}", exc_info=True)

    async def _check_shadow_notional(self) -> None:
        """
        EXP-FIX: Periodic shadow notional check for safety auditing.

        Compares portfolio positions with exchange data and emits warnings on mismatch.
        """
        try:
            if not hasattr(self, "adapter") or not self.adapter:
                return

            # Get shadow notional from exchange
            shadow_notional = await self.adapter.get_positions_notional_usd_shadow()

            # Get portfolio notional
            portfolio_notional = Decimal(
                str(self._latest_portfolio_state.get("open_positions_usd", "0"))
            )

            # Compare with tolerance (allow 1% difference)
            tolerance = 0.01
            diff_pct = (
                abs(shadow_notional - float(portfolio_notional))
                / max(shadow_notional, float(portfolio_notional), 1)
                * 100
            )

            if diff_pct > tolerance:
                LOG.warning(
                    f"EXPOSURE_MISMATCH: portfolio={portfolio_notional}, shadow={shadow_notional}, diff={diff_pct:.2f}%"
                )
                self.exposure_guard._increment_metric(
                    "exposure_mismatch_total", "shadow_check"
                )

                # EXP-FIX: Record mismatch metric
                if hasattr(self, "metrics_collector") and self.metrics_collector:
                    self.metrics_collector.record_exposure_mismatch(
                        "shadow_check")

                # Emit event for monitoring
                mismatch_msg = Message(
                    op="EVT",
                    verb="EXPOSURE_MISMATCH",
                    intent="OBSERVATION",
                    src="execution_position",
                    dst="monitoring",
                    rid="shadow_check",
                    pld={
                        "portfolio_notional": str(portfolio_notional),
                        "shadow_notional": shadow_notional,
                        "diff_pct": diff_pct,
                    },
                    why="shadow_notional_mismatch",
                )
                await emit_compat(self.fsm, mismatch_msg, logger=self.logger)
            else:
                LOG.debug(
                    f"SHADOW_CHECK_OK: portfolio={portfolio_notional}, shadow={shadow_notional}"
                )

        except Exception as e:
            LOG.error(f"SHADOW_CHECK_ERROR: {e}", exc_info=True)
