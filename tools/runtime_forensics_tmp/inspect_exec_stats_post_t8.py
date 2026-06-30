import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
EXEC_STATS = ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl"

post_t8 = []
with open(EXEC_STATS, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        ts = obj.get("recorded_ts_ms") or 0
        if ts > T8_TS_MS:
            post_t8.append(obj)

print(f"Found {len(post_t8)} post-T8 execution stats records.")
for idx, r in enumerate(post_t8[:15]):
    print(f"#{idx}: id={r.get('lifecycle_id')} symbol={r.get('symbol')} side={r.get('side')} ts={r.get('recorded_ts_ms')} status={r.get('row_status')} prov_st={r.get('provisional_status')} pnl={r.get('net_pnl')} close_reason={r.get('close_reason')}")
