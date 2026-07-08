import json
from pathlib import Path

def inspect_pre_patch_aurora():
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
                if event_name in ("EVT:TRADE_INTENT_REJECTED", "EVT:STRATEGY_DECISION_BLOCKED"):
                    strat = row.get("strategy_id") or row.get("payload", {}).get("strategy_id")
                    if strat == "aurora":
                        pf = row.get("payload_fragment") or row.get("payload") or {}
                        rc = pf.get("reason_code") or row.get("reject_reason") or row.get("gate_code") or pf.get("gate_code") or pf.get("reject_reason")
                        # Clean code name
                        if not rc:
                            rc = "UNKNOWN"
                        reasons[rc] = reasons.get(rc, 0) + 1
                        
    print("=== Pre-Patch aurora Rejection Codes ===")
    for rc, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
        print(f"  Code: {rc:<35} | Count: {count}")

inspect_pre_patch_aurora()
