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
    trades = list(reader)

blocked_trades = []
passed_trades = []

for t in trades:
    lid = t["lifecycle_id"]
    events = events_by_lid.get(lid, [])
    
    found_intent = None
    for ev in events:
        if ev["event_family"] == "ORDER_INTENT":
            r_conf = ev.get("regime_confidence")
            t_thresh = ev.get("resolved_min_regime_confidence")
            if r_conf and r_conf != "None" and r_conf != "" and t_thresh and t_thresh != "None" and t_thresh != "":
                found_intent = ev
                break
                
    if found_intent:
        r_conf = float(found_intent["regime_confidence"])
        t_thresh = float(found_intent["resolved_min_regime_confidence"])
        net_pnl = float(t["net_pnl"])
        
        if r_conf < t_thresh:
            blocked_trades.append((t["trade_id"], t["symbol"], r_conf, t_thresh, net_pnl, t["terminal_status"]))
        else:
            passed_trades.append((t["trade_id"], t["symbol"], r_conf, t_thresh, net_pnl, t["terminal_status"]))

print(f"Total Blocked Trades: {len(blocked_trades)}")
blocked_net_pnl = 0.0
for tid, sym, r_conf, thresh, pnl, status in blocked_trades:
    print(f"  {tid} ({sym}) [{status}]: r_conf={r_conf:.4f} < thresh={thresh:.4f}, Net PnL={pnl:.4f}")
    blocked_net_pnl += pnl
print(f"Blocked Net PnL: {blocked_net_pnl:.4f}")

print(f"\nTotal Passed Trades: {len(passed_trades)}")
passed_net_pnl = 0.0
passed_winners = 0
passed_losers = 0
for tid, sym, r_conf, thresh, pnl, status in passed_trades:
    passed_net_pnl += pnl
    if pnl > 0:
        passed_winners += 1
    elif pnl < 0:
        passed_losers += 1
print(f"Passed Net PnL: {passed_net_pnl:.4f}")
print(f"Passed Winners: {passed_winners}, Passed Losers: {passed_losers}")
