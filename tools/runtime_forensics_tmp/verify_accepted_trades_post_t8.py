import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
EXEC_STATS = ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl"

lids = {}
with open(EXEC_STATS, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        entry_ts = obj.get("entry_ts_ms") or 0
        if entry_ts > T8_TS_MS:
            lid = obj.get("lifecycle_id")
            if lid not in lids:
                lids[lid] = []
            lids[lid].append(obj)

print(f"Found {len(lids)} lifecycles opened post-T8:")
for lid, records in lids.items():
    # Find if there is a FINAL record
    final_rec = next((r for r in records if r.get("row_status") == "FINAL"), None)
    first_rec = records[0]
    symbol = first_rec.get("symbol")
    side = first_rec.get("side")
    entry_ts = first_rec.get("entry_ts_ms")
    
    if final_rec:
        print(f"  [CLOSED] lid={lid} symbol={symbol} side={side} entry_ts={entry_ts} pnl={final_rec.get('net_pnl')} fees={final_rec.get('fees')} reason={final_rec.get('close_reason')}")
    else:
        print(f"  [OPEN] lid={lid} symbol={symbol} side={side} entry_ts={entry_ts} last_status={records[-1].get('provisional_status')}")
