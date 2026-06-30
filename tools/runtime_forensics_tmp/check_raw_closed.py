import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
LOG_DIR = ROOT / "order_log_old"

found = 0
for filepath in LOG_DIR.glob("*.jsonl"):
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            ev = rec.get("event_type") or rec.get("event") or rec.get("record_type") or "UNKNOWN"
            if ev == "POSITION_CLOSED":
                print(f"File: {filepath.name}")
                print(json.dumps(rec, indent=2))
                found += 1
                if found >= 3:
                    break
    if found >= 3:
        break
