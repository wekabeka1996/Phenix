import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
TRADE_LIFECYCLE = ROOT / "logs" / "trade_lifecycle.jsonl"

event_types = {}
statuses = {}
count = 0
post_t8_records = []

with open(TRADE_LIFECYCLE, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        ts = obj.get("timestamp") or obj.get("ts_ms") or obj.get("ts") or 0
        if ts > T8_TS_MS:
            count += 1
            et = obj.get("event_type", "UNKNOWN")
            event_types[et] = event_types.get(et, 0) + 1
            st = obj.get("status", "UNKNOWN")
            statuses[st] = statuses.get(st, 0) + 1
            post_t8_records.append(obj)

print(f"Total post-T8 records: {count}")
print("Event types:")
for k, v in event_types.items():
    print(f"  {k}: {v}")
print("Statuses:")
for k, v in statuses.items():
    print(f"  {k}: {v}")

# Print a few samples of EXECUTION_WS_TERMINAL_CORRELATED or other events
print("\nSamples:")
for r in post_t8_records[:10]:
    print(f"[{r.get('event_type')}] ts_ms={r.get('ts_ms')} symbol={r.get('symbol')} rid={r.get('rid')} status={r.get('status')}")
