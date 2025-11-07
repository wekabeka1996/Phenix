import sys

sys.path.insert(0, ".")
sys.path.insert(0, "vfoundation")

# Test updated Binance adapter integration
from apps.reference.domains.execution_position.binance_execution_adapter import (
    BinanceExecutionAdapter,
)
from apps.reference.domains.execution_position.order_index import OrderIndex


# Create mock FSM core with order_index
class MockFSM:
    def __init__(self):
        self.order_index = OrderIndex()

    def emit(self, event, payload, why):
        print(
            f"EMIT: {event} - status={payload.get('status')}, rid={payload.get('rid')}"
        )


fsm = MockFSM()
adapter = BinanceExecutionAdapter(shadow_mode=True, fsm_core=fsm)

# Create correlation
ref = fsm.order_index.upsert_from_open(
    rid="test_rid",
    idempotent_key="test_key",
    clientOrderId="client123",
    symbol="BTCUSDT",
    side="BUY",
    order_type="MARKET",
)
print(f"Created correlation: {ref.rid} -> {ref.clientOrderId}")

# Test WebSocket message handling
test_msg = {
    "e": "ORDER_TRADE_UPDATE",
    "T": 1234567890000,
    "o": {
        "s": "BTCUSDT",
        "c": "client123",
        "i": "12345",
        "X": "FILLED",
        "z": "0.001",
        "p": "50000",
        "S": "BUY",
        "o": "MARKET",
    },
}

try:
    adapter._handle_order_trade_update(test_msg)
    print("FILLED message handling OK")
except Exception as e:
    print(f"Error: {e}")

# Check if order was marked terminal
found = fsm.order_index.get(rid="test_rid")
print(f"Order terminal: {found.terminal if found else None}")
