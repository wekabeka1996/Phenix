
import apps.reference.main
from apps.reference.domains.execution_position.runtime_factory import build_execution_runtime
from apps.reference.main import AuroraBridge, on_trade_intent_proposed, on_portfolio_state_updated
import asyncio
import threading
import time
import logging
import sys
from typing import Any, Dict

# Mock FSMCore


class MockFSMCore:
    def __init__(self):
        self.listeners = {}
        self.domains = {}

    def listen(self, event_name, callback):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def emit(self, event_name, payload, why, data_ref=None):
        print(f"[FSM] Emitting {event_name}")
        if event_name in self.listeners:
            msg = type('Message', (), {'op': 'EVT', 'verb': event_name.split(':')[
                       1], 'pld': payload, 'rid': 'test-rid', 'span_id': 'test-span', 'why': why, 'data_ref': data_ref or []})()
            for cb in self.listeners[event_name]:
                cb(msg)

# Mock Config


class MockConfig:
    def to_dict(self):
        return {
            "execution_position": {"runtime_mode": "v2"},
            "trading": {"mode": "testnet"},
            # Long TTL to ensure freshness
            "position_tracking": {"positions_stale_ttl_sec": 999}
        }

    def get(self, key, default=None):
        return self.to_dict().get(key, default)

    def get_domain_mode(self, domain):
        return "v2"

# Mock Adapter


class MockAdapter:
    async def place_order_v2(self, **kwargs):
        print(f"[MockAdapter] place_order_v2 called with {kwargs}")
        return {"success": True, "order_id": "123", "client_order_id": "abc"}

    async def get_open_orders(self, symbol=None):
        return []


# Setup Logging
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("AuroraCore")

# Import classes
sys.path.insert(0, "c:\\Users\\user\\Music\\Phenix")

# Global bridge instance hack
apps.reference.main.LOG = LOG


async def main():
    # 1. Setup Loop
    loop = asyncio.new_event_loop()

    def run_loop(l):
        asyncio.set_event_loop(l)
        l.run_forever()
    t = threading.Thread(target=run_loop, args=(loop,), daemon=True)
    t.start()
    asyncio.set_event_loop(loop)

    # 2. Setup FSM & Components
    fsm = MockFSMCore()
    config = MockConfig()

    # Initialize Bridge
    bridge = AuroraBridge(fsm=fsm, config=config.to_dict(), logger=LOG)
    apps.reference.main._bridge_instance = bridge

    # Initialize Runtime
    adapter = MockAdapter()
    execution_runtime = build_execution_runtime(config, fsm, adapter=adapter)
    # Inject into main module if needed, but main.py uses local var.
    apps.reference.main.execution_position = execution_runtime

    # Wait, AuroraBridge in main.py uses 'execution_position' global variable?
    # No, it uses 'execution_position' from the outer scope of 'main.py'.
    # But 'AuroraBridge' class doesn't reference 'execution_position'.
    # The '_dispatch_open' method in 'AuroraBridge' references 'execution_position'.
    # Wait, let's check AuroraBridge._dispatch_open in main.py again.

    # It says:
    # if execution_position is not None:
    #    result = execution_position.handle(open_command)

    # 'execution_position' is NOT a member of AuroraBridge. It's a GLOBAL variable in main.py?
    # Or is it captured in the closure?
    # AuroraBridge is a class. Methods cannot capture outer scope variables unless defined inside a function.
    # But AuroraBridge is defined at module level.
    # So it must be using the GLOBAL 'execution_position' variable.

    # So I need to set apps.reference.main.execution_position
    apps.reference.main.execution_position = execution_runtime

    # 3. Simulate Portfolio Update (to make it fresh)
    print("--- Simulating Portfolio Update ---")
    portfolio_payload = {"positions_last_ts_ms": int(time.time() * 1000)}
    fsm.emit("EVT:PORTFOLIO_STATE_UPDATED", portfolio_payload, "test")

    # Allow async tasks to run
    await asyncio.sleep(1)

    # 4. Simulate Trade Intent
    print("--- Simulating Trade Intent ---")
    intent_payload = {
        "instrument": "BTCUSDT",
        "side": "buy",
        "order": {"qty": "0.001", "price": "50000"},
        "idempotent_key": "test-key-1"
    }
    fsm.emit("EVT:TRADE_INTENT_PROPOSED", intent_payload, "test")

    # Allow async tasks to run
    await asyncio.sleep(2)

    print("--- Done ---")

if __name__ == "__main__":
    asyncio.run(main())
