import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
LOG_FILES = [
    ROOT / "logs" / "order_log_v1.20260619T000003Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.20260620T000005Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.jsonl",
]

placed = []
for lf in LOG_FILES:
    if not lf.exists():
        continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            ts = obj.get("timestamp") or obj.get("ts_ms") or obj.get("ts") or 0
            if ts > T8_TS_MS and obj.get("event_type") == "ORDER_PLACED":
                placed.append(obj)

print(f"Found {len(placed)} ORDER_PLACED events post-T8:")
for idx, o in enumerate(placed):
    meta = o.get("metadata", {})
    print(f"#{idx}: rid={o.get('rid')} symbol={o.get('symbol')} side={o.get('side')} qty={o.get('qty') or meta.get('qty')} price={o.get('price') or meta.get('price')} client_order_id={o.get('client_order_id') or meta.get('client_order_id')}")
