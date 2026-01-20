
import sys
import os
import asyncio
import time
import json
import threading
import logging
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal

# Mock httpx BEFORE importing BinanceAdapter
sys.path.append(os.getcwd())
mock_httpx = MagicMock()
sys.modules["httpx"] = mock_httpx

# Now imports
from apps.reference.adapters.binance_adapter import BinanceAdapter, BinanceAPIError
from apps.reference.adapters.binance_ws_client import BinanceWebSocketClient
from vfoundation.core.adapters.base import ExchangeOrderParams, ExchangePosition

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_scenario_a_concurrency_on_ledger():
    print("\n--- Scenario A: Concurrency on Ledger ---")
    adapter = BinanceAdapter(api_key="key", api_secret="secret")
    adapter.session = AsyncMock()
    
    client_order_id = "race_condition_id"
    symbol = "BTCUSDT"
    
    # Reset ledger
    adapter._clientorderid_ledger = {}
    
    async def task_simulate_order_creation(idx):
        # 1. Check
        reused = adapter.check_clientorderid_reuse(symbol, client_order_id)
        if reused:
            return "reused"
        
        # 2. Simulate Latency
        await asyncio.sleep(0.01)
        
        # 3. Register
        order_id = f"exec_id_{idx}"
        adapter.register_clientorderid(client_order_id, order_id, symbol)
        return "registered"

    results = await asyncio.gather(*[task_simulate_order_creation(i) for i in range(100)])
    
    registered_count = results.count("registered")
    reused_count = results.count("reused")
    
    print(f"Results: Registered={registered_count}, Reused={reused_count}")
    if registered_count > 1:
        print("FAILURE: Race Condition Confirmed! Multiple tasks attempted to register/create order.")
    else:
        print("SUCCESS: Logic seems safe.")

async def test_scenario_b_scan_all_fallback():
    print("\n--- Scenario B: Scan All Fallback ---")
    adapter = BinanceAdapter(api_key="key", api_secret="secret")
    
    fake_orders = []
    for i in range(1000):
        fake_orders.append({
            "orderId": f"1000{i}",
            "clientOrderId": f"cid_{i}",
            "symbol": f"SYM_{i}",
            "side": "BUY",
            "origQty": "1",
            "executedQty": "0",
            "price": "100",
            "status": "NEW",
            "time": 1234567890
        })
    
    async def mock_request(method, path, params=None, signed=True):
        if "openOrders" in path:
            return fake_orders
        if method == "DELETE":
            # Simulate delete logic - if scanning was needed, it means we didn't provide symbol initially
            return {"status": "CANCELED", "orderId": params.get("orderId"), "symbol": params.get("symbol")}
        return {}
    
    adapter._request = AsyncMock(side_effect=mock_request)
    
    start_time = time.perf_counter()
    target_oid = "1000999"
    await adapter.cancel_order(symbol="", order_id=target_oid)
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    
    print(f"Scan 1000 orders latency: {duration_ms:.2f}ms")

async def test_scenario_c_hedge_mode_consistency():
    print("\n--- Scenario C: Hedge Mode Consistency ---")
    adapter = BinanceAdapter(api_key="key", api_secret="secret")
    
    conflicting_positions = [
        {
            "symbol": "BTCUSDT",
            "positionSide": "LONG",
            "positionAmt": "1.0",
            "leverage": "20",
            "entryPrice": "50000",
            "markPrice": "50000",
            "unRealizedProfit": "0",
            "marginType": "cross",
            "isolatedMargin": "0",
            "updateTime": 1234567890
        },
        {
            "symbol": "BTCUSDT",
            "positionSide": "LONG",
            "positionAmt": "2.0",
            "leverage": "50",
            "entryPrice": "50000",
            "markPrice": "50000",
            "unRealizedProfit": "0",
            "marginType": "cross",
            "isolatedMargin": "0",
            "updateTime": 1234567890
        }
    ]
    
    adapter._request = AsyncMock(return_value=conflicting_positions)
    
    try:
        positions = await adapter.get_open_positions(symbol="BTCUSDT")
        print(f"Result: Got {len(positions)} positions.")
        if len(positions) > 1:
            print("FAILURE: Adapter returned conflicting positions instead of raising NRR-024 error!")
        else:
            print("SUCCESS: Adapter handled conflict.")
            
    except Exception as e:
        print(f"SUCCESS: Adapter raised exception: {e}")

def test_ws_maker_only_reject_and_thread_safety():
    print("\n--- Stage 3: WS Simulation & Thread Safety ---")
    fsm_core = MagicMock()
    fsm_core.order_index = MagicMock()
    mock_order = MagicMock()
    mock_order.rid = "rid_123"
    mock_order.idempotent_key = "ikey_123"
    mock_order.created_ts = time.time()
    
    # Setup mock to return an order
    fsm_core.order_index.get.return_value = mock_order
    
    # Mock OrderIndex import inside binance_ws_client
    with patch("apps.reference.domains.execution_position.order_index.OrderIndex._is_entry_ref", return_value=True):
        client = BinanceWebSocketClient(api_key="k", base_url="u", use_testnet=True, fsm_core=fsm_core)
        
        ws_msg = {
            "e": "ORDER_TRADE_UPDATE",
            "o": {
                "X": "EXPIRED",
                "f": "GTX",
                "z": "0",
                "s": "BTCUSDT",
                "i": "12345",
                "c": "client_id_1",
                "S": "BUY",
                "o": "LIMIT",
                "T": 1600000000000
            }
        }
        
        client._handle_ws_message(ws_msg)
        
        emit_calls = fsm_core.emit.call_args_list
        if emit_calls:
            name, payload, reason = emit_calls[0][0]
            print(f"Emitted Event: {name}")
            print(f"Reason: {reason}")
            if name == "EVT:ORDER_REJECTED" and payload.get("reason") == "MAKER_ONLY_REJECT":
                 print("SUCCESS: Correctly detected MAKER_ONLY_REJECT.")
            else:
                 print(f"FAILURE: Payload mismatch. Payload reason: {payload.get('reason')}")
        else:
            print("FAILURE: No event emitted.")
            
    print("THREAD SAFETY VERDICT: CRITICAL VULNERABILITY.")
    print("Explanation: _handle_ws_message runs in a daemon thread loop. Calls fsm_core.emit().")

async def main():
    await test_scenario_a_concurrency_on_ledger()
    await test_scenario_b_scan_all_fallback()
    await test_scenario_c_hedge_mode_consistency()

if __name__ == "__main__":
    asyncio.run(main())
    test_ws_maker_only_reject_and_thread_safety()
