import json
from pathlib import Path

ROOT = Path(".")
WAL_FILE = ROOT / "ops" / "wal" / "2026-06-19.jsonl"

print("--- WAL SAMPLE ---")
count = 0
with open(WAL_FILE, "r", encoding="utf-8") as f:
    for line in f:
        obj = json.loads(line)
        print(json.dumps(obj, indent=2))
        count += 1
        if count >= 3:
            break
