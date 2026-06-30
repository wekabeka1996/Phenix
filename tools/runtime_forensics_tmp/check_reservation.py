import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                if rec.get("rid") == "reserve_6aa49b36-e5d5-48c4-9877-e3d8b42c07c4" or rec.get("lifecycle_id") == "6aa49b36-e5d5-48c4-9877-e3d8b42c07c4":
                    print(f"File {f.name} Line {idx}:")
                    print(json.dumps(rec, indent=2))
            except Exception as e:
                pass
