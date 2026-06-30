import json
from pathlib import Path

ROOT = Path(".")
RIDS = ["mdamr-deb8a8627c08e73a", "aurora_BNBUSDT_1781849401488", "mdamr-c510a3a6d9247ce2"]

for f in ROOT.glob("logs/*"):
    if not f.is_file() or f.suffix not in (".jsonl", ".log", ".log.1", ".log.2"):
        continue
    try:
        print(f"Scanning {f.name}...")
        with open(f, "r", encoding="utf-8", errors="ignore") as file:
            # Let's read first few lines or search for the rids
            for line_no, line in enumerate(file, 1):
                for rid in RIDS:
                    if rid in line:
                        print(f"  FOUND {rid} in {f.name}:{line_no}")
                        print(f"    Line snippet: {line[:300]}...")
    except Exception as e:
        print(f"  Error reading {f.name}: {e}")
