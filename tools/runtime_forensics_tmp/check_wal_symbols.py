import json
from pathlib import Path

ROOT = Path(".")
WAL_FILES = [
    ROOT / "ops" / "wal" / "2026-06-18.jsonl",
    ROOT / "ops" / "wal" / "2026-06-19.jsonl",
    ROOT / "ops" / "wal" / "2026-06-20.jsonl",
]

symbols = {}
with open(WAL_FILES[1], "r", encoding="utf-8") as f:
    for line in f:
        if "BAR_CLOSED" in line:
            obj = json.loads(line)
            pld = obj.get("pld", {})
            symbol = pld.get("symbol")
            tf = pld.get("tf_sec")
            symbols[symbol] = symbols.get(symbol, 0) + 1
            if len(symbols) > 20:
                break
print("Symbols in WAL:", symbols)
