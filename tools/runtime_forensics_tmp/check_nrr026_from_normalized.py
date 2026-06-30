import csv
from pathlib import Path
from collections import defaultdict

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
REPORTS_DIR = ROOT / "reports" / "runtime_forensics" / "order_log_old_full_runtime_v1"

# Load reconstructed trades
trades = []
with open(REPORTS_DIR / "trades_reconstructed.csv", 'r', encoding='utf-8') as fh:
    reader = csv.DictReader(fh)
    for row in reader:
        trades.append(row)

trade_lids = {t["lifecycle_id"] for t in trades}

# Group normalized events by lifecycle_id
events_by_lid = defaultdict(list)
with open(REPORTS_DIR / "normalized_events.csv", 'r', encoding='utf-8') as fh:
    reader = csv.DictReader(fh)
    for row in reader:
        lid = row["lifecycle_id"]
        if lid in trade_lids:
            events_by_lid[lid].append(row)

print(f"Loaded {len(trades)} trades and grouped normalized events.")

both_present_count = 0
has_regime_conf_count = 0
has_threshold_count = 0

for t in trades:
    lid = t["lifecycle_id"]
    events = events_by_lid[lid]
    
    # Let's see what inputs are present in the events of this trade
    regime_confidence = None
    resolved_min_regime_confidence = None
    
    # Let's check ORDER_INTENT events (or other events in the group)
    for ev in events:
        if ev["event_family"] == "ORDER_INTENT":
            rc = ev.get("regime_confidence")
            rt = ev.get("resolved_min_regime_confidence")
            if rc and rc != "None" and rc != "":
                regime_confidence = rc
            if rt and rt != "None" and rt != "":
                resolved_min_regime_confidence = rt
                
    if regime_confidence:
        has_regime_conf_count += 1
    if resolved_min_regime_confidence:
        has_threshold_count += 1
    if regime_confidence and resolved_min_regime_confidence:
        both_present_count += 1
        
    print(f"Trade: {t['trade_id']} ({t['symbol']}, {t['regime_at_entry']}) -> regime_confidence: {regime_confidence}, resolved_min_threshold: {resolved_min_regime_confidence}")

print("\nSummary:")
print(f"Total trades: {len(trades)}")
print(f"Trades with regime_confidence: {has_regime_conf_count}")
print(f"Trades with resolved_min_regime_confidence: {has_threshold_count}")
print(f"Trades with both: {both_present_count}")
