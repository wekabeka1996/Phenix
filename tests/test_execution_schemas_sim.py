import pytest
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.schema_validator import patch_emit_validation

@pytest.mark.asyncio
async def test_execution_schemas_sim():
    fsm = FSMCore()
    patch_emit_validation(fsm)
    
    cmd_open_payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "0.1",
        "order_type": "MARKET",
        "idempotent_key": "sim_test_001",
        "strategy_id": "sim_tester",
        "target_price": "100000.0",
        "stop_price": "90000.0",
        "ts": 1700000000000
    }
    
    # CMD:OPEN
    fsm.emit("CMD:OPEN", payload=cmd_open_payload, why="sim_test")
    
    # EVT:ORDER_ACK
    evt_ack_payload = {
        "orderId": "ext_order_123",
        "symbol": "BTCUSDT",
        "status": "NEW",
        "clientOrderId": "sim_test_001",
        "rid": "sim_test_001"
    }
    fsm.emit("EVT:ORDER_ACK", payload=evt_ack_payload, why="sim_test")
    
    # EVT:ORDER_FILL
    evt_fill_payload = {
        "orderId": "ext_order_123",
        "symbol": "BTCUSDT",
        "status": "FILLED",
        "clientOrderId": "sim_test_001",
        "rid": "sim_test_001",
        "price": "95000.0",
        "quantity": "0.1",
        "commission": "0.05",
        "commissionAsset": "USDT",
        "tradeId": 999999
    }
    fsm.emit("EVT:ORDER_FILL", payload=evt_fill_payload, why="sim_test")

    # EVT:DEC_CLOSE_COMPLETED
    evt_close_payload = {
        "symbol": "BTCUSDT",
        "closed_qty": "0.1",
        "pnl": "50.0",
        "ts": 1700000001000
    }
    fsm.emit("EVT:DEC_CLOSE_COMPLETED", payload=evt_close_payload, why="sim_test")
