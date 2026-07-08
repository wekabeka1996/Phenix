import os
import sys
from pathlib import Path

# Reconfigure stdout to handle UTF-8/emojis on Windows console
sys.stdout.reconfigure(encoding='utf-8')

LOGS_DIR = Path("logs")

def search_logs(pattern):
    print(f"Searching logs for pattern: {pattern}")
    for file_path in sorted(LOGS_DIR.glob("aurora_core.log*"), key=lambda x: x.name):
        print(f"Checking {file_path.name}...")
        match_count = 0
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, 1):
                if pattern.lower() in line.lower():
                    match_count += 1
                    if match_count <= 50:
                        print(f"  Line {i}: {line.strip()[:200]}")
        print(f"Total matches in {file_path.name}: {match_count}")

if __name__ == "__main__":
    search_logs("aurora")
