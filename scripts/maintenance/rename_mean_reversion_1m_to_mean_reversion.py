#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Iterable


OLD = "mean_reversion_1m"
NEW = "mean_reversion"

DEFAULT_SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "venv",
}


@dataclass(frozen=True)
class Change:
    path: Path
    kind: str  # "edit" | "rename"
    detail: str


def _run_rg_files_with_matches(repo_root: Path, skip_dirs: set[str]) -> list[Path] | None:
    rg = subprocess.run(
        ["rg", "--version"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if rg.returncode != 0:
        return None

    cmd: list[str] = ["rg", "--files-with-matches"]
    for d in sorted(skip_dirs):
        cmd.append(f"--glob=!{d}/**")
    cmd.append(OLD)
    cmd.append(str(repo_root))

    res = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    if res.returncode not in (0, 1):
        return None
    files = [Path(line.strip()) for line in res.stdout.splitlines() if line.strip()]
    return files


def _should_skip(path: Path, repo_root: Path, skip_dirs: set[str]) -> bool:
    try:
        rel = path.relative_to(repo_root)
    except Exception:
        return True
    for part in rel.parts:
        if part in skip_dirs:
            return True
    return False


def _is_text_file(path: Path) -> bool:
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".bin"}:
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rename strategy id mean_reversion_1m -> mean_reversion across the repo (content + filenames)."
    )
    ap.add_argument("--apply", action="store_true", help="Write changes to disk (default: dry-run)")
    ap.add_argument("--skip-dir", action="append", default=[], help="Additional directory name(s) to skip")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    skip_dirs = set(DEFAULT_SKIP_DIRS) | set(args.skip_dir)

    # Avoid modifying this script itself in-place.
    self_path = Path(__file__).resolve()

    edits: list[tuple[Path, str]] = []
    renames: list[tuple[Path, Path]] = []
    changes: list[Change] = []

    candidate_files = _run_rg_files_with_matches(repo_root, skip_dirs)
    if candidate_files is None:
        candidate_files = [
            p
            for p in repo_root.rglob("*")
            if p.is_file() and not _should_skip(p, repo_root, skip_dirs)
        ]

    for path in candidate_files:
        if not path.is_file():
            continue
        if path.resolve() == self_path:
            continue

        # Content replacements (only for files that actually contain OLD)
        if _is_text_file(path):
            try:
                original = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if OLD in original:
                updated = original.replace(OLD, NEW)
                if updated != original:
                    edits.append((path, updated))
                    changes.append(Change(path=path, kind="edit", detail=f"replace {OLD} -> {NEW}"))

    # Filename/path renames (files only)
    for path in repo_root.rglob(f"*{OLD}*"):
        if _should_skip(path, repo_root, skip_dirs):
            continue
        if not path.is_file():
            continue
        if path.resolve() == self_path:
            continue
        new_path = path.with_name(path.name.replace(OLD, NEW))
        renames.append((path, new_path))
        changes.append(Change(path=path, kind="rename", detail=f"{path.name} -> {new_path.name}"))

    # Apply edits first (stable paths), then renames (deepest-first to avoid collisions).
    if args.apply:
        for path, updated in edits:
            path.write_text(updated, encoding="utf-8")

        renames_sorted = sorted(renames, key=lambda pair: len(pair[0].as_posix().split("/")), reverse=True)
        for old_path, new_path in renames_sorted:
            if not old_path.exists():
                continue
            new_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.rename(new_path)

    # Report
    if not changes:
        print("No changes needed.")
        return 0

    print(("APPLY" if args.apply else "DRY-RUN") + f": {len(changes)} change(s)")
    for ch in changes[:300]:
        rel = ch.path.relative_to(repo_root)
        print(f"- {ch.kind}: {rel} ({ch.detail})")
    if len(changes) > 300:
        print(f"... ({len(changes) - 300} more)")

    if not args.apply:
        print("\nRe-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
