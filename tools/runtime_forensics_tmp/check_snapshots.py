import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

print("=== Checking Config Snapshots in order_log_old === ")
for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            if "SNAPSHOT" in line or "CONFIG" in line or "snapshot" in line or "config" in line:
                try:
                    rec = json.loads(fh.readline()) # wait, let's just inspect line by line
                except:
                    pass
    # Let's do it properly:
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            if "SNAPSHOT" in line or "CONFIG" in line or "snapshot" in line or "config" in line:
                try:
                    rec = json.loads(line)
                    ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                    if ev in ("STRATEGY_REGISTRY_SNAPSHOT", "CONFIG_SNAPSHOT", "SYSTEM_CONFIG", "STRATEGY_REGISTRY"):
                        print(f"File {f.name} Line {idx}: Event = {ev}")
                        # print keys
                        print(f"  Keys: {list(rec.keys())}")
                        if "snapshot" in rec:
                            print(f"  Snapshot keys: {list(rec['snapshot'].keys())}")
                        if "registry" in rec:
                            print(f"  Registry keys: {list(rec['registry'].keys()) if isinstance(rec['registry'], dict) else type(rec['registry'])}")
                        if "config" in rec:
                            print(f"  Config type: {type(rec['config'])}")
                except Exception as e:
                    pass
