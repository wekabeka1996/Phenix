
import yaml
from pathlib import Path

path = Path("config/aurora/strategies.yaml")
with open(path, "r") as f:
    data = yaml.safe_load(f)

assignments = data.get("assignments", {})
for symbol, strats in assignments.items():
    print(f"Symbol: {symbol!r}")
    for s in strats:
        print(f"  Strategy: {s!r} (len={len(s)})")
        for char in s:
            print(f"    Char: {char!r} (ord={ord(char)})")
