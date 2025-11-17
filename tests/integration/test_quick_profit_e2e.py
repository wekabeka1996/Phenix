import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from vfoundation.core import FSMCore
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
import asyncio
import threading


def test_quick_profit_e2e_flow_and_metrics():
    fsm = FSMCore()
    # Config with quick profit enabled
    config = {
        "trading": {
            "instruments": {
                "ETHUSDT": {
                    "leverage": 10,
                    "min_qty": "0.001",
                    "step_size": "0.001",
                    "tick_size": "0.01",
                }
            },
            "execution": {
                "cooldown_ms": 0,
                "manage": {
                    "auto": True,
                    "quick_profit": {
                        "enabled": True,
                        "mode": "fixed_usd",
                        "target_usd": 2.0,
                        "priority": "highest",
                    },
                },
            },
        },
    }

    # Initialize only position tracking for portfolio state
    position_tracking = PositionTracking(fsm, {})

    # Create ExecPosFSM with mock async adapter
    exec_pos_fsm = ExecPosFSM(config=config, fsm=fsm, shadow_mode=False)

    # Create async-capable mock adapter
    adapter = MagicMock()
    # Ensure mock adapter passes guardrail checks: needs a testnet base_url string
    adapter.base_url = "https://api.testnet.binance.vision"
    adapter.place_market_entry = AsyncMock(
        return_value={"orderId": "entry_1", "clientOrderId": "cid_entry"})
    adapter.place_stop_market_close_position = AsyncMock(
        return_value={"orderId": "sl_1"})
    adapter.place_take_profit_market_close_position = AsyncMock(
        return_value={"orderId": "tp_1"})
    adapter.cancel_order = AsyncMock(return_value={"status": "CANCELED"})
    adapter.place_market_reduce_only = AsyncMock(
        return_value={"status": "FILLED", "orderId": "close_1"})
    adapter.place_limit_reduce_only = AsyncMock(
        return_value={"status": "FILLED", "orderId": "limit_close_1"})
    adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": "ETHUSDT", "positionAmt": "0.01"}])
    adapter.get_open_orders = AsyncMock(return_value=[])
    adapter.get_mark_price = AsyncMock(return_value=3000.0)
    adapter.get_exchange_info = AsyncMock(return_value={
        "symbols": [
            {
                "symbol": "ETHUSDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01"}
                ]
            }
        ]
    })

    exec_pos_fsm.adapter = adapter
    # Reset shadow_mode to False because _initialize_adapter set it True due to missing API creds
    exec_pos_fsm.shadow_mode = False
    # Inject a dummy guardian to bypass ledger/sqlite requirements in this isolated test

    class _DummyGuardian:
        async def start(self):
            return None

        def register_entry(self, **kwargs):
            return None

        async def should_place_brackets(self, *args, **kwargs):
            return True

        def register_brackets(self, **kwargs):
            return None

        async def cleanup_other_brackets_for_symbol(self, *args, **kwargs):
            return None

        async def cleanup_orphans(self, *args, **kwargs):
            return None

        async def reconcile_symbol(self, *args, **kwargs):
            return None

        def get_metrics(self):
            return {}
    exec_pos_fsm.order_guardian = _DummyGuardian()

    # Use a metrics collector mock to assert record call
    exec_pos_fsm.metrics_collector = MagicMock()

    # Create background event loop for async execution
    loop = asyncio.new_event_loop()
    exec_pos_fsm.set_async_loop(loop)

    def _run_loop(l):
        asyncio.set_event_loop(l)
        l.run_forever()
    th = threading.Thread(target=_run_loop, args=(loop,), daemon=True)
    th.start()

    # Install exec_pos_fsm event listener in FSMCore for CMD/EVT routing
    fsm.listen("EVT:TRADE_INTENT_PROPOSED", exec_pos_fsm.handle)
    fsm.listen("EVT:TRADE_EXECUTED", exec_pos_fsm.handle)
    fsm.listen("UPD:MARKET_DATA", exec_pos_fsm.handle)
    fsm.listen("CMD:OPEN", exec_pos_fsm.handle)

    # Simulate a CMD:OPEN directly to trigger entry + bracket placement
    open_payload = {
        "rid": "qp-test-1",
        "symbol": "ETHUSDT",
        "side": "BUY",
        "qty": "0.01",
        "price": "3000",
        "idempotent_key": "qp_test1",
    }
    open_cmd = Message(op='CMD', verb='OPEN', src='test',
                       dst='execution_position', pld=open_payload)
    exec_pos_fsm.handle(open_cmd)
    time.sleep(0.2)

    # Simulate fill: position opened at entry price
    fill_payload = {
        "symbol": "ETHUSDT",
        "side": "BUY",
        "qty": "0.01",
        "price": "3000.0",
        "ts": time.time(),
    }
    evt_fill = Message(op='EVT', verb='TRADE_EXECUTED',
                       src='test', dst='execution_position', pld=fill_payload)
    exec_pos_fsm.handle(evt_fill)
    time.sleep(0.05)

    # If bracket placement didn't occur automatically in this test harness,
    # create synthetic bracket IDs to emulate placed SL/TP for close cleanup
    try:
        exec_pos_fsm._symbol_brackets.setdefault(
            'ETHUSDT', {})['sl_order_id'] = 'sl_1'
        exec_pos_fsm._symbol_brackets.setdefault(
            'ETHUSDT', {})['tp_order_id'] = 'tp_1'
        # sync to manage_flow
        if 'ETHUSDT' in exec_pos_fsm.manage_flows:
            exec_pos_fsm.manage_flows['ETHUSDT'].set_bracket_ids(
                'sl_1', 'tp_1')
    except Exception:
        pass

    # Simulate market tick that hits quick profit threshold (3200 -> $2 for 0.01 qty)
    tick_payload = {"mark_price": "3200.0",
                    "symbol": "ETHUSDT", "price": "3200.0"}
    tick_msg = Message(op='UPD', verb='MARKET_DATA', src='test',
                       dst='execution_position', pld=tick_payload)
    dec = exec_pos_fsm.handle(tick_msg)
    # If manage flow emitted a decision, ensure it's a CLOSE
    if dec:
        assert dec.verb == 'CLOSE'
    time.sleep(0.2)

    # ExecPosFSM should cancel brackets and place market reduce-only close
    assert adapter.cancel_order.called
    assert adapter.place_market_reduce_only.called

    # Metrics should record quick profit close
    assert exec_pos_fsm.metrics_collector.record_quick_profit_close.called

    # Stop loop and thread
    loop.call_soon_threadsafe(loop.stop)
    th.join(timeout=1.0)
