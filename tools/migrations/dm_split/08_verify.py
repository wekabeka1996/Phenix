"""Verify the Package 2 decision_making split.

Input: moved tree, shims, and migration artifacts.
Output: artifacts/package2_verify_report.json.
Side effects: imports modules and writes the verification report.
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys

from dm_split_lib import ARTIFACTS, ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_MODULES = (
    "apps.reference.domains.decision_making",
    "apps.reference.domains.decision_making.core.facade",
    "apps.reference.domains.strategies.runtimes.aurora.handler",
    "apps.reference.domains.decision_making.primitives.position_queries",
    "apps.reference.domains.decision_making.primitives.operational_mode",
)


def verify() -> dict[str, object]:
    imported = []
    for module in REQUIRED_MODULES:
        importlib.import_module(module)
        imported.append(module)
    grep = subprocess.run(
        [
            "git",
            "grep",
            "-n",
            "from apps.reference.domains.decision_making.aurora_handler",
            "--",
            "apps",
            "tests",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "imported": imported,
        "aurora_handler_old_import_hits": grep.stdout.splitlines(),
        "aurora_handler_old_import_exit_code": grep.returncode,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = verify()
    if args.dry_run:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        (ARTIFACTS / "package2_verify_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
