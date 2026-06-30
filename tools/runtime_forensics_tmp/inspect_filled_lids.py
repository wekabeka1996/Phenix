import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
LOG_FILES = [
    ROOT / "logs" / "order_log_v1.20260619T000003Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.20260620T000005Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.jsonl",
]

for lf in LOG_FILES:
    if not lf.exists():
        continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            ts = obj.get("timestamp") or obj.get("ts_ms") or obj.get("ts") or 0
            if ts > T8_TS_MS and obj.get("event_type") == "ORDER_FILLED":
                print(f"ORDER_FILLED: entry_rid={obj.get('entry_rid')} lifecycle_id={obj.get('lifecycle_id')} symbol={obj.get('symbol')} side={obj.get('side')} qty={obj.get('quantity') or obj.get('qty')}")
