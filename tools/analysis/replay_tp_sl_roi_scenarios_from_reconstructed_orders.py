from __future__ import annotations

import argparse
import json
from pathlib import Path

from order_reconstruction_tp_sl_common import REPORT_ROOT, ROOT, run_replay


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay TP/SL ROI scenarios from reconstructed entries.")
    parser.add_argument(
        "--report-root",
        default=str(REPORT_ROOT),
        help="Output directory for generated artifacts.",
    )
    parser.add_argument(
        "--extra-recorder-root",
        action="append",
        default=[],
        help="Additional offline recorder root(s) to search alongside data/recorder. Analysis-only; runtime recorder behavior is unchanged.",
    )
    args = parser.parse_args()
    summary = run_replay(
        ROOT,
        Path(args.report_root),
        recorder_roots=[ROOT / "data" / "recorder", *
                        [Path(item) for item in args.extra_recorder_root]],
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
