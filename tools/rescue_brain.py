#!/usr/bin/env python3
"""
rescue_brain.py  --  Neocortex Checkpoint Recovery Tool

Scans checkpoint files for NaN/Inf weight corruption and recovers
the most recent clean checkpoint.

Usage:
    python tools/rescue_brain.py                           # auto-detect data/checkpoints/
    python tools/rescue_brain.py --dir data/checkpoints/   # explicit path
    python tools/rescue_brain.py --dry-run                 # scan only, don't copy

Exit codes:
    0 - checkpoint_latest.pt is clean (or was successfully recovered)
    1 - corruption detected and recovery failed (no clean checkpoint found)
    2 - no checkpoint files found
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("rescue_brain")

try:
    import torch
except ImportError:
    logger.error("PyTorch is required.  pip install torch")
    sys.exit(2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def scan_state_dict(state_dict: dict) -> dict:
    """
    Scan a state_dict for NaN and Inf values.

    Returns a summary dict:
      {
        "clean": bool,
        "total_params": int,
        "nan_params": [str, ...],
        "inf_params": [str, ...],
      }
    """
    nan_params = []
    inf_params = []
    total = 0

    for name, tensor in state_dict.items():
        if not isinstance(tensor, torch.Tensor):
            continue
        total += 1
        if torch.isnan(tensor).any():
            nan_params.append(name)
        if torch.isinf(tensor).any():
            inf_params.append(name)

    return {
        "clean": len(nan_params) == 0 and len(inf_params) == 0,
        "total_params": total,
        "nan_params": nan_params,
        "inf_params": inf_params,
    }


def scan_checkpoint(path: Path) -> dict:
    """
    Load a .pt checkpoint and scan ALL state_dicts it contains.

    Returns:
      {
        "path": Path,
        "clean": bool,
        "train_steps": int | None,
        "components": { "vae_state": <scan>, "ppo_model_state": <scan>, ... },
        "error": str | None,
      }
    """
    result = {
        "path": path,
        "clean": False,
        "train_steps": None,
        "components": {},
        "error": None,
    }

    try:
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:
        result["error"] = str(exc)
        return result

    result["train_steps"] = ckpt.get("train_steps")

    STATE_KEYS = [
        "vae_state", "wm_state", "ppo_model_state",
        "vae_opt_state", "wm_opt_state", "ppo_opt_state",
    ]

    all_clean = True
    for key in STATE_KEYS:
        sd = ckpt.get(key)
        if sd is None:
            continue
        scan = scan_state_dict(sd)
        result["components"][key] = scan
        if not scan["clean"]:
            all_clean = False

    result["clean"] = all_clean
    return result


def find_numbered_checkpoints(directory: Path) -> list[Path]:
    """
    Find all checkpoint_N.pt files, sorted by N descending (most recent first).
    """
    pattern = re.compile(r"checkpoint_(\d+)\.pt$")
    matches = []
    for f in directory.iterdir():
        m = pattern.match(f.name)
        if m:
            matches.append((int(m.group(1)), f))
    matches.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in matches]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Neocortex checkpoint NaN/Inf scanner & recovery")
    parser.add_argument("--dir", type=Path, default=Path("data/checkpoints"),
                        help="Checkpoint directory (default: data/checkpoints)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only scan, don't overwrite checkpoint_latest.pt")
    args = parser.parse_args()

    ckpt_dir = args.dir
    if not ckpt_dir.exists():
        logger.error("Checkpoint directory not found: %s", ckpt_dir)
        sys.exit(2)

    latest = ckpt_dir / "checkpoint_latest.pt"
    if not latest.exists():
        logger.error("checkpoint_latest.pt not found in %s", ckpt_dir)
        sys.exit(2)

    # 1. Scan latest
    logger.info("Scanning %s ...", latest)
    result = scan_checkpoint(latest)

    if result["error"]:
        logger.error("Failed to load checkpoint_latest.pt: %s",
                     result["error"])
        sys.exit(1)

    logger.info("  train_steps: %s", result["train_steps"])
    for comp, scan in result["components"].items():
        status = "CLEAN" if scan["clean"] else "CORRUPTED"
        details = ""
        if scan["nan_params"]:
            details += f" NaN in: {scan['nan_params'][:5]}{'...' if len(scan['nan_params']) > 5 else ''}"
        if scan["inf_params"]:
            details += f" Inf in: {scan['inf_params'][:5]}{'...' if len(scan['inf_params']) > 5 else ''}"
        logger.info("  %-20s [%s]%s", comp, status, details)

    if result["clean"]:
        logger.info("checkpoint_latest.pt is CLEAN. No recovery needed.")
        sys.exit(0)

    # 2. Latest is corrupted. Find the most recent clean checkpoint.
    logger.warning("checkpoint_latest.pt is CORRUPTED!")

    if args.dry_run:
        logger.info("--dry-run: not attempting recovery.")
        sys.exit(1)

    numbered = find_numbered_checkpoints(ckpt_dir)
    if not numbered:
        logger.error("No numbered checkpoints found for recovery.")
        sys.exit(1)

    logger.info(
        "Searching %d numbered checkpoints for the most recent clean one...", len(numbered))

    for candidate in numbered:
        cand_result = scan_checkpoint(candidate)
        if cand_result["error"]:
            logger.warning("  %s: load error (%s)",
                           candidate.name, cand_result["error"])
            continue
        if cand_result["clean"]:
            logger.info("  %s (step %s): CLEAN  <-- recovery candidate",
                        candidate.name, cand_result["train_steps"])

            # Back up the corrupted latest
            backup = ckpt_dir / "checkpoint_latest_corrupted.pt"
            shutil.copy2(latest, backup)
            logger.info("  Backed up corrupted latest to %s", backup.name)

            # Replace with clean
            shutil.copy2(candidate, latest)
            logger.info("  Restored checkpoint_latest.pt from %s (step %s)",
                        candidate.name, cand_result["train_steps"])
            sys.exit(0)
        else:
            logger.warning("  %s (step %s): CORRUPTED, skipping",
                           candidate.name, cand_result["train_steps"])

    logger.error(
        "ALL checkpoints are corrupted.  Manual intervention required.")
    sys.exit(1)


if __name__ == "__main__":
    main()
