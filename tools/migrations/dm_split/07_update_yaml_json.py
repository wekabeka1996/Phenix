"""Update YAML/JSON and schema-path string references after Variant A moves.

Input: current repository YAML/JSON files.
Output: package2_yaml_json_report.json.
Side effects: writes the report unless --dry-run is passed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dm_split_lib import ARTIFACTS, ROOT, write_json

OLD_SCHEMA_PREFIX = "apps/reference/domains/decision_making/schemas/"
NEW_SCHEMA_PREFIX = "apps/reference/domains/decision_making/intent/schemas/"
SEARCH_ROOTS = ("apps", "tests")
SUFFIXES = {".py", ".yaml", ".yml", ".json"}


def update_schema_paths(*, dry_run: bool) -> dict[str, object]:
    changed: list[str] = []
    for rel in SEARCH_ROOTS:
        root = ROOT / rel
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_dir() or path.suffix not in SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if OLD_SCHEMA_PREFIX not in text:
                continue
            updated = text.replace(OLD_SCHEMA_PREFIX, NEW_SCHEMA_PREFIX)
            changed.append(path.relative_to(ROOT).as_posix())
            if not dry_run:
                path.write_text(updated, encoding="utf-8")
    return {
        "updated": changed,
        "schema_path_rewrite": {
            "old": OLD_SCHEMA_PREFIX,
            "new": NEW_SCHEMA_PREFIX,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    write_json(ARTIFACTS / "package2_yaml_json_report.json", update_schema_paths(dry_run=args.dry_run), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
