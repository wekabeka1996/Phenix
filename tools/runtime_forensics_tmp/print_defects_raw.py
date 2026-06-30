import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "execution_lifecycle_defects.csv", 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    header = next(reader)
    print("Header:", header)
    for i in range(5):
        try:
            print(next(reader))
        except StopIteration:
            break
