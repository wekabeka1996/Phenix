import json
from pathlib import Path

def inspect_pre_patch():
    path = Path("logs/shadow_critical_event_journal_v1.jsonl")
    if not path.exists():
        return
    
    reasons = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            
            ts = row.get("ts_ms")
            if ts and ts < 1782845625000:
                event_name = row.get("event_name")
                if event_name == "EVT:TRADE_INTENT_REJECTED":
                    strat = row.get("strategy_id") or row.get("payload", {}).get("strategy_id")
                    if strat == "alpha_mr_s01":
                        pf = row.get("payload_fragment") or row.get("payload") or {}
                        rc = pf.get("reason_code")
                        why = pf.get("why")
                        reasons[(rc, why)] = reasons.get((rc, why), 0) + 1
                        
    print("=== Pre-Patch alpha_mr_s01 Rejection Reasons ===")
    for (rc, why), count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
        print(f"  Reason Code: {rc:<10} | Why: {str(why):<60} | Count: {count}")

inspect_pre_patch()
