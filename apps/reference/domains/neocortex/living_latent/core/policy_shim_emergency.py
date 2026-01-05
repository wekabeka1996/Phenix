# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""
Policy Shim V2 - Production Emergency Controls
===========================================

Scripts for runtime management and emergency controls.
Hardened for production deployment with trigger files and env var controls.
"""

import os
import time
import json
from pathlib import Path
import argparse
from typing import Dict, Any

from ..core.policy_shim_hardened import policy_shim_hardened


def emergency_stop():
    """Emergency stop for Policy Shim"""
    policy_shim_hardened.emergency_stop()
    print("🛑 EMERGENCY STOP activated")
    print(f"   Policy Shim disabled via: {policy_shim_hardened.disable_file}")
    print("   Use emergency-resume to re-enable")


def emergency_resume():
    """Resume Policy Shim after emergency stop"""
    policy_shim_hardened.emergency_resume()
    print("✅ Policy Shim RESUMED")
    print("   Normal operation restored")


def force_prefer_actions(minutes: int = 5):
    """Force prefer_actions for specified duration"""
    policy_shim_hardened.force_prefer_actions(minutes)
    print(f"🎯 PREFER ACTIONS forced for {minutes} minutes")
    print(f"   Remove file to stop: {policy_shim_hardened.force_prefer_file}")


def show_status():
    """Show current Policy Shim status"""
    config = policy_shim_hardened.get_current_config()
    
    print("📊 Policy Shim V2 Status:")
    print(f"   Status: {'🛑 DISABLED' if config['disabled'] else '✅ ACTIVE'}")
    print(f"   Prefer Actions: {'🎯 FORCED' if config['forced_prefer'] else '⏸️ Normal'}")
    print(f"   Streak Limit: {config['dynamic_streak_limit']} (base: {config['noop_streak_limit']})")
    print(f"   Cooldown: {config['cooldown_s']}s (remaining: {config['cooldown_remaining']:.1f}s)")
    print(f"   Hysteresis: {config['hysteresis']}")
    print(f"   Trigger Dir: {config['trigger_dir']}")
    
    # Check trigger files
    print("\n🗂️ Trigger Files:")
    disable_exists = policy_shim_hardened.disable_file.exists()
    prefer_exists = policy_shim_hardened.force_prefer_file.exists()
    print(f"   SHIM_DISABLE: {'✅ EXISTS' if disable_exists else '❌ Not found'}")
    print(f"   SHIM_FORCE_PREFER: {'✅ EXISTS' if prefer_exists else '❌ Not found'}")


def set_env_vars():
    """Set recommended environment variables for production"""
    env_vars = {
        "LLA_SHIM_NOOP_STREAK_LIMIT": "2",
        "LLA_SHIM_COOLDOWN_S": "20", 
        "LLA_SHIM_HYST": "65,80",
        "LLA_TRIGGERS_DIR": "C:/ProgramData/LLA/state"
    }
    
    print("🔧 Setting Policy Shim environment variables:")
    
    # Create PowerShell script for setting env vars
    ps_script = Path("set_policy_shim_env.ps1")
    with open(ps_script, 'w') as f:
        f.write("# Policy Shim V2 Environment Variables\n")
        f.write("# Run as Administrator for system-wide settings\n\n")
        
        for var, value in env_vars.items():
            f.write(f'[Environment]::SetEnvironmentVariable("{var}", "{value}", "User")\n')
            print(f"   {var}={value}")
        
        f.write('\nWrite-Host "✅ Policy Shim environment variables set"\n')
        f.write('Write-Host "   Restart applications to take effect"\n')
    
    print(f"\n📝 PowerShell script created: {ps_script}")
    print("   Run as Administrator for system-wide settings")


def validate_production_config():
    """Validate current production configuration"""
    config = policy_shim_hardened.get_current_config()
    
    print("🔍 Validating Policy Shim production configuration...")
    
    # Validation criteria
    checks = []
    
    # Check streak limit
    if config['noop_streak_limit'] >= 2:
        checks.append(("✅", f"NOOP_STREAK_LIMIT: {config['noop_streak_limit']} (safe)"))
    else:
        checks.append(("❌", f"NOOP_STREAK_LIMIT: {config['noop_streak_limit']} (too aggressive)"))
    
    # Check cooldown
    if config['cooldown_s'] >= 15:
        checks.append(("✅", f"COOLDOWN_S: {config['cooldown_s']} (safe)"))
    else:
        checks.append(("⚠️", f"COOLDOWN_S: {config['cooldown_s']} (may be too fast)"))
    
    # Check trigger directory
    trigger_dir = Path(config['trigger_dir'])
    if trigger_dir.exists() and trigger_dir.is_dir():
        checks.append(("✅", f"TRIGGER_DIR: {trigger_dir} (accessible)"))
    else:
        checks.append(("❌", f"TRIGGER_DIR: {trigger_dir} (not accessible)"))
    
    # Check hysteresis values
    hyst_parts = config['hysteresis'].replace('%', '').split('-')
    if len(hyst_parts) == 2:
        low, high = int(hyst_parts[0]), int(hyst_parts[1])
        if 60 <= low < high <= 85:
            checks.append(("✅", f"HYSTERESIS: {config['hysteresis']} (reasonable)"))
        else:
            checks.append(("⚠️", f"HYSTERESIS: {config['hysteresis']} (check thresholds)"))
    
    # Display results
    print("\n📋 Validation Results:")
    all_pass = True
    for status, message in checks:
        print(f"   {status} {message}")
        if status == "❌":
            all_pass = False
    
    print(f"\n🎯 Overall Status: {'✅ PRODUCTION READY' if all_pass else '⚠️ NEEDS ATTENTION'}")
    
    return all_pass


def main():
    """CLI for Policy Shim emergency controls"""
    parser = argparse.ArgumentParser(description="Policy Shim V2 Emergency Controls")
    parser.add_argument("action", choices=[
        "status", "stop", "resume", "prefer", "validate", "set-env"
    ], help="Action to perform")
    parser.add_argument("--minutes", type=int, default=5, 
                       help="Duration for prefer actions (default: 5)")
    
    args = parser.parse_args()
    
    if args.action == "status":
        show_status()
    elif args.action == "stop":
        emergency_stop()
    elif args.action == "resume":
        emergency_resume()
    elif args.action == "prefer":
        force_prefer_actions(args.minutes)
    elif args.action == "validate":
        validate_production_config()
    elif args.action == "set-env":
        set_env_vars()


if __name__ == "__main__":
    main()