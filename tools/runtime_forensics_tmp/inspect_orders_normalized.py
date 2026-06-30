import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "orders_normalized.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    orders = list(reader)

print(f"Total rows in orders_normalized.csv: {len(orders)}")
statuses = {}
for o in orders:
    s = o["status"]
    statuses[s] = statuses.get(s, 0) + 1

print("\nStatuses in orders_normalized.csv:")
for s, count in statuses.items():
    print(f"  {s}: {count}")

unique_order_ids = {o["order_id"] for o in orders if o["order_id"] and o["order_id"] != "None"}
print(f"\nUnique order_ids in orders_normalized.csv: {len(unique_order_ids)}")
