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

# Load trades from reported csv
with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    reported_trades = list(reader)

recomputed_trades = []
for rt in reported_trades:
    tid = rt["trade_id"]
    lid = rt["lifecycle_id"]
    group = events_by_lid.get(lid, [])
    
    # Re-extract entry fills and close fills
    entry_fills = []
    close_fills = []
    
    # Let's find ORDER_FILLED events
    fills = [e for e in group if e["event_family"] == "ORDER_FILLED"]
    
    # Group fills into entry and close
    # Following the same logic but without duplicating a single fill into both
    for f in fills:
        role = f["client_order_id"].split("-")[0].upper() if f["client_order_id"] else ""
        if "ENTRY" in role:
            entry_fills.append(f)
        elif "CLOSE" in role:
            close_fills.append(f)
        else:
            # If no role, fallback to side matching
            # First event is usually order intent or strategy signal, which tells us side
            side = rt["side"]
            if f["side"] == side:
                entry_fills.append(f)
            else:
                close_fills.append(f)
                
    # If all fills went to close_fills or entry_fills and one is empty, let's look closer.
    # In T_035, there is only 1 fill. It has role "CLOSE". So it goes to close_fills.
    # Entry fills is empty.
    
    entry_fee = sum(float(x["fee"] or 0.0) for x in entry_fills)
    close_fee = sum(float(x["fee"] or 0.0) for x in close_fills)
    
    # Now find POSITION_CLOSED events
    closes = [e for e in group if e["source_event_name"] == "POSITION_CLOSED"]
    
    # Find the resolved close event if it exists, otherwise the unresolved one
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
    terminal_status = rt["terminal_status"]
    close_trigger = rt["close_trigger"]
    
    if active_close:
        # If there is a resolved close, we use its realized PnL
        if resolved_close:
            gross_pnl = float(resolved_close["realized_pnl"] or 0.0)
            terminal_status = "CLOSED_EXACT"
            close_trigger = resolved_close["reject_reason"] or "CLOSE"
        else:
            gross_pnl = 0.0
            terminal_status = "UNRESOLVED"
            close_trigger = unresolved_close["reject_reason"] or "CLOSE"
            
        # Total fee should be the sum of entry fee and close fee
        # Wait, if we use the sum:
        total_fee = entry_fee + close_fee
        # If there are no fills but POSITION_CLOSED has fee, we can use it or fallback
        if total_fee == 0.0 and active_close.get("fee"):
            total_fee = float(active_close["fee"] or 0.0)
            
        # But wait, in T_048 there is only entry fills (no close fills, no resolved close).
        # T_048 was marked UNRESOLVED, and has total_fee = 0.0 in reported.
        # But it paid entry_fee = 1.195263!
        # If it is unresolved and open, should we include its entry fee?
        # Yes, we paid the entry fee!
        
        # If terminal_status is CLOSED_EXACT or CLOSED_WEAK:
        if terminal_status in ("CLOSED_EXACT", "CLOSED_WEAK"):
            net_pnl = gross_pnl - total_fee
        else:
            # For unresolved/open: gross PnL is 0.0, but we paid entry fee!
            # Wait, in standard accounting, open position PnL is estimated or we count the fee paid.
            # Let's check what the prompt says:
            # "Recompute PnL independently... net_pnl... separating estimated PnL from proven PnL"
            # Proven Net PnL is only for CLOSED_EXACT positions.
            # Open/Unresolved positions count towards estimated Net PnL.
            # Let's check how the prior agent calculated estimated net PnL.
            # Estimated Net PnL includes unresolved/open trades.
            net_pnl = gross_pnl - total_fee if terminal_status in ("CLOSED_EXACT", "CLOSED_WEAK") else -total_fee
    elif close_fills:
        # Reconstruct from close fills
        # Side sign
        side_sign = 1 if rt["side"] == "BUY" else -1
        # We need entry price and close price
        total_entry_qty = sum(float(x["qty"] or 0.0) for x in entry_fills)
        total_entry_notional = sum(float(x["qty"] or 0.0) * float(x["price"] or 0.0) for x in entry_fills)
        entry_price = total_entry_notional / total_entry_qty if total_entry_qty > 0 else 0.0
        
        total_close_qty = sum(float(x["qty"] or 0.0) for x in close_fills)
        total_close_notional = sum(float(x["qty"] or 0.0) * float(x["price"] or 0.0) for x in close_fills)
        close_price = total_close_notional / total_close_qty if total_close_qty > 0 else 0.0
        
        gross_pnl = (close_price - entry_price) * total_close_qty * side_sign
        total_fee = entry_fee + close_fee
        net_pnl = gross_pnl - total_fee
        terminal_status = "CLOSED_WEAK"
        close_trigger = "CLOSE_FILL"
    else:
        # Truly open or unresolved
        gross_pnl = 0.0
        total_fee = entry_fee
        net_pnl = -total_fee
        terminal_status = "OPEN"
        close_trigger = "UNKNOWN"

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

print("Recomputed vs Reported Totals:")
reported_proven_pnl = sum(t["reported_net_pnl"] for t in recomputed_trades if t["reported_status"] == "CLOSED_EXACT")
recomputed_proven_pnl = sum(t["net_pnl"] for t in recomputed_trades if t["terminal_status"] == "CLOSED_EXACT")
print(f"Proven Net PnL: Reported={reported_proven_pnl:.6f}, Recomputed={recomputed_proven_pnl:.6f}, Delta={recomputed_proven_pnl - reported_proven_pnl:.6f}")

reported_est_pnl = sum(t["reported_net_pnl"] for t in recomputed_trades)
recomputed_est_pnl = sum(t["net_pnl"] for t in recomputed_trades)
print(f"Estimated Net PnL (all trades): Reported={reported_est_pnl:.6f}, Recomputed={recomputed_est_pnl:.6f}, Delta={recomputed_est_pnl - reported_est_pnl:.6f}")

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

print(f"CLOSED_EXACT count: {len(closed_exact_recomp)}")
print(f"Winners: {winners}, Losers: {losers}, Flats: {flats}")
print(f"Winrate: {winrate * 100:.4f}%")
print(f"Profit Factor: {profit_factor:.4f}")
