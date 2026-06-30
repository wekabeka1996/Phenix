import json
from pathlib import Path

ROOT = Path(".")
TRADE_LIFECYCLE = ROOT / "logs" / "trade_lifecycle.jsonl"
T8_TS_MS = 1781811230000

closed_records = []
with open(TRADE_LIFECYCLE, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        if obj.get("status") == "CLOSED":
            closed_records.append(obj)

print(f"Total CLOSED records found: {len(closed_records)}")
for idx, r in enumerate(closed_records):
    ts = r.get("created_ts_ms") or r.get("ts_ms") or r.get("timestamp") or 0
    pnl = r.get("net_pnl") or r.get("realized_pnl")
    fees = r.get("fill_fees") or r.get("fees") or r.get("total_fees") or 0.0
    print(f"#{idx}: rid={r.get('rid')} symbol={r.get('symbol')} side={r.get('side')} ts={ts} pnl={pnl} fees={fees} status={r.get('status')}")
    print(f"  Keys: {list(r.keys())}")
