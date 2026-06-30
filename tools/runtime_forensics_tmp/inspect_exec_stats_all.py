import json
from pathlib import Path

ROOT = Path(".")
EXEC_STATS = ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl"

print("--- EXEC STATS SAMPLE ---")
count = 0
with open(EXEC_STATS, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        print(json.dumps(obj, indent=2))
        count += 1
        if count >= 3:
            break
