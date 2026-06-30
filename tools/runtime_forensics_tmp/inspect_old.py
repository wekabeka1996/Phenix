import os
import json
from pathlib import Path

ROOT = Path(r"C:\Users\wekab\Music\Phenix")

def scan_dir(dir_name):
    dir_path = ROOT / dir_name
    if not dir_path.exists():
        print(f"Directory {dir_name} does not exist")
        return
    print(f"\n=== Scanning {dir_name} ===")
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            p = Path(root) / file
            rel_p = p.relative_to(ROOT).as_posix()
            size = p.stat().st_size
            print(f"- {rel_p} ({size} bytes)")

scan_dir("order_log_old")
scan_dir("logs")
scan_dir("data")
scan_dir("wal")
scan_dir("ops")
