import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "normalized_events.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    events = list(reader)

print(f"Total events in normalized_events.csv: {len(events)}")
non_empty_conf = [e for e in events if e.get("regime_confidence") and e.get("regime_confidence") != "None" and e.get("regime_confidence") != ""]
print(f"Events with non-empty regime_confidence: {len(non_empty_conf)}")
if non_empty_conf:
    print("Example event with non-empty regime_confidence:")
    for k, v in non_empty_conf[0].items():
        if v:
            print(f"  {k}: {v}")
