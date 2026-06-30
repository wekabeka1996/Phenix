import csv
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

# Group normalized events by lifecycle_id
events_by_lid = {}
with open(REPORTS_DIR / "normalized_events.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        lid = row["lifecycle_id"]
        if lid not in events_by_lid:
            events_by_lid[lid] = []
        events_by_lid[lid].append(row)

# Get trades
with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    reported_trades = list(reader)

for rt in reported_trades:
    if rt["trade_id"] == "T_002":
        lid = rt["lifecycle_id"]
        group = events_by_lid.get(lid, [])
        entry_fills = []
        close_fills = []
        fills = [e for e in group if e["event_family"] == "ORDER_FILLED"]
        for f in fills:
            role = f["client_order_id"].split("-")[0].upper() if f["client_order_id"] else ""
            if "ENTRY" in role:
                entry_fills.append(f)
            elif "CLOSE" in role:
                close_fills.append(f)
            else:
                side = rt["side"]
                if f["side"] == side:
                    entry_fills.append(f)
                else:
                    close_fills.append(f)
        entry_qty = sum(float(x["qty"] or 0.0) for x in entry_fills)
        close_qty = sum(float(x["qty"] or 0.0) for x in close_fills)
        print(f"T_002: entry_qty={entry_qty}, close_qty={close_qty}")
        for ev in group:
            if ev["source_event_name"] == "POSITION_CLOSED":
                print(f"  POSITION_CLOSED event: TS={ev['ts']}, Status={ev['status']}, PnL={ev['realized_pnl']}, Fee={ev['fee']}, Trigger={ev['reject_reason']}")
        break
