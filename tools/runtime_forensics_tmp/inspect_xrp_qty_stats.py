import json
from pathlib import Path

ROOT = Path(".")
EXEC_STATS = ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl"

print("--- XRPUSDT STATS ---")
count = 0
with open(EXEC_STATS, "r", encoding="utf-8") as f:
    for line in f:
        if "XRPUSDT" in line:
            obj = json.loads(line)
            print(f"symbol={obj.get('symbol')} qty={obj.get('qty')} price={obj.get('entry_price')}")
            count += 1
            if count >= 5:
                break
