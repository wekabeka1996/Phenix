from __future__ import annotations
import json
import pathlib
import time
from typing import Any, Dict

SNAP_DIR = pathlib.Path("ops/snapshots")

def save(domain: str, state: Dict[str, Any]) -> str:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAP_DIR / domain / f"{int(time.time()*1000)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return str(path)

def load_latest(domain: str) -> Dict[str, Any] | None:
    p = SNAP_DIR / domain
    if not p.exists():
        return None
    files = sorted(p.glob("*.json"))
    if not files:
        return None
    data: Dict[str, Any] = json.loads(files[-1].read_text(encoding="utf-8"))
    return data
