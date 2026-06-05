#!/usr/bin/env python3
from __future__ import annotations
from tools.alpha_search.j6_s17_c1_shadow_outcomes import (
    REPORTS_DIR,
    run_shadow_simulations,
    write_json,
    write_jsonl,
)

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run J6-S17-C1 shadow simulation outcome collection.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPORTS_DIR / "j6_s17_c1_shadow_simulation_results.jsonl",
    )
    parser.add_argument(
        "--contract-audit",
        type=Path,
        default=REPORTS_DIR / "j6_s17_c1_simulator_contract_audit.json",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=REPORTS_DIR / "j6_s17_c1_simulator_run_summary.json",
    )
    args = parser.parse_args()

    contract_audit, records, summary = run_shadow_simulations(
        args.root, args.output)
    write_json(args.contract_audit, contract_audit)
    write_jsonl(args.output, records)
    write_json(args.summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
