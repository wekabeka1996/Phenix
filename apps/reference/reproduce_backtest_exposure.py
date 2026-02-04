
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
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.config_loader import ConfigLoader

# Setup logging
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("Reproduction")

# Mock classes
class MockClock:
    def now_sec(self): return 1700000000.0
    def now_ms(self): return 1700000000000

def _run_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def test_exposure_chain_with_loop():
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
        LOG.info("Initializing ExecPosFSM...")
        try:
             # Use shadow_mode=False but intercept adapter init?
             # Or just allow it to fail strict init and monkeypatch adapter?
             # ExecPosFSM init is strict.
             # We use shadow_mode=True to avoid adapter, but then we must enabled emission.
             # ExecPosFSM code: if not self.shadow_mode: _initialize_adapter().
             # But emission of EXPOSURE is in _on_portfolio_state_updated, which runs regardless of shadow_mode?
             # Let's check logic. Yes, _on_portfolio_state_updated doesn't check shadow_mode.
             
             exec_pos = ExecPosFSM(config=config, fsm=fsm, shadow_mode=True)
             exec_pos.set_async_loop(loop)
             # Mock exposure_guard if needed? It's created in init.
             
        except Exception as e:
             LOG.warning(f"ExecPosFSM init warning: {e}", exc_info=True)
             raise

        LOG.info("Initializing DecisionMaking...")
        dm = DecisionMaking(fsm=fsm, config=config, clock=MockClock())
        
        # Register DM listener (it does it in init but we want to be sure)
        # It IS registered in init.
        
        LOG.info("Checking initial cache state...")
        if dm._exposure_cache is None:
            LOG.info("Cache is initially None (Correct)")
        else:
            LOG.error("Cache is NOT None initially!")

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
        
        LOG.info("Checking cache state IMMEDIATELY after emit (Race Check)...")
        if dm._exposure_cache:
            LOG.info(f"✅ Cache populated immediately (Fast local?)")
        else:
            LOG.info("ℹ️ Cache not yet populated (Expected valid race)")
            
        # Drain / Wait
        LOG.info("Waiting for async task...")
        time.sleep(1) # Simple wait to simulate drain
        
        LOG.info("Checking cache state after wait...")
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
    test_exposure_chain_with_loop()
