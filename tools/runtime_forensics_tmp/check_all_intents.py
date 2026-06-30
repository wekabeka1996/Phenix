import json
from pathlib import Path
from collections import Counter

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

print("=== Scanning all 202 ORDER_INTENT events ===")
strat_counts = Counter()
metadata_keys = Counter()

for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                if ev == "ORDER_INTENT":
                    meta = rec.get("metadata") or {}
                    # Check strategy from reservation_id or other fields
                    resid = rec.get("reservation_id") or "none"
                    strat = "unknown"
                    if "aurora" in resid:
                        strat = "aurora"
                    elif "md_amr" in resid or "mdamr" in resid:
                        strat = "md_amr"
                    elif "mean_reversion" in resid:
                        strat = "mean_reversion"
                    
                    # Let's inspect all fields of the record for strategy
                    for k, v in rec.items():
                        if "strat" in k.lower():
                            strat = str(v)
                    for k, v in meta.items():
                        if "strat" in k.lower():
                            strat = str(v)
                            
                    strat_counts[strat] += 1
                    for k in meta.keys():
                        metadata_keys[k] += 1
            except Exception as e:
                pass

print("Strategy counts:")
for s, c in strat_counts.items():
    print(f"- {s}: {c}")

print("\nMetadata keys frequency:")
for k, c in metadata_keys.items():
    print(f"- {k}: {c}")
