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
                    # print string values recursively that contain 'trend' or 'veto'
                    def print_values(d, path=""):
                        if isinstance(d, dict):
                            for k, v in d.items():
                                if isinstance(v, str) and ("trend" in v.lower() or "veto" in v.lower()):
                                    print(f"  {path}.{k} = {v}")
                                print_values(v, f"{path}.{k}")
                        elif isinstance(d, list):
                            for i, v in enumerate(d):
                                print_values(v, f"{path}[{i}]")
                    print_values(rec)
                    break
            except:
                pass
