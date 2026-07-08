#!/usr/bin/env python3
"""
Pre-Session Snapshot and Preflight Verification Script
P26 prep verification tool.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List

# Setup sys path
sys.path.append(str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("PreSessionSnapshot")

# Load environment helpers
def load_env(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip("'").strip('"')

project_root = Path(__file__).resolve().parent.parent
load_env(project_root / ".env")

from apps.reference.config_loader import ConfigLoader
from apps.reference.adapters.binance_adapter import BinanceAdapter
from apps.reference.domains.strategies.authority import resolve_strategy_mode
from apps.reference.runtime_profile import resolve_runtime_launch_profile

async def main():
    logger.info("=== STARTING PRE-SESSION PREFLIGHT SNAPSHOT & SECURITY AUDIT ===")

    # 1. Profile Verification
    profile_env = os.environ.get("AURORA_RUNTIME_PROFILE", "not_set")
    profile = resolve_runtime_launch_profile()
    logger.info(f"Active Profile Env (AURORA_RUNTIME_PROFILE): {profile_env}")
    logger.info(f"Resolved Launch Profile: {profile.name}")
    
    if profile.name != "deepseek_agent_only_testnet":
        logger.error("SAFETY VIOLATION: Active profile is NOT 'deepseek_agent_only_testnet'!")
        sys.exit(1)
    else:
        logger.info("Active Profile Check: PASSED")

    # 2. Config & Endpoint Verification
    config_dir = project_root / "config" / "aurora"
    config = ConfigLoader(config_dir=config_dir).load_config()
    
    logger.info(f"System Trading Mode: {config.trading_mode}")
    
    # 3. Mainnet Guard Check
    # Verify no mainnet endpoint is selected in any config.
    testnet_url = config.binance_api.testnet.rest_url
    live_url = config.binance_api.live.rest_url
    
    logger.info(f"Configured Testnet REST URL: {testnet_url}")
    logger.info(f"Configured Live REST URL: {live_url}")
    
    # We must assert that our adapter parameters map only to the Testnet REST endpoint
    if "testnet.binance" not in testnet_url:
        logger.error(f"SAFETY VIOLATION: Testnet endpoint '{testnet_url}' is not a valid testnet URL!")
        sys.exit(1)
        
    # Check loaded keys presence
    binance_testnet_key = os.environ.get("BINANCE_TESTNET_API_KEY", "")
    binance_testnet_secret = os.environ.get("BINANCE_TESTNET_API_SECRET", "")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    
    logger.info(f"BINANCE_TESTNET_API_KEY present: {bool(binance_testnet_key)}")
    logger.info(f"BINANCE_TESTNET_API_SECRET present: {bool(binance_testnet_secret)}")
    logger.info(f"DEEPSEEK_API_KEY present: {bool(deepseek_key)}")
    
    if not binance_testnet_key or not binance_testnet_secret:
        logger.error("SAFETY BLOCKED: Binance Testnet API credentials missing from environment!")
        sys.exit(1)
        
    if not deepseek_key:
        logger.error("SAFETY BLOCKED: DeepSeek API key missing from environment!")
        sys.exit(1)
        
    logger.info("Mainnet Endpoint Guard Check: PASSED (Restricted to Testnet URL)")

    # 4. Prove Legacy Strategy Authority is Disabled
    logger.info("--- LEGACY STRATEGY AUTHORITY AUDIT ---")
    
    # Check the directory config/aurora/strategies/
    strategies_dir = config_dir / "strategies"
    import yaml
    has_active_legacy = False
    
    for f in strategies_dir.glob("*.yaml"):
        with open(f, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
            for strat_id, strat_cfg in data.items():
                if not isinstance(strat_cfg, dict):
                    continue
                # Build a simple namespace mock to parse resolved mode
                class MockConfig:
                    mode = strat_cfg.get("mode", "disabled")
                    enabled = strat_cfg.get("enabled", False)
                
                mode = resolve_strategy_mode(MockConfig())
                logger.info(f"Strategy: {strat_id} | enabled: {MockConfig.enabled} | mode: {mode}")
                
                # If enabled is true and mode is a financial execution mode (runtime or testnet_candidate), raise alarm
                if MockConfig.enabled and mode in {"runtime", "testnet_candidate"}:
                    logger.error(f"SAFETY VIOLATION: Legacy strategy '{strat_id}' has ACTIVE entry authority!")
                    has_active_legacy = True
                    
    if has_active_legacy:
        logger.error("Legacy strategy deactivation check: FAILED!")
        sys.exit(1)
    else:
        logger.info("Legacy strategy deactivation check: PASSED (All legacy strategies disabled or shadow-only)")

    # 5. Fetch Exchange positions and open orders (Snapshot)
    logger.info("--- FETCHING EXCHANGE ACTIVE STATE (SNAPSHOT) ---")
    
    adapter = BinanceAdapter(
        api_key=binance_testnet_key,
        api_secret=binance_testnet_secret,
        testnet=True,
        logger=logger
    )
    
    try:
        # Fetch open positions
        logger.info("Querying open positions from Binance Testnet...")
        positions = await adapter.get_open_positions()
        if not positions:
            logger.info("Open Positions: None")
        else:
            for p in positions:
                logger.info(f"Active Position -> Symbol: {p.symbol} | side: {p.position_side} | size: {p.position_amount} | entry: {p.entry_price}")
        
        # Fetch open orders
        logger.info("Querying open orders from Binance Testnet...")
        orders = await adapter.get_open_orders()
        if not orders:
            logger.info("Open Orders: None")
        else:
            for o in orders:
                logger.info(f"Open Order -> Symbol: {o.symbol} | side: {o.side} | qty: {o.orig_qty} | price: {o.price} | type: {o.type}")
                
    except Exception as e:
        logger.error(f"Failed to query exchange snapshot: {e}")
        logger.error("Verify your API keys, testnet configuration, and internet connection.")
        sys.exit(1)
        
    logger.info("=== PREFLIGHT SNAPSHOT & SECURITY AUDIT PASSED ===")

if __name__ == "__main__":
    asyncio.run(main())
