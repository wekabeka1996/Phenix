"""Build the Python import rename plan.

Input: tools/migrations/dm_split/dm_move_map.csv.
Output: artifacts/rename_plan.json.
Side effects: writes the rename plan unless --dry-run is passed.
"""

from __future__ import annotations

import argparse

from dm_split_lib import ARTIFACTS, build_rename_plan, load_move_map, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    plan = [{"old": old, "new": new} for old, new in sorted(build_rename_plan(load_move_map()).items())]
    write_json(ARTIFACTS / "rename_plan.json", plan, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
