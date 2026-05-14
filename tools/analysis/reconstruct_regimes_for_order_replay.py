from __future__ import annotations

import argparse
import json
from pathlib import Path

from order_reconstruction_tp_sl_common import REPORT_ROOT, ROOT, run_regime_reconstruction


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconstruct regimes for replay-ready entries.")
    parser.add_argument(
        "--report-root",
        default=str(REPORT_ROOT),
        help="Output directory for generated artifacts.",
    )
    args = parser.parse_args()
    summary = run_regime_reconstruction(ROOT, Path(args.report_root))
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
