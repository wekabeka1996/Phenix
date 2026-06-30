import json
from pathlib import Path
import re

ROOT = Path(r"C:\Users\wekab\Music\Phenix")

def find_trend_keyword():
    files = list(ROOT.glob("order_log_old/*.jsonl")) + list(ROOT.glob("logs/*.jsonl")) + list(ROOT.glob("ops/wal/*.jsonl"))
    
    seen_keys = set()
    found_lines = 0
    for f in files:
        if f.name == "order_log_v1.jsonl" and "old" not in f.parts:
            continue
        try:
            with open(f, 'r', encoding='utf-8', errors='replace') as fh:
                for idx, line in enumerate(fh, 1):
                    if "trend" in line.lower() or "veto" in line.lower():
                        found_lines += 1
                        try:
                            rec = json.loads(line)
                            def extract_keys(d, path=""):
                                if isinstance(d, dict):
                                    for k, v in d.items():
                                        if "trend" in k.lower() or "veto" in k.lower():
                                            seen_keys.add(f"{path}.{k}")
                                        extract_keys(v, f"{path}.{k}")
                                elif isinstance(d, list):
                                    for i, v in enumerate(d):
                                        extract_keys(v, f"{path}[{i}]")
                            extract_keys(rec)
                        except:
                            pass
                        if found_lines >= 1000:
                            break
        except Exception as e:
            pass
        if found_lines >= 1000:
            break
    print("Keys containing 'trend' or 'veto':")
    for k in sorted(list(seen_keys)):
        print(f"- {k}")

find_trend_keyword()
