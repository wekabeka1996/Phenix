import json
from pathlib import Path

PATCH_TS_MS = 1782845625000

def inspect_quadratic_traces():
    path = Path("logs/shadow_critical_event_journal_v1.jsonl")
    if not path.exists():
         return
    
    print("\n--- Post-Patch EVT:QUADRATIC_DECISION_TRACE details ---")
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            
            ts = row.get("ts_ms")
            if ts and ts >= PATCH_TS_MS:
                if row.get("event_name") == "EVT:QUADRATIC_DECISION_TRACE":
                    count += 1
                    print(f"Row {count}: {json.dumps(row, indent=2)}")
                    if count >= 3:
                        break

inspect_quadratic_traces()
