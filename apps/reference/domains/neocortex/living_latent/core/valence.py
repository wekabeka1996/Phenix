"""
Utilities for valence propagation and logging.

Functions:
- ensure_meta_valence(bridge_payload: dict, logs_dir: str) -> dict
  Ensures payload.meta.valence is populated from the latest valence.log if missing or falsy.
  Also ensures payload.meta.bridge_uid exists (stable sha256 over key fields) for dedup.

- append_valence(logs_dir: str, ts: float, h_t: float) -> None
  Appends a JSON line {"ts": ts, "valence": h_t} to logs_dir/valence.log (best-effort).

Notes:
- Supports both JSON-lines and simple CSV parsing when reading latest valence.
- logs_dir defaults can be resolved via LLA_RUN_LOGS env from callers.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable


def _resolve_logs_dir(logs_dir: str | os.PathLike | None) -> Path:
    if logs_dir:
        p = Path(logs_dir)
    else:
        p = Path(os.environ.get("LLA_RUN_LOGS", "living_latent/runs/last/logs"))
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def _read_latest_valence_line(val_path: Path) -> float | None:
    if not val_path.exists():
        return None
    last_val: float | None = None
    try:
        # Read file in reverse efficiently (fallback to forward)
        with val_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-200:]  # limit scan
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            # Try JSON first
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "valence" in obj:
                    v = float(obj.get("valence"))
                    last_val = v
                    break
            except Exception:
                # Try CSV: ts,val
                try:
                    parts = [p for p in line.split(",") if p]
                    if len(parts) >= 2:
                        v = float(parts[-1])
                        last_val = v
                        break
                except Exception:
                    continue
    except Exception:
        last_val = None
    return last_val


def _sha256_bytes(chunks: Iterable[bytes]) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(c)
    return h.hexdigest()


def _compute_bridge_uid(payload: dict) -> str:
    """Compute a stable UID for a bridge from its critical fields.

    Uses: points (rounded), J/cost, and selected meta keys.
    """
    pts = payload.get("points")
    J = payload.get("J", payload.get("cost", 0.0))
    meta = payload.get("meta", payload.get("metadata", {})) or {}
    # Round points to reduce uid sensitivity to minute FP noise
    try:
        pts_round = None
        if isinstance(pts, list):
            pts_round = [[round(float(x), 6) for x in row] for row in pts if isinstance(row, (list, tuple))]
        elif hasattr(pts, "tolist"):
            arr = pts.tolist()
            pts_round = [[round(float(x), 6) for x in row] for row in arr]
    except Exception:
        pts_round = pts
    # Exclude volatile or runtime fields from the canonical fingerprint so
    # identical logical bridges produce the same UID even if timestamps,
    # delta_J, runtime ids or file paths differ.
    volatile_keys = {"delta_J", "delta_j", "ts", "timestamp", "runtime_ids"}
    key_meta = {}
    for k, v in (meta or {}).items():
        if k in volatile_keys:
            continue
        if k.startswith('file_'):
            continue
        # keep a small allowlist of deterministic scalar fields commonly used
        if k in ("efe", "ood", "energy", "plan_points", "cvar", "cvar_alpha", "cvar_lambda"):
            key_meta[k] = v
    # Use a canonical JSON serialization (sorted keys, compact separators)
    blob = json.dumps({"points": pts_round, "J": J, "meta": key_meta}, sort_keys=True, ensure_ascii=False, separators=(",",":"))
    return _sha256_bytes([blob.encode("utf-8")])


def ensure_meta_valence(bridge_payload: dict, logs_dir: str | os.PathLike | None = None) -> dict:
    """Ensure payload.meta.valence and meta.bridge_uid are set.

    - If meta.valence is missing or falsy (0/None), set from the latest valence.log value if available.
    - Compute and set stable meta.bridge_uid.
    Returns the mutated payload.
    """
    if not isinstance(bridge_payload, dict):
        return bridge_payload
    meta_key = "meta" if "meta" in bridge_payload else ("metadata" if "metadata" in bridge_payload else None)
    if meta_key is None:
        bridge_payload["meta"] = {}
        meta_key = "meta"
    meta = bridge_payload.get(meta_key) or {}

    logs_p = _resolve_logs_dir(logs_dir)
    val_path = logs_p / "valence.log"
    latest = _read_latest_valence_line(val_path)
    # Fallback: use process-global cache if available (populated by runtime)
    if latest is None:
        try:
            from living_latent.scripts.run_r0 import _LATEST_VALENCE  # type: ignore
            if float(_LATEST_VALENCE or 0.0) != 0.0:
                latest = float(_LATEST_VALENCE)
        except Exception:
            try:
                from living_latent.core.bridge_slerp import _LATEST_VALENCE as _LV2  # type: ignore
                if float(_LV2 or 0.0) != 0.0:
                    latest = float(_LV2)
            except Exception:
                pass
    # Fill valence if not present or falsy
    cur = meta.get("valence")
    try:
        missing_or_falsy = (cur is None) or (float(cur) == 0.0)
    except Exception:
        missing_or_falsy = True
    if missing_or_falsy and latest is not None:
        try:
            meta["valence"] = float(latest)
        except Exception:
            pass

    # Bridge UID
    try:
        uid = _compute_bridge_uid(bridge_payload)
        meta["bridge_uid"] = uid
    except Exception:
        pass
    bridge_payload[meta_key] = meta
    return bridge_payload


def append_valence(logs_dir: str | os.PathLike | None, ts: float, h_t: float) -> None:
    """Append a JSON line to valence.log best-effort and ensure directory exists."""
    logs_p = _resolve_logs_dir(logs_dir)
    val_path = logs_p / "valence.log"
    try:
        rec = {"ts": float(ts), "valence": float(h_t)}
        with val_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # ignore failures
        pass


__all__ = [
    "ensure_meta_valence",
    "append_valence",
]
