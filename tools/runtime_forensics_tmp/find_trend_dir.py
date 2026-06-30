import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")

def find_trend_dir():
    # Scan logs and wal files
    files = []
    files.extend(list(ROOT.glob("order_log_old/*.jsonl")))
    files.extend(list(ROOT.glob("logs/*.jsonl")))
    files.extend(list(ROOT.glob("ops/wal/*.jsonl")))
    files.extend(list(ROOT.glob("ops/wal/old/*.jsonl")))
    
    found = 0
    for f in files:
        if f.name == "order_log_v1.jsonl" and "old" not in f.parts:
            continue
        # Check if "trend_dir" is in the file text
        try:
            with open(f, 'r', encoding='utf-8', errors='replace') as fh:
                for idx, line in enumerate(fh, 1):
                    if "trend_dir" in line:
                        print(f"Found trend_dir in {f.relative_to(ROOT).as_posix()} at line {idx}")
                        # print the parsed json
                        rec = json.loads(line)
                        # search for trend_dir value
                        def find_key(d, path=""):
                            if isinstance(d, dict):
                                for k, v in d.items():
                                    if k == "trend_dir":
                                        print(f"  {path}.trend_dir = {v}")
                                    find_key(v, f"{path}.{k}")
                            elif isinstance(d, list):
                                for i, v in enumerate(d):
                                    find_key(v, f"{path}[{i}]")
                        find_key(rec)
                        found += 1
                        if found >= 10:
                            return
        except Exception as e:
            pass

find_trend_dir()
