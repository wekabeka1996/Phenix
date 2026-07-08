import json
from pathlib import Path

def search_nrr():
    path = Path("logs/shadow_critical_event_journal_v1.jsonl")
    if not path.exists():
        return
    
    nrr_events = {}
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if "NRR-" in line:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                ts = row.get("ts_ms")
                event_name = row.get("event_name")
                strat = row.get("strategy_id") or row.get("payload", {}).get("strategy_id")
                pf = row.get("payload_fragment") or row.get("payload") or {}
                rc = pf.get("reason_code") or row.get("reject_reason") or row.get("gate_code") or pf.get("gate_code")
                symbol = row.get("symbol") or pf.get("symbol")
                
                key = (event_name, strat, rc)
                nrr_events[key] = nrr_events.get(key, 0) + 1
                
                if nrr_events[key] <= 5:
                     print(f"Line {i} | Event: {event_name} | Strategy: {strat} | Code: {rc} | Symbol: {symbol} | TS: {ts}")
                     print(f"  Payload: {json.dumps(pf)}")
                     
    print("\n=== Aggregated NRR occurrences ===")
    for (event_name, strat, rc), count in sorted(nrr_events.items(), key=lambda x: x[1], reverse=True):
        print(f"  Event: {event_name:<30} | Strategy: {str(strat):<15} | Code: {str(rc):<10} | Count: {count}")

search_nrr()
