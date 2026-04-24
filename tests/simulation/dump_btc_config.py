import sys
import os
import decimal
from pathlib import Path

# Fix path
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../"))

from apps.reference.config_loader import get_config
from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler

def dump_config():
    print("Loading config...")
    config = get_config()
    
    # Check Global Aurora Threshold (The one actually used)
    aurora_decision = config.strategies.aurora.decision
    print(f"Global Aurora Decision Config:")
    print(f"  signal_threshold: {aurora_decision.signal_threshold}")
    print(f"  neutral_threshold: {getattr(aurora_decision, 'neutral_threshold', 'NOT_FOUND')}")

    # Check BTCUSDT specific config
    btc_asset = config.strategies.aurora.assets.get("BTCUSDT")
    if not btc_asset:
        print("BTCUSDT asset config not found!")
        return

    print(f"\nBTCUSDT Config:")
    print(f"  enabled: {btc_asset.enabled}")
    
    # Check signal_threshold override in YAML (even if code ignores it)
    st_cfg = getattr(btc_asset, "signal_threshold", None)
    if st_cfg is not None:
        if hasattr(st_cfg, "enabled"):
            print(f"  signal_threshold (override): enabled={st_cfg.enabled} value={st_cfg.value}")
        else:
            print(f"  signal_threshold (override): {st_cfg}")
    else:
        print(f"  signal_threshold (override): NOT_SET")

    print(f"\nBTCUSDT Weights:")
    if btc_asset.weights:
        for k, v in btc_asset.weights.items():
            print(f"  {k}: {v}")
    else:
        print("  Using global weights (if any)")

    # Instantiate Handler to see what it *thinks* it has
    # We mock emit_fn
    handler = AuroraHandler(config=config, emit_fn=lambda x, y: None)
    print(f"\nHandler Global Threshold (fallback): {handler.signal_threshold}")
    
    # Simulate per-symbol resolution
    print(f"\n=== PER-SYMBOL EFFECTIVE THRESHOLDS ===")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]:
        asset_cfg = config.strategies.aurora.assets.get(sym)
        if not asset_cfg:
            print(f"  {sym}: NOT_CONFIGURED")
            continue
        
        effective = handler.signal_threshold  # global default
        st = getattr(asset_cfg, "signal_threshold", None)
        if st is not None:
            if isinstance(st, (int, float)):
                effective = decimal.Decimal(str(st))
            elif hasattr(st, "enabled") and st.enabled and hasattr(st, "value") and st.value is not None:
                effective = decimal.Decimal(str(st.value))
        
        print(f"  {sym}: {effective}")

if __name__ == "__main__":
    dump_config()
