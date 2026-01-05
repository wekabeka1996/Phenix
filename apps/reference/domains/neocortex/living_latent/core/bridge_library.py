# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""Bridge Library (R0-Lite)

SPEC intent (Road_map R0-07 -> R0 hardening):
 - Centralize persistence of VALID bridge plans beyond raw per-run files.
 - Provide simple deduplication via content hash (points + initial_cost + final_cost).
 - Maintain an index JSONL (`bridges_index.jsonl`) with minimal metadata for
   fast later querying / selection experiments (R1).
 - Keep library append-only (immutability) except GC (future).

Design:
 - Each accepted valid bridge is serialized under `library_dir/bridge_<hash>.json`.
 - Index line written atomically (append). Contains: hash, ts, complexity_score,
   improvement, plan_points, file path.
 - Dedup: if file exists, skip storing (idempotent add).
 - Thread-safety: minimal (single process orchestrator); for future concurrency
   a file lock would be added.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Optional

from .bridge_slerp import BridgePlan

class BridgeLibrary:
    def __init__(self, library_dir: Path):
        self.dir = Path(library_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "bridges_index.jsonl"

    def _hash_plan(self, plan: BridgePlan) -> str:
        h = hashlib.sha256()
        h.update(json.dumps({
            "points": plan.points,
            "initial_cost": plan.metadata.get("initial_cost"),
            "final_cost": plan.cost,
        }, sort_keys=True).encode("utf-8"))
        return h.hexdigest()[:32]

    def add(self, plan: BridgePlan) -> Optional[str]:
        """Add a VALID bridge plan to the library.

        Returns the hash if stored (or existing hash if duplicate), else None if plan invalid.
        """
        if not plan.valid:
            return None
        h = self._hash_plan(plan)
        dst = self.dir / f"bridge_{h}.json"
        if not dst.exists():
            with open(dst, "w", encoding="utf-8") as f:
                try:
                    f.write(plan.model_dump_json(indent=2))
                except AttributeError:
                    f.write(plan.json(indent=2))
        # Avoid duplicate index row
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            rec = json.loads(line)
                            if rec.get("hash") == h:
                                return h
                        except Exception:
                            continue
            except Exception:
                pass
        idx_row = {
            "hash": h,
            "ts": plan.metadata.get("ts"),
            "complexity_score": plan.metadata.get("complexity_score"),
            "improvement": plan.metadata.get("improvement"),
            "plan_points": plan.metadata.get("plan_points"),
            "path": str(dst),
        }
        with open(self.index_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(idx_row, ensure_ascii=False) + "\n")
        return h

__all__ = ["BridgeLibrary"]
