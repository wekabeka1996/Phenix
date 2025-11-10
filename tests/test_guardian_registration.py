#!/usr/bin/env python3
"""
Test OrderGuardian registration logging.
"""

from apps.reference.services.order_guardian import OrderGuardian
import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

LOG = logging.getLogger(__name__)


async def test_guardian_registration():
    """Test OrderGuardian registration logging"""
    LOG.info("🔍 Testing OrderGuardian registration logging")

    # Create OrderGuardian
    guardian = OrderGuardian(
        adapter=None,
        poll_interval_ms=0,  # Disable polling
        bus=None
    )

    LOG.info("✅ OrderGuardian created")

    # Register an entry order
    guardian.register_entry(
        symbol="BTCUSDT",
        order_id="123456",
        client_order_id="client_123456",
        side="BUY",
        qty=0.001,
        corr_id="test_corr_001",
        rid="test_rid_001"
    )

    # Register SL bracket
    guardian.register_bracket(
        symbol="BTCUSDT",
        parent_order_id="123456",
        order_id="123457",
        client_order_id="client_123457",
        kind="SL",
        corr_id="test_corr_001",
        rid="test_rid_001"
    )

    # Register TP bracket
    guardian.register_bracket(
        symbol="BTCUSDT",
        parent_order_id="123456",
        order_id="123458",
        client_order_id="client_123458",
        kind="TP",
        corr_id="test_corr_001",
        rid="test_rid_001"
    )

    LOG.info("✅ Registration test completed - check logs for detailed order IDs")

if __name__ == "__main__":
    asyncio.run(test_guardian_registration())
