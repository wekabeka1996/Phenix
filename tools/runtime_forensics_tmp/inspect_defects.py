import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "execution_lifecycle_defects.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    defects = list(reader)

print(f"Total rows in execution_lifecycle_defects.csv: {len(defects)}")
p0_defects = [d for d in defects if d["severity"] == "P0"]
p2_defects = [d for d in defects if d["severity"] == "P2"]
print(f"P0 defects: {len(p0_defects)}, P2 defects: {len(p2_defects)}")

print("\nP0 Defects examples (first 5):")
for d in p0_defects[:5]:
    print(f"  TS: {d['ts']}, Symbol: {d['symbol']}, Class: {d['defect_class']}, Desc: {d['description']}, Lifecycle: {d['lifecycle_id']}")

print("\nP2 Defects examples (first 5):")
for d in p2_defects[:5]:
    print(f"  TS: {d['ts']}, Symbol: {d['symbol']}, Class: {d['defect_class']}, Desc: {d['description']}, Lifecycle: {d['lifecycle_id']}")
