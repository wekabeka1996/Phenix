import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

with open(REPORTS_DIR / "normalized_events.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    events = [row for row in reader if row["lifecycle_id"] == "aurora_XRPUSDT_1780965003107"]

print(f"Total events for T_001: {len(events)}")
for i, ev in enumerate(events):
    print(f"\nEvent {i}: {ev['source_event_name']}, family: {ev['event_family']}")
    for k, v in ev.items():
        if v and k in ("regime", "regime_confidence", "resolved_min_regime_confidence", "pm_norm_60s", "pm_norm_300s", "low_vol_cost_floor_present", "price_motion_context_present"):
            print(f"  {k}: {v}")
