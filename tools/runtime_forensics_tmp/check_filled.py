import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

count = 0
for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                if ev == "ORDER_FILLED":
                    print(json.dumps(rec, indent=2))
                    count += 1
                    if count >= 3:
                        break
            except Exception as e:
                pass
    if count >= 3:
        break
