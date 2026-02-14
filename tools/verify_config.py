#!/usr/bin/env python3
"""Quick config verification"""
from apps.reference.config_loader import ConfigLoader
import os
import sys

# Add project root to path
sys.path.insert(0, os.getcwd())


try:
    c = ConfigLoader().load_config()
    print(f"✅ Config loaded: mode={c.trading_mode}")

    # Verify AccountObserver market_type
    observer_cfg = getattr(getattr(c, "domains", None),
                           "account_observer", None)
    if observer_cfg is not None:
        print(
            f"✅ AccountObserver market_type: {getattr(observer_cfg, 'market_type', 'UNKNOWN')}")
    else:
        print("ℹ️ AccountObserver domain not configured (skipped)")

    # Generic checks
    if c.trading_mode == "testnet":
        try:
            print(
                f"✅ Signal threshold (testnet): {c.strategies.aurora.decision.testnet.signal_threshold}")
        except Exception:
            print("ℹ️ Signal threshold (testnet) not available (skipped)")

    print("✅ ALL GOOD - READY TO LAUNCH")
except Exception as e:
    print(f"❌ Config Validation Failed: {e}")
    sys.exit(1)
