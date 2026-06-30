import os
from pathlib import Path
import json

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
TARGET_DIRS = ["order_log_old", "logs", "data", "ops", "reports"]
EXTENSIONS = {".jsonl", ".json", ".log", ".csv", ".parquet", ".wal", ".db", ".sqlite", ".sqlite3"}

found_files = []
for dir_name in TARGET_DIRS:
    dir_path = ROOT / dir_name
    if not dir_path.exists():
        continue
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            p = Path(root) / file
            if p.suffix.lower() in EXTENSIONS:
                rel_p = p.relative_to(ROOT).as_posix()
                size = p.stat().st_size
                found_files.append((rel_p, size))

print(f"Total matching files found: {len(found_files)}")
# Print first 50 files
for rel_p, size in sorted(found_files)[:100]:
    print(f"- {rel_p} ({size} bytes)")
