import json
from pathlib import Path

ROOT = Path(".")
EXEC_STATS = ROOT / "logs" / "execution_lifecycle_stats_v1.jsonl"
RIDS = ["aurora_BNBUSDT_1781943305149", "mdamr-96c189df297610bb"]

for rid in RIDS:
    print(f"\n--- Records for RID: {rid} ---")
    with open(EXEC_STATS, "r", encoding="utf-8") as f:
        for line in f:
            if rid in line:
                obj = json.loads(line)
                print(json.dumps(obj, indent=2))
