#!/usr/bin/env python3
"""
Diagnostic script to verify flip orchestration config loading in backtest.

Run: python3 tools/verify_flip_config.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from apps.reference.config_loader import ConfigLoader


def main():
    print("=" * 60)
    print("FLIP ORCHESTRATION CONFIG VERIFICATION")
    print("=" * 60)
    
    loader = ConfigLoader()
    config = loader.load_config()
    
    # Get trading mode
    trading_mode = getattr(config, "trading_mode", "UNKNOWN")
    print(f"\n📋 Trading Mode: {trading_mode}")
    
    # Get flip config from decision_making domain
    dm_cfg = config.domains.decision_making
    flip_cfg = dm_cfg.flip
    
    print(f"\n🔄 Flip Orchestration Config:")
    print(f"   flip.enabled:        {flip_cfg.enabled}")
    print(f"   flip.hysteresis_mult: {flip_cfg.hysteresis_mult}")
    
    # Expected backtest values
    if trading_mode.lower() == "backtest":
        print(f"\n✅ Backtest mode detected - verifying overlay applied:")
        
        if flip_cfg.hysteresis_mult == 2.5:
            print(f"   ✅ hysteresis_mult=2.5 (from backtest_override.yaml)")
        else:
            print(f"   ❌ hysteresis_mult={flip_cfg.hysteresis_mult} (expected 2.5)")
            
        if flip_cfg.enabled is True:
            print(f"   ✅ enabled=True")
        else:
            print(f"   ❌ enabled={flip_cfg.enabled}")
            
        # Check other backtest overrides
        print(f"\n📊 Other Backtest Overrides:")
        print(f"   risk_skew.max_skew_sec:         {dm_cfg.risk_skew.max_skew_sec} (expected 999999)")
        print(f"   directional_sanity.enabled:    {dm_cfg.directional_sanity.enabled} (expected False)")
        print(f"   price_motion_sanity.enabled:   {dm_cfg.price_motion_sanity.enabled} (expected False)")
        print(f"   qos.symbol_cooldown_sec:       {dm_cfg.qos.symbol_cooldown_sec} (expected 10)")
    else:
        print(f"\n⚠️  Live mode detected - overlay should NOT be applied")
        if flip_cfg.hysteresis_mult == 2.5:
            print(f"   ⚠️  WARNING: hysteresis_mult=2.5 in live mode!")
        else:
            print(f"   ✅ hysteresis_mult={flip_cfg.hysteresis_mult} (base config)")
    
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
