import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

print("=== NRR-027 Rejections ===")
count = 0
for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                if ev == "DECISION_INTENT_REJECTED" and rec.get("nrr_code") == "NRR-027":
                    print(f"\nFile {f.name} Line {idx}:")
                    print(json.dumps(rec, indent=2))
                    count += 1
                    if count >= 3:
                        break
            except Exception as e:
                pass
    if count >= 3:
        break
