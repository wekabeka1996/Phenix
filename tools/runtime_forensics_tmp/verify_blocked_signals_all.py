import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
LOG_FILES = [
    ROOT / "logs" / "order_log_v1.20260619T000003Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.20260620T000005Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.jsonl",
]

# First get all blocked RIDs
blocked_rids = set()
for lf in LOG_FILES:
    if not lf.exists():
        continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            ts = obj.get("timestamp") or obj.get("ts_ms") or obj.get("ts") or 0
            if ts > T8_TS_MS and obj.get("event_type") == "DECISION_INTENT_REJECTED":
                nrr = obj.get("nrr_code")
                if nrr in ("NRR-027", "NRR-028", "NRR-029", "NRR-030"):
                    blocked_rids.add(obj["rid"])

print(f"Total blocked RIDs: {len(blocked_rids)}")

# Now find their STRATEGY_SIGNAL_PRODUCED events
signals = {}
for lf in LOG_FILES:
    if not lf.exists():
        continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            rid = obj.get("rid")
            if rid in blocked_rids and obj.get("event_type") == "STRATEGY_SIGNAL_PRODUCED":
                signals[rid] = obj

print(f"Found signals for {len(signals)} out of {len(blocked_rids)} blocked RIDs.")
missing = blocked_rids - set(signals.keys())
if missing:
    print(f"Missing signals for: {missing}")

for rid, sig in signals.items():
    meta = sig.get("metadata", {})
    entry = meta.get("entry_price")
    stop = meta.get("stop_price")
    target = meta.get("target_price")
    print(f"rid={rid} symbol={sig.get('symbol')} entry={entry} stop={stop} target={target}")
