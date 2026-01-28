#!/usr/bin/env python3
"""Diagnostic script to verify flip orchestration config loading.

Backtest is expected to use the same SSOT config as live (no overlay layer).

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
    
    print("\nℹ️  Note: no backtest overlay layer is applied.")
    print("   Values should come directly from SSOT YAMLs under config/aurora/.")
    
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
