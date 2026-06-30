import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
EXEC_STATS = ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl"

final_ids = set()
provisional_ids = set()
provisional_details = {}

with open(EXEC_STATS, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        ts = obj.get("recorded_ts_ms") or 0
        if ts > T8_TS_MS:
            lid = obj.get("lifecycle_id")
            if obj.get("row_status") == "FINAL":
                final_ids.add(lid)
            elif obj.get("row_status") == "PROVISIONAL":
                provisional_ids.add(lid)
                provisional_details[lid] = obj

open_ids = provisional_ids - final_ids
print(f"Found {len(open_ids)} open/unresolved lifecycle IDs.")
for idx, lid in enumerate(sorted(open_ids)):
    r = provisional_details[lid]
    print(f"#{idx}: id={lid} symbol={r.get('symbol')} side={r.get('side')} ts={r.get('recorded_ts_ms')} prov_st={r.get('provisional_status')} pnl={r.get('net_pnl')} close_reason={r.get('close_reason')}")
