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

# Load trades
with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    reported_trades = list(reader)

for rt in reported_trades:
    if rt["trade_id"] == "T_048":
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
                    
        if not entry_fills and fills:
            entry_fills = [fills[0]]
            
        entry_qty = sum(float(x["qty"] or 0.0) for x in entry_fills)
        close_qty = sum(float(x["qty"] or 0.0) for x in close_fills)
        
        closes = [e for e in group if e["source_event_name"] == "POSITION_CLOSED"]
        resolved_close = None
        unresolved_close = None
        for c in closes:
            if c["status"] == "resolved":
                resolved_close = c
            elif c["status"] == "unresolved":
                unresolved_close = c
                
        active_close = resolved_close or unresolved_close
        
        print(f"T_048: active_close={active_close is not None}, resolved={resolved_close is not None}, unresolved={unresolved_close is not None}")
        print(f"  entry_qty={entry_qty}, close_qty={close_qty}")
        
        terminal_status = "UNKNOWN"
        if active_close:
            if resolved_close:
                terminal_status = "CLOSED_EXACT"
            else:
                terminal_status = "UNRESOLVED"
            if close_qty > 0 and abs(close_qty - entry_qty) > 1e-5:
                terminal_status = "PARTIAL"
        elif close_fills:
            terminal_status = "CLOSED_WEAK"
            if abs(close_qty - entry_qty) > 1e-5:
                terminal_status = "PARTIAL"
        else:
            terminal_status = "OPEN"
            
        print(f"  Recomputed status={terminal_status}")
        break
