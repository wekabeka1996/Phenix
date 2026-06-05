from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.order_log_scenario_backtest.parity_harness import run_parity_harness


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", default="logs")
    parser.add_argument("--report-root", default="reports/production_realistic_harness")
    parser.add_argument("--recorder-root", default="data/recorder")
    parser.add_argument("--extra-recorder-root", action="append", default=["data/recorder_backfill_1m"])
    parser.add_argument("--scenarios", default="real_gate_parity")
    parser.add_argument("--strict", default="true")
    parser.add_argument("--mode", default="actual_trace_replay")
    parser.add_argument("--tolerance-pct", type=float, default=0.10)
    parser.add_argument("--day", default=None)
    args = parser.parse_args(argv)

    workspace_root = Path.cwd()
    result = run_parity_harness(
        workspace_root=workspace_root,
        runtime_root=(workspace_root / args.runtime_root).resolve(),
        report_root=(workspace_root / args.report_root).resolve(),
        recorder_root=(workspace_root / args.recorder_root).resolve(),
        extra_recorder_roots=[
            (workspace_root / item).resolve() if not Path(item).is_absolute() else Path(item)
            for item in args.extra_recorder_root
        ],
        scenarios=args.scenarios,
        strict=_parse_bool(args.strict),
        mode=args.mode,
        tolerance_pct=float(args.tolerance_pct),
        parity_day=args.day,
    )
    print(json.dumps(result["parity_summary"], ensure_ascii=False, indent=2))
    return 0 if result["manifest"].get("status") == "complete" and result["parity_summary"].get("behavioral_family_level_parity_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
