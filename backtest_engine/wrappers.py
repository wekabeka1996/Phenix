from apps.reference.domains.execution_position.fsm import ExecPosFSM
from backtest_engine.mock_broker import MockBroker
from vfoundation.core.protocol import Message

import asyncio
import concurrent.futures
from typing import Any, Coroutine, Optional, Set

# DET-BT-09: Use MockClock for determinism
from apps.reference.core.time import get_clock


class BacktestExecPosFSM(ExecPosFSM):
    """
    Safe wrapper for Backtest mode.
    Overrides _initialize_adapter to FORCE usage of MockBroker.
    Guarantees NO connection to real Binance API.
    
    DET-BT-09: Disables watchdog async loop to eliminate race condition
    between simulated time (MockClock) and real asyncio.sleep().
    
    DET-BT-14: Adds tick-barrier synchronization via drain_pending_tasks()
    to ensure all async tasks complete before next bar is processed.
    """
    
    def __init__(self, *args, **kwargs):
        # DET-BT-14: Track pending async tasks for tick-barrier
        self._pending_tasks: Set[asyncio.Task] = set()
        # DET-BT-15: Track cross-thread futures for tick-barrier
        self._pending_futures: Set[concurrent.futures.Future] = set()
        super().__init__(*args, **kwargs)

    def _initialize_adapter(self):
        print("🛡️ [BacktestWrapper] INTERCEPTED: Initializing MockBroker (Offline Mode)")
        initial_balance = 10000.0
        try:
            if getattr(self.config, "trading", None) and getattr(self.config.trading, "backtest", None):
                initial_balance = float(self.config.trading.backtest.initial_balance)
        except Exception:
            pass

        self.adapter = MockBroker(initial_balance_usdt=initial_balance)

        # Wire adapter back into the system for event emission + correlation lookup.
        # (Backtest uses FSMCore, not real exchange/websocket)
        try:
            self.adapter.exec_fsm = self
            self.adapter.fsm_core = self.fsm
        except Exception:
            pass

        # Force "Live" behavior for event processing, but using Mock adapter
        self.shadow_mode = False
        
        # DET-BT-09: Disable watchdog async loop for determinism
        # Watchdog uses asyncio.sleep() which causes race with simulated time
        self._disable_watchdog_loop()

    def _disable_watchdog_loop(self) -> None:
        """
        DET-BT-09: Disable watchdog async loop in backtest.
        
        The watchdog uses asyncio.sleep() (wall-clock) but checks deadlines
        using get_clock().now_ms() (simulated time). This creates a race:
        - Engine processes 100+ bars in <1 real second
        - Watchdog wakes after real 1s, finds unpredictable state
        - Result: bimodal behavior (8 vs 166 trades)
        
        In backtest, MockBroker does sync fills, so timeout watchdog is unnecessary.
        """
        if hasattr(self, 'watchdog') and self.watchdog is not None:
            self.watchdog.disable()
            print("🔇 [BacktestWrapper] Watchdog async loop DISABLED for determinism")

    def _submit_async(
        self,
        coro: Coroutine[Any, Any, Any],
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """
        DET-BT-14: Override to track pending tasks for tick-barrier.
        
        Parent schedules the coroutine; we additionally track it so
        drain_pending_tasks() can wait for completion.
        """
        target_loop = loop or self._get_async_loop()
        if not target_loop:
            return
        
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        
        if running_loop is target_loop:
            task = target_loop.create_task(coro)
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)
        else:
            # Cross-thread scheduling - track the future for drain
            future = asyncio.run_coroutine_threadsafe(coro, target_loop)
            self._pending_futures.add(future)
            # Clean up when done (not blocking)
            def _cleanup_future(f):
                self._pending_futures.discard(f)
            future.add_done_callback(_cleanup_future)

    def drain_pending_tasks(self) -> None:
        """
        DET-BT-14: TICK-BARRIER for deterministic backtest.
        
        Blocks until all pending async tasks from this FSM are complete.
        Called by BacktestEngine after each bar to ensure deterministic ordering.
        
        This eliminates non-determinism from async task completion order.
        """
        loop = self._get_async_loop()
        if not loop:
            return
        
        # Handle cross-thread futures first (these block synchronously)
        pending_futures = list(self._pending_futures)
        for future in pending_futures:
            try:
                if not future.done():
                    future.result(timeout=5.0)  # Block until done
            except Exception:
                pass
        self._pending_futures.clear()
        
        if not self._pending_tasks:
            return
        
        # Remove already-done tasks
        pending = {t for t in self._pending_tasks if not t.done()}
        if not pending:
            return
        
        # Wait for all pending tasks with a small timeout
        # Using asyncio.sleep(0) style drain
        try:
            async def _drain():
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            
            # Schedule drain and wait synchronously
            future = asyncio.run_coroutine_threadsafe(_drain(), loop)
            future.result(timeout=5.0)  # Max 5s wait
        except Exception:
            pass
        
        # Clear completed tasks
        self._pending_tasks = {t for t in self._pending_tasks if not t.done()}

    def _on_order_fill(self, event: Message) -> None:
        """Backtest-only shim to keep ExposureGuard postfill reservations schema-consistent."""
        super()._on_order_fill(event)
        try:
            ttl = 5.0
            try:
                exp_cfg = self.config.trading.execution.exposure
                ttl = float(getattr(exp_cfg, "post_fill_hold_ttl_sec", ttl) or ttl)
            except Exception:
                pass

            # DET-BT-09: Use MockClock instead of wall-clock
            now = get_clock().now_sec()
            state = getattr(self.exposure_guard, "state", None)
            postfill = getattr(state, "postfill_reservations", None)
            if not isinstance(postfill, dict):
                return

            for item in postfill.values():
                if not isinstance(item, dict):
                    continue
                if "exp_ts" in item:
                    continue
                ts_ms = item.get("ts_ms")
                base_ts = (float(ts_ms) / 1000.0) if ts_ms is not None else now
                item["exp_ts"] = base_ts + ttl
        except Exception:
            pass
