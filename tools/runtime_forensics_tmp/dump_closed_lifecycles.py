import json
from pathlib import Path

ROOT = Path(".")
TRADE_LIFECYCLE = ROOT / "logs" / "trade_lifecycle.jsonl"

with open(TRADE_LIFECYCLE, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        if obj.get("status") == "CLOSED" or "CLOSED" in obj.get("event_type", ""):
            print(json.dumps(obj, indent=2))
