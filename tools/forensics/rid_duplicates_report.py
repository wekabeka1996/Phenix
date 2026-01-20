
import glob
import json
import os
from collections import defaultdict

def scan_wal():
    wal_dir = "ops/wal"
    wal_files = sorted(glob.glob(os.path.join(wal_dir, "*.jsonl")))
    
    counts = defaultdict(lambda: defaultdict(int))
    
    print(f"Scanning {len(wal_files)} WAL files in {wal_dir}...")
    
    msg_count = 0
    for fpath in wal_files:
        with open(fpath, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    msg_count += 1
                    rid = data.get("rid")
                    verb = data.get("verb")
                    
                    if not rid or not verb:
                        continue
                        
                    # Normalize verbs if needed (e.g. op:verb)
                    # WAL usually dumps "verb": "TRADE_INTENT_PROPOSED"
                    # But sometimes full message: "op": "CMD", "verb": "OPEN"
                    
                    op = data.get("op")
                    full_verb = f"{op}:{verb}" if op else verb
                    
                    # Track interesting verbs
                    if "TRADE_INTENT" in full_verb or "CMD:OPEN" in full_verb or "DEC:OPEN" in full_verb or "ORDER_" in full_verb:
                         counts[rid][full_verb] += 1
                         
                except Exception:
                    pass

    print(f"Processed {msg_count} messages. Found {len(counts)} unique RIDs.")

    # Analysis
    dupe_attempts = []
    black_holes = []
    
    for rid, stats in counts.items():
        # Check Dupes
        if stats.get("CMD:OPEN", 0) > 1:
            dupe_attempts.append((rid, "CMD:OPEN", stats["CMD:OPEN"]))
        
        # Check Black Holes
        # If PROPOSED exists, but NOT (CMD:OPEN or DEC:OPEN or REJECTED)
        proposed = stats.get("EVT:TRADE_INTENT_PROPOSED") or stats.get("TRADE_INTENT_PROPOSED")
        if proposed:
             # Did it progress?
             progress = (
                 stats.get("CMD:OPEN") or stats.get("DEC:OPEN") 
                 or stats.get("EVT:TRADE_INTENT_REJECTED") or stats.get("TRADE_INTENT_REJECTED")
                 or stats.get("EVT:ORDER_PLACED")
             )
             if not progress:
                 black_holes.append((rid, stats))

    # Report
    print("\n=== DUPLICATE ANALYSIS ===")
    if dupe_attempts:
        print(f"FAILED: Found {len(dupe_attempts)} RIDs with duplicate execution attempts!")
        for rid, typ, n in dupe_attempts[:10]:
            print(f"  {rid}: {typ} x{n}")
    else:
        print("PASSED: No duplicate execution attempts found.")

    print("\n=== BLACK HOLE ANALYSIS ===")
    if black_holes:
        print(f"WARNING: Found {len(black_holes)} RIDs that stalled after Proposal (Potential Black Holes)")
        for rid, stats in black_holes[:5]:
             print(f"  {rid}: {dict(stats)}")
    else:
        print("PASSED: No black holes found.")

if __name__ == "__main__":
    scan_wal()
