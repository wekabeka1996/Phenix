#!/usr/bin/env python3
"""
Test OrderGuardian cleanup loop directly.

This test initializes OrderGuardian with poll_interval_ms=500
to verify the cleanup loop starts and logs cleanup operations.
"""

from apps.reference.services.order_guardian import OrderGuardian
import asyncio
import logging
import time
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))


# Setup logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG to see poll loop iterations
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Also set order_guardian logger to DEBUG
logging.getLogger('order_guardian').setLevel(logging.DEBUG)

LOG = logging.getLogger(__name__)


async def test_guardian_cleanup_loop():
    """Test OrderGuardian cleanup loop functionality"""
    LOG.info("🔍 Starting OrderGuardian cleanup loop test")

    # Create OrderGuardian with polling enabled (poll_interval_ms=500)
    guardian = OrderGuardian(
        adapter=None,  # No adapter for this test
        poll_interval_ms=500,  # Enable polling
        bus=None
    )

    LOG.info("✅ OrderGuardian created with polling enabled")

    try:
        # Start the cleanup loop
        await guardian.start()
        LOG.info("✅ OrderGuardian cleanup loop started")

        # Wait a bit for the loop to run (should see poll_loop_start and cleanup_orphans logs)
        LOG.info("Waiting 3 seconds for cleanup loop operations...")
        await asyncio.sleep(3.0)

        LOG.info("✅ Test completed - check order_guardian.log for cleanup operations")

    except Exception as e:
        LOG.error(f"❌ Test failed: {e}")
        raise
    finally:
        # Stop the guardian
        await guardian.stop()
        LOG.info("✅ OrderGuardian stopped")

if __name__ == "__main__":
    asyncio.run(test_guardian_cleanup_loop())
