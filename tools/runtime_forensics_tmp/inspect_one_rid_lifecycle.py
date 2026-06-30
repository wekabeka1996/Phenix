import json
from pathlib import Path

ROOT = Path(".")
TRADE_LIFECYCLE = ROOT / "logs" / "trade_lifecycle.jsonl"
RID = "aurora_BNBUSDT_1781850002085"

print(f"--- Records containing {RID} ---")
with open(TRADE_LIFECYCLE, "r", encoding="utf-8") as f:
    for line in f:
        if RID in line:
            obj = json.loads(line)
            print(json.dumps(obj, indent=2))
