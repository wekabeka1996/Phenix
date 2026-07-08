import os
from pathlib import Path
from datetime import datetime, timezone

LOGS_DIR = Path("logs")
PATCH_TIME = datetime.fromisoformat("2026-06-30T18:47:37+00:00")

def check_guardian_start():
    path = LOGS_DIR / "order_guardian.log"
    if not path.exists():
         return
    print(f"Scanning order_guardian.log for startup after {PATCH_TIME.isoformat()}...")
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.split(" - ")
            if len(parts) < 2:
                continue
            ts_str = parts[0].strip()
            try:
                dt_local = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
                epoch = dt_local.timestamp() - 3*3600
                dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
            except ValueError:
                continue
            
            if dt >= PATCH_TIME:
                l_lower = line.lower()
                if "start" in l_lower or "init" in l_lower or "boot" in l_lower or "version" in l_lower or "guardian" in l_lower or "reconnect" in l_lower:
                    # filter out common noisy lines
                    if "linked existing orders" not in l_lower and "ping" not in l_lower:
                         print(f"  [{dt.isoformat()}] {line.strip()[:150]}")

if __name__ == "__main__":
    check_guardian_start()
