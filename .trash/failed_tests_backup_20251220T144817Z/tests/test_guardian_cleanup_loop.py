#!/usr/bin/env python3
"""
Simple test to verify OrderGuardian cleanup loop is running
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG = logging.getLogger(__name__)


async def test_guardian_cleanup_loop():
    """Test that OrderGuardian cleanup loop runs and logs cleanup operations"""
    try:
        LOG.info("🔍 Starting OrderGuardian cleanup loop test")

        # Import required modules
        from apps.reference.domains.execution_position.fsm import ExecPosFSM
        from vfoundation.core.fsm_core import FSMCore

        # Create minimal config
        config = {
            "trading": {
                "mode": "testnet",
                "execution": {
                    "order_guardian": {
                        "poll_interval_ms": 500  # Fast polling for test
                    }
                }
            },
            "binance_api": {
                "testnet": {
                    "api_key": "test",
                    "api_secret": "test",
                    "rest_url": "https://testnet.binance.vision"
                }
            }
        }

        # Create FSM core (minimal)
        fsm_core = FSMCore()

        # Create ExecPosFSM (this should initialize and start OrderGuardian)
        LOG.info("Creating ExecPosFSM...")
        exec_fsm = ExecPosFSM(config=config, fsm=fsm_core, shadow_mode=True)
        LOG.info("✅ ExecPosFSM created")

        # Wait for cleanup loop to run (should see poll_loop_start and cleanup_orphans logs)
        LOG.info("Waiting 3 seconds for cleanup loop...")
        await asyncio.sleep(3.0)

        LOG.info("✅ Test completed - check logs for cleanup operations")

    except Exception as e:
        LOG.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_guardian_cleanup_loop())
    sys.exit(0 if success else 1)
