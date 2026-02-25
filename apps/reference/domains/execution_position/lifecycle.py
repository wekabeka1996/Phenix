"""
Lifecycle management for execution_position domain.

Extracted from ExecPosFSM (Phase 14A decomposition).
Handles adapter initialization, guardian scheduling, cleanup loops,
and startup reconciliation.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Set

from apps.reference.core.time import get_clock
from apps.reference.utils.accessors import aget, dget

if TYPE_CHECKING:
    pass

LOG = logging.getLogger(__name__)


class LifecycleManager:
    """Manages adapter initialization, guardian scheduling, and cleanup loops."""

    def __init__(self, fsm: Any) -> None:
        self._fsm = fsm

    def initialize_adapter(self) -> None:
        """Initialize the BinanceAdapter for live trading."""
        from apps.reference.adapters.binance_adapter import BinanceAdapter

        if self._fsm.shadow_mode:
            LOG.info("ExecPosFSM running in SHADOW mode — adapter not initialized")
            return

        if self._fsm.adapter is not None:
            LOG.info("ExecPosFSM adapter already initialized")
            return

        # Get API credentials from config
        api_cfg = getattr(self._fsm.config, "api", None)
        if api_cfg is None:
            LOG.error("No API config found — adapter not initialized")
            return

        api_key = getattr(api_cfg, "key", None) or getattr(api_cfg, "api_key", None)
        api_secret = getattr(api_cfg, "secret", None) or getattr(api_cfg, "api_secret", None)

        if not api_key or not api_secret:
            LOG.error("API key/secret missing — adapter not initialized")
            return

        # Determine if testnet
        testnet = bool(getattr(api_cfg, "testnet", False))
        base_url = getattr(api_cfg, "base_url", None)

        try:
            self._fsm.adapter = BinanceAdapter(
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet,
                base_url=base_url,
            )
            LOG.info(f"BinanceAdapter initialized (testnet={testnet})")
        except Exception as e:
            LOG.error(f"Failed to initialize BinanceAdapter: {e}")
            raise

    def schedule_guardian_start(self) -> None:
        """Schedule guardian startup once (idempotent)."""
        if self._fsm._guardian_started:
            return

        loop = self._fsm._get_async_loop()
        if loop:
            async def _start_guardian():
                try:
                    await self._fsm.order_guardian.start()
                    self._fsm._guardian_started = True
                    LOG.info("OrderGuardian started successfully")
                except Exception as e:
                    LOG.error(f"Failed to start OrderGuardian: {e}")

            self._fsm._submit_async(_start_guardian(), loop)
        else:
            LOG.warning("No event loop available to schedule guardian start")

    def schedule_fsm_cleanup_loop(self) -> None:
        """Start FSM cleanup loop (orphan order cleanup)."""
        if self._fsm._cleanup_loop_started:
            return

        loop = self._fsm._get_async_loop()
        if loop:
            self._fsm._submit_async(self.cleanup_loop(), loop)
            self._fsm._cleanup_loop_started = True
            LOG.info("FSM cleanup loop started")
        else:
            LOG.warning("No event loop available for cleanup loop")

    async def cleanup_loop(self) -> None:
        """Periodic orphaned-order cleanup loop (interval from config)."""
        while True:
            try:
                interval = int(self._fsm._orphan_cfg["periodic_interval_sec"])
                await get_clock().sleep_sec(interval)
                await self._fsm.order_guardian.cleanup_orphans()
                self._fsm._orphan_metrics["loops"] += 1
            except asyncio.CancelledError:
                self._fsm._orphan_metrics["errors"] += 1
            except Exception as e:
                LOG.debug(f"cleanup loop error: {e}")
                self._fsm._orphan_metrics["errors"] += 1

    async def startup_order_guardian_reconcile(self) -> None:
        """
        Startup reconciliation: Link existing orders and positions for OrderGuardian.
        """
        try:
            LOG.info("🔄 Starting OrderGuardian startup reconciliation...")

            if self._fsm.adapter:
                try:
                    positions = await self._fsm.adapter.get_open_positions()
                    symbols_with_positions = set()

                    positions_list = [
                        p.to_dict() if hasattr(p, 'to_dict') else (
                            p.__dict__ if not isinstance(p, dict) else p)
                        for p in positions
                    ]

                    for pos in positions_list:
                        symbol = pos.get("symbol")
                        if symbol:
                            symbols_with_positions.add(symbol)

                    all_orders = await self._fsm.adapter.get_open_orders()
                    orders_list = [
                        o.to_dict() if hasattr(o, 'to_dict') else (
                            o.__dict__ if not isinstance(o, dict) else o)
                        for o in all_orders
                    ]

                    for order in orders_list:
                        symbol = order.get("symbol")
                        if symbol:
                            symbols_with_positions.add(symbol)

                    symbols_with_positions.update(
                        self._fsm._collect_guardian_symbols())

                    for symbol in symbols_with_positions:
                        await self._fsm.order_guardian.link_existing_from_rest(symbol)
                        LOG.debug(f"✅ Linked existing orders for {symbol}")

                    LOG.info(
                        f"✅ Linked existing orders for {len(symbols_with_positions)} symbols")

                except Exception as e:
                    LOG.warning(
                        f"Failed to link existing orders during startup: {e}")

            await self._fsm.order_guardian.cleanup_orphans()
            LOG.info("✅ OrderGuardian startup reconciliation completed")
        except Exception as e:
            LOG.error(f"❌ OrderGuardian startup reconciliation failed: {e}")

    def resolve_guardian_config(self) -> Dict[str, Any]:
        """Aggregate guardian config from SSOT."""
        result = {}
        try:
            og_cfg = self._fsm.config.domains.execution_position.order_guardian
            result["unified_guardian"] = og_cfg.unified_guardian
            result["emit_tidy_event"] = og_cfg.emit_tidy_event
            result["cleanup_ttl_ms"] = og_cfg.cleanup_ttl_ms
            result["symbol_cooldown_ms"] = og_cfg.symbol_cooldown_ms
            result["max_cleanup_per_tick"] = og_cfg.max_cleanup_per_tick
        except (AttributeError, TypeError):
            result.setdefault("unified_guardian", True)
            result.setdefault("emit_tidy_event", True)
            result.setdefault("cleanup_ttl_ms", 6000)
            result.setdefault("symbol_cooldown_ms", 4000)
            result.setdefault("max_cleanup_per_tick", 10)
        return result

    def collect_guardian_symbols(self) -> Set[str]:
        """Gather configured symbols for OrderGuardian reconciliation."""
        symbols = set()
        try:
            aurora = getattr(self._fsm.config.strategies, "aurora", None)
            if aurora and aurora.assets:
                symbols.update(aurora.assets.keys())
        except AttributeError:
            pass
        try:
            mr = getattr(self._fsm.config.strategies, "mean_reversion", None)
            if mr and mr.assets:
                symbols.update(mr.assets.keys())
        except AttributeError:
            pass
        return symbols

    def start_order_guardian(self) -> None:
        """Start guardian after FSM init."""
        self.schedule_guardian_start()
        self.schedule_fsm_cleanup_loop()
