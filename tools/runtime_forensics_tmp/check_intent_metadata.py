import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

print("=== Scanning ORDER_INTENT metadata keys ===")
keys_seen = set()
for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                if ev == "ORDER_INTENT":
                    meta = rec.get("metadata") or {}
                    for k in meta.keys():
                        keys_seen.add(k)
            except Exception as e:
                pass

print("Metadata keys seen in ORDER_INTENT:", sorted(list(keys_seen)))

# Let's print the entire metadata dictionary for a few ORDER_INTENT events
count = 0
for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                if ev == "ORDER_INTENT":
                    print(f"\nFile {f.name} Line {idx}:")
                    print(json.dumps(rec.get("metadata"), indent=2))
                    count += 1
                    if count >= 3:
                        break
            except Exception as e:
                pass
    if count >= 3:
        break
