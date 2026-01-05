# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""Utility helpers for calibration & objective computation (Batch 008).

SPEC: Calibration objective b008-v1
OBJ = PASS_share − 0.5*violations − 0.05*(Δsurprisal_p95/5) − 0.02*(latency_p95_ms/200)
where Δsurprisal_p95 = max(0, surprisal_p95_post − surprisal_p95_pre), all normalized & clipped to [0,1].
"""
from __future__ import annotations

import json
import hashlib
import uuid
from pathlib import Path
from typing import Any, Dict

__all__ = [
    "file_sha256",
    "new_run_id",
    "load_json",
    "save_json",
    "derive_calib_metrics",
    "compute_objective_v_b008_v1",
    "kappa_plus_placeholder",
]


def file_sha256(p: Path) -> str:
    """Return SHA256 hex digest for file (streamed)."""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def new_run_id() -> str:
    return str(uuid.uuid4())


def load_json(p: Path) -> Dict[str, Any]:  # lenient
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(p: Path, obj: Dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def derive_calib_metrics(acc: Dict[str, Any]) -> Dict[str, float]:
    """Extract & normalize metrics needed for objective.

    Expected optional fields in acceptance.json:
    - passed (bool)
    - surprisal_p95_pre (float)
    - surprisal_p95_post (float)
    - latency_p95_ms (float)
    - violations (int/float)
    """
    passed = 1.0 if acc.get("passed") else 0.0
    viol = float(acc.get("violations", 0.0))
    s_pre = float(acc.get("surprisal_p95_pre", 0.0))
    s_post = float(acc.get("surprisal_p95_post", 0.0))
    delta = max(0.0, s_post - s_pre)  # only penalize increase
    lat_p95 = float(acc.get("latency_p95_ms", 0.0))

    viol_clip = min(1.0, max(0.0, viol))
    dS_norm = min(1.0, max(0.0, delta / 5.0))
    lat_norm = min(1.0, max(0.0, lat_p95 / 200.0))
    return {
        "PASS_share": passed,
        "violations": viol_clip,
        "dS_norm": dS_norm,
        "lat_norm": lat_norm,
    }


def compute_objective_v_b008_v1(m: Dict[str, float]) -> float:
    """Compute objective value for b008-v1 formula."""
    return float(
        m["PASS_share"]
        - 0.5 * m["violations"]
        - 0.05 * m["dS_norm"]
        - 0.02 * m["lat_norm"]
    )


def kappa_plus_placeholder(homeostasis_pct: float | None, efe_norm_clip: float | None) -> float | None:
    """Placeholder for future validated kappa_plus definition."""
    if homeostasis_pct is None or efe_norm_clip is None:
        return None
    homeostasis_pct = max(0.0, min(1.0, homeostasis_pct))
    efe_norm_clip = max(0.0, min(1.0, efe_norm_clip))
    return homeostasis_pct * (1.0 - efe_norm_clip)
