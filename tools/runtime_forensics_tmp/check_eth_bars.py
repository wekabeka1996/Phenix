import json
from pathlib import Path

ROOT = Path(".")
WAL_FILES = [
    ROOT / "ops" / "wal" / "2026-06-18.jsonl",
    ROOT / "ops" / "wal" / "2026-06-19.jsonl",
    ROOT / "ops" / "wal" / "2026-06-20.jsonl",
]

# Load ETHUSDT bars after 1781811905972
bars = []
for wf in WAL_FILES:
    if not wf.exists():
        continue
    with open(wf, "r", encoding="utf-8") as f:
        for line in f:
            if "BAR_CLOSED" not in line:
                continue
            obj = json.loads(line)
            pld = obj.get("pld", {})
            if pld.get("symbol") == "ETHUSDT" and pld.get("tf_sec") in (180, 300):
                bar = pld.get("bar", {})
                bars.append({
                    "ts": pld.get("bar_close_ts") or bar.get("end_ts_ms"),
                    "high": float(bar["high"]),
                    "low": float(bar["low"]),
                })

bars.sort(key=lambda x: x["ts"])
after = [b for b in bars if b["ts"] > 1781811905972]
print(f"Total after bars: {len(after)}")
if after:
    highs = [b["high"] for b in after]
    lows = [b["low"] for b in after]
    print(f"High range: {min(highs)} -> {max(highs)}")
    print(f"Low range: {min(lows)} -> {max(lows)}")
