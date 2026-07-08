import os
import sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

LOGS_DIR = Path("logs")
START_LOCAL = datetime.fromisoformat("2026-06-30T21:45:00")
END_LOCAL = datetime.fromisoformat("2026-06-30T21:55:00")

def dump_around_patch():
    print(f"Dumping log lines between {START_LOCAL.isoformat()} and {END_LOCAL.isoformat()} local time...")
    for file_path in sorted(LOGS_DIR.glob("aurora_core.log*"), key=lambda x: x.name):
        print(f"\n--- Checking {file_path.name} ---")
        line_count = 0
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = line.split(" - ")
                if len(parts) < 2:
                    continue
                ts_str = parts[0].strip()
                try:
                    dt_local = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
                except ValueError:
                    continue
                
                if START_LOCAL <= dt_local <= END_LOCAL:
                    line_count += 1
                    if line_count <= 40:
                        print(f"  Line {line_count}: {line.strip()[:180]}")
        print(f"Total lines in range for {file_path.name}: {line_count}")

if __name__ == "__main__":
    dump_around_patch()
