from apps.reference.domains.execution_position.fsm import ExecPosFSM
from backtest_engine.mock_broker import MockBroker
from vfoundation.core.protocol import Message

import time


class BacktestExecPosFSM(ExecPosFSM):
    """
    Safe wrapper for Backtest mode.
    Overrides _initialize_adapter to FORCE usage of MockBroker.
    Guarantees NO connection to real Binance API.
    """

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

            now = time.time()
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
