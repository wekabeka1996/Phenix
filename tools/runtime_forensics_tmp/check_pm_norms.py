import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "normalized_events.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    events = list(reader)

with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    trades = list(reader)

events_by_lid = {}
for row in events:
    lid = row["lifecycle_id"]
    if lid not in events_by_lid:
        events_by_lid[lid] = []
    events_by_lid[lid].append(row)

pm_present_count = 0
for t in trades:
    lid = t["lifecycle_id"]
    group = events_by_lid.get(lid, [])
    has_pm = any(
        (ev.get("pm_norm_60s") and ev.get("pm_norm_60s") != "None" and ev.get("pm_norm_60s") != "") or
        (ev.get("pm_norm_300s") and ev.get("pm_norm_300s") != "None" and ev.get("pm_norm_300s") != "")
        for ev in group
    )
    if has_pm:
        pm_present_count += 1

print(f"Total trades: {len(trades)}")
print(f"Trades with price motion norms present: {pm_present_count}")
