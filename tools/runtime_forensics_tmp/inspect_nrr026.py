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

replayable_count = 0
block_count = 0
pass_count = 0
missing_count = 0

print("Replaying NRR-026 for all 50 trades:")
for t in trades:
    lid = t["lifecycle_id"]
    events = events_by_lid.get(lid, [])
    # Find ORDER_INTENT events
    intents = [e for e in events if e["event_family"] == "ORDER_INTENT"]
    if not intents:
        print(f"Trade: {t['trade_id']}, status: {t['terminal_status']}, NO INTENTS FOUND")
        missing_count += 1
        continue
    
    # Use the first intent or one with features
    intent = intents[0]
    regime_conf = intent.get("regime_confidence")
    min_thresh = intent.get("resolved_min_regime_confidence")
    
    # Try parsing
    r_conf = float(regime_conf) if (regime_conf and regime_conf != "None" and regime_conf != "") else None
    t_thresh = float(min_thresh) if (min_thresh and min_thresh != "None" and min_thresh != "") else None
    
    if r_conf is not None and t_thresh is not None:
        replayable_count += 1
        result = "PASS"
        if r_conf < t_thresh:
            result = "BLOCK"
            block_count += 1
            print(f"Trade: {t['trade_id']}, status: {t['terminal_status']}, r_conf: {r_conf}, threshold: {t_thresh} -> BLOCK (Net PnL: {t['net_pnl']})")
        else:
            pass_count += 1
    else:
        print(f"Trade: {t['trade_id']}, status: {t['terminal_status']}, r_conf: {regime_conf}, threshold: {min_thresh} -> MISSING")
        missing_count += 1

print(f"\nSummary: Replayable: {replayable_count}, Blocks: {block_count}, Passes: {pass_count}, Missing: {missing_count}")
