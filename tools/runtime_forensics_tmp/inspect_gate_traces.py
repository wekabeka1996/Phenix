import json
from pathlib import Path

ROOT = Path(".")
RIDS = ["mdamr-deb8a8627c08e73a", "aurora_BNBUSDT_1781849401488", "mdamr-c510a3a6d9247ce2"]

# Check EVT:GATE_CHAIN_TRACE in shadow_critical_event_journal_v1.jsonl
print("--- SHADOW JOURNAL ---")
with open(ROOT / "logs" / "shadow_critical_event_journal_v1.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        for rid in RIDS:
            if rid in line:
                obj = json.loads(line)
                print(f"\nRID: {rid} Event: {obj.get('event_name')}")
                print(json.dumps(obj, indent=2))
