
import asyncio
import threading
import time
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from vfoundation.core.protocol import Message
from apps.reference.main import AuroraBridge

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BridgeTest")

# Mock classes
class MockFSM:
    def listen(self, event, handler):
        pass
    def emit(self, event, pld, why, data_ref=None):
        logger.info(f"FSM emitted: {event}")

class MockExecPosFSM:
    def __init__(self):
        self.handle_called = False
        self.loop = None
        
    def set_async_loop(self, loop):
        self.loop = loop
        
    def handle(self, msg):
        logger.info(f"ExecPosFSM.handle called with {msg.verb}")
        self.handle_called = True
        
        # Simulate scheduling async work
        if self.loop:
            asyncio.run_coroutine_threadsafe(self._async_work(), self.loop)
        return Message(op="DEC", verb="OPEN", pld={})

    async def _async_work(self):
        logger.info("ExecPosFSM async work started")
        await asyncio.sleep(0.1)
        logger.info("ExecPosFSM async work finished")

def test_bridge_from_thread():
    # Setup async loop (Guardian Loop)
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    
    # Setup mocks
    fsm = MockFSM()
    config = {"position_tracking": {"positions_stale_ttl_sec": 60}}
    bridge = AuroraBridge(fsm, config)
    
    # Inject mock execution_position into main module namespace (hacky but needed for the test)
    import apps.reference.main
    apps.reference.main.execution_position = MockExecPosFSM()
    apps.reference.main.execution_position.set_async_loop(loop)
    
    # Simulate fresh portfolio
    bridge._last_portfolio_ts = int(time.time() * 1000)
    
    # Define the test function to run in a separate thread
    def consumer_thread_func():
        logger.info("Consumer thread started")
        
        # Create trade intent
        intent = Message(
            op="EVT",
            verb="TRADE_INTENT_PROPOSED",
            src="decision_making",
            dst="bridge",
            pld={
                "instrument": "BTCUSDT",
                "side": "BUY",
                "order": {"qty": "0.001", "price": "50000"}
            }
        )
        
        # Call the sync handler (as main.py does)
        bridge.on_trade_intent_proposed_sync(intent)
        logger.info("Consumer thread finished")

    # Run the test
    t = threading.Thread(target=consumer_thread_func)
    t.start()
    t.join()
    
    # Verify
    time.sleep(0.5) # Wait for async work
    
    if apps.reference.main.execution_position.handle_called:
        logger.info("✅ ExecPosFSM.handle was called")
    else:
        logger.error("❌ ExecPosFSM.handle was NOT called")
        
    loop.call_soon_threadsafe(loop.stop)
    loop_thread.join()

if __name__ == "__main__":
    test_bridge_from_thread()
