#!/usr/bin/env python3
"""
CLI Tool to audit Algo Orders consistency between local state and Binance.
Usage: python tools/audit_algo_orders.py [--symbol BTCUSDT] [--config configs/execution_testnet_algo.yaml]
"""

from apps.reference.domains.execution_position.binance_execution_adapter import BinanceExecutionAdapter
from apps.reference.config_loader import ConfigLoader
import asyncio
import argparse
import sys
import os
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(
        description="Audit Algo Orders Consistency")
    parser.add_argument("--symbol", type=str,
                        help="Symbol to audit (e.g., BTCUSDT)")
    parser.add_argument("--config", type=str,
                        help="Path to config file", default=None)
    args = parser.parse_args()

    # Load Config
    logger.info("Loading configuration...")
    loader = ConfigLoader()
    # If specific config file provided, we might need to hack ConfigLoader or set env var
    # For now, we rely on standard loading or env vars.
    # If args.config is passed, we assume the user wants to use that specific file.
    # ConfigLoader usually looks at CONFIG_PATH env var.
    if args.config:
        os.environ["CONFIG_PATH"] = args.config

    try:
        config = loader.load_config()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    # Initialize Adapter
    logger.info("Initializing BinanceExecutionAdapter...")
    adapter = BinanceExecutionAdapter(config=config)

    if not adapter.use_algo_service_for_conditionals:
        logger.warning("Algo Service is DISABLED in this configuration.")
        logger.warning(
            "Use --config configs/execution_testnet_algo.yaml to enable.")
        # We continue anyway to show the "disabled" message from audit

    # Start Adapter (for time sync)
    # adapter.start() # Starts WS, which we might not need for simple audit, but we need time sync
    # We can just call audit, it does time sync internally.

    # Run Audit
    logger.info(f"Running audit for symbol: {args.symbol or 'ALL'}...")
    report = await adapter.audit_algo_orders_consistency(symbol=args.symbol)

    # Print Report
    print("\n" + "="*50)
    print("ALGO ORDER AUDIT REPORT")
    print("="*50)
    print(f"Consistent: {report.get('is_consistent')}")

    if not report.get('is_consistent'):
        print(f"\n[!] INCONSISTENCIES FOUND:")
        print(
            f"Missing Local (On Binance, not here): {report.get('missing_local')}")
        print(
            f"Missing Remote (Here, not on Binance): {report.get('missing_remote')}")
    else:
        print("\n[OK] Local and Remote states match.")

    if 'details' in report:
        print(f"\nDetails:")
        print(f"Remote Count: {report.get('remote_count')}")
        print(f"Local Count: {report.get('local_count')}")

    print("="*50 + "\n")

    # Cleanup
    # adapter.stop()

if __name__ == "__main__":
    asyncio.run(main())
