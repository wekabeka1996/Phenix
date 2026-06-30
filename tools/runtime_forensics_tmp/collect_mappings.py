import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

# Let's inspect how ORDER_INTENT fields can map to RIDs and UUIDs
mapping = []
for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                if ev == "ORDER_INTENT":
                    rid = rec.get("rid")
                    meta = rec.get("metadata") or {}
                    
                    # Search for decision RID in metadata
                    dec_rid = None
                    # 1. From low_vol_cost_floor
                    if "low_vol_cost_floor" in meta and meta["low_vol_cost_floor"]:
                        dec_rid = meta["low_vol_cost_floor"].get("persistence_context", {}).get("rid")
                    # 2. From idempotent_key or other fields
                    if not dec_rid:
                        dec_rid = meta.get("idempotent_key")
                    if not dec_rid:
                        # check other keys
                        for k, v in meta.items():
                            if isinstance(v, str) and (v.startswith("aurora_") or v.startswith("mdamr_") or v.startswith("mean_reversion_")):
                                dec_rid = v
                                break
                                
                    mapping.append({
                        "file": f.name,
                        "line": idx,
                        "rid": rid,
                        "dec_rid": dec_rid,
                        "symbol": rec.get("symbol"),
                        "side": rec.get("side"),
                        "timestamp": rec.get("timestamp")
                    })
            except Exception as e:
                pass

print(f"Total mappings collected: {len(mapping)}")
# Print first 20 mappings
for item in mapping[:20]:
    print(item)
