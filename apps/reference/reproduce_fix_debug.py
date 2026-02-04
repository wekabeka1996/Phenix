
import sys
from pathlib import Path
import logging
import asyncio
import threading
import time

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from vfoundation.core import FSMCore, Message
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.config_loader import ConfigLoader
from backtest_engine.wrappers import BacktestExecPosFSM
from apps.reference.domains.execution_position.fsm import ExecPosFSM

# Setup logging
logging.basicConfig(level=logging.DEBUG) 
logging.getLogger("polars").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
LOG = logging.getLogger("Reproduction")

# Mock classes
class MockClock:
    def now_sec(self): return 1700000000.0
    def now_ms(self): return 1700000000000

def _run_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def test_exposure_chain_fixed_debug():
    try:
        LOG.info("Loading config...")
        config_path = project_root / "config" / "aurora"
        config_loader = ConfigLoader(config_dir=config_path)
        config = config_loader.load_config()
        
        fsm = FSMCore()
        
        # Start loop
        loop = asyncio.new_event_loop()
        t = threading.Thread(target=_run_async_loop, args=(loop,), daemon=True)
        t.start()
        
        # Initialize domains
        LOG.info("Initializing BacktestExecPosFSM...")
        try:
             exec_pos = BacktestExecPosFSM(config=config, fsm=fsm, shadow_mode=False)
             exec_pos.set_async_loop(loop)
             
             # MONKEYPATCH to trace calls
             original_submit = exec_pos._submit_async
             def trace_submit(coro, loop=None):
                 LOG.info(f"🕵️ _submit_async called with coro={coro}, loop={loop}")
                 original_submit(coro, loop)
                 LOG.info(f"   Pending tasks count: {len(exec_pos._pending_tasks)}")
                 LOG.info(f"   Pending futures count: {len(exec_pos._pending_futures)}")
             exec_pos._submit_async = trace_submit

             original_drain = exec_pos.drain_pending_tasks
             def trace_drain():
                 LOG.info(f"🕵️ drain_pending_tasks called. Pending: {len(exec_pos._pending_tasks)} tasks, {len(exec_pos._pending_futures)} futures")
                 original_drain()
                 LOG.info("   Drain finished.")
             exec_pos.drain_pending_tasks = trace_drain

        except Exception as e:
             LOG.warning(f"BacktestExecPosFSM init warning: {e}", exc_info=True)
             raise

        dm = DecisionMaking(fsm=fsm, config=config, clock=MockClock())
        
        # Monitor cache updates
        def on_exposure_cache_update(event):
            LOG.info(f"🔥 CACHE UPDATE RECEIVED: {event.pld.keys()}")
            
        fsm.listen("EVT:EXPOSURE_SUMMARY_UPDATED", on_exposure_cache_update)

        # Create portfolio payload
        payload = {
            "balances": [{"asset": "USDT", "balance": "10000"}],
            "positions": [],
            "event_time_ms": 1700000000000,
            "positions_last_ts_ms": 1700000000000,
            "open_positions_usd": "0",
            "open_positions_margin_usd": "0",
            "equity": "10000",
            "equity_free_usdt": "10000",
            "equity_cross_usdt": "10000",
            "margin": "0",
        }
        
        LOG.info("Emitting EVT:PORTFOLIO_STATE_UPDATED...")
        fsm.emit("EVT:PORTFOLIO_STATE_UPDATED", payload, "test")
        
        LOG.info("Applying FIX barrier: calling drain_pending_tasks()...")
        if hasattr(exec_pos, "drain_pending_tasks"):
             exec_pos.drain_pending_tasks()
        else:
             LOG.error("No drain method!")

        LOG.info("Checking cache state after barrier...")
        if dm._exposure_cache:
            LOG.info(f"✅ Cache populated: {len(dm._exposure_cache)} symbols")
        else:
            LOG.error("❌ Cache still None/Empty!")
            
    except Exception as e:
        LOG.error(f"Test failed: {e}", exc_info=True)
    finally:
        if 'loop' in locals():
            loop.call_soon_threadsafe(loop.stop)

if __name__ == "__main__":
    test_exposure_chain_fixed_debug()
