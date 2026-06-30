import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
p = ROOT / "ops" / "wal" / "2026-06-17.jsonl"

with open(p, 'r', encoding='utf-8', errors='replace') as fh:
    for idx, line in enumerate(fh, 1):
        try:
            rec = json.loads(line)
            if rec.get("verb") == "TRADE_INTENT_PROPOSED" and rec.get("rid") == "aurora_BNBUSDT_1781715901137":
                trace = rec.get("pld", {}).get("trace") or {}
                print("Keys in trace:", list(trace.keys()))
                print(json.dumps(trace, indent=2))
                break
        except Exception as e:
            pass
