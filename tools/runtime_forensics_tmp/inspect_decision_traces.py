import json
from pathlib import Path
from datetime import datetime, timezone

PATCH_TS_MS = 1782845625000

def inspect_traces():
    path = Path("logs/shadow_critical_event_journal_v1.jsonl")
    if not path.exists():
         return
    
    pre_reasons = {}
    post_reasons = {}
    
    pre_details = []
    post_details = []
    
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            
            if row.get("event_name") == "EVT:DECISION_TRACE_EMITTED":
                ts = row.get("ts_ms")
                pf = row.get("payload_fragment") or row.get("payload") or {}
                
                # Check outcome and reject reason
                outcome = pf.get("gate_outcome") or pf.get("gate_chain_result")
                reason = pf.get("reject_reason") or pf.get("deny_reason")
                strat = pf.get("strategy_id")
                
                is_post = (ts >= PATCH_TS_MS)
                reasons = post_reasons if is_post else pre_reasons
                details = post_details if is_post else pre_details
                
                key = (strat, outcome, reason)
                reasons[key] = reasons.get(key, 0) + 1
                details.append((ts, strat, outcome, reason, pf))
                
    print("=== PRE-PATCH DECISION TRACE STATS ===")
    for (strat, outcome, reason), count in sorted(pre_reasons.items(), key=lambda x: x[1], reverse=True):
        print(f"  Strategy: {str(strat):<12} | Outcome: {str(outcome):<10} | Reason: {str(reason):<10} | Count: {count}")
        
    print("\n=== POST-PATCH DECISION TRACE STATS ===")
    for (strat, outcome, reason), count in sorted(post_reasons.items(), key=lambda x: x[1], reverse=True):
        print(f"  Strategy: {str(strat):<12} | Outcome: {str(outcome):<10} | Reason: {str(reason):<10} | Count: {count}")
        
    print(f"\nTotal pre-patch decision traces: {len(pre_details)}")
    print(f"Total post-patch decision traces: {len(post_details)}")
    
    if post_details:
        print("\n--- Post-Patch Decision Trace Details ---")
        for ts, strat, outcome, reason, pf in post_details:
            dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).isoformat()
            print(f"  [{dt}] strat={strat} outcome={outcome} reason={reason} symbol={pf.get('symbol')}")
            # print safety gate snapshot
            snapshot = pf.get("safety_gate_snapshot", {})
            print(f"    Snapshot: {json.dumps(snapshot)}")

inspect_traces()
