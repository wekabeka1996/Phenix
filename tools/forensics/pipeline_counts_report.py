
import json
import os
import glob
from collections import defaultdict, Counter

def analyze():
    # Find latest WAL
    wal_dir = "ops/wal"
    wal_files = sorted(glob.glob(os.path.join(wal_dir, "*.jsonl")))
    if not wal_files:
        print("No WAL files found.")
        return
    
    target_wal = wal_files[-1]
    print(f"Analyzing latest WAL: {target_wal}")
    
    counts = defaultdict(Counter)
    reject_reasons = Counter()
    rid_tracking = defaultdict(list)
    
    with open(target_wal, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            try:
                row = json.loads(line)
                
                # Determine Verb
                op = row.get("op")
                verb_part = row.get("verb")
                if op == "CMD" or op == "DEC":
                    full_verb = f"{op}:{verb_part}"
                elif verb_part:
                    full_verb = verb_part if verb_part.startswith("EVT:") else f"EVT:{verb_part}"
                else:
                    continue
                
                # Normalize known verbs
                # We specifically look for the requested ones
                interesting_verbs = [
                    "EVT:BAR_CLOSED", 
                    "EVT:FEATURES_CALCULATED",
                    "EVT:REGIME_DETECTED",
                    "EVT:TRADE_INTENT_PROPOSED",
                    "EVT:TRADE_INTENT_REJECTED",
                    "CMD:OPEN", "CMD:CLOSE",
                    "DEC:OPEN", "DEC:CLOSE",
                    "EVT:ORDER_PLACED", "EVT:ORDER_REJECTED"
                ]
                
                # Check fuzzy match
                matched_verb = None
                for iv in interesting_verbs:
                    # Match "TRADE_INTENT_PROPOSED" to "EVT:TRADE_INTENT_PROPOSED"
                    if iv == full_verb or iv.split(":")[1] == full_verb or iv == f"EVT:{full_verb}":
                        matched_verb = iv
                        break
                
                if matched_verb:
                    pld = row.get("pld") or row.get("payload") or {}
                    sym = pld.get("symbol") or pld.get("instrument") or "unknown"
                    counts[matched_verb][sym] += 1
                    
                    if "REJECTED" in matched_verb:
                         reason = pld.get("reason") or "unknown"
                         # Extract NRR if standard
                         reject_reasons[f"{reason}"] += 1
                         
            except Exception:
                pass

    # Print CSV
    print("VERB,SYMBOL,COUNT")
    all_symbols = set()
    for c in counts.values(): all_symbols.update(c.keys())
    
    # Sort verbs logically
    sort_order = [
                    "EVT:BAR_CLOSED", 
                    "EVT:FEATURES_CALCULATED",
                    "EVT:REGIME_DETECTED",
                    "EVT:TRADE_INTENT_PROPOSED",
                    "CMD:OPEN", "CMD:CLOSE",
                    "DEC:OPEN", "DEC:CLOSE",
                    "EVT:ORDER_PLACED", 
                    "EVT:ORDER_REJECTED",
                    "EVT:TRADE_INTENT_REJECTED"
    ]
    
    for v in sort_order:
        if v in counts:
            for sym in sorted(counts[v].keys()):
                print(f"{v},{sym},{counts[v][sym]}")

    print("\n=== REJECTION REASONS ===")
    for reason, count in reject_reasons.most_common():
        print(f"{reason}: {count}")

if __name__ == "__main__":
    analyze()
