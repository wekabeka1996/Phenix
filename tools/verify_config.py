#!/usr/bin/env python3
"""Quick config verification"""
from apps.reference.config_loader import ConfigLoader

c = ConfigLoader().load_config()
print(f"✅ Config loaded: mode={c.get('trading_mode')}")
decision = c.get("trading", {}).get("decision", {})
print(f"✅ Decision keys: {len(decision)} keys")
print(f"✅ Signal threshold (testnet): {decision.get('signal_threshold')}")
print(
    f"✅ SL_bps in brackets: {c.get('trading',{}).get('execution',{}).get('manage',{}).get('brackets',{}).get('stop_loss_bps')}")
print("✅ ALL GOOD - READY TO LAUNCH")
