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

events_by_rid = {r: [] for r in rids}

for lf in LOG_FILES:
    if not lf.exists():
        continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            ts = obj.get("timestamp") or obj.get("ts_ms") or obj.get("ts") or 0
            if ts > T8_TS_MS:
                # check if this record is related to our RIDs
                # it could be in rid, entry_rid, metadata.rid, metadata.entry_rid
                matching_rid = None
                for r in rids:
                    if r == obj.get("rid") or r == obj.get("entry_rid") or r == obj.get("metadata", {}).get("rid") or r == obj.get("metadata", {}).get("entry_rid") or r in str(obj):
                        matching_rid = r
                        break
                if matching_rid:
                    events_by_rid[matching_rid].append((ts, obj))

for rid in rids:
    print(f"\n=========================================")
    print(f"RID: {rid}")
    print(f"=========================================")
    # Sort events by timestamp
    events_by_rid[rid].sort(key=lambda x: x[0])
    for ts, obj in events_by_rid[rid]:
        et = obj.get("event_type")
        # print concise summary
        if et == "ORDER_PLACED":
            meta = obj.get("metadata", {})
            print(f"  [{et}] ts={ts} client_order_id={obj.get('client_order_id') or meta.get('client_order_id')} side={obj.get('side')} qty={obj.get('qty')} price={obj.get('price')}")
        elif et == "ORDER_FILLED":
            meta = obj.get("metadata", {})
            print(f"  [{et}] ts={ts} client_order_id={obj.get('rid')} side={obj.get('side')} qty={obj.get('quantity') or obj.get('qty')} price={obj.get('price')} realized_pnl={meta.get('realized_pnl')} fee={meta.get('commission')}{meta.get('commissionAsset')}")
        elif et == "POSITION_CLOSED":
            meta = obj.get("metadata", {})
            print(f"  [{et}] ts={ts} side={obj.get('side')} qty={obj.get('qty')} price={obj.get('price')} realized_pnl={obj.get('realized_pnl') or meta.get('realized_pnl')} fee={obj.get('fee') or meta.get('commission')}")
        else:
            print(f"  [{et}] ts={ts} keys={list(obj.keys())} why={obj.get('why')} status={obj.get('status')}")
