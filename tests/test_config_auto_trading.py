"""Test script to verify auto-trading config loading."""

from pathlib import Path
from apps.reference.config_loader import ConfigLoader

# Load config
project_root = Path(__file__).resolve().parent
config_loader = ConfigLoader(config_dir=project_root / "config" / "aurora")
config = config_loader.load_config()

# Check auto-trading setting
cfg_exec = config.to_dict().get("execution", {})
manage_cfg = cfg_exec.get("manage", {})
auto_enabled = manage_cfg.get("auto", False)

print("=" * 60)
print("AUTO-TRADING CONFIGURATION CHECK")
print("=" * 60)
print(f"execution.manage.auto = {auto_enabled}")
print(f"Type: {type(auto_enabled)}")
print(f"Bool value: {bool(auto_enabled)}")
print()
print("Full execution config:")
print(cfg_exec)
print("=" * 60)

# Check position sizing config
decision_config = config.to_dict().get("trading", {}).get("decision", {})
position_sizing = decision_config.get("position_sizing", {})
print("\nPOSITION SIZING CONFIG:")
print(f"min_position_size_usd: {position_sizing.get('min_position_size_usd')}")
print(
    f"liquidity_based_cap_usd: {position_sizing.get('liquidity_based_cap_usd')}")
print()

# Check instruments config
instruments = config.to_dict().get("trading", {}).get("instruments", {})
print("INSTRUMENTS CONFIG:")
for symbol, specs in instruments.items():
    print(f"{symbol}:")
    print(f"  step_size: {specs.get('step_size')}")
    print(f"  min_notional: {specs.get('min_notional')}")
print("=" * 60)
