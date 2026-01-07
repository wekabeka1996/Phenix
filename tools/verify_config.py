#!/usr/bin/env python3
"""Quick config verification"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.getcwd())

from apps.reference.config_loader import ConfigLoader

try:
    c = ConfigLoader().load_config()
    print(f"✅ Config loaded: mode={c.trading_mode}")
    
    # Verify AccountObserver market_type
    observer_cfg = c.domains.account_observer
    print(f"✅ AccountObserver market_type: {getattr(observer_cfg, 'market_type', 'UNKNOWN')}")
    
    # Generic checks
    if c.trading_mode == "testnet":
         print(f"✅ Signal threshold (testnet): {c.strategies.aurora.decision.testnet.signal_threshold}")
    
    print("✅ ALL GOOD - READY TO LAUNCH")
except Exception as e:
    print(f"❌ Config Validation Failed: {e}")
    sys.exit(1)
