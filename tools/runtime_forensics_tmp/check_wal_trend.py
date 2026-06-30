import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
p = ROOT / "ops" / "wal" / "2026-06-17.jsonl"

with open(p, 'r', encoding='utf-8', errors='replace') as fh:
    for idx, line in enumerate(fh, 1):
        if "trend" in line.lower() or "veto" in line.lower():
            try:
                rec = json.loads(line)
                if rec.get("verb") == "TRADE_INTENT_PROPOSED":
                    print(f"Line {idx} matches:")
                    # print keys recursively that contain 'trend' or 'veto'
                    def print_keys(d, path=""):
                        if isinstance(d, dict):
                            for k, v in d.items():
                                if "trend" in k.lower() or "veto" in k.lower():
                                    print(f"  {path}.{k} = {v}")
                                print_keys(v, f"{path}.{k}")
                        elif isinstance(d, list):
                            for i, v in enumerate(d):
                                print_keys(v, f"{path}[{i}]")
                    print_keys(rec)
                    break
            except:
                pass
