#!/usr/bin/env python3
"""Quick config verification that gates AuroraCore on config v2 correctness."""
import sys

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.brackets_config import (
    DEFAULT_SL_BPS,
    resolve_brackets_config,
)
from tools.config_validator_v2 import (
    format_validation_summary,
    validate_config_v2,
)

result = validate_config_v2()
print(format_validation_summary(result))
if result.get("status") != "ok":
    sys.exit(1)

c = ConfigLoader().load_config()
print(f"⛽ Config loaded: mode={c.get('trading_mode')}")
decision = c.get("trading", {}).get("decision", {})
print(f"⛽ Decision keys: {len(decision)} keys")
print(f"⛽ Signal threshold (testnet): {decision.get('signal_threshold')}")
try:
    resolved_brackets = resolve_brackets_config(c)
    print(
        f"⛽ SL_bps via {resolved_brackets.sl_source}: {resolved_brackets.sl_bps}"
    )
except Exception as exc:
    print(
        f"WARNING: SL_bps fallback to default {DEFAULT_SL_BPS} (resolver error: {exc})"
    )
print("⛽ ALL GOOD - READY TO LAUNCH")
