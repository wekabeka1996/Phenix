import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
LOG_FILES = [
    ROOT / "logs" / "order_log_v1.20260619T000003Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.20260620T000005Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.jsonl",
]

rids = [
    "mdamr-ceb38772b8dc7241",
    "mdamr-bd2656d45e762d96",
    "mdamr-1a03553ec2de1321",
    "mdamr-eae77ff022464091",
    "aurora_BNBUSDT_1781850002085",
    "aurora_BNBUSDT_1781943305149",
    "mdamr-96c189df297610bb"
]

filled = {r: False for r in rids}

for lf in LOG_FILES:
    if not lf.exists():
        continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            ts = obj.get("timestamp") or obj.get("ts_ms") or obj.get("ts") or 0
            if ts > T8_TS_MS and obj.get("event_type") == "ORDER_FILLED":
                entry_rid = obj.get("entry_rid") or obj.get("rid")
                if entry_rid in filled:
                    filled[entry_rid] = True
                    print(f"Filled: entry_rid={entry_rid} symbol={obj.get('symbol')} side={obj.get('side')} price={obj.get('price')} quantity={obj.get('quantity') or obj.get('qty')}")

for r, f in filled.items():
    if not f:
        print(f"NOT FILLED: rid={r}")
