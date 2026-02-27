#!/usr/bin/env python3
"""
Checkpoint utility: remove PPO state from a Neocortex checkpoint.

Use this after latent-space surgery to keep VAE/WorldModel weights while
forcing PPO (actor/critic/optimizer) to re-initialize from scratch.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, List


REPO_ROOT = Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove PPO states from checkpoint_latest.pt (PPO amnesia)."
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=REPO_ROOT / "data/checkpoints/checkpoint_latest.pt",
        help="Path to input checkpoint (.pt).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output checkpoint path. Ignored with --inplace. "
            "Default: <checkpoint_stem>_clean.pt"
        ),
    )
    parser.add_argument(
        "--inplace",
        action="store_true",
        help="Overwrite the input checkpoint path.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        default=False,
        help="Create .bak copy before in-place overwrite.",
    )
    parser.add_argument(
        "--keys",
        nargs="+",
        default=["ppo_model_state", "ppo_opt_state"],
        help="Checkpoint keys to remove.",
    )
    return parser.parse_args()


def _require_torch():
    try:
        import torch  # type: ignore

        return torch
    except ModuleNotFoundError:
        print(
            "[ERROR] Missing dependency: torch. Install with: pip install torch",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _load_checkpoint(torch_mod, path: Path) -> Dict[str, Any]:
    ckpt = torch_mod.load(path, map_location="cpu")
    if not isinstance(ckpt, dict):
        raise ValueError(f"Checkpoint root is not a dict: {type(ckpt)}")
    return ckpt


def _remove_keys(ckpt: Dict[str, Any], keys: List[str]) -> List[str]:
    removed: List[str] = []
    for key in keys:
        if key in ckpt:
            del ckpt[key]
            removed.append(key)
    return removed


def _target_path(checkpoint: Path, output: Path | None, inplace: bool) -> Path:
    if inplace:
        return checkpoint
    if output is not None:
        return output
    return checkpoint.with_name(f"{checkpoint.stem}_clean{checkpoint.suffix}")


def _write_metadata(ckpt: Dict[str, Any], removed: List[str], src: Path) -> None:
    meta = ckpt.get("checkpoint_metadata")
    if not isinstance(meta, dict):
        meta = {}
        ckpt["checkpoint_metadata"] = meta
    meta["ppo_reset"] = {
        "timestamp_utc": dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "removed_keys": removed,
        "source_checkpoint": str(src),
        "reason": "ppo_amnesia_after_latent_surgery",
    }


def main() -> int:
    args = parse_args()
    torch_mod = _require_torch()

    checkpoint_path = args.checkpoint.resolve()
    if not checkpoint_path.exists():
        print(f"[ERROR] Checkpoint not found: {checkpoint_path}", file=sys.stderr)
        return 2

    try:
        checkpoint = _load_checkpoint(torch_mod, checkpoint_path)
    except Exception as e:
        print(f"[ERROR] Failed to load checkpoint: {e}", file=sys.stderr)
        return 2

    original = copy.deepcopy(checkpoint)
    removed = _remove_keys(checkpoint, list(args.keys))
    _write_metadata(checkpoint, removed=removed, src=checkpoint_path)

    output_path = _target_path(
        checkpoint=checkpoint_path,
        output=args.output.resolve() if args.output else None,
        inplace=bool(args.inplace),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.inplace and args.backup:
        backup_path = checkpoint_path.with_suffix(
            checkpoint_path.suffix
            + ".bak."
            + dt.datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        )
        shutil.copy2(checkpoint_path, backup_path)
        print(f"[INFO] Backup created: {backup_path}")

    try:
        torch_mod.save(checkpoint, output_path)
    except Exception as e:
        print(f"[ERROR] Failed to save checkpoint: {e}", file=sys.stderr)
        return 2

    print(f"[INFO] Input checkpoint:  {checkpoint_path}")
    print(f"[INFO] Output checkpoint: {output_path}")
    if removed:
        print("[INFO] Removed keys: " + ", ".join(removed))
    else:
        print("[WARN] No requested PPO keys were present; checkpoint unchanged structurally.")

    kept = sorted(k for k in original.keys() if k not in removed)
    print("[INFO] Remaining top-level keys: " + ", ".join(kept))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
