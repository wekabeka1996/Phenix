import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
f = ROOT / "order_log_old" / "order_log_v1.20260614T100428Z.000.jsonl"

with open(f, 'r', encoding='utf-8') as fh:
    for idx, line in enumerate(fh, 1):
        if idx == 864:
            rec = json.loads(line)
            print("Event keys:", rec.keys())
            print("strategies keys/type:", type(rec['strategies']), list(rec['strategies'].keys()) if isinstance(rec['strategies'], dict) else "not dict")
            # Print strategies detail
            print(json.dumps(rec['strategies'], indent=2)[:2000])
            break
