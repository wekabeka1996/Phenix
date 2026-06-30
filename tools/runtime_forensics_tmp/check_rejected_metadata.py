import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

print("=== Checking DECISION_INTENT_REJECTED metadata for NRR gates ===")
counts = defaultdict(int)
for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
                if ev == "DECISION_INTENT_REJECTED":
                    nrr = rec.get("nrr_code") or "NONE"
                    counts[nrr] += 1
                    if counts[nrr] <= 2:
                        print(f"\nFile {f.name} Line {idx} | NRR: {nrr}:")
                        print(json.dumps(rec.get("metadata"), indent=2)[:1500])
            except Exception as e:
                pass

print("\nDECISION_INTENT_REJECTED counts by NRR:", dict(counts))
