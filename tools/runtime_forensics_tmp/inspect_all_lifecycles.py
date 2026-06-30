import json
from pathlib import Path

ROOT = Path(".")
TRADE_LIFECYCLE = ROOT / "logs" / "trade_lifecycle.jsonl"
EXEC_STATS = ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl"

print("--- TRADE LIFECYCLE ALL ---")
tl_statuses = {}
tl_event_types = {}
with open(TRADE_LIFECYCLE, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        st = obj.get("status", "NONE")
        tl_statuses[st] = tl_statuses.get(st, 0) + 1
        et = obj.get("event_type", "NONE")
        tl_event_types[et] = tl_event_types.get(et, 0) + 1

print("TL Statuses:", tl_statuses)
print("TL Event Types:", tl_event_types)

print("\n--- EXEC STATS ALL ---")
es_statuses = {}
es_event_types = {}
with open(EXEC_STATS, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        st = obj.get("status", "NONE")
        es_statuses[st] = es_statuses.get(st, 0) + 1
        et = obj.get("event_type", "NONE")
        es_event_types[et] = es_event_types.get(et, 0) + 1

print("ES Statuses:", es_statuses)
print("ES Event Types:", es_event_types)
