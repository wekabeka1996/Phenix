"""Move decision_making files to the Variant A skeleton.

Input: dm_move_map.csv plus schemas/ and domain_dict.json.
Output: moved files and package __init__.py files.
Side effects: runs git mv unless --dry-run is passed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dm_split_lib import ROOT, load_move_map, run_git_mv

PACKAGE_ANCHOR = ROOT / "apps" / "reference"


def planned_init_paths(rows) -> list[str]:
    mapped_targets = {row.target_path.replace("\\", "/") for row in rows}
    init_paths: set[str] = set()
    for row in rows:
        parent = row.target.parent
        while parent != PACKAGE_ANCHOR and PACKAGE_ANCHOR in parent.parents:
            rel_path = (parent / "__init__.py").relative_to(ROOT).as_posix()
            if rel_path not in mapped_targets:
                init_paths.add(rel_path)
            parent = parent.parent
    return sorted(init_paths)


def ensure_init(rel_path: str, mapped_targets: set[str], *, dry_run: bool) -> None:
    path = ROOT / rel_path
    if rel_path in mapped_targets:
        return
    if path.exists():
        return
    if dry_run:
        print(f"write {rel_path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--move-map")
    args = parser.parse_args()
    move_map_path = Path(args.move_map) if args.move_map else None
    if move_map_path and not move_map_path.is_absolute():
        move_map_path = ROOT / move_map_path
    rows = load_move_map(move_map_path) if move_map_path else load_move_map()
    mapped_targets = {row.target_path for row in rows}
    for rel_path in planned_init_paths(rows):
        ensure_init(rel_path, mapped_targets, dry_run=args.dry_run)
    for row in rows:
        run_git_mv(row.source, row.target, dry_run=args.dry_run)
    run_git_mv(
        ROOT / "apps/reference/domains/decision_making/domain_dict.json",
        ROOT / "apps/reference/domains/decision_making/contracts/domain_dict.json",
        dry_run=args.dry_run,
    )
    schemas = ROOT / "apps/reference/domains/decision_making/schemas"
    target = ROOT / "apps/reference/domains/decision_making/intent/schemas"
    if schemas.exists() or target.exists():
        run_git_mv(schemas, target, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
