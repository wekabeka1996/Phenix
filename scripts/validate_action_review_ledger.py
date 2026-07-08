#!/usr/bin/env python3
"""Offline schema/safety lint for the P9 ActionReviewV1 JSONL ledger."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.reference.domains.agent_bridge.action_review import validate_ledger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("ops/agent_bridge/action_reviews/action_review_ledger_v1.jsonl"),
    )
    args = parser.parse_args()
    errors = validate_ledger(args.path)
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print(f"VALID {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
