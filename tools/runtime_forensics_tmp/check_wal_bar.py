import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
p = ROOT / "ops" / "wal" / "2026-06-17.jsonl"

with open(p, 'r', encoding='utf-8', errors='replace') as fh:
    for idx, line in enumerate(fh, 1):
        try:
            rec = json.loads(line)
            if rec.get("verb") == "BAR_CLOSED":
                print(f"File: {p.relative_to(ROOT).as_posix()} | Line: {idx}")
                print(json.dumps(rec, indent=2))
                break
        except Exception as e:
            pass
