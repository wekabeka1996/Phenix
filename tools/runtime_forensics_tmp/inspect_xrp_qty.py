import json
from pathlib import Path

ROOT = Path(".")
TRADE_LIFECYCLE = ROOT / "logs" / "trade_lifecycle.jsonl"

print("--- XRPUSDT FILLS ---")
count = 0
with open(TRADE_LIFECYCLE, "r", encoding="utf-8") as f:
    for line in f:
        if "XRPUSDT" in line and "fill_qty" in line:
            obj = json.loads(line)
            print(f"symbol={obj.get('symbol')} qty={obj.get('fill_qty')} price={obj.get('fill_price')}")
            count += 1
            if count >= 5:
                break
