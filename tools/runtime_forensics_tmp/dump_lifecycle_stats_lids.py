import json
from pathlib import Path

ROOT = Path(".")
EXEC_STATS = ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl"
LIDS = ["8e34f539-f390-48bf-9982-34f28e76e7b5", "6c658dd3-0fbd-473a-b11c-27c8676141b8"]

for lid in LIDS:
    print(f"\n--- Records for LID: {lid} ---")
    with open(EXEC_STATS, "r", encoding="utf-8") as f:
        for line in f:
            if lid in line:
                obj = json.loads(line)
                print(json.dumps(obj, indent=2))
