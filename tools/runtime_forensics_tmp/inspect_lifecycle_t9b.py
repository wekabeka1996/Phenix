import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
TRADE_LIFECYCLE = ROOT / "logs" / "trade_lifecycle.jsonl"
EXEC_STATS = ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl"

print("--- TRADE LIFECYCLE HEAD ---")
count = 0
with open(TRADE_LIFECYCLE, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        ts = obj.get("timestamp") or obj.get("ts_ms") or obj.get("ts") or 0
        if ts > T8_TS_MS:
            print(json.dumps(obj, indent=2))
            count += 1
            if count >= 3:
                break
print(f"Found {count} records in trade_lifecycle > T8_TS_MS")

print("\n--- EXEC STATS HEAD ---")
count = 0
with open(EXEC_STATS, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        ts = obj.get("timestamp") or obj.get("ts_ms") or obj.get("ts") or 0
        if ts > T8_TS_MS:
            print(json.dumps(obj, indent=2))
            count += 1
            if count >= 3:
                break
print(f"Found {count} records in execution_lifecycle_stats_v1 > T8_TS_MS")
