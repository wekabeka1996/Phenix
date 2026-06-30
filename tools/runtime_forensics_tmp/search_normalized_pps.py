import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

print("Searching in normalized_events.csv:")
found_norm = 0
with open(REPORTS_DIR / "normalized_events.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        for k, v in row.items():
            if v and "pps" in v:
                print(f"Row {i}: key={k}, value={v}, source={row['source_file']}")
                found_norm += 1
                break
print(f"Found {found_norm} matching rows in normalized_events.csv")
