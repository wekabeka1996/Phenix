# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
import json, time
from pathlib import Path

def log_event(run_dir: str, name: str, payload: dict | None = None):
    payload = payload or {}
    rec = {"event": name, "ts": time.time(), **payload}
    p = Path(run_dir) / "logs" / "blackbox.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
