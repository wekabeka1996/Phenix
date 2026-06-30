import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(".")
MKT_DATA = ROOT / "logs" / "aurora_market_data.log"

print("--- MARKET DATA SAMPLE ---")
count = 0
with open(MKT_DATA, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        print(line.strip())
        count += 1
        if count >= 20:
            break
