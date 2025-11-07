from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter
import time
import sys
sys.path.insert(0, '.')


class MockOrderRef:
    def __init__(self):
        self.rid = "test-rid-123"
        self.idempotent_key = "test-idem-key"
        self.created_ts = time.time()


class MockOrderIndex:
    def get(self, clientOrderId=None, exchangeOrderId=None):
        print(
            f"MockOrderIndex.get called: clientOrderId={clientOrderId}, exchangeOrderId={exchangeOrderId}")
        return MockOrderRef()

    def mark_terminal(self, order_ref):
        pass


class MockFSMCore:
    def __init__(self):
        self.emitted_events = []
        self.order_index = None

    def emit(self, verb, payload, why):
        print(f"EMIT: {verb}")
        self.emitted_events.append(
            {"verb": verb, "payload": payload, "why": why})


fsm_core = MockFSMCore()
adapter = BinanceExecutionAdapter(shadow_mode=True, fsm_core=fsm_core)

fsm_core.order_index = MockOrderIndex()

print(f"Has order_index: {hasattr(fsm_core, 'order_index')}")
print(f"order_index: {fsm_core.order_index}")

raw_event = {
    "e": "ORDER_TRADE_UPDATE",
    "E": 1568879465651,
    "T": 1568879465650,
    "o": {
        "s": "BTCUSDT",
        "c": "ENTRY-test",
        "S": "BUY",
        "o": "MARKET",
        "X": "FILLED",
        "i": 1234567890,
        "q": "0.01",
        "z": "0.01",
        "p": "0",
        "ap": "50000.0",
        "R": False,
        "cp": False,
    }
}

print("Calling _handle_order_trade_update...")
adapter._handle_order_trade_update(raw_event)

print(f"Emitted events: {len(fsm_core.emitted_events)}")
for evt in fsm_core.emitted_events:
    print(f"  - {evt['verb']}")
