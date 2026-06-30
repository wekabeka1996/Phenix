import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

# We first load the mapping of RIDs or client order IDs to lifecycles to find the 50 accepted trades
# Let's read reports/runtime_forensics/order_log_old_full_runtime_v1/trades_reconstructed.csv
import csv
trades = []
with open(ROOT / "reports/runtime_forensics/order_log_old_full_runtime_v1/trades_reconstructed.csv", 'r', encoding='utf-8') as fh:
    reader = csv.DictReader(fh)
    for row in reader:
        trades.append(row)

print(f"Loaded {len(trades)} trades from reconstructed trades.")

# For each trade, let's find all events in the logs that belong to its lifecycle_id
lifecycle_ids = {t["lifecycle_id"] for t in trades}
lifecycle_events = {lid: [] for lid in lifecycle_ids}

for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            try:
                rec = json.loads(line)
                # Check for lifecycle_id or resolve it
                lid = rec.get("lifecycle_id")
                if not lid and rec.get("rid"):
                    rid = rec.get("rid")
                    if rid.startswith("reserve_"):
                        lid = rid.split("reserve_", 1)[1]
                    elif len(rid) == 36 and "-" in rid:
                        lid = rid
                    else:
                        # try matching client_order_id or metadata
                        pass
                if lid in lifecycle_ids:
                    lifecycle_events[lid].append(rec)
            except Exception:
                pass

print("\nChecking inputs for NRR-026 per trade:")
has_regime_conf_count = 0
has_threshold_count = 0
both_present_count = 0

for t in trades:
    lid = t["lifecycle_id"]
    events = lifecycle_events[lid]
    
    # Check if any event has regime_confidence and resolved_min_regime_confidence
    regime_conf = None
    min_threshold = None
    
    for rec in events:
        ev = rec.get("event_type") or rec.get("event") or rec.get("record_type")
        
        # Check top-level
        if rec.get("regime_confidence") is not None:
            regime_conf = rec.get("regime_confidence")
            
        meta = rec.get("metadata") or {}
        if isinstance(meta, dict):
            if meta.get("resolved_min_regime_confidence") is not None:
                min_threshold = meta.get("resolved_min_regime_confidence")
            elif meta.get("min_regime_confidence") is not None:
                min_threshold = meta.get("min_regime_confidence")
                
            low_vol = meta.get("low_vol_cost_floor") or {}
            if isinstance(low_vol, dict):
                if low_vol.get("regime_confidence") is not None:
                    regime_conf = low_vol.get("regime_confidence")
                if low_vol.get("thresholds", {}).get("min_regime_confidence") is not None:
                    min_threshold = low_vol.get("thresholds", {}).get("min_regime_confidence")
                    
    print(f"Trade: {t['trade_id']} ({t['symbol']}, {t['regime_at_entry']}) -> regime_confidence: {regime_conf}, min_threshold: {min_threshold}")
    if regime_conf is not None:
        has_regime_conf_count += 1
    if min_threshold is not None:
        has_threshold_count += 1
    if regime_conf is not None and min_threshold is not None:
        both_present_count += 1

print(f"\nSummary:")
print(f"Total trades checked: {len(trades)}")
print(f"Trades with regime_confidence: {has_regime_conf_count}")
print(f"Trades with min_threshold: {has_threshold_count}")
print(f"Trades with both present: {both_present_count}")
