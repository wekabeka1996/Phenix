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

recomputed_trades = []
for rt in reported_trades:
    tid = rt["trade_id"]
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
    if not close_fills and len(fills) > 1:
        close_fills = [fills[-1]]
        
    entry_qty = sum(float(x["qty"] or 0.0) for x in entry_fills)
    close_qty = sum(float(x["qty"] or 0.0) for x in close_fills)
    entry_fee = sum(float(x["fee"] or 0.0) for x in entry_fills)
    close_fee = sum(float(x["fee"] or 0.0) for x in close_fills)
    
    closes = [e for e in group if e["source_event_name"] == "POSITION_CLOSED"]
    resolved_close = None
    unresolved_close = None
    for c in closes:
        if c["status"] == "resolved":
            resolved_close = c
        elif c["status"] == "unresolved":
            unresolved_close = c
            
    active_close = resolved_close or unresolved_close
    
    gross_pnl = 0.0
    total_fee = entry_fee + close_fee
    net_pnl = 0.0
    terminal_status = "UNKNOWN"
    close_trigger = "UNKNOWN"
    
    if active_close:
        if resolved_close:
            gross_pnl = float(resolved_close["realized_pnl"] or 0.0)
            terminal_status = "CLOSED_EXACT"
            close_trigger = resolved_close["reject_reason"] or "CLOSE"
        else:
            gross_pnl = 0.0
            terminal_status = "UNRESOLVED"
            close_trigger = unresolved_close["reject_reason"] or "CLOSE"
            
        if close_qty > 0 and abs(close_qty - entry_qty) > 1e-5:
            terminal_status = "PARTIAL"
    elif close_fills:
        side_sign = 1 if rt["side"] == "BUY" else -1
        total_entry_qty = sum(float(x["qty"] or 0.0) for x in entry_fills)
        total_entry_notional = sum(float(x["qty"] or 0.0) * float(x["price"] or 0.0) for x in entry_fills)
        entry_price = total_entry_notional / total_entry_qty if total_entry_qty > 0 else 0.0
        
        total_close_qty = sum(float(x["qty"] or 0.0) for x in close_fills)
        total_close_notional = sum(float(x["qty"] or 0.0) * float(x["price"] or 0.0) for x in close_fills)
        close_price = total_close_notional / total_close_qty if total_close_qty > 0 else 0.0
        
        gross_pnl = (close_price - entry_price) * total_close_qty * side_sign
        terminal_status = "CLOSED_WEAK"
        close_trigger = "CLOSE_FILL"
        if abs(total_close_qty - total_entry_qty) > 1e-5:
            terminal_status = "PARTIAL"
    else:
        gross_pnl = 0.0
        terminal_status = "OPEN"
        close_trigger = "UNKNOWN"
        
    net_pnl = gross_pnl - total_fee
    
    recomputed_trades.append({
        "trade_id": tid,
        "symbol": rt["symbol"],
        "side": rt["side"],
        "terminal_status": terminal_status,
        "entry_fee": entry_fee,
        "close_fee": close_fee,
        "gross_pnl": gross_pnl,
        "total_fee": total_fee,
        "net_pnl": net_pnl,
        "close_trigger": close_trigger,
        "reported_net_pnl": float(rt["net_pnl"]),
        "reported_total_fee": float(rt["total_fee"]),
        "reported_status": rt["terminal_status"]
    })

status_counts = {}
pnl_sums = {}
fee_sums = {}
for t in recomputed_trades:
    status = t["terminal_status"]
    status_counts[status] = status_counts.get(status, 0) + 1
    pnl_sums[status] = pnl_sums.get(status, 0.0) + t["net_pnl"]
    fee_sums[status] = fee_sums.get(status, 0.0) + t["total_fee"]

print("Recomputed Breakdown (with fallback):")
for status, count in status_counts.items():
    print(f"  {status}: count={count}, Net PnL={pnl_sums[status]:.6f}, Total Fee={fee_sums[status]:.6f}")

reported_proven_pnl = sum(t["reported_net_pnl"] for t in recomputed_trades if t["reported_status"] == "CLOSED_EXACT")
recomputed_proven_pnl = pnl_sums.get("CLOSED_EXACT", 0.0)
print(f"\nProven Net PnL: Reported={reported_proven_pnl:.6f}, Recomputed={recomputed_proven_pnl:.6f}, Delta={recomputed_proven_pnl - reported_proven_pnl:.6f}")

reported_est_pnl = sum(t["reported_net_pnl"] for t in recomputed_trades if t["reported_status"] == "PARTIAL")
recomputed_est_pnl = pnl_sums.get("PARTIAL", 0.0)
print(f"Estimated Net PnL (PARTIAL only): Reported={reported_est_pnl:.6f}, Recomputed={recomputed_est_pnl:.6f}, Delta={recomputed_est_pnl - reported_est_pnl:.6f}")

reported_fees = sum(t["reported_total_fee"] for t in recomputed_trades)
recomputed_fees = sum(t["total_fee"] for t in recomputed_trades)
print(f"Total Fees: Reported={reported_fees:.6f}, Recomputed={recomputed_fees:.6f}, Delta={recomputed_fees - reported_fees:.6f}")

# Win rate and profit factor for CLOSED_EXACT
closed_exact_recomp = [t for t in recomputed_trades if t["terminal_status"] == "CLOSED_EXACT"]
winners = sum(1 for t in closed_exact_recomp if t["net_pnl"] > 0)
losers = sum(1 for t in closed_exact_recomp if t["net_pnl"] < 0)
flats = sum(1 for t in closed_exact_recomp if t["net_pnl"] == 0)
winrate = winners / len(closed_exact_recomp) if closed_exact_recomp else 0.0
gross_profits = sum(t["net_pnl"] for t in closed_exact_recomp if t["net_pnl"] > 0)
gross_losses = sum(abs(t["net_pnl"]) for t in closed_exact_recomp if t["net_pnl"] < 0)
profit_factor = gross_profits / gross_losses if gross_losses > 0 else 0.0

print(f"\nCLOSED_EXACT Win Rate metrics (with fallback):")
print(f"  Count: {len(closed_exact_recomp)}")
print(f"  Winners: {winners}, Losers: {losers}, Flats: {flats}")
print(f"  Winrate: {winrate * 100:.4f}%")
print(f"  Profit Factor: {profit_factor:.4f}")
