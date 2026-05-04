"""Collect decision_making inventory.

Input: apps/reference/domains/decision_making/**/*.py and dm_move_map.csv.
Output: artifacts/package2_inventory.json.
Side effects: writes the inventory artifact unless --dry-run is passed.
"""

from __future__ import annotations

import argparse

from dm_split_lib import ARTIFACTS, DM_ROOT, ROOT, load_move_map, write_json


def collect_inventory() -> dict[str, object]:
    rows = load_move_map()
    files = []
    for path in sorted(DM_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        files.append({
            "path": path.relative_to(ROOT).as_posix(),
            "loc": len(text.splitlines()),
        })
    return {
        "python_file_count": len(files),
        "move_map_rows": len(rows),
        "missing_from_move_map": sorted(
            set(item["path"] for item in files) - set(row.source_path for row in rows)
        ),
        "extra_in_move_map": sorted(
            set(row.source_path for row in rows) - set(item["path"] for item in files)
        ),
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    write_json(ARTIFACTS / "package2_inventory.json", collect_inventory(), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
