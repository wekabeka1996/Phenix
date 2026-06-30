import json
from pathlib import Path

ROOT = Path(".")
T8_TS_MS = 1781811230000
LOG_FILES = [
    ROOT / "logs" / "order_log_v1.20260619T000003Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.20260620T000005Z.000.jsonl",
    ROOT / "logs" / "order_log_v1.jsonl",
]

blocked_rids = ["mdamr-deb8a8627c08e73a", "aurora_BNBUSDT_1781849401488", "mdamr-c510a3a6d9247ce2"]

for lf in LOG_FILES:
    if not lf.exists():
        continue
    with open(lf, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            rid = obj.get("rid")
            if rid in blocked_rids and obj.get("event_type") == "STRATEGY_SIGNAL_PRODUCED":
                print(f"\n--- Signal for RID: {rid} ---")
                print(json.dumps(obj, indent=2))
