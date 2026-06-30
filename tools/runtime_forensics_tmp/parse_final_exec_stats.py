import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
EXEC_STATS = ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl"

final_trades = []
with open(EXEC_STATS, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        ts = obj.get("recorded_ts_ms") or 0
        if ts > T8_TS_MS and obj.get("row_status") == "FINAL":
            final_trades.append(obj)

print(f"Found {len(final_trades)} completed (FINAL) trades in execution_lifecycle_stats post-T8.")
for idx, r in enumerate(final_trades):
    print(f"#{idx}: id={r.get('lifecycle_id')} symbol={r.get('symbol')} side={r.get('side')} entry_ts={r.get('entry_ts_ms')} close_ts={r.get('close_ts_ms')} pnl={r.get('net_pnl')} fees={r.get('fees')} reason={r.get('close_reason')}")
