import json
from pathlib import Path
from collections import Counter

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
ORDER_LOG_OLD_DIR = ROOT / "order_log_old"

print("Scanning all logs for nested safety gate variables...")

trend_dir_paths = Counter()
trend_run_length_paths = Counter()
pm_norm_60s_paths = Counter()
pm_norm_300s_paths = Counter()

def scan_dict(d, path=""):
    for k, v in d.items():
        curr_path = f"{path}.{k}" if path else k
        if k == "trend_dir":
            trend_dir_paths[curr_path] += 1
        elif k == "trend_run_length":
            trend_run_length_paths[curr_path] += 1
        elif k == "pm_norm_60s":
            pm_norm_60s_paths[curr_path] += 1
        elif k == "pm_norm_300s":
            pm_norm_300s_paths[curr_path] += 1
            
        if isinstance(v, dict):
            scan_dict(v, curr_path)
        elif isinstance(v, str):
            # Check if it is a nested JSON string
            if v.strip().startswith("{") and v.strip().endswith("}"):
                try:
                    nested = json.loads(v)
                    scan_dict(nested, curr_path)
                except Exception:
                    pass

for f in sorted(list(ORDER_LOG_OLD_DIR.glob("*.jsonl"))):
    with open(f, 'r', encoding='utf-8', errors='replace') as fh:
        for idx, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                scan_dict(rec)
            except Exception:
                pass

print("\n--- trend_dir paths found ---")
for p, c in trend_dir_paths.items():
    print(f"Path: {p}, Count: {c}")

print("\n--- trend_run_length paths found ---")
for p, c in trend_run_length_paths.items():
    print(f"Path: {p}, Count: {c}")

print("\n--- pm_norm_60s paths found ---")
for p, c in pm_norm_60s_paths.items():
    print(f"Path: {p}, Count: {c}")

print("\n--- pm_norm_300s paths found ---")
for p, c in pm_norm_300s_paths.items():
    print(f"Path: {p}, Count: {c}")
