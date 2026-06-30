import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
f = ROOT / "order_log_old" / "order_log_v1.20260614T100428Z.000.jsonl"

with open(f, 'r', encoding='utf-8') as fh:
    for idx, line in enumerate(fh, 1):
        if idx == 51:
            print(json.dumps(json.loads(line), indent=2))
            break
